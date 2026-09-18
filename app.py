from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from flips import rank_flips
from ge_client import GeClient, catalog

st.set_page_config(
    page_title="OSRS GE Flipper",
    page_icon="🪙",
    layout="wide",
)


@st.cache_data(ttl=90, show_spinner="Pulling live GE prices...")
def load_catalog() -> pd.DataFrame:
    return catalog(GeClient())


@st.cache_data(ttl=300, show_spinner="Loading price history...")
def load_history(item_id: int, timestep: str) -> pd.DataFrame:
    return GeClient().timeseries(item_id, timestep=timestep)


def gp(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    n = float(value)
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}b"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}m"
    if abs(n) >= 10_000:
        return f"{n / 1_000:.1f}k"
    return f"{int(n):,}"


def main() -> None:
    st.title("OSRS Grand Exchange flipper")
    st.caption(
        "Live buy/sell prices from the OSRS Wiki real-time API. "
        "Flips assume you buy at the current **low** (wait for a seller) and sell at the current **high** "
        "(wait for a buyer), minus the 2% GE tax (capped at 5m)."
    )

    with st.sidebar:
        st.header("Filters")
        cash_stack = st.number_input(
            "Cash stack (gp)",
            min_value=1_000,
            max_value=2_147_483_647,
            value=5_000_000,
            step=100_000,
        )
        min_profit = st.number_input("Min profit per item (gp)", 0, 10_000_000, 1_000, 500)
        min_volume = st.number_input("Min 1h volume", 0, 10_000_000, 50, 10)
        max_stale = st.slider("Max stale quotes (minutes)", 5, 180, 45)
        world = st.selectbox("Worlds", ["All", "Members", "F2P"])
        members_only = {"All": None, "Members": True, "F2P": False}[world]
        search = st.text_input("Search item name")
        if st.button("Refresh prices"):
            load_catalog.clear()
            st.rerun()

    try:
        data = load_catalog()
    except Exception as exc:
        st.error(f"Could not reach the GE price API: {exc}")
        st.stop()

    flips = rank_flips(
        data,
        cash_stack=int(cash_stack),
        min_profit=int(min_profit),
        min_volume_1h=int(min_volume),
        max_stale_min=int(max_stale),
        members_only=members_only,
        max_limit=None,
        search=search,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Items tracked", f"{len(data):,}")
    c2.metric("Flip candidates", f"{len(flips):,}")
    best = flips.iloc[0] if not flips.empty else None
    c3.metric("Top item", best["name"] if best is not None else "—")
    c4.metric(
        "Top est. 1h profit",
        gp(best["potential_profit"]) if best is not None else "—",
    )

    if flips.empty:
        st.warning("No items match those filters. Loosen profit, volume, or cash stack.")
        st.stop()

    table = flips.head(75).copy()
    display = table[
        [
            "name",
            "buy_price",
            "sell_price",
            "tax",
            "profit",
            "roi",
            "volume_1h",
            "low_vol_1h",
            "high_vol_1h",
            "limit",
            "flip_qty",
            "potential_profit",
            "stale_min",
            "members",
        ]
    ].rename(
        columns={
            "name": "Item",
            "buy_price": "Buy (low)",
            "sell_price": "Sell (high)",
            "tax": "Tax",
            "profit": "Profit / ea",
            "roi": "ROI",
            "volume_1h": "Vol 1h",
            "low_vol_1h": "Vol buy 1h",
            "high_vol_1h": "Vol sell 1h",
            "limit": "GE limit (4h)",
            "flip_qty": "Est. 1h qty",
            "potential_profit": "Est. 1h profit",
            "stale_min": "Stale (min)",
            "members": "Members",
        }
    )
    display["ROI"] = display["ROI"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "—")
    display["Stale (min)"] = display["Stale (min)"].map(lambda x: f"{x:.0f}")
    for vol_col in ["Vol 1h", "Vol buy 1h", "Vol sell 1h", "GE limit (4h)", "Est. 1h qty"]:
        display[vol_col] = display[vol_col].map(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
    money_cols = [
        "Buy (low)",
        "Sell (high)",
        "Tax",
        "Profit / ea",
        "Est. 1h profit",
    ]
    for col in money_cols:
        display[col] = display[col].map(gp)

    names = table["name"].tolist()
    selected = st.selectbox("Inspect item", names, index=0)
    row = table[table["name"] == selected].iloc[0]

    left, right = st.columns([2, 1])
    with left:
        timestep = st.radio(
            "Each chart point averages",
            ["5m", "1h", "6h", "24h"],
            index=3,
            horizontal=True,
            help=(
                "This is the size of each dot, not the length of the x-axis. "
                "24h = one daily average (the axis is still many months). "
                "5m = one point every five minutes (much shorter recent window)."
            ),
        )
        st.caption(
            "X-axis is always time. **24h** means each point is a full day "
            "(about a year of days). **5m** means each point is five minutes "
            "(a short recent window)."
        )
        history = load_history(int(row["item_id"]), timestep)
        if history.empty:
            st.info("No history for this item.")
        else:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=history["timestamp"],
                    y=history["avgHighPrice"],
                    name="Avg high (sell)",
                    line=dict(color="#e1c16e"),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=history["timestamp"],
                    y=history["avgLowPrice"],
                    name="Avg low (buy)",
                    line=dict(color="#7ec8e3"),
                )
            )
            fig.update_layout(
                title=f"{row['name']} price history",
                xaxis_title="Date",
                yaxis_title="gp",
                margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(orientation="h"),
                template="plotly_dark",
                paper_bgcolor="#1b1a17",
                plot_bgcolor="#1b1a17",
            )
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader(row["name"])
        st.metric("Buy at (low)", gp(row["buy_price"]))
        st.metric("Sell at (high)", gp(row["sell_price"]))
        st.metric("Profit after tax", gp(row["profit"]))
        st.metric("1h volume (total)", f"{int(row['volume_1h']):,}")
        st.metric("Buy-side vol 1h", f"{int(row['low_vol_1h']):,}")
        st.metric("Sell-side vol 1h", f"{int(row['high_vol_1h']):,}")
        st.caption("Buy-side = trades at the low (you getting stock). Sell-side = trades at the high (you dumping). Est. 1h qty uses the smaller of those two, then cash and the 4h buy limit.")
        wiki = row["name"].replace(" ", "_")
        st.link_button("Open on OSRS Wiki", f"https://oldschool.runescape.wiki/w/{wiki}")
        st.caption(
            "This is not financial advice for a pixel market either. "
            "Wide margins on thin volume often do not fill."
        )

    st.subheader("Flip candidates")
    st.dataframe(display, use_container_width=True, hide_index=True, height=420)


if __name__ == "__main__":
    main()
