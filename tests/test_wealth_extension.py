"""全资产扩展估值、同步和历史曲线测试。"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
from src.extensions.wealth.service import (
    build_summary,
    list_summary,
    performance_series,
    record_snapshot,
    sync_google_sheets,
)
from src.web.database import Base


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            WealthAsset.__table__,
            WealthSnapshot.__table__,
            WealthSnapshotItem.__table__,
            WealthSyncRun.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def _asset(**kwargs) -> WealthAsset:
    defaults = {
        "account_name": "默认账户",
        "category": "a_stock",
        "symbol": "600000",
        "name": "样例",
        "market": "CN",
        "currency": "CNY",
        "exchange_rate": 1,
        "valuation_method": "price",
        "quantity": 1,
        "current_price": 1,
        "contract_multiplier": 1,
        "position_side": "long",
        "enabled": True,
        "source_system": "manual",
        "source_key": "sample",
    }
    defaults.update(kwargs)
    return WealthAsset(**defaults)


def test_b_share_uses_explicit_usd_and_hkd_exchange_rates():
    """沪B按美元、深B按港币折算，不能把原币价格直接当人民币。"""

    summary = build_summary(
        [
            _asset(
                category="b_stock",
                symbol="900948",
                name="伊泰B股",
                currency="USD",
                exchange_rate=6.75525052,
                quantity=27900,
                current_price=2.875,
                source_key="900948",
            ),
            _asset(
                category="b_stock",
                symbol="200429",
                name="粤高速B",
                currency="HKD",
                exchange_rate=0.861293,
                quantity=13100,
                current_price=9.87,
                source_key="200429",
            ),
        ]
    )

    expected = 27900 * 2.875 * 6.75525052 + 13100 * 9.87 * 0.861293
    assert summary["by_category"]["b_stock"]["value_cny"] == round(expected, 2)
    assert summary["net_assets"] == round(expected, 2)


def test_derivative_equity_is_separate_from_notional_exposure():
    """期货账户权益计入净资产，合约名义金额只计敞口和杠杆。"""

    summary = build_summary(
        [
            _asset(
                category="future",
                symbol="IF2608",
                name="沪深300股指期货",
                valuation_method="derivative",
                quantity=2,
                current_price=4200,
                contract_multiplier=300,
                margin=737841,
                source_key="IF2608",
            ),
            _asset(
                category="liability",
                symbol="",
                name="融资负债",
                valuation_method="manual",
                manual_amount=2600000,
                source_key="liability",
            ),
            _asset(
                category="cash",
                symbol="CNY",
                name="现金",
                valuation_method="manual",
                manual_amount=5000000,
                source_key="cash",
            ),
        ]
    )

    assert summary["derivative_exposure"] == 2 * 4200 * 300
    assert summary["gross_assets"] == 5_737_841
    assert summary["liabilities"] == 2_600_000
    assert summary["net_assets"] == 3_137_841
    assert summary["leverage"] > 1


def test_google_sheets_sync_is_idempotent_and_deactivates_missing_assets():
    """Google Sheets 重复同步只更新同一来源记录，删除的行会停用。"""

    db = _session()
    try:
        first = GoogleSheetsSyncPayload(
            spreadsheet_id="sheet-1",
            as_of_date="2026-07-30",
            assets=[
                AssetInput(
                    category="b_stock",
                    symbol="900948",
                    name="伊泰B股",
                    currency="USD",
                    exchange_rate=6.75,
                    quantity=100,
                    current_price=3,
                    source_key="stock:900948",
                ),
                AssetInput(
                    category="cash",
                    name="现金",
                    valuation_method="manual",
                    manual_amount=1000,
                    source_key="summary:cash",
                ),
            ],
        )
        sync_google_sheets(db, first)
        sync_google_sheets(db, first)
        assert db.query(WealthAsset).count() == 2

        second = GoogleSheetsSyncPayload(
            spreadsheet_id="sheet-1",
            as_of_date="2026-07-31",
            assets=[
                AssetInput(
                    category="b_stock",
                    symbol="900948",
                    name="伊泰B股",
                    currency="USD",
                    exchange_rate=6.8,
                    quantity=100,
                    current_price=3.1,
                    source_key="stock:900948",
                )
            ],
        )
        sync_google_sheets(db, second)
        rows = db.query(WealthAsset).order_by(WealthAsset.id).all()
        assert len(rows) == 2
        assert rows[0].current_price == 3.1
        assert rows[0].exchange_rate == 6.8
        assert rows[1].enabled is False
    finally:
        db.close()


def test_imported_nav_curve_compares_with_benchmark_on_same_base():
    """历史曲线以份额净值和基准价格各自归一化，超额收益口径一致。"""

    db = _session()
    try:
        payload = GoogleSheetsSyncPayload(
            spreadsheet_id="sheet-1",
            as_of_date="2026-07-31",
            assets=[],
            history=[
                GoogleSheetsHistoryRow(
                    snapshot_date="2026-07-29",
                    categories={"a_stock": 1_000_000},
                    gross_assets=1_000_000,
                    net_assets=800_000,
                    liabilities=200_000,
                    performance_nav=1.0,
                    benchmark_price=4.0,
                ),
                GoogleSheetsHistoryRow(
                    snapshot_date="2026-07-30",
                    categories={"a_stock": 1_120_000},
                    gross_assets=1_120_000,
                    net_assets=920_000,
                    liabilities=200_000,
                    performance_nav=1.1,
                    benchmark_price=4.2,
                ),
            ],
        )
        sync_google_sheets(db, payload)
        curve = performance_series(db, "max")
        summary = list_summary(db)
        last = curve["points"][-1]
        assert summary["snapshot_count"] == 2
        assert round(last["portfolio_return"], 6) == 0.1
        assert round(last["benchmark_return"], 6) == 0.05
        assert round(last["excess_return"], 6) == 0.05
    finally:
        db.close()


def test_daily_snapshot_upserts_same_date_instead_of_duplicating():
    """同一交易日重复记录会覆盖快照，保证定时器幂等。"""

    db = _session()
    try:
        db.add(
            _asset(
                category="cash",
                name="现金",
                valuation_method="manual",
                manual_amount=1000,
                source_key="cash",
            )
        )
        db.commit()
        record_snapshot(
            db,
            snapshot_date="2026-07-31",
            benchmark_price_provider=lambda: 4.5,
        )
        asset = db.query(WealthAsset).first()
        asset.manual_amount = 1200
        db.commit()
        record_snapshot(
            db,
            snapshot_date="2026-07-31",
            benchmark_price_provider=lambda: 4.6,
        )

        assert db.query(WealthSnapshot).count() == 1
        snapshot = db.query(WealthSnapshot).first()
        assert snapshot.net_assets == 1200
        assert snapshot.benchmark_price == 4.6
        assert db.query(WealthSnapshotItem).count() == 1
    finally:
        db.close()


def test_relay_payload_requires_same_sync_schema(monkeypatch):
    """中继响应沿用 Google Sheets 同步 schema，异常字段不能污染数据库。"""

    from src.extensions.wealth import relay

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "spreadsheet_id": "sheet-1",
                "as_of_date": "2026-07-31",
                "assets": [
                    {
                        "category": "b_stock",
                        "symbol": "900948",
                        "name": "伊泰B股",
                        "currency": "USD",
                        "exchange_rate": 6.75,
                        "quantity": 100,
                        "current_price": 3,
                    }
                ],
                "history": [],
            }

    monkeypatch.setenv("PANWATCH_WEALTH_SYNC_TOKEN", "secret")
    monkeypatch.setattr(relay.httpx, "get", lambda *args, **kwargs: Response())
    payload = relay.fetch_relay_payload()
    assert payload.assets[0].currency == "USD"
    assert payload.assets[0].category == "b_stock"
