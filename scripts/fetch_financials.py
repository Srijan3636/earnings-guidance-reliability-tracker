"""
Build this project's own reported_financials data via yfinance — kept
separate from the financial-investment-analytics repo on purpose (see
DECISIONS.md: each repo must be self-contained and run standalone).

Usage: py -3.10 scripts/fetch_financials.py
"""
from pathlib import Path

import pandas as pd
import yfinance as yf

# Same peer set as financial-investment-analytics, minus LTIM.NS (excluded
# there too — no data on Yahoo Finance for that ticker, see that repo's
# DECISIONS.md).
COMPANIES = {
    "TCS.NS": "Tata Consultancy Services",
    "INFY.NS": "Infosys",
    "WIPRO.NS": "Wipro",
    "HCLTECH.NS": "HCL Technologies",
    "TECHM.NS": "Tech Mahindra",
}

OUT_DIR = Path(__file__).parent.parent / "data" / "clean"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    rows = []
    for ticker in COMPANIES:
        t = yf.Ticker(ticker)
        q = t.quarterly_income_stmt
        if q is None or q.empty:
            print(f"  {ticker}: no quarterly data, skipping")
            continue

        for metric in ["Total Revenue", "Operating Income"]:
            if metric not in q.index:
                continue
            for period_end, value in q.loc[metric].items():
                if pd.isna(value):
                    continue
                rows.append({
                    "ticker": ticker,
                    "period_end": period_end,
                    "metric_name": metric,
                    "value": value,
                })
        print(f"  {ticker}: {q.shape[1]} quarters fetched")

    df = pd.DataFrame(rows)
    out_path = OUT_DIR / "reported_financials.csv"
    df.to_csv(out_path, index=False)
    print(f"\n{len(df)} rows -> {out_path}")


if __name__ == "__main__":
    main()
