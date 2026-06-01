#!/usr/bin/env python3
"""
Convert one or more PDF files to Markdown using pdfminer.six.
Output is placed in the same directory as each input PDF,
with the same base filename and a .md extension.

Usage:
    python pdf2md.py <file1.pdf> [file2.pdf ...]
"""

import sys
from pathlib import Path

from pdfminer.high_level import extract_text


def convert(pdf_path: Path) -> None:
    md_path = pdf_path.with_suffix(".md")
    print(f"Converting: {pdf_path}")
    text = extract_text(str(pdf_path))
    # Wrap extracted text in a minimal Markdown structure
    md_path.write_text(text, encoding="utf-8")
    print(f"  -> Saved:  {md_path}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python pdf2md.py <file1.pdf> [file2.pdf ...]")
        sys.exit(1)

    errors = []
    for arg in sys.argv[1:]:
        path = Path(arg).expanduser().resolve()
        if not path.exists():
            print(f"  [SKIP] File not found: {path}")
            errors.append(arg)
            continue
        if path.suffix.lower() != ".pdf":
            print(f"  [SKIP] Not a PDF: {path}")
            errors.append(arg)
            continue
        try:
            convert(path)
        except Exception as exc:
            print(f"  [ERROR] {path}: {exc}")
            errors.append(arg)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
