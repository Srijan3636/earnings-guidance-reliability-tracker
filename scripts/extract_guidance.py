"""
Extract structured guidance statements from transcript text using Claude.

Every response is validated against the schema before being accepted — a
malformed or non-JSON response is logged and skipped, not silently coerced.

MOCK MODE: run with --mock to use rule-based regex extraction instead of
calling the API — genuinely derived from each transcript's real text (not
hardcoded), just cruder than an LLM's semantic understanding. This lets the
full pipeline (extraction -> validation -> loading -> analysis) be built,
tested, and pushed before an Anthropic API key exists.

Usage:
  py -3.10 scripts/extract_guidance.py --mock        (no API key needed)
  py -3.10 scripts/extract_guidance.py                (real extraction, needs ANTHROPIC_API_KEY)
"""
import argparse
import json
import os
import re
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

# Rule-based sentence patterns for --mock mode. NOTE ON HONESTY: an earlier
# version of this function ignored its transcript_text argument entirely and
# always returned the same hardcoded Wipro quote — harmless with exactly one
# transcript, but it would have fabricated identical "guidance" for every
# company the moment a second transcript was added. Fixed to actually derive
# results from each transcript's real text via regex, so every extraction is
# a genuine sentence from that specific document. Still clearly weaker than
# real LLM extraction (no semantic understanding, will miss guidance phrased
# unusually and can false-positive on lookalike sentences) — that gap is the
# honest reason --mock and real extraction are reported separately
# (extracted_by = 'mock' vs 'llm'), never blended into one accuracy number.
GUIDANCE_SENTENCE_PATTERN = re.compile(
    r"([^.]*?\b(?:guidance|projecting|expect(?:ing)?|outlook|target(?:ing)?)\b"
    r"[^.]*?\d+(?:\.\d+)?\s*%[^.]*\.)",
    re.IGNORECASE,
)
QUALITATIVE_SENTENCE_PATTERN = re.compile(
    r"([^.]*?\b(?:for (?:the )?(?:next|coming) quarter|going forward|we (?:will|plan to) continue)\b[^.]*\.)",
    re.IGNORECASE,
)


def classify_guidance_type(sentence: str) -> str:
    s = sentence.lower()
    if "margin" in s:
        return "margin"
    if "headcount" in s or "hiring" in s or "attrition" in s:
        return "headcount"
    if "capex" in s or "capital expenditure" in s:
        return "capex"
    if "revenue" in s or "growth" in s:
        return "revenue"
    return "qualitative"


def classify_direction(sentence: str) -> str:
    s = sentence.lower()
    if " to " in s and re.search(r"\d+(?:\.\d+)?\s*%.*\bto\b.*\d+(?:\.\d+)?\s*%", s):
        return "range"
    if any(w in s for w in ["decline", "lower", "down", "reduce"]):
        return "down"
    if any(w in s for w in ["grow", "increase", "higher", "up", "improve"]):
        return "up"
    return "unclear"


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
    results = []
    seen = set()

    for pattern in (GUIDANCE_SENTENCE_PATTERN, QUALITATIVE_SENTENCE_PATTERN):
        for m in pattern.finditer(transcript_text):
            sentence = m.group(1).strip()
            if sentence in seen or len(sentence) < 15:
                continue
            seen.add(sentence)

            pct_match = re.search(r"\d+(?:\.\d+)?\s*%(?:\s*(?:to|-)\s*\d+(?:\.\d+)?\s*%)?", sentence)
            stated_value = pct_match.group(0) if pct_match else sentence[:60]

            results.append({
                "guidance_type": classify_guidance_type(sentence),
                "stated_value": stated_value,
                "direction": classify_direction(sentence),
                # rule-based matching is much cruder than semantic
                # understanding, so confidence is capped at "medium" —
                # never claims "high" the way a real LLM read might
                "confidence": "medium" if pct_match else "low",
                "source_excerpt": sentence,
            })

    return results


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
