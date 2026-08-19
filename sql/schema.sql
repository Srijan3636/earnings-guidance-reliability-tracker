-- Earnings Guidance Reliability Tracker — schema

DROP TABLE IF EXISTS guidance CASCADE;
DROP TABLE IF EXISTS reported_financials CASCADE;
DROP TABLE IF EXISTS companies CASCADE;
DROP TABLE IF EXISTS transcripts CASCADE;

CREATE TABLE companies (
    company_id  SERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL
);

CREATE TABLE transcripts (
    transcript_id   SERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(company_id),
    quarter_label   TEXT NOT NULL,          -- e.g. 'Q3FY26'
    call_date       DATE,                   -- extracted from the transcript's own
                                             -- header text (see load_data.py) — needed
                                             -- so guidance_vs_actuals.sql can correctly
                                             -- find the NEXT reported period after the
                                             -- call, not just the earliest one on file
    source_file     TEXT NOT NULL,
    extracted_chars INT
);

-- One row per extracted guidance statement. A single transcript can (and
-- usually does) yield multiple rows: revenue guidance, margin guidance,
-- headcount commentary, etc. are separate statements, not one blob.
CREATE TABLE guidance (
    guidance_id     SERIAL PRIMARY KEY,
    transcript_id   INT NOT NULL REFERENCES transcripts(transcript_id),
    company_id      INT NOT NULL REFERENCES companies(company_id),
    guidance_type   TEXT NOT NULL CHECK (guidance_type IN
                        ('revenue', 'margin', 'headcount', 'capex', 'qualitative')),
    stated_value    TEXT,           -- e.g. "0% to 2.0%" — kept as text, ranges/qualifiers vary
    direction       TEXT CHECK (direction IN ('up', 'down', 'flat', 'range', 'unclear')),
    confidence      TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    source_excerpt  TEXT NOT NULL,   -- the actual quote the extraction was based on
    extracted_by    TEXT NOT NULL DEFAULT 'llm',  -- 'llm' or 'mock', for auditability
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Self-contained: this project builds its own financials table from yfinance
-- rather than depending on the financial-investment-analytics repo's
-- database, so this repo runs standalone from a fresh clone.
CREATE TABLE reported_financials (
    company_id   INT NOT NULL REFERENCES companies(company_id),
    period_end   DATE NOT NULL,
    metric_name  TEXT NOT NULL,
    value        NUMERIC NOT NULL,
    PRIMARY KEY (company_id, period_end, metric_name)
);

CREATE INDEX idx_guidance_company ON guidance(company_id);
CREATE INDEX idx_guidance_type ON guidance(guidance_type);
CREATE INDEX idx_reported_company ON reported_financials(company_id);
