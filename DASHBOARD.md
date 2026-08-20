# Power BI Dashboard — Build Guide

**Status note:** this project currently has 2 real transcripts loaded (Wipro
Q3 FY26 and Q3 FY24) — enough to prove the pipeline generalises, not yet
enough for a statistically meaningful dashboard. This guide is written to
work as-is with more transcripts added later; nothing below needs to change
as the data grows.

## 1. Connect

**Get Data** → **Text/CSV** → import from `exports/`:
`guidance_raw.csv`, `guidance_vs_actuals.csv`, and
`validation_accuracy_by_type.csv` **once you've labelled some items** (run
`py -3.10 scripts/make_labelling_template.py`, fill in `human_is_correct_extraction`
for each row in `data/labelling_template.csv`, then
`py -3.10 scripts/score_validation.py` — that writes the CSV this needs).

## 2. Relationships

`guidance_raw` and `guidance_vs_actuals` both key on `ticker` — relate them if
you want cross-filtering, though each is usable standalone as a flat table.

## 3. DAX measures

On `guidance_raw`:
```dax
Total Guidance Statements = COUNTROWS(guidance_raw)

High Confidence Statements =
CALCULATE(COUNTROWS(guidance_raw), guidance_raw[confidence] = "high")

Real vs Mock Extractions =
CALCULATE(COUNTROWS(guidance_raw), guidance_raw[extracted_by] = "llm")
```

On `validation_accuracy_by_type` (once it exists):
```dax
Overall Accuracy % = AVERAGE(validation_accuracy_by_type[accuracy_pct])
```

## 4. Pages

**Page 1 — Extraction Overview**
- Cards: `Total Guidance Statements`, `High Confidence Statements`
- Bar chart: `guidance_raw[guidance_type]` on axis, count of rows on values —
  shows what kind of guidance gets extracted most often
- Table: `guidance_raw[ticker]`, `quarter_label`, `guidance_type`,
  `stated_value`, `confidence`

**Page 2 — Accuracy by Type** (needs labelled data — see step 1)
- Bar chart: `validation_accuracy_by_type[guidance_type]` on axis,
  `accuracy_pct` on values — this is the chart that matters most; a single
  blended accuracy number hides exactly the finding worth having (see
  DECISIONS.md on why per-type breakdown is the real output, not an overall %)
- Card: `Overall Accuracy %`

**Page 3 — Guidance vs Actuals**
- Table directly on `guidance_vs_actuals`: `ticker`, `guidance_given_in_quarter`,
  `guidance_stated_value`, `next_reported_period`, `actual_revenue_qoq_growth_pct`
- This table is small (currently 1 row) but grows automatically as more
  transcripts are processed — re-run `export_data.py` after adding data and
  refresh the Power BI file

## 5. Formatting

Same conventions as the other two projects: non-default theme, percentage
formatting on `_pct` fields.

## 6. Save and screenshot

Save as `.pbix` in `dashboard/` (gitignored). Screenshot into
`dashboard/screenshots/` for the README — and re-screenshot once you've added
more transcripts, since the current state is intentionally thin.
