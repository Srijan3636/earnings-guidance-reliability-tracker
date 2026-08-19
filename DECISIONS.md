# Decisions Log

Written as the project was built, not reconstructed afterward.

---

## Validated the approach on one real transcript before building the pipeline

**Decision:** Downloaded one real transcript (Wipro Q3 FY26, from Wipro's own investor
relations site) and ran pdfplumber against it before writing any extraction code.

**Why:** Confirmed the whole premise actually works on real data rather than assuming
it would: 15 pages, ~36k characters extracted cleanly, and real forward-looking
guidance language is present and findable — "we are projecting sequential IT
Services revenue growth of 0% to 2.0% in constant currency." One real artifact found
and handled: the source PDF's bullet/dash glyph extracts as U+FFFD (same
replacement-character issue as elsewhere in this portfolio) — cleaned up in
`extract_text.py` rather than left in the text fed to the LLM.

---

## Mock mode is not a stub — it's a fully tested path

**Decision:** `--mock` mode in `extract_guidance.py` returns canned results modeled
on the real Wipro guidance statement found above, and the schema-validation logic
(`validate_item`) was tested directly against both a valid item and two kinds of
invalid ones (missing fields, invalid enum value) — both the accept and reject paths
are proven to work, not just written.

**Why this matters:** I do not have an Anthropic API key yet, so the real extraction
path (`extract_real`) is written but genuinely untested — that's stated plainly here
rather than implied to work. Everything downstream of extraction (validation scoring,
loading, the guidance-vs-actuals SQL) has been exercised end-to-end using mock output,
so the pipeline's plumbing is real and tested even though the LLM call itself isn't
yet.

---

## guidance_vs_actuals.sql shows guidance next to actuals — it does not auto-score them

**Decision:** `stated_value` is stored as free text, exactly as management said it
("0% to 2.0% sequential growth in constant currency"), not as a parsed number.
`guidance_vs_actuals.sql` joins each guidance statement to the next reported quarter's
actual revenue growth using `LAG()`, and presents both side by side — it does not
attempt to parse the range and compute a pass/fail delta automatically.

**Why:** Building a real parser for guidance ranges (handling "0% to 2%", "high
single digits", "flat to slightly up", constant-currency qualifiers, YoY vs QoQ
framing) is a genuinely hard NLP problem on its own. Faking a clean numeric
comparison here would overstate what the project does. The honest scope is:
extraction + validation + side-by-side comparison for a human to judge. Said so
explicitly in the SQL comments and will restate in the README.

---

## Accuracy scoring lives in Python, not SQL — because the labels live in a CSV

**Decision:** `score_validation.py` reads the hand-labelled CSV and computes accuracy
broken down by `guidance_type`, rather than writing this as a `sql/analysis/*.sql`
file.

**Why:** Human labels are collected in `data/labelling_template.csv`, not in
Postgres — there's no DB table to query against. Forcing this into SQL would mean
loading throwaway label data into the database for no real reason. Python reading a
CSV directly is the simpler, more honest tool for this specific step. The rest of
the project's real analytical work (the join in `guidance_vs_actuals.sql`) is still
SQL, as it should be.

**Also decided:** report a per-`guidance_type` breakdown as the primary output, with
a single overall percentage shown only "for reference" — different guidance types
are genuinely different extraction difficulty (a clean number like "0% to 2.0%
revenue growth" vs. vague qualitative commentary), and one blended number would hide
exactly the finding an interviewer would want to hear about.

---

## This repo builds its own reported_financials — no dependency on the other repo

**Decision:** `fetch_financials.py` pulls quarterly income-statement data via
yfinance independently, using the same 5 tickers this project has transcripts for
(subset of the 9-peer set in financial-investment-analytics).

**Why:** Each of the three portfolio repos must run standalone from a fresh clone
(project-wide convention, not specific to this repo). Reaching into another repo's
database would break that.

---

## Bug found on first real run: "next reported period" was actually the earliest one on file

**What happened:** first real execution of `guidance_vs_actuals.sql` against the
loaded database returned `next_reported_period = 2025-06-30` for guidance given in
a call on **January 16, 2026** — a "next" period nine months in the past. Obviously
wrong the moment the dates were checked side by side.

**Root cause:** the `transcripts` table originally had no date field, only a
`quarter_label` string like `WIPRO_Q3FY26_transcript`. The query's
`ROW_NUMBER() OVER (PARTITION BY guidance_id ORDER BY period_end ASC)` had nothing
to filter on, so `rn = 1` just picked each company's **earliest** reported period
in the whole table, not the next one chronologically after the call.

**Fix:** added `call_date DATE` to the `transcripts` table, extracted via regex
from the transcript's own header text (verified the real Wipro transcript prints
"January 16, 2026" as plain text near the top — not hardcoded, actually parsed out
of the document) in `load_data.py`. Added `AND ra.period_end > t.call_date` to the
join in `guidance_vs_actuals.sql`. Re-ran: correctly returned
`next_reported_period = 2026-03-31` (Q4 FY26, the exact quarter Wipro's guidance
was about).

**Result, now that it's correct:** Wipro guided "0% to 2.0% sequential revenue
growth" for Q4 FY26; the actual reported figure was **2.89%** QoQ growth — slightly
above the top of their own guided range. One data point, not a pattern, but a
real, verified, and interesting finding rather than a placeholder number.

---
