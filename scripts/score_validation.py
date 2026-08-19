"""
Score extraction accuracy against the hand-labelled CSV, broken down by
guidance_type. A single headline "accuracy: X%" is deliberately not the
primary output — different guidance types are genuinely different
difficulty, and averaging hides that.

Usage: py -3.10 scripts/score_validation.py
Requires data/labelling_template.csv with human_is_correct_extraction filled in.
"""
from pathlib import Path

import pandas as pd

LABEL_PATH = Path(__file__).parent.parent / "data" / "labelling_template.csv"
EXPORT_PATH = Path(__file__).parent.parent / "exports" / "validation_accuracy_by_type.csv"


def main():
    if not LABEL_PATH.exists():
        print(f"{LABEL_PATH} not found. Run make_labelling_template.py first.")
        return

    df = pd.read_csv(LABEL_PATH)
    df["human_is_correct_extraction"] = df["human_is_correct_extraction"].astype(str).str.strip().str.lower()

    labelled = df[df["human_is_correct_extraction"].isin(["yes", "no"])]
    unlabelled = len(df) - len(labelled)

    if len(labelled) == 0:
        print("No rows have been labelled yet (human_is_correct_extraction is empty).")
        print(f"Open {LABEL_PATH}, read source_excerpt for each row, and fill in yes/no.")
        return

    if unlabelled:
        print(f"NOTE: {unlabelled} row(s) not yet labelled — excluded from this report.\n")

    labelled = labelled.copy()
    labelled["correct"] = labelled["human_is_correct_extraction"] == "yes"

    print("=== Accuracy by guidance_type ===")
    by_type = labelled.groupby("extracted_guidance_type")["correct"].agg(["sum", "count"])
    by_type["accuracy_pct"] = (100 * by_type["sum"] / by_type["count"]).round(1)
    by_type = by_type.rename(columns={"sum": "correct", "count": "total"})
    print(by_type.to_string())

    EXPORT_PATH.parent.mkdir(exist_ok=True)
    by_type.reset_index().rename(
        columns={"extracted_guidance_type": "guidance_type"}
    ).to_csv(EXPORT_PATH, index=False)
    print(f"\nExported for Power BI -> {EXPORT_PATH}")

    overall = labelled["correct"].mean() * 100
    print(f"\nOverall (n={len(labelled)}): {overall:.1f}% — shown for reference only, ")
    print("see per-type breakdown above for the real picture.")

    incorrect = labelled[~labelled["correct"]]
    if len(incorrect):
        print(f"\n=== {len(incorrect)} incorrect extraction(s) — for the Limitations section ===")
        for _, row in incorrect.iterrows():
            print(f"  [{row['extracted_guidance_type']}] {row['source_file']} #{row['item_index']}: "
                  f"{row['human_notes'] or '(no notes)'}")


if __name__ == "__main__":
    main()
