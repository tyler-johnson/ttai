package tastytrade

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/ttai/ttai/internal/cache"
	"github.com/ttai/ttai/internal/credentials"
)

const (
	baseURL       = "https://api.tastyworks.com"
	quoteCacheTTL = 60 * time.Second
)

var (
	ErrNotAuthenticated = errors.New("not authenticated")
	ErrLoginFailed      = errors.New("login failed")
)

// Client is a TastyTrade API client.
type Client struct {
	mu           sync.RWMutex
	httpClient   *http.Client
	credManager  *credentials.Manager
	cache        *cache.Cache
	sessionToken string
}

// NewClient creates a new TastyTrade API client.
func NewClient(credManager *credentials.Manager, c *cache.Cache) *Client {
	return &Client{
		httpClient:  &http.Client{Timeout: 30 * time.Second},
		credManager: credManager,
		cache:       c,
	}
}

// IsAuthenticated returns true if the client has an active session.
func (c *Client) IsAuthenticated() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.sessionToken != ""
}

// Login authenticates with TastyTrade using OAuth credentials.
func (c *Client) Login(clientSecret, refreshToken string, rememberMe bool) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	// OAuth token request
	payload := map[string]string{
		"grant_type":    "refresh_token",
		"client_secret": clientSecret,
		"refresh_token": refreshToken,
	}

	body, _ := json.Marshal(payload)
	req, err := http.NewRequest("POST", baseURL+"/oauth/token", bytes.NewReader(body))
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		log.Printf("Login failed with status %d: %s", resp.StatusCode, string(respBody))
		return ErrLoginFailed
	}

	var tokenResp OAuthTokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
		return err
	}

	c.sessionToken = tokenResp.AccessToken

	if c.sessionToken == "" {
		return ErrLoginFailed
	}

	log.Printf("Successfully authenticated via OAuth")

	if rememberMe {
		if err := c.credManager.Store(clientSecret, refreshToken); err != nil {
			log.Printf("Warning: failed to store credentials: %v", err)
		}
	}

	return nil
}

// RestoreSession attempts to restore a session from stored credentials.
func (c *Client) RestoreSession() error {
	creds, err := c.credManager.Load()
	if err != nil {
		return err
	}
	if creds == nil {
		return errors.New("no stored credentials")
	}

	return c.Login(creds.ClientSecret, creds.RefreshToken, false)
}

// Logout destroys the session and optionally clears stored credentials.
func (c *Client) Logout(clearCredentials bool) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.sessionToken != "" {
		// Attempt to destroy the session on the server
		req, err := http.NewRequest("DELETE", baseURL+"/sessions", nil)
		if err == nil {
			req.Header.Set("Authorization", c.sessionToken)
			resp, err := c.httpClient.Do(req)
			if err != nil {
				log.Printf("Warning: failed to destroy session: %v", err)
			} else {
				resp.Body.Close()
			}
		}
	}

	c.sessionToken = ""

	if clearCredentials {
		if err := c.credManager.Clear(); err != nil {
			log.Printf("Warning: failed to clear credentials: %v", err)
		}
	}

	log.Println("Logged out successfully")
	return nil
}

// GetAuthStatus returns the current authentication status.
func (c *Client) GetAuthStatus() AuthStatus {
	c.mu.RLock()
	defer c.mu.RUnlock()

	return AuthStatus{
		Authenticated:        c.sessionToken != "",
		HasStoredCredentials: c.credManager.HasCredentials(),
	}
}

// GetQuote fetches quote data for a symbol.
func (c *Client) GetQuote(symbol string) (*QuoteData, error) {
	if !c.IsAuthenticated() {
		return nil, ErrNotAuthenticated
	}

	symbol = strings.ToUpper(symbol)
	cacheKey := "quote:" + symbol

	// Check cache first
	if cached := c.cache.Get(cacheKey); cached != nil {
		if quote, ok := cached.(*QuoteData); ok {
			return quote, nil
		}
	}

	// Fetch market data
	marketData, err := c.fetchMarketData(symbol)
	if err != nil {
		return nil, err
	}

	// Fetch market metrics
	metrics, err := c.fetchMarketMetrics(symbol)
	if err != nil {
		log.Printf("Warning: failed to fetch market metrics for %s: %v", symbol, err)
		// Continue without metrics
	}

	quote := &QuoteData{
		Symbol: symbol,
	}

	// Populate from market data
	if marketData != nil {
		quote.Bid = &marketData.Bid
		quote.Ask = &marketData.Ask
		quote.Last = &marketData.Last
		quote.Mid = &marketData.Mid
		quote.Mark = &marketData.Mark
		quote.Volume = &marketData.Volume
		quote.Open = &marketData.DayOpen
		quote.High = &marketData.DayHighPrice
		quote.Low = &marketData.DayLowPrice
		quote.Close = &marketData.Close
		quote.PrevClose = &marketData.PrevClose
		quote.YearHigh = &marketData.YearHighPrice
		quote.YearLow = &marketData.YearLowPrice

		if !marketData.UpdatedAt.IsZero() {
			updatedAt := marketData.UpdatedAt.Format(time.RFC3339)
			quote.UpdatedAt = &updatedAt
		}
	}

	// Populate from market metrics
	if metrics != nil {
		quote.IVRank = metrics.ImpliedVolatilityIndexRank
		quote.IVPercentile = metrics.ImpliedVolatilityPercentile
		quote.IV30Day = metrics.ImpliedVolatility30Day
		quote.HV30Day = metrics.HistoricalVolatility30Day
		quote.IVHVDiff = metrics.IVHV30DayDifference
		quote.Beta = metrics.Beta
		quote.MarketCap = metrics.MarketCap
		quote.PERatio = metrics.PriceEarningsRatio
		quote.EarningsPerShare = metrics.EarningsPerShare
		quote.DividendYield = metrics.DividendYield
		quote.LiquidityRating = metrics.LiquidityRating

		if metrics.Earnings != nil && metrics.Earnings.ExpectedReportDate != "" {
			quote.EarningsDate = &metrics.Earnings.ExpectedReportDate
		}
	}

	// Cache the result
	c.cache.Set(cacheKey, quote, quoteCacheTTL)

	return quote, nil
}

func (c *Client) fetchMarketData(symbol string) (*MarketDataItem, error) {
	c.mu.RLock()
	token := c.sessionToken
	c.mu.RUnlock()

	url := fmt.Sprintf("%s/market-data/equities/%s/quotes", baseURL, symbol)
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("market data request failed with status %d: %s", resp.StatusCode, string(respBody))
	}

	var dataResp MarketDataResponse
	if err := json.NewDecoder(resp.Body).Decode(&dataResp); err != nil {
		return nil, err
	}

	if len(dataResp.Data.Items) == 0 {
		return nil, fmt.Errorf("no market data found for %s", symbol)
	}

	return &dataResp.Data.Items[0], nil
}

func (c *Client) fetchMarketMetrics(symbol string) (*MarketMetricsItem, error) {
	c.mu.RLock()
	token := c.sessionToken
	c.mu.RUnlock()

	url := fmt.Sprintf("%s/market-metrics?symbols=%s", baseURL, symbol)
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("market metrics request failed with status %d: %s", resp.StatusCode, string(respBody))
	}

	var metricsResp MarketMetricsResponse
	if err := json.NewDecoder(resp.Body).Decode(&metricsResp); err != nil {
		return nil, err
	}

	if len(metricsResp.Data.Items) == 0 {
		return nil, fmt.Errorf("no market metrics found for %s", symbol)
	}

	return &metricsResp.Data.Items[0], nil
}
