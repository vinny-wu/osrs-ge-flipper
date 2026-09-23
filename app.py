from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from flips import rank_flips
from ge_client import GeClient, catalog, ge_tax

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


def chart_stats(series: pd.Series) -> dict[str, float | int | pd.Series]:
    """IQR fences on a timeseries of averages (not the latest snapshot)."""
    values = pd.to_numeric(series, errors="coerce")
    clean = values.dropna()
    empty_mask = values.isna() & False
    if len(clean) < 8:
        return {
            "median": float(clean.median()) if len(clean) else float("nan"),
            "min": float(clean.min()) if len(clean) else float("nan"),
            "max": float(clean.max()) if len(clean) else float("nan"),
            "low_fence": float("nan"),
            "high_fence": float("nan"),
            "outliers": empty_mask,
            "n_outliers": 0,
        }
    q1 = float(clean.quantile(0.25))
    q3 = float(clean.quantile(0.75))
    iqr = q3 - q1
    low_fence = q1 - 1.5 * iqr if iqr > 0 else q1
    high_fence = q3 + 1.5 * iqr if iqr > 0 else q3
    outliers = (values < low_fence) | (values > high_fence)
    return {
        "median": float(clean.median()),
        "min": float(clean.min()),
        "max": float(clean.max()),
        "low_fence": low_fence,
        "high_fence": high_fence,
        "outliers": outliers.fillna(False),
        "n_outliers": int(outliers.fillna(False).sum()),
    }


