#!/usr/bin/env python3
"""
PDF Splicer — splice pages from document B into document A at custom positions.

Usage:
    python pdf_splicer.py                          # fully interactive
    python pdf_splicer.py A.pdf B.pdf out.pdf      # prompts for the page map only
    python pdf_splicer.py A.pdf B.pdf out.pdf --map "3:1,2;7:5"  # fully non-interactive

Page-map syntax (--map / interactive):
    "A_page:B_pages"  pairs separated by  ;
    B_pages is a comma-separated list or range (e.g. 1,2  or  2-5  or  1,3-5)
    A_page = 0  →  insert B pages BEFORE the first page of A
    A_page = N  →  insert B pages AFTER page N of A (original numbering, 1-based)

Example:
    --map "0:1;3:2,3;10:4-6"
    Insert B p.1 before A p.1, B pp.2-3 after A p.3, B pp.4-6 after A p.10.
"""

import argparse
import sys
from pypdf import PdfReader, PdfWriter


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def parse_b_pages(spec: str) -> list[int]:
    """Parse a page spec like '1,3-5,7' into a sorted list of 1-based ints."""
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


def parse_map_string(map_str: str) -> dict[int, list[int]]:
    """
    Parse a map string like '0:1;3:2,3;10:4-6' into
    {0: [1], 3: [2, 3], 10: [4, 5, 6]}.
    """
    page_map: dict[int, list[int]] = {}
    for entry in map_str.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        a_str, b_str = entry.split(":", 1)
        a_page = int(a_str.strip())
        b_pages = parse_b_pages(b_str.strip())
        page_map.setdefault(a_page, []).extend(b_pages)
    return page_map


def build_page_map_interactive(total_a: int, total_b: int) -> dict[int, list[int]]:
    """
    Prompt the user to build the page map interactively.
    Returns a dict {a_page_num: [b_page_nums]}.
    """
    print(f"\nDocument A has {total_a} pages.")
    print(f"Document B has {total_b} pages.")
    print(
        "\nEnter insertion rules one at a time."
        "\n  Format:  <A-page> : <B-pages>"
        "\n  A-page   = 0 to insert BEFORE A page 1, or 1–{ta} to insert AFTER that page."
        "\n  B-pages  = comma list or range, e.g.  1,3   or   2-5   or   1,3-5"
        "\n  Press Enter with no input when done.\n".format(ta=total_a)
    )

    page_map: dict[int, list[int]] = {}
    while True:
        raw = input("  Rule (or Enter to finish): ").strip()
        if not raw:
            break
        try:
            a_str, b_str = raw.split(":", 1)
            a_page = int(a_str.strip())
            b_pages = parse_b_pages(b_str.strip())

            if not (0 <= a_page <= total_a):
                print(f"  ! A-page must be 0–{total_a}. Try again.")
                continue
            invalid = [p for p in b_pages if not (1 <= p <= total_b)]
            if invalid:
                print(f"  ! B pages out of range (1–{total_b}): {invalid}. Try again.")
                continue

            page_map.setdefault(a_page, []).extend(b_pages)
            print(f"  + After A p.{a_page if a_page else '(start)'}: insert B {b_pages}")
        except (ValueError, TypeError):
            print("  ! Invalid format. Use  <number> : <pages>  e.g.   3 : 1,2")

    return page_map


def splice_and_merge(
    input_pdf_a: str,
    input_pdf_b: str,
    output_name: str,
    page_map: dict[int, list[int]],
    verbose: bool = True,
) -> None:
    """
    Splice pages from B into A according to page_map and write to output_name.

    page_map keys are A's original 1-based page numbers (0 = before page 1).
    page_map values are lists of 1-based B page numbers to insert at that position.
    """
    reader_a = PdfReader(input_pdf_a)
    reader_b = PdfReader(input_pdf_b)
    writer = PdfWriter()

    total_a = len(reader_a.pages)
    total_b = len(reader_b.pages)

    def insert_b_pages(after_label: str, b_page_list: list[int]) -> None:
        for bp in b_page_list:
            if 1 <= bp <= total_b:
                writer.add_page(reader_b.pages[bp - 1])
                if verbose:
                    print(f"    inserted B p.{bp} {after_label}")
            else:
                print(f"  WARNING: B page {bp} out of range (1–{total_b}), skipped.")

    # Pages to insert before A page 1 (key = 0)
    if 0 in page_map:
        if verbose:
            print("Before A p.1:")
        insert_b_pages("(before A p.1)", page_map[0])

    for a_idx in range(total_a):
        a_page_num = a_idx + 1  # 1-based
        writer.add_page(reader_a.pages[a_idx])
        if verbose:
            print(f"  A p.{a_page_num}")

        if a_page_num in page_map:
            insert_b_pages(f"(after A p.{a_page_num})", page_map[a_page_num])

    with open(output_name, "wb") as fh:
        writer.write(fh)

    if verbose:
        print(f"\nOutput: {output_name}  ({len(writer.pages)} pages total)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Splice pages from PDF B into PDF A at custom positions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pdf_a", nargs="?", help="Base PDF document (A)")
    parser.add_argument("pdf_b", nargs="?", help="PDF to splice in (B)")
    parser.add_argument("output", nargs="?", help="Output PDF path")
    parser.add_argument(
        "--map",
        metavar="MAP_STRING",
        help='Page map, e.g. "0:1;3:2,3;10:4-6"',
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress page-by-page output")
    args = parser.parse_args()

    # Collect paths interactively if not provided
    pdf_a = args.pdf_a or input("Path to document A (base PDF): ").strip()
    pdf_b = args.pdf_b or input("Path to document B (pages to splice in): ").strip()
    output = args.output or input("Output file name [output.pdf]: ").strip() or "output.pdf"

    # Peek at page counts for interactive mapper
    try:
        total_a = len(PdfReader(pdf_a).pages)
        total_b = len(PdfReader(pdf_b).pages)
    except FileNotFoundError as exc:
        sys.exit(f"Error: {exc}")

    if args.map:
        page_map = parse_map_string(args.map)
    else:
        page_map = build_page_map_interactive(total_a, total_b)

    if not page_map:
        print("No insertion rules defined — output will be a plain copy of A.")

    splice_and_merge(pdf_a, pdf_b, output, page_map, verbose=not args.quiet)


if __name__ == "__main__":
    main()
