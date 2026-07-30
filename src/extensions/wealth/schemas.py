"""全资产扩展 API 数据结构。"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AssetCategory = Literal[
    "a_stock",
    "hk_stock",
    "b_stock",
    "etf",
    "public_fund",
    "private_fund",
    "cash",
    "liability",
    "future",
    "option",
    "adjustment",
]
ValuationMethod = Literal["price", "manual", "derivative"]
PositionSide = Literal["long", "short"]


class AssetInput(BaseModel):
    account_name: str = "默认账户"
    category: AssetCategory
    symbol: str = ""
    name: str
    market: str = ""
    currency: str = "CNY"
    exchange_rate: float = Field(default=1.0, gt=0)
    valuation_method: ValuationMethod = "price"
    quantity: float = 0
    current_price: float | None = None
    cost_price: float | None = None
    manual_amount: float | None = None
    contract_multiplier: float = Field(default=1.0, gt=0)
    position_side: PositionSide = "long"
    margin: float | None = None
    enabled: bool = True
    source_system: str = "manual"
    source_key: str = ""
    price_as_of: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"CNY", "HKD", "USD"}:
            raise ValueError("币种仅支持 CNY、HKD、USD")
        return normalized

    @field_validator("symbol", "market", "account_name", "name", "source_system")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class AssetUpdate(BaseModel):
    account_name: str | None = None
    category: AssetCategory | None = None
    symbol: str | None = None
    name: str | None = None
    market: str | None = None
    currency: str | None = None
    exchange_rate: float | None = Field(default=None, gt=0)
    valuation_method: ValuationMethod | None = None
    quantity: float | None = None
    current_price: float | None = None
    cost_price: float | None = None
    manual_amount: float | None = None
    contract_multiplier: float | None = Field(default=None, gt=0)
    position_side: PositionSide | None = None
    margin: float | None = None
    enabled: bool | None = None
    price_as_of: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in {"CNY", "HKD", "USD"}:
            raise ValueError("币种仅支持 CNY、HKD、USD")
        return normalized


class SnapshotInput(BaseModel):
    snapshot_date: str | None = None
    external_flow: float = 0
    note: str = ""


class GoogleSheetsHistoryRow(BaseModel):
    snapshot_date: str
    categories: dict[str, float] = Field(default_factory=dict)
    liabilities: float = 0
    gross_assets: float | None = None
    net_assets: float | None = None
    real_market_value: float | None = None
    leverage: float | None = None
    unit_count: float | None = None
    performance_nav: float | None = None
    daily_return: float | None = None
    benchmark_symbol: str = "510300"
    benchmark_name: str = "沪深300ETF"
    benchmark_price: float | None = None
    benchmark_daily_return: float | None = None
    note: str = ""


class GoogleSheetsSyncPayload(BaseModel):
    spreadsheet_id: str
    as_of_date: str
    assets: list[AssetInput]
    history: list[GoogleSheetsHistoryRow] = Field(default_factory=list)
    deactivate_missing: bool = True
