
import argparse
import json
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader


# ============================================================
# 1. CONFIGURATION
# ============================================================

PROJECT_DIR = Path(
    r"D:\Work\VinAI\Lab05\K5-L3A-Day06-TranNguyenAnhPhong-2A202603629-DataIngestionEngineering"
)

PDF_PATH = PROJECT_DIR / "data" / "calculus_volume_1_openstax.pdf"
OUTPUT_PATH = PROJECT_DIR / "data" / "manifest.json"

SOURCE_ID = "openstax_calculus_v1"
TITLE = "Calculus Volume 1"

MIN_USEFUL_PAGES = 30
MIN_CHARS_PER_PAGE = 100


# ============================================================
# 2. HELPER FUNCTIONS
# ============================================================

def normalize_text(text: str) -> str:
    """Normalize extracted PDF text."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_page_list(value: str) -> set[int]:
    """
    Parse page numbers.

    Example:
        51,52,60-63
    """
    result = set()

    if not value.strip():
        return result

    for item in value.split(","):
        item = item.strip()

        if "-" in item:
            start, end = map(int, item.split("-", 1))

            if start > end:
                raise ValueError(
                    f"Invalid page range: {item}"
                )

            result.update(range(start, end + 1))
        else:
            result.add(int(item))

    return result


def validate_pdf_path() -> Path:
    """Check whether the configured PDF exists."""
    if not PDF_PATH.is_file():
        raise FileNotFoundError(
            f"PDF file not found:\n{PDF_PATH}\n"
            "Check the PDF filename and location."
        )

    return PDF_PATH


# ============================================================
# 3. CREATE MANIFEST
# ============================================================

def create_manifest(
    start_page: int,
    end_page: int,
    excluded_pages: set[int],
    reviewed: bool,
    source_url: str,
    license_name: str,
    version: str | None = None,
):
    pdf_path = validate_pdf_path()

    print("\nLoading PDF...")
    print(f"PDF path: {pdf_path}")

    reader = PdfReader(str(pdf_path))
    total_pdf_pages = len(reader.pages)

    if not (1 <= start_page <= end_page <= total_pdf_pages):
        raise ValueError(
            f"Invalid page range {start_page}-{end_page}. "
            f"PDF has {total_pdf_pages} pages."
        )

    selected_pages = list(
        range(start_page, end_page + 1)
    )

    invalid_exclusions = excluded_pages - set(selected_pages)

    if invalid_exclusions:
        raise ValueError(
            "Excluded pages outside selected range: "
            f"{sorted(invalid_exclusions)}"
        )

    page_details = []
    counted_pages = []
    excluded_details = []
    review_required = []

    total_characters = 0

    # --------------------------------------------------------
    # Process each selected physical PDF page
    # --------------------------------------------------------

    for physical_page in selected_pages:

        page_index = physical_page - 1
        extraction_error = None

        try:
            raw_text = (
                reader.pages[page_index].extract_text() or ""
            )

        except Exception as exc:
            raw_text = ""
            extraction_error = str(exc)

        normalized_text = normalize_text(raw_text)

        character_count = len(normalized_text)

        review_flags = []

        if extraction_error:
            review_flags.append("extraction_error")

        if character_count == 0:
            review_flags.append("empty_or_scanned_page")

        elif character_count < MIN_CHARS_PER_PAGE:
            review_flags.append("very_short_text")

        # Possible references-only page
        if re.search(
            r"\b(bibliography|references)\b",
            normalized_text[:300],
            flags=re.IGNORECASE
        ):
            review_flags.append("possible_references_page")

        manually_excluded = physical_page in excluded_pages

        eligible = (
            not manually_excluded
            and extraction_error is None
            and character_count >= MIN_CHARS_PER_PAGE
        )

        counted = eligible and reviewed

        if counted:
            counted_pages.append(physical_page)
            total_characters += character_count

        if review_flags and not manually_excluded:
            review_required.append(physical_page)

        if manually_excluded:
            excluded_details.append({
                "page": physical_page,
                "reason": "manually_excluded"
            })

        page_details.append({
            "page_id": (
                f"{SOURCE_ID}_p{physical_page:04d}"
            ),
            "physical_page_number": physical_page,
            "character_count": character_count,
            "has_text": bool(normalized_text),
            "extraction_error": extraction_error,
            "review_flags": review_flags,
            "manually_excluded": manually_excluded,
            "counted": counted
        })

    # --------------------------------------------------------
    # Store relative file path
    # --------------------------------------------------------

    source_path = (
        pdf_path.relative_to(PROJECT_DIR)
        .as_posix()
    )

    # --------------------------------------------------------
    # Construct manifest
    # --------------------------------------------------------

    manifest = {
        "source_id": SOURCE_ID,
        "title": TITLE,
        "source_path_or_url": source_path,
        "source_url": source_url,
        "license_or_permission": license_name,
        "accessed_at": date.today().isoformat(),
        "snapshot_or_version": version,

        "total_pdf_pages": total_pdf_pages,

        "selected_physical_pages": selected_pages,
        "selected_page_count": len(selected_pages),

        "counted_pages": counted_pages,
        "counted_page_count": len(counted_pages),
        "character_count": total_characters,

        "excluded_pages": excluded_details,

        "pages_requiring_review": sorted(
            set(review_required)
        ),

        "page_details": page_details,

        "counting_method": {
            "type": "PDF physical pages",
            "text_normalization": (
                "Collapse whitespace and strip text"
            ),
            "minimum_characters_for_candidate":
                MIN_CHARS_PER_PAGE,
            "requires_manual_review": True,
            "manual_review_confirmed": reviewed,
            "excluded_content": [
                "cover",
                "table_of_contents",
                "blank_pages",
                "references_only",
                "irrelevant_content"
            ]
        },

        "validation": {
            "minimum_required_pages": MIN_USEFUL_PAGES,
            "meets_minimum": (
                reviewed
                and len(counted_pages) >= MIN_USEFUL_PAGES
            ),
            "status": (
                "reviewed"
                if reviewed
                else "pending_manual_review"
            )
        }
    }

    # --------------------------------------------------------
    # Save manifest
    # --------------------------------------------------------

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            manifest,
            file,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # Print summary
    # --------------------------------------------------------

    print("\n========== CORPUS MANIFEST ==========")

    print(f"PDF: {pdf_path}")
    print(f"Total PDF pages: {total_pdf_pages}")
    print(f"Selected pages: {len(selected_pages)}")
    print(f"Counted pages: {len(counted_pages)}")
    print(f"Characters: {total_characters}")

    print(
        "Pages requiring review:",
        sorted(set(review_required))
    )

    print(f"Manifest saved: {OUTPUT_PATH}")

    print(
        "Validation:",
        manifest["validation"]["status"]
    )

    if not reviewed:
        print("\nMANUAL REVIEW REQUIRED")
        print(
            "Check selected pages and rerun "
            "with --reviewed."
        )

    elif len(counted_pages) < MIN_USEFUL_PAGES:
        print(
            "\nFAIL: Corpus has fewer than "
            "30 useful pages."
        )
        raise SystemExit(1)

    else:
        print(
            "\nPASS: Corpus contains at least "
            "30 counted pages."
        )
        print(
            "Manual review confirmation supplied."
        )


# ============================================================
# 4. COMMAND LINE INTERFACE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate corpus manifest for "
            "OpenStax Calculus Volume 1"
        )
    )

    parser.add_argument(
        "--start",
        type=int,
        required=True,
        help="First physical PDF page"
    )

    parser.add_argument(
        "--end",
        type=int,
        required=True,
        help="Last physical PDF page"
    )

    parser.add_argument(
        "--exclude-pages",
        default="",
        help="Pages to exclude, e.g. 52,55,70-72"
    )

    parser.add_argument(
        "--reviewed",
        action="store_true",
        help="Confirm manual review completed"
    )

    parser.add_argument(
        "--source-url",
        required=True,
        help="Official source URL"
    )

    parser.add_argument(
        "--license",
        required=True,
        help="Verified document license"
    )

    parser.add_argument(
        "--version",
        default=None,
        help="Document snapshot/version if available"
    )

    args = parser.parse_args()

    excluded_pages = parse_page_list(
        args.exclude_pages
    )

    create_manifest(
        start_page=args.start,
        end_page=args.end,
        excluded_pages=excluded_pages,
        reviewed=args.reviewed,
        source_url=args.source_url,
        license_name=args.license,
        version=args.version
    )


if __name__ == "__main__":
    main()
