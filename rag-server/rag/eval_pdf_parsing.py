from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rag.pdf_parser import parse_pdf_to_page_items


def build_summary(page_items, parser_name: str):
    text_lengths = [len(item.get("text", "")) for item in page_items]

    ocr_used_pages = 0
    ocr_text_lengths = []

    for item in page_items:
        meta = item.get("metadata", {}) or {}
        if meta.get("ocr_used"):
            ocr_used_pages += 1
            ocr_text_lengths.append(int(meta.get("ocr_text_len", 0) or 0))

    return {
        "parser": parser_name,
        "pages": len(page_items),
        "non_empty_pages": sum(1 for length in text_lengths if length > 0),
        "avg_text_length": round(sum(text_lengths) / len(text_lengths), 2)
        if text_lengths
        else 0,
        "max_text_length": max(text_lengths) if text_lengths else 0,
        "min_text_length": min(text_lengths) if text_lengths else 0,

        # OCR 비교용
        "ocr_used_pages": ocr_used_pages,
        "avg_ocr_text_length": round(sum(ocr_text_lengths) / len(ocr_text_lengths), 2)
        if ocr_text_lengths
        else 0,
    }



def preview_page_items(page_items, sample_pages: int = 3, preview_chars: int = 400):
    previews = []

    for item in page_items[:sample_pages]:
        previews.append(
            {
                "page": item.get("page"),
                "preview": item.get("text", "")[:preview_chars],
                "metadata": item.get("metadata", {}),
            }
        )

    return previews


def evaluate_pdf_parsing(file_path: str, parser_names):
    pdf_path = Path(file_path)
    file_bytes = pdf_path.read_bytes()

    results = []

    for parser_name in parser_names:

        print(f"[start] parser={parser_name}", file=sys.stderr, flush=True)

        page_items = parse_pdf_to_page_items(file_bytes, parser_name=parser_name)
        results.append(
            {
                "summary": build_summary(page_items, parser_name),
                "samples": preview_page_items(page_items),
            }
        )

        print(f"[done] parser={parser_name}, pages={len(page_items)}", file=sys.stderr, flush=True)

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path")
    parser.add_argument(
        "--parsers",
        nargs="+",
        default=[
            "fitz",
            "pdfplumber",
            "unstructured",
            "fitz_pytesseract",
            "fitz_easyocr",
            "fitz_rapidocr",
        ],
    )
    args = parser.parse_args()

    results = evaluate_pdf_parsing(args.file_path, args.parsers)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
