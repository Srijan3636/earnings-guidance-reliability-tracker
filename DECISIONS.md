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

## Mock mode was hardcoded and didn't scale — fixed, and the fix revealed a real limitation

**What happened:** the original `extract_mock()` ignored its `transcript_text`
argument entirely and always returned the same hardcoded Wipro quote. Harmless
with exactly one transcript loaded; it would have silently fabricated identical
"guidance" attributed to every company the moment a second transcript was added
— a real integrity problem, not a cosmetic one, since `source_excerpt` is
supposed to be an actual quote from that specific document.

**Fix:** rewrote `extract_mock()` as genuine rule-based extraction — regex over
guidance-keyword sentences containing a percentage, classified by simple keyword
rules into `guidance_type` and `direction`. Confidence capped at `medium`/`low`,
never `high` — a crude regex has no business claiming the confidence a real LLM
read would.

**Tested by adding a second real transcript** (Wipro Q3 FY24, downloaded from
Wipro's own investor-relations site) and confirming the two transcripts produce
genuinely different, document-specific results (4 items vs. 8), not copies of
each other.

**What that test then revealed, honestly:** Q3FY24's real guidance sentence
("sequential guidance of minus 1.5% to a plus...") doesn't contain the literal
words "revenue" or "growth", so the keyword classifier tagged it `qualitative`
instead of `revenue` — meaning it's excluded from `guidance_vs_actuals.sql`,
which filters to `guidance_type = 'revenue'`. Also found a clean false-positive
example: an analyst's question ("I just wanted your thoughts on that
vertical...") got matched by the regex and mis-tagged as revenue guidance.

**Decision: did not tune the regex to fix either case.** Doing so would be
curve-fitting the extractor to look good on the two specific transcripts I
happen to have, which defeats the actual point. Both are exactly the kind of
error the human-labelling step (`make_labelling_template.py` →
`score_validation.py`) exists to catch — leaving them in place, visible in the
raw output, is more honest than quietly patching them out. This is also a good,
concrete answer to "where does mock mode actually fail" if asked in an
interview: keyword classification of `guidance_type` is measurably unreliable
even on 2 real documents, which real LLM extraction (semantic understanding
rather than keyword matching) should meaningfully improve on — a testable claim
once a key is added, not just an assumption.

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
