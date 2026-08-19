"""
Extract structured guidance statements from transcript text using Claude.

Every response is validated against the schema before being accepted — a
malformed or non-JSON response is logged and skipped, not silently coerced.

MOCK MODE: run with --mock to use canned extraction results instead of
calling the API. This lets the full pipeline (extraction -> validation ->
loading -> analysis) be built, tested, and pushed before an Anthropic API
key exists. Real numbers only ever come from --mock or a real API call —
never hardcoded as if they were real.

Usage:
  py -3.10 scripts/extract_guidance.py --mock        (no API key needed)
  py -3.10 scripts/extract_guidance.py                (real extraction, needs ANTHROPIC_API_KEY)
"""
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

EXTRACTED_DIR = Path(__file__).parent.parent / "data" / "extracted"
OUT_DIR = Path(__file__).parent.parent / "data" / "guidance"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VALID_TYPES = {"revenue", "margin", "headcount", "capex", "qualitative"}
VALID_DIRECTIONS = {"up", "down", "flat", "range", "unclear"}
VALID_CONFIDENCE = {"high", "medium", "low"}

EXTRACTION_PROMPT = """You are extracting forward-looking management guidance from an
earnings call transcript. Find every statement where management gives guidance,
outlook, or a forward projection — about revenue, margins, headcount, capex, or
general qualitative outlook.

Return ONLY a JSON array, no other text. Each element:
{
  "guidance_type": "revenue" | "margin" | "headcount" | "capex" | "qualitative",
  "stated_value": "the specific figure or range as stated, e.g. '0% to 2.0%'",
  "direction": "up" | "down" | "flat" | "range" | "unclear",
  "confidence": "high" | "medium" | "low"  (your confidence this IS forward guidance,
                 not a description of past results),
  "source_excerpt": "the exact quote from the transcript this was extracted from"
}

If there is no guidance in the transcript, return [].

TRANSCRIPT:
{transcript_text}
"""

# Canned results for --mock mode, modeled on the real guidance statement
# actually found in the Wipro Q3 FY26 transcript during development ("we are
# projecting sequential IT Services revenue growth of 0% to 2.0% in constant
# currency") — not invented from nothing, but not a live API call either.
MOCK_RESULTS = [
    {
        "guidance_type": "revenue",
        "stated_value": "0% to 2.0% sequential growth (constant currency)",
        "direction": "range",
        "confidence": "high",
        "source_excerpt": "we are projecting sequential IT Services revenue growth of 0% to 2.0% in constant currency",
    },
    {
        "guidance_type": "qualitative",
        "stated_value": "continued focus on large deal wins and AI-led transformation",
        "direction": "unclear",
        "confidence": "medium",
        "source_excerpt": "[MOCK] placeholder qualitative guidance excerpt",
    },
]


def validate_item(item: dict) -> tuple[bool, str]:
    required = {"guidance_type", "stated_value", "direction", "confidence", "source_excerpt"}
    missing = required - item.keys()
    if missing:
        return False, f"missing fields: {missing}"
    if item["guidance_type"] not in VALID_TYPES:
        return False, f"invalid guidance_type: {item['guidance_type']}"
    if item["direction"] not in VALID_DIRECTIONS:
        return False, f"invalid direction: {item['direction']}"
    if item["confidence"] not in VALID_CONFIDENCE:
        return False, f"invalid confidence: {item['confidence']}"
    return True, ""


def extract_mock(transcript_text: str) -> list[dict]:
    return MOCK_RESULTS


def extract_real(transcript_text: str) -> list[dict]:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or api_key.startswith("sk-ant-YOUR"):
        raise SystemExit(
            "ANTHROPIC_API_KEY not set (or still the placeholder) in .env.\n"
            "Run with --mock instead, or add a real key to .env."
        )

    client = anthropic.Anthropic(api_key=api_key)
    prompt = EXTRACTION_PROMPT.format(transcript_text=transcript_text[:15000])

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # model sometimes wraps JSON in markdown fences despite instructions
        if raw.startswith("```"):
            raw = raw.strip("`").removeprefix("json").strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        print(f"  WARNING: could not parse response as JSON, skipping. Raw: {raw[:200]}")
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="use canned results, no API call")
    args = parser.parse_args()

    txt_files = sorted(EXTRACTED_DIR.glob("*.txt"))
    if not txt_files:
        print(f"No extracted transcripts in {EXTRACTED_DIR}. Run extract_text.py first.")
        return

    extractor = extract_mock if args.mock else extract_real
    mode_label = "MOCK" if args.mock else "REAL (calling Anthropic API)"
    print(f"Mode: {mode_label}\n")

    for txt_path in txt_files:
        text = txt_path.read_text(encoding="utf-8")
        print(f"Extracting from {txt_path.name} ({len(text)} chars)...")

        raw_items = extractor(text)

        valid_items = []
        for item in raw_items:
            ok, reason = validate_item(item)
            if ok:
                valid_items.append(item)
            else:
                print(f"  REJECTED (schema validation failed: {reason}): {item}")

        for item in valid_items:
            item["extracted_by"] = "mock" if args.mock else "llm"
            item["source_file"] = txt_path.name

        out_path = OUT_DIR / f"{txt_path.stem}.json"
        out_path.write_text(json.dumps(valid_items, indent=2))
        print(f"  {len(valid_items)}/{len(raw_items)} items passed validation -> {out_path.name}\n")


if __name__ == "__main__":
    main()
