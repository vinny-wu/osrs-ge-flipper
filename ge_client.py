"""OSRS Wiki real-time Grand Exchange prices.

Docs: https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices
A unique User-Agent is required.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

BASE = "https://prices.runescape.wiki/api/v1/osrs"
USER_AGENT = "osrs-ge-flipper (local learning project)"
GE_TAX_RATE = 0.02
GE_TAX_CAP = 5_000_000


class GeClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{BASE}{path}"
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def mapping(self) -> pd.DataFrame:
        rows = self._get("/mapping")
        frame = pd.DataFrame(rows)
        frame = frame.rename(columns={"id": "item_id"})
        return frame

    def latest(self) -> pd.DataFrame:
        payload = self._get("/latest")
        rows = []
        for item_id, prices in payload.get("data", {}).items():
            rows.append(
                {
                    "item_id": int(item_id),
                    "high": prices.get("high"),
                    "low": prices.get("low"),
                    "high_time": prices.get("highTime"),
                    "low_time": prices.get("lowTime"),
                }
            )
        return pd.DataFrame(rows)

    def averages(self, window: str) -> pd.DataFrame:
        if window not in {"5m", "1h"}:
            raise ValueError("window must be 5m or 1h")
        payload = self._get(f"/{window}")
        rows = []
        for item_id, stats in payload.get("data", {}).items():
            rows.append(
                {
                    "item_id": int(item_id),
                    f"avg_high_{window}": stats.get("avgHighPrice"),
                    f"high_vol_{window}": stats.get("highPriceVolume") or 0,
                    f"avg_low_{window}": stats.get("avgLowPrice"),
                    f"low_vol_{window}": stats.get("lowPriceVolume") or 0,
                }
            )
        return pd.DataFrame(rows)

    def timeseries(self, item_id: int, timestep: str = "24h") -> pd.DataFrame:
        payload = self._get(
            "/timeseries",
            params={"id": item_id, "timestep": timestep},
        )
        frame = pd.DataFrame(payload.get("data", []))
        if frame.empty:
            return frame
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        return frame


def ge_tax(sell_price: float) -> int:
    if sell_price is None or sell_price <= 0:
        return 0
    return int(min(sell_price * GE_TAX_RATE, GE_TAX_CAP))


def catalog(client: GeClient | None = None) -> pd.DataFrame:
    client = client or GeClient()
    mapping = client.mapping()
    latest = client.latest()
    hour = client.averages("1h")
    five = client.averages("5m")
    now = int(time.time())

    frame = mapping.merge(latest, on="item_id", how="left")
    frame = frame.merge(hour, on="item_id", how="left")
    frame = frame.merge(five, on="item_id", how="left")

    frame["high_vol_1h"] = frame["high_vol_1h"].fillna(0)
    frame["low_vol_1h"] = frame["low_vol_1h"].fillna(0)
    frame["high_vol_5m"] = frame["high_vol_5m"].fillna(0)
    frame["low_vol_5m"] = frame["low_vol_5m"].fillna(0)
    frame["volume_1h"] = frame["high_vol_1h"] + frame["low_vol_1h"]
    frame["volume_5m"] = frame["high_vol_5m"] + frame["low_vol_5m"]

    frame["buy_price"] = frame["low"]
    frame["sell_price"] = frame["high"]
    frame["tax"] = frame["sell_price"].map(
        lambda price: ge_tax(price) if pd.notna(price) else 0
    )
    frame["profit"] = frame["sell_price"] - frame["buy_price"] - frame["tax"]
    frame["roi"] = frame["profit"] / frame["buy_price"]
    frame["age_high_min"] = (now - frame["high_time"]) / 60
    frame["age_low_min"] = (now - frame["low_time"]) / 60
    frame["stale_min"] = frame[["age_high_min", "age_low_min"]].max(axis=1)
    return frame
