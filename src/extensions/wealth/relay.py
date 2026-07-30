"""从私有 Cloudflare Worker 中继拉取 Google Sheets 当日快照。"""

from __future__ import annotations

import os

import httpx
from sqlalchemy.orm import Session

from src.extensions.wealth.schemas import GoogleSheetsSyncPayload
from src.extensions.wealth.service import sync_google_sheets


DEFAULT_RELAY_URL = (
    "https://holdings-api.ja-invent.workers.dev/wealth-snapshot/current"
)


def fetch_relay_payload() -> GoogleSheetsSyncPayload:
    token = os.getenv("PANWATCH_WEALTH_SYNC_TOKEN", "").strip()
    if not token:
        raise RuntimeError("未配置 PANWATCH_WEALTH_SYNC_TOKEN")
    url = os.getenv("PANWATCH_WEALTH_RELAY_URL", DEFAULT_RELAY_URL).strip()
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()
    return GoogleSheetsSyncPayload.model_validate(response.json())


def sync_from_relay(db: Session) -> dict:
    payload = fetch_relay_payload()
    return sync_google_sheets(db, payload)
