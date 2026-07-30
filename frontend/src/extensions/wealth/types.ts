export type AssetCategory =
  | 'a_stock'
  | 'hk_stock'
  | 'b_stock'
  | 'etf'
  | 'public_fund'
  | 'private_fund'
  | 'cash'
  | 'liability'
  | 'future'
  | 'option'
  | 'adjustment'

export type ValuationMethod = 'price' | 'manual' | 'derivative'
export type PositionSide = 'long' | 'short'

export interface WealthAsset {
  id: number
  account_name: string
  category: AssetCategory
  category_label: string
  symbol: string
  name: string
  market: string
  currency: 'CNY' | 'HKD' | 'USD'
  exchange_rate: number
  valuation_method: ValuationMethod
  quantity: number
  current_price: number | null
  cost_price: number | null
  manual_amount: number | null
  contract_multiplier: number
  position_side: PositionSide
  margin: number | null
  enabled: boolean
  source_system: string
  source_key: string
  price_as_of: string
  metadata: Record<string, unknown>
  value_native: number
  value_cny: number
  cost_cny: number | null
  pnl_cny: number | null
  exposure_cny: number
}

export interface AssetPayload {
  account_name: string
  category: AssetCategory
  symbol: string
  name: string
  market: string
  currency: 'CNY' | 'HKD' | 'USD'
  exchange_rate: number
  valuation_method: ValuationMethod
  quantity: number
  current_price: number | null
  cost_price: number | null
  manual_amount: number | null
  contract_multiplier: number
  position_side: PositionSide
  margin: number | null
  enabled: boolean
  price_as_of: string
}

export interface CategorySummary {
  label: string
  value_cny: number
  exposure_cny: number
}

export interface WealthSnapshot {
  snapshot_date: string
  gross_assets: number
  liabilities: number
  net_assets: number
  derivative_exposure: number
  real_market_value: number
  leverage: number
  performance_nav: number | null
  daily_return: number | null
  benchmark_price: number | null
  benchmark_daily_return: number | null
  note: string
}

export interface WealthSummary {
  gross_assets: number
  liabilities: number
  net_assets: number
  derivative_exposure: number
  real_market_value: number
  leverage: number
  by_category: Record<string, CategorySummary>
  assets: WealthAsset[]
  latest_snapshot: WealthSnapshot | null
  latest_sync: {
    status: string
    as_of_date: string
    asset_count: number
    snapshot_count: number
    message: string
    created_at: string | null
  } | null
}

export interface PerformancePoint extends WealthSnapshot {
  portfolio_return: number | null
  benchmark_return: number | null
  excess_return: number | null
}

export interface PerformanceResponse {
  period: string
  points: PerformancePoint[]
  summary: {
    portfolio_return: number | null
    benchmark_return: number | null
    excess_return: number | null
    start_date: string
    end_date: string
  } | null
}
