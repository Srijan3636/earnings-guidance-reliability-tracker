# Earnings Guidance Reliability Tracker

AI-assisted pipeline that extracts structured management guidance from
earnings call transcripts, validates extraction accuracy against hand-labelled
data, and joins guidance to what actually got reported.

**Status: prototype, working end-to-end on 1 real transcript.** This is
explicitly a proof of concept, not a production tool — see Limitations.

## Why this project exists

Management guidance — revenue targets, margin targets, capex plans — only
exists in earnings call transcripts as unstructured text. There's no easy way
to check, months later, whether a management team delivered on what they said.
Investors end up relying on institutional memory ("this management tends to
overpromise") rather than data. This project turns guidance into structured,
queryable data and checks it against reported results — the same shape of
problem as diligence work: turning unstructured source documents into
structured, comparable data points, and being honest about how reliable the
extraction actually is.

## Reproduce it yourself

```bash
py -3.10 -m pip install -r requirements.txt
cp .env.example .env   # fill in your Postgres password; ANTHROPIC_API_KEY
                        # can stay as the placeholder — --mock mode needs no key
py -3.10 scripts/extract_text.py           # PDF -> clean text
py -3.10 scripts/extract_guidance.py --mock   # or omit --mock with a real key
py -3.10 scripts/fetch_financials.py       # pulls reported actuals via yfinance
py -3.10 scripts/load_data.py
py -3.10 scripts/export_data.py
```

To validate extraction accuracy:
```bash
py -3.10 scripts/make_labelling_template.py
# open data/labelling_template.csv, fill in human_is_correct_extraction (yes/no)
py -3.10 scripts/score_validation.py
```

## What's actually been verified, not just written

- Downloaded and extracted a **real** transcript (Wipro, Q3 FY26, from
  Wipro's own investor-relations site) before writing any extraction code —
  confirmed real guidance language extracts cleanly: *"we are projecting
  sequential IT Services revenue growth of 0% to 2.0% in constant currency"*
- Schema-validation logic tested directly against both valid and invalid
  extraction items — the reject path is proven, not just the happy path
- `guidance_vs_actuals.sql` correctly finds **2026-03-31** (the real quarter
  Wipro's guidance was about) as the next reported period after the January
  16, 2026 call — this required fixing a real bug found on first run (see
  DECISIONS.md)
- One real result: Wipro guided 0-2% sequential revenue growth for that
  quarter; the actual reported figure was **2.89%** — slightly above their
  own guided range

## Scope boundary, stated plainly

`stated_value` is stored as free text exactly as management said it (e.g.
"0% to 2.0% sequential growth in constant currency"), not parsed into a
clean number. `guidance_vs_actuals.sql` shows guidance and actuals side by
side for a human to judge — it does not auto-score a pass/fail delta.
Building a real parser for guidance ranges (handling qualifiers like
"constant currency," "high single digits," YoY vs QoQ framing) is a genuinely
hard NLP problem on its own, and faking a clean numeric comparison here would
overstate what this project does.

## Limitations

- **1 real transcript loaded.** Enough to prove the pipeline works end-to-end
  on real data; not enough for a meaningful accuracy sample. More transcripts
  need adding before the validation numbers mean anything statistically
- **Real LLM extraction is untested** — I don't have an Anthropic API key yet.
  Everything downstream of extraction (validation, loading, the join query)
  has been tested using `--mock` mode, so the pipeline plumbing is proven even
  though the actual model call isn't yet
- **No automated guidance-vs-actual scoring** — by design, see above
- This is a prototype proving out a workflow, not a tool any fund is using —
  said outright rather than implied otherwise

## Project structure

```
scripts/           extract_text.py, extract_guidance.py, fetch_financials.py,
                    load_data.py, export_data.py, make_labelling_template.py,
                    score_validation.py
sql/schema.sql      database DDL
sql/analysis/       guidance_vs_actuals.sql
exports/            Power BI-ready CSVs
dashboard/          Power BI file (build it yourself — see DASHBOARD.md)
DECISIONS.md        every non-obvious choice and why, including 2 real bugs found
QUESTIONS.md        interview questions with honest answers
```
