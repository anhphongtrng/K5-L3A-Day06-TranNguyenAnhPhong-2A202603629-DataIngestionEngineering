
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader


# Đường dẫn theo cấu trúc repository của bạn
PROJECT_DIR = Path(
    r"D:\Work\VinAI\Lab05\K5-L3A-Day06-TranNguyenAnhPhong-2A202603629-DataIngestionEngineering"
)

PDF_PATH = PROJECT_DIR / "data" / "calculus_volume_1_openstax.pdf"

# Chỉ tạo các file kiểm tra, không sửa PDF gốc
OUTPUT_DIR = PROJECT_DIR / "artifacts" / "pdf_quality"

START_PAGE = 51
END_PAGE = 100


def normalize_text(text: str) -> str:
    """Chuẩn hóa khoảng trắng, giữ nguyên nội dung và ký hiệu."""
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main():
    if not PDF_PATH.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy PDF: {PDF_PATH}"
        )

    reader = PdfReader(str(PDF_PATH))

    if not (1 <= START_PAGE <= END_PAGE <= len(reader.pages)):
        raise ValueError("Khoảng trang không hợp lệ.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report = []
    hashes = defaultdict(list)

    for page_number in range(START_PAGE, END_PAGE + 1):
        raw_text = ""
        error = None

        try:
            raw_text = reader.pages[page_number - 1].extract_text() or ""
        except Exception as exc:
            error = str(exc)

        cleaned = normalize_text(raw_text)

        # Xuất riêng mỗi trang để xem và so sánh
        text_path = OUTPUT_DIR / f"page_{page_number:04d}.txt"
        text_path.write_text(cleaned, encoding="utf-8")

        # Băm toàn văn bản đã chuẩn hóa để tìm trang trùng tuyệt đối
        import hashlib
        digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        if cleaned:
            hashes[digest].append(page_number)

        flags = []
        if error:
            flags.append("extraction_error")
        if not cleaned:
            flags.append("empty_text")
        if len(cleaned) < 500:
            flags.append("short_text_under_500_chars")
        if "\ufffd" in cleaned:
            flags.append("replacement_character")

        report.append({
            "physical_page_number": page_number,
            "raw_characters": len(raw_text),
            "cleaned_characters": len(cleaned),
            "text_file": str(text_path.relative_to(PROJECT_DIR)).replace("\\", "/"),
            "flags": flags,
            "error": error,
        })

    duplicates = [
        pages for pages in hashes.values() if len(pages) > 1
    ]

    summary = {
        "pdf": str(PDF_PATH),
        "total_pdf_pages": len(reader.pages),
        "selected_pages": list(range(START_PAGE, END_PAGE + 1)),
        "pages": report,
        "exact_duplicate_page_groups": duplicates,
        "pages_with_flags": [
            entry["physical_page_number"]
            for entry in report if entry["flags"]
        ],
    }

    (OUTPUT_DIR / "quality_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("PDF pages:", len(reader.pages))
    print("Selected pages:", len(report))
    print("Pages with warnings:", summary["pages_with_flags"])
    print("Exact duplicate groups:", duplicates)
    print("Output:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
