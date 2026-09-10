"""Print ge_client / flips data before Streamlit formats it.

  .venv/bin/python inspect_layers.py
  .venv/bin/python inspect_layers.py --item 2
"""

from __future__ import annotations

import argparse

from flips import rank_flips
from ge_client import GeClient, catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--item", type=int, default=2, help="item_id to zoom in on")
    parser.add_argument("--cash", type=int, default=5_000_000)
    args = parser.parse_args()

    client = GeClient()
    mapping = client.mapping()
    latest = client.latest()
    hour = client.averages("1h")
    cat = catalog(client)
    flips = rank_flips(
        cat,
        cash_stack=args.cash,
        min_profit=1_000,
        min_volume_1h=50,
        max_stale_min=45,
        members_only=None,
        max_limit=None,
    )

    item_id = args.item
    print(f"mapping  {mapping.shape}  {list(mapping.columns)}")
    print(f"latest   {latest.shape}  {list(latest.columns)}")
    print(f"1h       {hour.shape}  {list(hour.columns)}")
    print(f"catalog  {cat.shape}  {list(cat.columns)}")
    print(f"flips    {flips.shape}  {list(flips.columns)}")
    print()

    print("--- mapping / latest / 1h / catalog for item_id", item_id)
    print(mapping[mapping["item_id"] == item_id].T.to_string())
    print()
    print(latest[latest["item_id"] == item_id].T.to_string())
    print()
    print(hour[hour["item_id"] == item_id].T.to_string())
    print()
    print(
        cat[cat["item_id"] == item_id][
            [
                "name",
                "buy_price",
                "sell_price",
                "tax",
                "profit",
                "roi",
                "stale_min",
                "volume_1h",
                "high_vol_1h",
                "low_vol_1h",
            ]
        ].T.to_string()
    )

    print()
    print("--- rank_flips top 10 (raw numbers)")
    cols = [
        "name",
        "buy_price",
        "sell_price",
        "tax",
        "profit",
        "roi",
        "volume_1h",
        "flip_qty",
        "potential_profit",
        "stale_min",
    ]
    print(flips.head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
