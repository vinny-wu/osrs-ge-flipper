# OSRS GE Flipper

A local dashboard for Old School RuneScape Grand Exchange prices.

It pulls live highs/lows, hourly volume, and price history from the
[OSRS Wiki real-time prices API](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices),
then ranks items you could buy at the **low** and sell at the **high** after the 2% GE tax.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## How flips are scored

- **Buy price** = latest `low` (place a buy offer and wait)
- **Sell price** = latest `high` (place a sell offer and wait)
- **Tax** = 2% of the sell price, capped at 5,000,000 gp
- **Potential profit** = profit per item × estimated 1h qty
- **Est. 1h qty** = smallest of: cash stack ÷ buy price, GE 4-hour buy limit, and the thinner of last-hour buy-side vs sell-side volume

Thin volume + a fat margin often means the offers will not fill.
