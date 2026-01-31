// Package tastytrade provides a client for the TastyTrade API.
package tastytrade

import (
	"encoding/json"
	"strconv"
	"time"
)

// FlexFloat is a float64 that can unmarshal from both JSON strings and numbers.
type FlexFloat float64

func (f *FlexFloat) UnmarshalJSON(data []byte) error {
	// Try as number first
	var num float64
	if err := json.Unmarshal(data, &num); err == nil {
		*f = FlexFloat(num)
		return nil
	}

	// Try as string
	var str string
	if err := json.Unmarshal(data, &str); err != nil {
		return err
	}

	if str == "" {
		*f = 0
		return nil
	}

	num, err := strconv.ParseFloat(str, 64)
	if err != nil {
		return err
	}
	*f = FlexFloat(num)
	return nil
}

// FlexFloatPtr is a *float64 that can unmarshal from JSON strings, numbers, or null.
type FlexFloatPtr struct {
	Value *float64
}

func (f *FlexFloatPtr) UnmarshalJSON(data []byte) error {
	if string(data) == "null" {
		f.Value = nil
		return nil
	}

	// Try as number first
	var num float64
	if err := json.Unmarshal(data, &num); err == nil {
		f.Value = &num
		return nil
	}

	// Try as string
	var str string
	if err := json.Unmarshal(data, &str); err != nil {
		return err
	}

	if str == "" {
		f.Value = nil
		return nil
	}

	num, err := strconv.ParseFloat(str, 64)
	if err != nil {
		return err
	}
	f.Value = &num
	return nil
}

func (f FlexFloatPtr) MarshalJSON() ([]byte, error) {
	if f.Value == nil {
		return []byte("null"), nil
	}
	return json.Marshal(*f.Value)
}

// Float64 returns the float64 pointer value.
func (f FlexFloatPtr) Float64() *float64 {
	return f.Value
}

// QuoteData represents quote data with market data and metrics.
type QuoteData struct {
	Symbol string `json:"symbol"`

	// Quote data
	Bid       *float64 `json:"bid,omitempty"`
	Ask       *float64 `json:"ask,omitempty"`
	Last      *float64 `json:"last,omitempty"`
	Mid       *float64 `json:"mid,omitempty"`
	Mark      *float64 `json:"mark,omitempty"`
	Volume    *float64 `json:"volume,omitempty"`
	Open      *float64 `json:"open,omitempty"`
	High      *float64 `json:"high,omitempty"`
	Low       *float64 `json:"low,omitempty"`
	Close     *float64 `json:"close,omitempty"`
	PrevClose *float64 `json:"prev_close,omitempty"`

	// 52-week range
	YearHigh *float64 `json:"year_high,omitempty"`
	YearLow  *float64 `json:"year_low,omitempty"`

	// Market metrics
	IVRank           *float64 `json:"iv_rank,omitempty"`
	IVPercentile     *float64 `json:"iv_percentile,omitempty"`
	IV30Day          *float64 `json:"iv_30_day,omitempty"`
	HV30Day          *float64 `json:"hv_30_day,omitempty"`
	IVHVDiff         *float64 `json:"iv_hv_diff,omitempty"`
	Beta             *float64 `json:"beta,omitempty"`
	MarketCap        *float64 `json:"market_cap,omitempty"`
	PERatio          *float64 `json:"pe_ratio,omitempty"`
	EarningsPerShare *float64 `json:"earnings_per_share,omitempty"`
	DividendYield    *float64 `json:"dividend_yield,omitempty"`
	LiquidityRating  *int     `json:"liquidity_rating,omitempty"`
	EarningsDate     *string  `json:"earnings_date,omitempty"`
	UpdatedAt        *string  `json:"updated_at,omitempty"`
}

// OAuthTokenResponse represents the OAuth token response.
type OAuthTokenResponse struct {
	AccessToken string `json:"access_token"`
	ExpiresIn   int    `json:"expires_in"`
	TokenType   string `json:"token_type"`
}

// MarketDataResponse represents the market data API response.
type MarketDataResponse struct {
	Data MarketDataItem `json:"data"`
}

// MarketDataItem represents a single market data item.
type MarketDataItem struct {
	Symbol        string    `json:"symbol"`
	Bid           FlexFloat `json:"bid"`
	Ask           FlexFloat `json:"ask"`
	Last          FlexFloat `json:"last"`
	Mid           FlexFloat `json:"mid"`
	Mark          FlexFloat `json:"mark"`
	Volume        FlexFloat `json:"volume"`
	DayOpen       FlexFloat `json:"day-open"`
	DayHighPrice  FlexFloat `json:"day-high-price"`
	DayLowPrice   FlexFloat `json:"day-low-price"`
	Close         FlexFloat `json:"close"`
	PrevClose     FlexFloat `json:"prev-close"`
	YearHighPrice FlexFloat `json:"year-high-price"`
	YearLowPrice  FlexFloat `json:"year-low-price"`
	UpdatedAt     time.Time `json:"updated-at"`
}

// MarketMetricsResponse represents the market metrics API response.
type MarketMetricsResponse struct {
	Data struct {
		Items []MarketMetricsItem `json:"items"`
	} `json:"data"`
}

// MarketMetricsItem represents market metrics for a symbol.
type MarketMetricsItem struct {
	Symbol                      string        `json:"symbol"`
	ImpliedVolatilityIndex      FlexFloatPtr  `json:"implied-volatility-index"`
	ImpliedVolatilityIndexRank  FlexFloatPtr  `json:"implied-volatility-index-rank"`
	ImpliedVolatilityPercentile FlexFloatPtr  `json:"implied-volatility-percentile"`
	ImpliedVolatility30Day      FlexFloatPtr  `json:"implied-volatility-30-day"`
	HistoricalVolatility30Day   FlexFloatPtr  `json:"historical-volatility-30-day"`
	IVHV30DayDifference         FlexFloatPtr  `json:"iv-hv-30-day-difference"`
	Beta                        FlexFloatPtr  `json:"beta"`
	MarketCap                   FlexFloatPtr  `json:"market-cap"`
	PriceEarningsRatio          FlexFloatPtr  `json:"price-earnings-ratio"`
	EarningsPerShare            FlexFloatPtr  `json:"earnings-per-share"`
	DividendYield               FlexFloatPtr  `json:"dividend-yield"`
	LiquidityRating             *int          `json:"liquidity-rating"`
	Earnings                    *EarningsInfo `json:"earnings"`
}

// EarningsInfo represents earnings information.
type EarningsInfo struct {
	ExpectedReportDate string `json:"expected-report-date"`
}

// AuthStatus represents the authentication status.
type AuthStatus struct {
	Authenticated        bool `json:"authenticated"`
	HasStoredCredentials bool `json:"has_stored_credentials"`
}
