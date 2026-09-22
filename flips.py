"""Rank Grand Exchange flip candidates from live prices."""

from __future__ import annotations

import pandas as pd


def rank_flips(
    catalog: pd.DataFrame,
    *,
    cash_stack: int,
    min_profit: int,
    min_volume_1h: int,
    max_stale_min: int,
    members_only: bool | None,
    max_limit: int | None,
    search: str = "",
) -> pd.DataFrame:
    frame = catalog.copy()
    lookup = bool(search.strip())
    if lookup:
        needle = search.strip().lower()
        frame = frame[frame["name"].str.lower().str.contains(needle, na=False, regex=False)]
        frame = frame.dropna(subset=["buy_price", "sell_price"])
        frame = frame[frame["buy_price"] > 0]
    else:
        frame = frame.dropna(subset=["buy_price", "sell_price", "profit"])
        frame = frame[frame["buy_price"] > 0]
        frame = frame[frame["buy_price"] <= cash_stack]
        frame = frame[frame["profit"] >= min_profit]
        frame = frame[frame["volume_1h"] >= min_volume_1h]
        frame = frame[frame["high_vol_1h"].fillna(0) >= max(1, min_volume_1h // 4)]
        frame = frame[frame["low_vol_1h"].fillna(0) >= max(1, min_volume_1h // 4)]
        frame = frame[frame["stale_min"].fillna(10_000) <= max_stale_min]
        # Extreme ROI on cheap items is usually a stale/thin book, not a real flip.
        frame = frame[frame["roi"].fillna(0) <= 1.0]

        if members_only is True:
            frame = frame[frame["members"] == True]  # noqa: E712
        elif members_only is False:
            frame = frame[frame["members"] == False]  # noqa: E712

        if max_limit is not None:
            frame = frame[frame["limit"].fillna(0) <= max_limit]

    frame["limit"] = frame["limit"].fillna(0).astype(int)
    frame["max_qty"] = (cash_stack // frame["buy_price"]).clip(upper=frame["limit"])
    frame["max_qty"] = frame["max_qty"].fillna(0).astype(int)
    hourly_flow = frame[["high_vol_1h", "low_vol_1h"]].min(axis=1)
    frame["flip_qty"] = frame[["max_qty", "limit"]].min(axis=1)
    frame["flip_qty"] = frame["flip_qty"].clip(upper=hourly_flow).fillna(0).astype(int)
    frame["potential_profit"] = frame["profit"] * frame["flip_qty"]

    cols = [
        "name",
        "item_id",
        "members",
        "buy_price",
        "sell_price",
        "tax",
        "profit",
        "roi",
        "volume_1h",
        "high_vol_1h",
        "low_vol_1h",
        "volume_5m",
        "limit",
        "max_qty",
        "flip_qty",
        "potential_profit",
        "stale_min",
        "examine",
    ]
    if lookup:
        ranked = frame.sort_values(["name"])
    else:
        ranked = frame.sort_values(
            ["potential_profit", "profit", "volume_1h"],
            ascending=False,
        )
    return ranked[cols]