def typical_quantile(series: pd.Series, q: float) -> int | None:
    """Percentile of a series after dropping IQR outliers."""
    values = pd.to_numeric(series, errors="coerce")
    stats = chart_stats(values)
    typical = values[~stats["outliers"]].dropna()
    if typical.empty:
        typical = values.dropna()
    if typical.empty:
        return None
    n = float(typical.quantile(q))
    if pd.isna(n):
        return None
    return int(round(n))


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
            value=10_000_000,
            step=100_000,
        )
        min_profit = st.number_input("Min profit per item (gp)", 0, 10_000_000, 1_000, 500)
        min_volume = st.number_input("Min 1h volume", 0, 10_000_000, 50, 10)
        max_stale = st.slider("Max stale quotes (minutes)", 5, 180, 45)
        world = st.selectbox("Worlds", ["All", "Members", "F2P"])
        members_only = {"All": None, "Members": True, "F2P": False}[world]
        search = st.text_input(
            "Look up item (for listing)",
            help=(
                "Type a name to see live high/low even if it is not a flip candidate. "
                "Use this after a buy fills: list at Sell (high). "
                "Leave empty to rank flips with the filters above."
            ),
        )
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

    looking_up = bool(search.strip())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Items tracked", f"{len(data):,}")
    c2.metric("Name matches" if looking_up else "Flip candidates", f"{len(flips):,}")
    best = flips.iloc[0] if not flips.empty else None
    c3.metric("Top item", best["name"] if best is not None else "—")
    c4.metric(
        "List at (high)" if looking_up else "Top est. 1h profit",
        gp(best["sell_price"] if looking_up else best["potential_profit"])
        if best is not None
        else "—",
    )

    if looking_up:
        st.caption(
            "Lookup ignores flip filters (profit, volume, stale, cash). "
            "**Sell (high)** is the live list price after a buy fills."
        )

    if flips.empty:
        if looking_up:
            st.warning("No item names match that lookup.")
        else:
            st.warning("No items match those filters. Loosen profit, volume, or cash stack.")
        st.stop()

    table = flips.head(75).copy()
    display = table[
        [
            "name",
            "potential_profit",
            "flip_qty",
            "buy_price",
            "sell_price",
            "tax",
            "profit",
            "roi",
            "volume_1h",
            "low_vol_1h",
            "high_vol_1h",
            "limit",
            "stale_min",
            "members",
        ]
    ].rename(
        columns={
            "name": "Item",
            "potential_profit": "Est. 1h profit",
            "flip_qty": "Est. 1h qty",
            "buy_price": "Buy (low)",
            "sell_price": "Sell (high)",
            "tax": "Tax",
            "profit": "Profit / ea",
            "roi": "ROI",
            "volume_1h": "Vol 1h",
            "low_vol_1h": "Vol buy 1h",
            "high_vol_1h": "Vol sell 1h",
            "limit": "GE limit (4h)",
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
    item_id = int(row["item_id"])

    buy_wait = int(row["buy_price"])
    sell_latest = int(row["sell_price"])
    tax_latest = ge_tax(sell_latest)

    history_6h = load_history(item_id, "6h")
    buy_afk_6h = None
    sell_afk_6h = None
    if not history_6h.empty:
        # Cheap tail of lows / rich tail of highs — same "wait longer" idea, opposite sides.
        buy_afk_6h = typical_quantile(history_6h["avgLowPrice"], 0.25)
        sell_afk_6h = typical_quantile(history_6h["avgHighPrice"], 0.75)

    left, right = st.columns([2, 1])
    with left:
        timestep_labels = {
            "5m": "Every 5 min",
            "1h": "Hourly avg",
            "6h": "Every 6 hours",
            "24h": "Daily avg",
        }
        timestep = st.radio(
            "Each point is",
            list(timestep_labels),
            index=3,
            format_func=lambda key: timestep_labels[key],
            horizontal=True,
            help=(
                "How much time one dot summarizes — the gap between x-axis values. "
                "Daily avg = one average per day (chart covers about a year). "
                "Every 5 min = one average every five minutes (short recent window)."
            ),
        )
        st.caption(
            "Not the length of the x-axis: **Daily avg** spaces points one day apart; "
            "**Every 5 min** spaces them five minutes apart."
        )
        history = load_history(item_id, timestep)
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
            high_stats = chart_stats(history["avgHighPrice"])
            low_stats = chart_stats(history["avgLowPrice"])
            high_out = history.loc[high_stats["outliers"]]
            low_out = history.loc[low_stats["outliers"]]
            if not high_out.empty:
                fig.add_trace(
                    go.Scatter(
                        x=high_out["timestamp"],
                        y=high_out["avgHighPrice"],
                        name="High outlier",
                        mode="markers",
                        marker=dict(color="#e07a5f", size=8, symbol="x"),
                    )
                )
            if not low_out.empty:
                fig.add_trace(
                    go.Scatter(
                        x=low_out["timestamp"],
                        y=low_out["avgLowPrice"],
                        name="Low outlier",
                        mode="markers",
                        marker=dict(color="#81b29a", size=8, symbol="x"),
                    )
                )
            x0 = history["timestamp"].min()
            x1 = history["timestamp"].max()
            offer_lines = [
                (buy_wait, "Latest low", "#7ec8e3"),
                (sell_latest, "Latest high", "#e1c16e"),
            ]
            if buy_afk_6h is not None:
                offer_lines.append((buy_afk_6h, "Buy AFK (6h)", "#81b29a"))
            if sell_afk_6h is not None:
                offer_lines.append((sell_afk_6h, "Sell AFK (6h)", "#c084fc"))
            seen_y: set[int] = set()
            for y, name, color in offer_lines:
                key = int(round(float(y)))
                if key in seen_y:
                    continue
                seen_y.add(key)
                fig.add_trace(
                    go.Scatter(
                        x=[x0, x1],
                        y=[y, y],
                        mode="lines",
                        name=name,
                        line=dict(color=color, dash="dot", width=1),
                        hovertemplate=name + ": %{y:,.0f} gp<extra></extra>",
                    )
                )
            fig.update_layout(
                title=f"{row['name']} price history",
                xaxis_title="Date",
                yaxis_title="gp",
                margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=-0.28, font=dict(size=11)),
                template="plotly_dark",
                paper_bgcolor="#1b1a17",
                plot_bgcolor="#1b1a17",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                f"X marks IQR outliers on this series ({timestep_labels[timestep]}). "
                f"{int(high_stats['n_outliers'])} unusual highs, "
                f"{int(low_stats['n_outliers'])} unusual lows. "
                "A spike high may never fill; a crash low may never get a seller. "
                "Dotted lines are the inspect-table list prices."
            )

    with right:
        st.subheader(row["name"])
        offers = [
            {
                "Offer": "Latest low",
                "List": gp(buy_wait),
                "After tax": "—",
                "Source": "Wiki /latest low",
            },
        ]
        if buy_afk_6h is not None:
            offers.append(
                {
                    "Offer": "Buy AFK (6h)",
                    "List": gp(buy_afk_6h),
                    "After tax": "—",
                    "Source": "25th pct 6h avg low, outliers dropped",
                }
            )
        offers.append(
            {
                "Offer": "Latest high",
                "List": gp(sell_latest),
                "After tax": gp(sell_latest - tax_latest),
                "Source": "Wiki /latest high",
            }
        )
        if sell_afk_6h is not None:
            offers.append(
                {
                    "Offer": "Sell AFK (6h)",
                    "List": gp(sell_afk_6h),
                    "After tax": gp(sell_afk_6h - ge_tax(sell_afk_6h)),
                    "Source": "75th pct 6h avg high, outliers dropped",
                }
            )
        st.dataframe(pd.DataFrame(offers), hide_index=True, use_container_width=True)

        if not history.empty:
            hs = chart_stats(history["avgHighPrice"])
            ls = chart_stats(history["avgLowPrice"])
            if pd.notna(hs["high_fence"]) and sell_latest > hs["high_fence"]:
                st.warning(
                    "Latest high is above typical highs on this chart — listing there may never fill."
                )
            if pd.notna(ls["low_fence"]) and buy_wait < ls["low_fence"]:
                st.warning(
                    "Latest low is below typical lows on this chart — waiting on a buy may take forever."
                )

        vol = pd.DataFrame(
            [
                {
                    "Vol buy 1h": f"{int(row['low_vol_1h']):,}",
                    "Vol sell 1h": f"{int(row['high_vol_1h']):,}",
                    "Vol 1h": f"{int(row['volume_1h']):,}",
                }
            ]
        )
        st.dataframe(vol, hide_index=True, use_container_width=True)
        st.caption(
            "Dotted lines are these list prices. "
            "Buy AFK / Sell AFK are the ambitious tails of 6h history (25th of lows, 75th of highs), "
            "not the current book. "
            "Worth waiting on a buy if Buy AFK is **below** Latest low; "
            "worth waiting on a sell if Sell AFK is **above** Latest high. "
            "If the AFK line is on the other side, the latest print already beats that tail. "
            "None of these prices guarantee a fill."
        )
        wiki = row["name"].replace(" ", "_")
        st.link_button("Open on OSRS Wiki", f"https://oldschool.runescape.wiki/w/{wiki}")
        st.caption(
            "This is not financial advice for a pixel market either. "
            "Wide margins on thin volume often do not fill."
        )

    st.subheader("Flip candidates")
    profit_col = "Est. 1h profit"
    styled = display.style.set_properties(
        subset=[profit_col],
        **{
            "color": "#e1c16e",
            "font-weight": "700",
            "background-color": "#3a3324",
        },
    )
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            profit_col: st.column_config.TextColumn(
                profit_col,
                help="Ranked by this: profit after tax × estimated round trips this hour.",
                width="medium",
            ),
        },
    )


if __name__ == "__main__":
    main()
