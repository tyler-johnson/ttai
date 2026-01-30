// Package tastytrade provides a client for the TastyTrade API.
package tastytrade

import "time"

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
	IVRank            *float64 `json:"iv_rank,omitempty"`
	IVPercentile      *float64 `json:"iv_percentile,omitempty"`
	IV30Day           *float64 `json:"iv_30_day,omitempty"`
	HV30Day           *float64 `json:"hv_30_day,omitempty"`
	IVHVDiff          *float64 `json:"iv_hv_diff,omitempty"`
	Beta              *float64 `json:"beta,omitempty"`
	MarketCap         *float64 `json:"market_cap,omitempty"`
	PERatio           *float64 `json:"pe_ratio,omitempty"`
	EarningsPerShare  *float64 `json:"earnings_per_share,omitempty"`
	DividendYield     *float64 `json:"dividend_yield,omitempty"`
	LiquidityRating   *int     `json:"liquidity_rating,omitempty"`
	EarningsDate      *string  `json:"earnings_date,omitempty"`
	UpdatedAt         *string  `json:"updated_at,omitempty"`
}

// OAuthTokenResponse represents the OAuth token response.
type OAuthTokenResponse struct {
	AccessToken string `json:"access_token"`
	ExpiresIn   int    `json:"expires_in"`
	TokenType   string `json:"token_type"`
}

// MarketDataResponse represents the market data API response.
type MarketDataResponse struct {
	Data struct {
		Items []MarketDataItem `json:"items"`
	} `json:"data"`
}

// MarketDataItem represents a single market data item.
type MarketDataItem struct {
	Symbol       string  `json:"symbol"`
	Bid          float64 `json:"bid"`
	Ask          float64 `json:"ask"`
	Last         float64 `json:"last"`
	Mid          float64 `json:"mid"`
	Mark         float64 `json:"mark"`
	Volume       float64 `json:"volume"`
	DayOpen      float64 `json:"day-open"`
	DayHighPrice float64 `json:"day-high-price"`
	DayLowPrice  float64 `json:"day-low-price"`
	Close        float64 `json:"close"`
	PrevClose    float64 `json:"prev-close"`
	YearHighPrice float64 `json:"year-high-price"`
	YearLowPrice  float64 `json:"year-low-price"`
	UpdatedAt    time.Time `json:"updated-at"`
}

// MarketMetricsResponse represents the market metrics API response.
type MarketMetricsResponse struct {
	Data struct {
		Items []MarketMetricsItem `json:"items"`
	} `json:"data"`
}

// MarketMetricsItem represents market metrics for a symbol.
type MarketMetricsItem struct {
	Symbol                       string   `json:"symbol"`
	ImpliedVolatilityIndex       *float64 `json:"implied-volatility-index"`
	ImpliedVolatilityIndexRank   *float64 `json:"implied-volatility-index-rank"`
	ImpliedVolatilityPercentile  *float64 `json:"implied-volatility-percentile"`
	ImpliedVolatility30Day       *float64 `json:"implied-volatility-30-day"`
	HistoricalVolatility30Day    *float64 `json:"historical-volatility-30-day"`
	IVHV30DayDifference          *float64 `json:"iv-hv-30-day-difference"`
	Beta                         *float64 `json:"beta"`
	MarketCap                    *float64 `json:"market-cap"`
	PriceEarningsRatio           *float64 `json:"price-earnings-ratio"`
	EarningsPerShare             *float64 `json:"earnings-per-share"`
	DividendYield                *float64 `json:"dividend-yield"`
	LiquidityRating              *int     `json:"liquidity-rating"`
	Earnings                     *EarningsInfo `json:"earnings"`
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
