"""全资产扩展 API。"""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.extensions.wealth.models import WealthAsset, WealthSnapshot
from src.extensions.wealth.schemas import (
    AssetInput,
    AssetUpdate,
    GoogleSheetsSyncPayload,
    SnapshotInput,
)
from src.extensions.wealth.service import (
    CATEGORY_LABELS,
    create_asset,
    default_benchmark_price,
    list_summary,
    performance_series,
    record_snapshot,
    serialize_asset,
    serialize_snapshot,
    sync_google_sheets,
)
from src.extensions.wealth.relay import sync_from_relay
from src.web.database import get_db


router = APIRouter()
sync_router = APIRouter()


@router.get("/categories")
def categories():
    """返回所有受支持的资产类别。"""

    return [{"value": key, "label": value} for key, value in CATEGORY_LABELS.items()]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    """返回当前净资产汇总和持仓明细。"""

    return list_summary(db)


@router.get("/assets")
def assets(db: Session = Depends(get_db)):
    """返回全部资产，包括停用项。"""

    rows = db.query(WealthAsset).order_by(
        WealthAsset.enabled.desc(),
        WealthAsset.category,
        WealthAsset.account_name,
        WealthAsset.id,
    )
    return [serialize_asset(row) for row in rows]


@router.post("/assets")
def add_asset(data: AssetInput, db: Session = Depends(get_db)):
    """新增一项资产或负债。"""

    try:
        return serialize_asset(create_asset(db, data))
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"新增失败: {exc}") from exc


@router.put("/assets/{asset_id}")
def update_asset(asset_id: int, data: AssetUpdate, db: Session = Depends(get_db)):
    """更新资产。同步来源字段保持不变，避免破坏下一次幂等同步。"""

    asset = db.query(WealthAsset).filter(WealthAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "资产不存在")
    values = data.model_dump(exclude_unset=True)
    if "metadata" in values:
        asset.metadata_json = values.pop("metadata")
    for key, value in values.items():
        setattr(asset, key, value)
    db.commit()
    db.refresh(asset)
    return serialize_asset(asset)


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    """删除资产。"""

    asset = db.query(WealthAsset).filter(WealthAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "资产不存在")
    db.delete(asset)
    db.commit()
    return {"success": True}


@router.post("/snapshots")
def create_snapshot(data: SnapshotInput, db: Session = Depends(get_db)):
    """立即记录或覆盖指定日期快照。"""

    snapshot = record_snapshot(
        db,
        snapshot_date=data.snapshot_date,
        external_flow=data.external_flow,
        note=data.note,
        benchmark_price_provider=default_benchmark_price,
    )
    return serialize_snapshot(snapshot)


@router.post("/sync-relay")
def sync_relay(db: Session = Depends(get_db)):
    """立即从私有 Worker 中继同步 Google Sheets 当日数据。"""

    try:
        return sync_from_relay(db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(502, f"Google Sheets 中继同步失败: {exc}") from exc


@router.get("/snapshots")
def snapshots(
    limit: int = 400,
    db: Session = Depends(get_db),
):
    """按日期倒序返回快照。"""

    safe_limit = max(1, min(limit, 2000))
    rows = (
        db.query(WealthSnapshot)
        .order_by(WealthSnapshot.snapshot_date.desc())
        .limit(safe_limit)
        .all()
    )
    return [serialize_snapshot(row) for row in rows]


@router.get("/performance")
def performance(period: str = "1y", db: Session = Depends(get_db)):
    """返回组合与沪深300 ETF 的归一化收益曲线。"""

    normalized = period.lower()
    if normalized not in {"1m", "3m", "6m", "1y", "3y", "max"}:
        raise HTTPException(400, "period 仅支持 1m/3m/6m/1y/3y/max")
    return performance_series(db, normalized)


def _verify_sync_token(token: str | None) -> None:
    expected = os.getenv("PANWATCH_WEALTH_SYNC_TOKEN", "").strip()
    if not expected:
        raise HTTPException(503, "未配置 PANWATCH_WEALTH_SYNC_TOKEN")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, "同步密钥无效")


@sync_router.post("/google-sheets")
def google_sheets_sync(
    payload: GoogleSheetsSyncPayload,
    x_panwatch_sync_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """由本机桥接器推送 Google Sheets 当前持仓与历史。"""

    _verify_sync_token(x_panwatch_sync_token)
    return sync_google_sheets(db, payload)
