"""
Extract clean text from every transcript PDF in data/raw/ into data/extracted/.

Verified against a real transcript (Wipro Q3 FY26) before building this: 15
pages, ~36k chars, guidance language present and extracts cleanly, e.g.
"we are projecting sequential IT Services revenue growth of 0% to 2.0%".

One real artifact found and handled: pdfplumber renders the source PDF's
bullet/dash glyph as U+FFFD (the same replacement-character issue as the
LaTeX resume bullets) — cleaned up below rather than left in the output that
gets fed to the LLM.

Usage: py -3.10 scripts/extract_text.py
"""
import re
from pathlib import Path

import pdfplumber

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
OUT_DIR = Path(__file__).parent.parent / "data" / "extracted"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(text: str) -> str:
    text = text.replace("�", "-")  # garbled bullet/dash glyph -> plain hyphen
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    return clean_text("\n".join(pages))


def main():
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {RAW_DIR}. Download transcripts there first.")
        return

    print(f"Extracting {len(pdfs)} transcript(s)...\n")
    for pdf_path in pdfs:
        text = extract_pdf(pdf_path)
        out_path = OUT_DIR / f"{pdf_path.stem}.txt"
        out_path.write_text(text, encoding="utf-8")
        print(f"  {pdf_path.name}: {len(text)} chars -> {out_path.name}")


if __name__ == "__main__":
    main()
