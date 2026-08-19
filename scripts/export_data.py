"""
Run every sql/analysis/*.sql file and write results to exports/*.csv for
the Power BI accuracy dashboard.

Usage: py -3.10 scripts/export_data.py
Requires DATABASE_URL in .env and the DB already loaded (run load_data.py first).
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set. Copy .env.example to .env and fill in your password.")

ROOT = Path(__file__).parent.parent
ANALYSIS_DIR = ROOT / "sql" / "analysis"
EXPORT_DIR = ROOT / "exports"
EXPORT_DIR.mkdir(exist_ok=True)


def main():
    engine = create_engine(DATABASE_URL)

    sql_files = sorted(ANALYSIS_DIR.glob("*.sql"))
    print(f"Running {len(sql_files)} analysis queries...\n")

    for sql_file in sql_files:
        query = sql_file.read_text()
        try:
            df = pd.read_sql(text(query), engine)
        except Exception as e:
            print(f"  FAILED: {sql_file.name} -> {e}")
            continue
        out_path = EXPORT_DIR / f"{sql_file.stem}.csv"
        df.to_csv(out_path, index=False)
        print(f"  {sql_file.name}: {len(df)} rows -> {out_path.name}")

    # Also export the guidance table raw, and the validation scores, for the
    # dashboard's accuracy-by-type visual.
    with engine.connect() as conn:
        guidance_raw = pd.read_sql(
            "SELECT g.*, c.ticker, c.name, t.quarter_label "
            "FROM guidance g "
            "JOIN companies c ON c.company_id = g.company_id "
            "JOIN transcripts t ON t.transcript_id = g.transcript_id", conn)
    guidance_raw.to_csv(EXPORT_DIR / "guidance_raw.csv", index=False)
    print(f"\n  guidance_raw: {len(guidance_raw)} rows")

    print(f"\nAll exports written to {EXPORT_DIR}")


if __name__ == "__main__":
    main()
