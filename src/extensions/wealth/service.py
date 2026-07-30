"""全资产估值、同步和历史收益服务。"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from src.extensions.wealth.models import (
    WealthAsset,
    WealthSnapshot,
    WealthSnapshotItem,
    WealthSyncRun,
)
from src.extensions.wealth.schemas import (
    AssetInput,
    GoogleSheetsHistoryRow,
    GoogleSheetsSyncPayload,
)


CATEGORY_LABELS = {
    "a_stock": "A股",
    "hk_stock": "港股",
    "b_stock": "B股",
    "etf": "ETF",
    "public_fund": "公募基金",
    "private_fund": "私募基金",
    "cash": "现金",
    "liability": "负债",
    "future": "内盘期货",
    "option": "期权",
    "adjustment": "调整项",
}

DERIVATIVE_CATEGORIES = {"future", "option"}
LIABILITY_CATEGORIES = {"liability"}


def _finite(value: float | int | None, default: float = 0.0) -> float:
    if value is None:
        return default
    number = float(value)
    return number if math.isfinite(number) else default


def serialize_asset(asset: WealthAsset) -> dict:
    valuation = calculate_asset(asset)
    return {
        "id": asset.id,
        "account_name": asset.account_name,
        "category": asset.category,
        "category_label": CATEGORY_LABELS.get(asset.category, asset.category),
        "symbol": asset.symbol,
        "name": asset.name,
        "market": asset.market,
        "currency": asset.currency,
        "exchange_rate": asset.exchange_rate,
        "valuation_method": asset.valuation_method,
        "quantity": asset.quantity,
        "current_price": asset.current_price,
        "cost_price": asset.cost_price,
        "manual_amount": asset.manual_amount,
        "contract_multiplier": asset.contract_multiplier,
        "position_side": asset.position_side,
        "margin": asset.margin,
        "enabled": asset.enabled,
        "source_system": asset.source_system,
        "source_key": asset.source_key,
        "price_as_of": asset.price_as_of,
        "metadata": asset.metadata_json or {},
        **valuation,
    }


def calculate_asset(asset: WealthAsset) -> dict[str, float | None]:
    """按品类计算人民币净值、成本与名义敞口。

    - B 股与境外资产显式使用资产自身汇率；
    - 期货的账户权益与名义敞口分开，避免把合约名义金额误算成资产；
    - 空头期权按负市值计入，负债始终按绝对值扣减。
    """

    rate = max(_finite(asset.exchange_rate, 1.0), 0.0)
    quantity = _finite(asset.quantity)
    price = _finite(asset.current_price)
    multiplier = max(_finite(asset.contract_multiplier, 1.0), 0.0)
    side = -1.0 if asset.position_side == "short" else 1.0

    if asset.valuation_method == "manual":
        native_value = _finite(asset.manual_amount)
        exposure_native = abs(native_value)
    elif asset.category == "future" or asset.valuation_method == "derivative":
        native_value = _finite(asset.margin, _finite(asset.manual_amount))
        exposure_native = abs(quantity * price * multiplier)
    else:
        native_value = quantity * price * multiplier
        exposure_native = abs(native_value)

    if asset.category == "option" and asset.valuation_method != "manual":
        native_value *= side
    value_cny = native_value * rate
    if asset.category in LIABILITY_CATEGORIES:
        value_cny = -abs(value_cny)

    cost_cny: float | None = None
    if asset.cost_price is not None and asset.valuation_method != "manual":
        cost_cny = quantity * _finite(asset.cost_price) * multiplier * rate
        if asset.category == "option":
            cost_cny *= side

    pnl_cny = value_cny - cost_cny if cost_cny is not None else None
    return {
        "value_native": round(native_value, 6),
        "value_cny": round(value_cny, 2),
        "cost_cny": round(cost_cny, 2) if cost_cny is not None else None,
        "pnl_cny": round(pnl_cny, 2) if pnl_cny is not None else None,
        "exposure_cny": round(exposure_native * rate, 2),
    }


def build_summary(assets: Iterable[WealthAsset]) -> dict:
    by_category: dict[str, float] = defaultdict(float)
    exposure_by_category: dict[str, float] = defaultdict(float)
    gross_assets = 0.0
    liabilities = 0.0
    derivative_exposure = 0.0
    serialized = []

    for asset in assets:
        if not asset.enabled:
            continue
        row = serialize_asset(asset)
        value = _finite(row["value_cny"])
        exposure = _finite(row["exposure_cny"])
        serialized.append(row)
        by_category[asset.category] += value
        exposure_by_category[asset.category] += exposure
        if asset.category in LIABILITY_CATEGORIES:
            liabilities += abs(value)
        else:
            gross_assets += value
        if asset.category in DERIVATIVE_CATEGORIES:
            derivative_exposure += exposure

    net_assets = gross_assets - liabilities
    real_market_value = gross_assets + derivative_exposure
    leverage = real_market_value / net_assets if net_assets > 0 else 0.0
    return {
        "gross_assets": round(gross_assets, 2),
        "liabilities": round(liabilities, 2),
        "net_assets": round(net_assets, 2),
        "derivative_exposure": round(derivative_exposure, 2),
        "real_market_value": round(real_market_value, 2),
        "leverage": round(leverage, 6),
        "by_category": {
            key: {
                "label": CATEGORY_LABELS.get(key, key),
                "value_cny": round(value, 2),
                "exposure_cny": round(exposure_by_category.get(key, 0.0), 2),
            }
            for key, value in sorted(by_category.items())
        },
        "assets": serialized,
    }


def list_summary(db: Session) -> dict:
    assets = (
        db.query(WealthAsset)
        .filter(WealthAsset.enabled == True)  # noqa: E712
        .order_by(WealthAsset.category, WealthAsset.account_name, WealthAsset.id)
        .all()
    )
    summary = build_summary(assets)
    summary["snapshot_count"] = db.query(WealthSnapshot).count()
    latest = (
        db.query(WealthSnapshot)
        .order_by(WealthSnapshot.snapshot_date.desc())
        .first()
    )
    summary["latest_snapshot"] = serialize_snapshot(latest) if latest else None
    latest_sync = db.query(WealthSyncRun).order_by(WealthSyncRun.id.desc()).first()
    summary["latest_sync"] = (
        {
            "status": latest_sync.status,
            "as_of_date": latest_sync.as_of_date,
            "asset_count": latest_sync.asset_count,
            "snapshot_count": latest_sync.snapshot_count,
            "message": latest_sync.message,
            "created_at": latest_sync.created_at.isoformat()
            if latest_sync.created_at
            else None,
        }
        if latest_sync
        else None
    )
    return summary


def create_asset(db: Session, data: AssetInput) -> WealthAsset:
    source_key = data.source_key or _manual_source_key(data)
    asset = WealthAsset(
        account_name=data.account_name or "默认账户",
        category=data.category,
        symbol=data.symbol,
        name=data.name,
        market=data.market,
        currency=data.currency,
        exchange_rate=data.exchange_rate,
        valuation_method=data.valuation_method,
        quantity=data.quantity,
        current_price=data.current_price,
        cost_price=data.cost_price,
        manual_amount=data.manual_amount,
        contract_multiplier=data.contract_multiplier,
        position_side=data.position_side,
        margin=data.margin,
        enabled=data.enabled,
        source_system=data.source_system or "manual",
        source_key=source_key,
        price_as_of=data.price_as_of,
        metadata_json=data.metadata,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _manual_source_key(data: AssetInput) -> str:
    identity = data.symbol or data.name
    return f"{data.account_name}:{data.category}:{identity}".lower()


def _upsert_asset(db: Session, data: AssetInput, source_system: str) -> WealthAsset:
    source_key = data.source_key or _manual_source_key(data)
    asset = (
        db.query(WealthAsset)
        .filter(
            WealthAsset.source_system == source_system,
            WealthAsset.source_key == source_key,
        )
        .first()
    )
    if asset is None:
        asset = WealthAsset(source_system=source_system, source_key=source_key)
        db.add(asset)

    for field in (
        "account_name",
        "category",
        "symbol",
        "name",
        "market",
        "currency",
        "exchange_rate",
        "valuation_method",
        "quantity",
        "current_price",
        "cost_price",
        "manual_amount",
        "contract_multiplier",
        "position_side",
        "margin",
        "enabled",
        "price_as_of",
    ):
        setattr(asset, field, getattr(data, field))
    asset.source_system = source_system
    asset.source_key = source_key
    asset.metadata_json = data.metadata
    return asset


def sync_google_sheets(db: Session, payload: GoogleSheetsSyncPayload) -> dict:
    """幂等同步 Google Sheets 当前资产和历史快照。"""

    source_system = f"google_sheets:{payload.spreadsheet_id}"
    seen_keys: set[str] = set()
    try:
        for data in payload.assets:
            data.source_system = source_system
            asset = _upsert_asset(db, data, source_system)
            seen_keys.add(asset.source_key)

        if payload.deactivate_missing:
            missing_query = db.query(WealthAsset).filter(
                WealthAsset.source_system == source_system
            )
            if seen_keys:
                missing_query = missing_query.filter(
                    ~WealthAsset.source_key.in_(seen_keys)
                )
            missing_query.update(
                {WealthAsset.enabled: False}, synchronize_session=False
            )

        for row in payload.history:
            upsert_history_snapshot(db, row, source_system)

        db.add(
            WealthSyncRun(
                source_system=source_system,
                status="success",
                as_of_date=payload.as_of_date,
                asset_count=len(payload.assets),
                snapshot_count=len(payload.history),
                message="同步完成",
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        db.add(
            WealthSyncRun(
                source_system=source_system,
                status="failed",
                as_of_date=payload.as_of_date,
                asset_count=0,
                snapshot_count=0,
                message=str(exc)[:500],
            )
        )
        db.commit()
        raise

    summary = list_summary(db)
    return {
        "asset_count": len(payload.assets),
        "snapshot_count": len(payload.history),
        "as_of_date": payload.as_of_date,
        "summary": summary,
    }


def upsert_history_snapshot(
    db: Session,
    row: GoogleSheetsHistoryRow,
    source_system: str,
) -> WealthSnapshot:
    categories = {k: _finite(v) for k, v in row.categories.items()}
    liabilities = abs(_finite(row.liabilities))
    gross_assets = (
        _finite(row.gross_assets)
        if row.gross_assets is not None
        else sum(value for key, value in categories.items() if key != "liability")
    )
    net_assets = (
        _finite(row.net_assets)
        if row.net_assets is not None
        else gross_assets - liabilities
    )
    derivative_exposure = abs(categories.get("future", 0.0)) + abs(
        categories.get("option", 0.0)
    )
    real_market_value = (
        _finite(row.real_market_value)
        if row.real_market_value is not None
        else gross_assets + derivative_exposure
    )
    leverage = (
        _finite(row.leverage)
        if row.leverage is not None
        else (real_market_value / net_assets if net_assets > 0 else 0.0)
    )

    snapshot = (
        db.query(WealthSnapshot)
        .filter(WealthSnapshot.snapshot_date == row.snapshot_date)
        .first()
    )
    if snapshot is None:
        snapshot = WealthSnapshot(snapshot_date=row.snapshot_date)
        db.add(snapshot)
        db.flush()

    snapshot.gross_assets = gross_assets
    snapshot.liabilities = liabilities
    snapshot.net_assets = net_assets
    snapshot.derivative_exposure = derivative_exposure
    snapshot.leverage = leverage
    snapshot.unit_count = row.unit_count
    snapshot.performance_nav = row.performance_nav
    snapshot.daily_return = row.daily_return
    snapshot.benchmark_symbol = row.benchmark_symbol
    snapshot.benchmark_name = row.benchmark_name
    snapshot.benchmark_price = row.benchmark_price
    snapshot.benchmark_daily_return = row.benchmark_daily_return
    snapshot.real_market_value = real_market_value
    snapshot.source_system = source_system
    snapshot.note = row.note

    db.query(WealthSnapshotItem).filter(
        WealthSnapshotItem.snapshot_id == snapshot.id
    ).delete(synchronize_session=False)
    for category, value in categories.items():
        db.add(
            WealthSnapshotItem(
                snapshot_id=snapshot.id,
                category=category,
                value_cny=value,
                exposure_cny=abs(value)
                if category in DERIVATIVE_CATEGORIES
                else 0.0,
            )
        )
    if liabilities:
        db.add(
            WealthSnapshotItem(
                snapshot_id=snapshot.id,
                category="liability",
                value_cny=-liabilities,
                exposure_cny=liabilities,
            )
        )
    return snapshot


def record_snapshot(
    db: Session,
    snapshot_date: str | None = None,
    external_flow: float = 0.0,
    note: str = "",
    benchmark_price_provider: Callable[[], float | None] | None = None,
) -> WealthSnapshot:
    target_date = snapshot_date or date.today().isoformat()
    assets = (
        db.query(WealthAsset)
        .filter(WealthAsset.enabled == True)  # noqa: E712
        .all()
    )
    summary = build_summary(assets)
    previous = (
        db.query(WealthSnapshot)
        .filter(WealthSnapshot.snapshot_date < target_date)
        .order_by(WealthSnapshot.snapshot_date.desc())
        .first()
    )
    benchmark_price = benchmark_price_provider() if benchmark_price_provider else None

    daily_return = None
    performance_nav = None
    if previous:
        denominator = previous.net_assets + external_flow
        if denominator > 0:
            daily_return = summary["net_assets"] / denominator - 1
        previous_nav = previous.performance_nav or previous.net_assets
        if previous_nav is not None and daily_return is not None:
            performance_nav = previous_nav * (1 + daily_return)
    elif summary["net_assets"] > 0:
        performance_nav = summary["net_assets"]

    benchmark_daily_return = None
    if previous and previous.benchmark_price and benchmark_price:
        benchmark_daily_return = benchmark_price / previous.benchmark_price - 1

    snapshot = (
        db.query(WealthSnapshot)
        .filter(WealthSnapshot.snapshot_date == target_date)
        .first()
    )
    if snapshot is None:
        snapshot = WealthSnapshot(snapshot_date=target_date)
        db.add(snapshot)
        db.flush()

    snapshot.gross_assets = summary["gross_assets"]
    snapshot.liabilities = summary["liabilities"]
    snapshot.net_assets = summary["net_assets"]
    snapshot.derivative_exposure = summary["derivative_exposure"]
    snapshot.real_market_value = summary["real_market_value"]
    snapshot.leverage = summary["leverage"]
    snapshot.external_flow = external_flow
    snapshot.performance_nav = performance_nav
    snapshot.daily_return = daily_return
    snapshot.benchmark_symbol = "510300"
    snapshot.benchmark_name = "沪深300ETF"
    snapshot.benchmark_price = benchmark_price
    snapshot.benchmark_daily_return = benchmark_daily_return
    snapshot.source_system = "panwatch"
    snapshot.note = note

    db.query(WealthSnapshotItem).filter(
        WealthSnapshotItem.snapshot_id == snapshot.id
    ).delete(synchronize_session=False)
    for category, values in summary["by_category"].items():
        db.add(
            WealthSnapshotItem(
                snapshot_id=snapshot.id,
                category=category,
                value_cny=values["value_cny"],
                exposure_cny=values["exposure_cny"],
            )
        )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def serialize_snapshot(snapshot: WealthSnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return {
        "id": snapshot.id,
        "snapshot_date": snapshot.snapshot_date,
        "gross_assets": round(snapshot.gross_assets, 2),
        "liabilities": round(snapshot.liabilities, 2),
        "net_assets": round(snapshot.net_assets, 2),
        "derivative_exposure": round(snapshot.derivative_exposure, 2),
        "real_market_value": round(
            snapshot.real_market_value or snapshot.gross_assets, 2
        ),
        "leverage": round(snapshot.leverage, 6),
        "external_flow": snapshot.external_flow,
        "unit_count": snapshot.unit_count,
        "performance_nav": snapshot.performance_nav,
        "daily_return": snapshot.daily_return,
        "benchmark_symbol": snapshot.benchmark_symbol,
        "benchmark_name": snapshot.benchmark_name,
        "benchmark_price": snapshot.benchmark_price,
        "benchmark_daily_return": snapshot.benchmark_daily_return,
        "source_system": snapshot.source_system,
        "note": snapshot.note,
    }


def _start_date_for_period(period: str) -> str | None:
    today = date.today()
    days = {"1m": 31, "3m": 93, "6m": 186, "1y": 366, "3y": 1098}.get(period)
    return (today - timedelta(days=days)).isoformat() if days else None


def performance_series(db: Session, period: str = "1y") -> dict:
    query = db.query(WealthSnapshot)
    start_date = _start_date_for_period(period.lower())
    if start_date:
        query = query.filter(WealthSnapshot.snapshot_date >= start_date)
    snapshots = query.order_by(WealthSnapshot.snapshot_date.asc()).all()
    if not snapshots:
        return {"period": period, "points": [], "summary": None}

    first_nav = snapshots[0].performance_nav or snapshots[0].net_assets
    first_benchmark = next(
        (s.benchmark_price for s in snapshots if s.benchmark_price), None
    )
    points = []
    for snapshot in snapshots:
        nav = snapshot.performance_nav or snapshot.net_assets
        portfolio_return = (
            nav / first_nav - 1 if first_nav and nav is not None else None
        )
        benchmark_return = (
            snapshot.benchmark_price / first_benchmark - 1
            if first_benchmark and snapshot.benchmark_price
            else None
        )
        points.append(
            {
                **(serialize_snapshot(snapshot) or {}),
                "portfolio_return": portfolio_return,
                "benchmark_return": benchmark_return,
                "excess_return": (
                    portfolio_return - benchmark_return
                    if portfolio_return is not None and benchmark_return is not None
                    else None
                ),
            }
        )
    last = points[-1]
    return {
        "period": period,
        "points": points,
        "summary": {
            "portfolio_return": last["portfolio_return"],
            "benchmark_return": last["benchmark_return"],
            "excess_return": last["excess_return"],
            "start_date": points[0]["snapshot_date"],
            "end_date": last["snapshot_date"],
        },
    }


def default_benchmark_price() -> float | None:
    """读取 510300 最新价；失败时保留空值，不伪造行情。"""

    try:
        from src.core.marketdata_client import md_quote_rows

        rows = md_quote_rows(["510300"], "CN")
        if not rows:
            return None
        return _finite(rows[0].get("current_price")) or None
    except Exception:
        return None


def now_shanghai_date() -> str:
    """返回应用默认时区下的日期，独立函数便于测试。"""

    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    except Exception:
        return date.today().isoformat()
