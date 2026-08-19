"""
Load companies, transcripts, extracted guidance, and reported financials
into Postgres database `earnings_guidance`.

Usage: py -3.10 scripts/load_data.py [--mock]
Requires DATABASE_URL in .env. Run extract_text.py, extract_guidance.py
(with --mock if no API key yet), and fetch_financials.py first.
"""
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set. Copy .env.example to .env and fill in your password.")

ROOT = Path(__file__).parent.parent
SCHEMA_SQL = ROOT / "sql" / "schema.sql"
GUIDANCE_DIR = ROOT / "data" / "guidance"
EXTRACTED_DIR = ROOT / "data" / "extracted"
FINANCIALS_CSV = ROOT / "data" / "clean" / "reported_financials.csv"

CALL_DATE_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r" \d{1,2}, \d{4}"
)


def extract_call_date(transcript_stem: str) -> "datetime | None":
    """Transcripts print their call date near the top, e.g. 'January 16, 2026'
    (verified against the real Wipro transcript). Regex it out of the first
    500 chars rather than hardcoding a date per file — this is what makes
    guidance_vs_actuals.sql able to find the correct NEXT reported period."""
    txt_path = EXTRACTED_DIR / f"{transcript_stem}.txt"
    if not txt_path.exists():
        return None
    head = txt_path.read_text(encoding="utf-8")[:500]
    m = CALL_DATE_PATTERN.search(head)
    if not m:
        return None
    return datetime.strptime(m.group(0), "%B %d, %Y").date()

# Same peer-name mapping as fetch_financials.py
COMPANY_NAMES = {
    "TCS.NS": "Tata Consultancy Services",
    "INFY.NS": "Infosys",
    "WIPRO.NS": "Wipro",
    "HCLTECH.NS": "HCL Technologies",
    "TECHM.NS": "Tech Mahindra",
}

# Maps a transcript filename prefix to its ticker. Extend this as more
# transcripts are added to data/raw/.
FILENAME_TO_TICKER = {
    "WIPRO": "WIPRO.NS",
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "HCLTECH": "HCLTECH.NS",
    "TECHM": "TECHM.NS",
}


def ensure_database_exists(database_url: str) -> None:
    target_db = urlparse(database_url).path.lstrip("/")
    maintenance_url = database_url.rsplit("/", 1)[0] + "/postgres"
    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": target_db},
        ).scalar()
        if not exists:
            print(f"Database '{target_db}' does not exist — creating it.")
            conn.execute(text(f'CREATE DATABASE "{target_db}"'))
        else:
            print(f"Database '{target_db}' already exists.")
    engine.dispose()


def ticker_for_filename(stem: str) -> str | None:
    for prefix, ticker in FILENAME_TO_TICKER.items():
        if stem.upper().startswith(prefix):
            return ticker
    return None


def main():
    ensure_database_exists(DATABASE_URL)
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        print("Applying schema...")
        conn.execute(text(SCHEMA_SQL.read_text()))

        companies = pd.DataFrame(
            [{"ticker": t, "name": n} for t, n in COMPANY_NAMES.items()]
        )
        companies.to_sql("companies", conn, if_exists="append", index=False)
        print(f"  companies: {len(companies)} rows")

        company_map = pd.read_sql("SELECT company_id, ticker FROM companies", conn)
        company_id_by_ticker = dict(zip(company_map.ticker, company_map.company_id))

        # --- transcripts + guidance ---
        guidance_files = sorted(GUIDANCE_DIR.glob("*.json"))
        if not guidance_files:
            print(f"  WARNING: no files in {GUIDANCE_DIR} — run extract_guidance.py first")

        transcript_rows = []
        guidance_rows = []
        for gf in guidance_files:
            ticker = ticker_for_filename(gf.stem)
            if ticker is None:
                print(f"  SKIPPED {gf.name}: can't map filename to a known ticker")
                continue
            company_id = company_id_by_ticker.get(ticker)
            if company_id is None:
                print(f"  SKIPPED {gf.name}: ticker {ticker} not in companies table")
                continue

            items = json.loads(gf.read_text())
            call_date = extract_call_date(gf.stem)
            if call_date is None:
                print(f"  WARNING: could not find a call date in {gf.stem} — "
                      f"guidance_vs_actuals.sql won't be able to place it correctly")
            transcript_rows.append({
                "company_id": company_id,
                "quarter_label": gf.stem,
                "call_date": call_date,
                "source_file": gf.name,
                "extracted_chars": None,
            })
            for item in items:
                guidance_rows.append({**item, "company_id": company_id, "_transcript_key": gf.stem})

        if transcript_rows:
            pd.DataFrame(transcript_rows).to_sql(
                "transcripts", conn, if_exists="append", index=False
            )
        transcript_map = pd.read_sql(
            "SELECT transcript_id, quarter_label FROM transcripts", conn
        )
        tid_by_label = dict(zip(transcript_map.quarter_label, transcript_map.transcript_id))

        if guidance_rows:
            gdf = pd.DataFrame(guidance_rows)
            gdf["transcript_id"] = gdf["_transcript_key"].map(tid_by_label)
            gdf = gdf.drop(columns=["_transcript_key", "source_file"], errors="ignore")
            gdf.to_sql("guidance", conn, if_exists="append", index=False)
        print(f"  transcripts: {len(transcript_rows)} rows")
        print(f"  guidance: {len(guidance_rows)} rows")

        # --- reported_financials ---
        if FINANCIALS_CSV.exists():
            fin = pd.read_csv(FINANCIALS_CSV, parse_dates=["period_end"])
            fin["company_id"] = fin["ticker"].map(company_id_by_ticker)
            fin = fin.dropna(subset=["company_id"])
            fin = fin[["company_id", "period_end", "metric_name", "value"]]
            fin.to_sql("reported_financials", conn, if_exists="append", index=False)
            print(f"  reported_financials: {len(fin)} rows")
        else:
            print(f"  WARNING: {FINANCIALS_CSV} not found — run fetch_financials.py first")

    print("\nLoad complete.")


if __name__ == "__main__":
    main()
