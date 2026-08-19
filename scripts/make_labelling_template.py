"""
Generate a CSV for manual labelling: one row per extracted guidance item,
with empty columns for a human to fill in the "true" values. Comparing
these to the extraction output is how extraction accuracy actually gets
measured (see sql/analysis/validation_accuracy.sql).

Usage: py -3.10 scripts/make_labelling_template.py
"""
import json
from pathlib import Path

import pandas as pd

GUIDANCE_DIR = Path(__file__).parent.parent / "data" / "guidance"
OUT_PATH = Path(__file__).parent.parent / "data" / "labelling_template.csv"


def main():
    rows = []
    for gf in sorted(GUIDANCE_DIR.glob("*.json")):
        items = json.loads(gf.read_text())
        for i, item in enumerate(items):
            rows.append({
                "source_file": gf.stem,
                "item_index": i,
                "extracted_guidance_type": item.get("guidance_type"),
                "extracted_stated_value": item.get("stated_value"),
                "extracted_direction": item.get("direction"),
                "source_excerpt": item.get("source_excerpt"),
                # empty — fill these in by hand while reading source_excerpt
                "human_is_correct_extraction": "",   # yes / no
                "human_correct_guidance_type": "",   # only if 'no' above
                "human_correct_stated_value": "",    # only if 'no' above
                "human_notes": "",
            })

    if not rows:
        print(f"No guidance JSON files in {GUIDANCE_DIR}. Run extract_guidance.py first.")
        return

    df = pd.DataFrame(rows)
    df.to_csv(OUT_PATH, index=False)
    print(f"{len(df)} items -> {OUT_PATH}")
    print("\nFill in human_is_correct_extraction (yes/no) for each row by reading")
    print("source_excerpt against what was extracted, then run the validation query.")


if __name__ == "__main__":
    main()
