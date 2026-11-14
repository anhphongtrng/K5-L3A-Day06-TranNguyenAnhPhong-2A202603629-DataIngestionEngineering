# Day 06 – Data Ingestion Engineering

## 1. Giới thiệu

Dự án thực hành **Data Ingestion Engineering** xây dựng pipeline chuyển tài liệu PDF thành các vector có thể truy xuất, lưu trong **PostgreSQL + pgvector** và so sánh ba chiến lược chuẩn bị dữ liệu trên cùng một corpus và bộ câu hỏi benchmark.

- **Chủ đề:** Toán học – Giải tích cơ bản (Calculus).
- **Nguồn:** *OpenStax – Calculus Volume 1* (tiếng Anh).
- **Corpus dùng trong thí nghiệm:** 50 trang PDF vật lý, từ trang **51 đến 100** (tài liệu PDF đầy đủ có 769 trang).
- **Embedding model:** `BAAI/bge-m3` (1024 chiều), chạy local qua `sentence-transformers`.
- **Vector store:** PostgreSQL 16 + pgvector, chạy bằng Docker Compose.
- **Benchmark:** 20 câu hỏi, gồm 15 câu DEV và 5 câu TEST; tìm kiếm Top-3.

### Ba chiến lược

| Cấu hình | Phương pháp | Số chunks/vectors |
| --- | --- | ---: |
| A | Fixed-size, 500 ký tự, overlap 50 ký tự | 171 |
| B | Paragraph-aware, tối đa 500 ký tự/chunk | 162 |
| C | Dùng chung chunks và vectors của B; thêm bộ lọc metadata `section` khi truy xuất | 162 (không tạo bộ vectors thứ ba) |

PDF được tách thành **52 đoạn có metadata section** trước khi chunking; metadata phục vụ truy xuất nguồn, trang và section. Kết quả thí nghiệm được lưu trong `artifacts/`.

## 2. Yêu cầu môi trường

- Git.
- **Python 3.11–3.14** và `pip`.
- Docker Desktop (Windows) hoặc Docker Engine kèm Docker Compose.
- Kết nối mạng trong lần đầu tải Docker image, Python packages và model `BAAI/bge-m3`.
- Dung lượng trống đủ cho mô hình embedding và database.

Các lệnh dưới đây dành cho **Windows PowerShell**, thực hiện từ thư mục gốc repository trừ khi có chỉ dẫn khác.

## 3. Cài đặt

### Bước 1 – Clone repository

```powershell
git clone https://github.com/anhphongtrng/K5-L3A-Day06-TranNguyenAnhPhong-2A202603629-DataIngestionEngineering.git
cd K5-L3A-Day06-TranNguyenAnhPhong-2A202603629-DataIngestionEngineering
```

### Bước 2 – Tạo môi trường Python

```powershell
cd starter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install sentence-transformers
```

`starter/requirements.txt` gồm các dependency cơ bản (`psycopg`, `pypdf`, `python-dotenv`); thư viện embedding local cần cài thêm riêng. Trên macOS/Linux, kích hoạt môi trường bằng `source .venv/bin/activate`.

### Bước 3 – Tạo file cấu hình

```powershell
Copy-Item .env.example .env
```

Trong `starter/.env`, sử dụng các giá trị tương ứng với Docker Compose:

```dotenv
DATABASE_URL=postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab
EMBEDDING_MODEL=BAAI/bge-m3
```

Model local này **không yêu cầu API key**. Không commit `starter/.env`, API key hoặc thông tin bí mật. Thông tin kết nối ví dụ chỉ dùng cho database lab trên máy cá nhân, không dùng nguyên trạng trong môi trường production.

### Bước 4 – Khởi động PostgreSQL + pgvector

Mở Docker Desktop trước, sau đó chạy từ thư mục `starter/`:

```powershell
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
```

Nếu cấu hình đúng, script kiểm tra sẽ in thông tin PostgreSQL/pgvector và `Setup OK`. Database được mở ở địa chỉ local `127.0.0.1:55433`.

## 4. Đường dẫn dữ liệu và cấu trúc thư mục

Các đường dẫn sau được tính từ **thư mục gốc repository**; phân biệt `data/` ở gốc với `starter/data/` của bộ khởi động.

```text
.
├── README.md
├── data/
│   ├── calculus_volume_1_openstax.pdf   # PDF gốc
│   ├── manifest.json                    # Nguồn, số trang vật lý, trang sử dụng
│   └── section_map.json                 # Ánh xạ trang/đoạn sang section
├── starter/
│   ├── .env.example
│   ├── .env                            # Tạo trên máy cá nhân, không commit
│   ├── requirements.txt
│   ├── docker-compose.yml
│   ├── init.sql
│   ├── benchmark/
│   │   └── benchmark_calculus_v1.json   # 20 câu hỏi DEV/TEST
│   ├── scripts/
│   │   ├── check_setup.py
│   │   ├── create_manifest.py           # Tạo manifest.json từ PDF
│   │   ├── check_pdf_quality.py         # Kiểm tra chất lượng PDF, số trang vật lý, section map
│   │   └── prepare_audit.py             # Chuẩn bị CSV đánh giá từ traces
│   └── src/
│       ├── ingestion.py
│       ├── chunking.py
│       ├── embeddings.py
│       ├── store.py
│       ├── run.py
│       └── run_benchmark.py            # Chạy benchmark DEV/TEST
├── artifacts/
│   ├── pdf_quality/                     # Văn bản trang 51–100 và báo cáo chất lượng
│   ├── ingestion/                       # Thống kê dry-run, ingestion, smoke retrieval
│   ├── benchmark/
│   │   ├── dev/                          # retrieval_A/B/C.json, summary.json
│   │   └── test/                         # retrieval_A/B/C.json, summary.json
│   ├── audit/                            # Các CSV đánh giá coherence/metadata/grounding/data strategy
│   └── experiment_log.csv               # Nhật ký so sánh các cấu hình
|   └──
└── report/
    └── individual/2A202603629_TranNguyenAnhPhong_                      # Báo cáo và phân tích Data Strategy Impact
    └── individual/README.md            # CÁCH SETUP, CHẠY, ĐƯỜNG DẪN DỮ LIỆU
```

**Lưu ý:** Nếu file PDF không đi kèm bản clone do giới hạn kích thước hoặc quy định chia sẻ, cần tải đúng tài liệu *OpenStax – Calculus Volume 1* và đặt tại `data/calculus_volume_1_openstax.pdf`, tương ứng với manifest hiện có. Không thay PDF bằng phiên bản khác khi chưa kiểm tra lại số trang vật lý, manifest và section map.

Đường dẫn chính xác được sử dụng trong mã:

| Thành phần | Đường dẫn |
| --- | --- |
| PDF nguồn | `data/calculus_volume_1_openstax.pdf` |
| Manifest | `data/manifest.json` |
| Section map | `data/section_map.json` |
| Benchmark câu hỏi | `starter/benchmark/benchmark_calculus_v1.json` |
| Kết quả ingestion | `artifacts/ingestion/` |
| Kết quả DEV/TEST | `artifacts/benchmark/dev/`, `artifacts/benchmark/test/` |
| Đánh giá CSV | `artifacts/audit/` |
| Nhật ký thí nghiệm | `artifacts/experiment_log.csv` |

## 5. Chạy pipeline

Tất cả lệnh trong phần này đều chạy từ thư mục **`starter/`**, sau khi kích hoạt `.venv`.

### 5.1. Kiểm tra dữ liệu và chia chunk (không cần Docker)

```powershell
python -m src.run --dry-run
```

Kết quả kỳ vọng với corpus hiện tại:

```text
Corpus: 50 physical pages -> 52 segments
A fixed: 171 chunks
B paragraph: 162 chunks
Dry-run OK; no model loaded, database untouched
```

Chi tiết số chunks theo section được in thêm ở terminal. Lệnh không tải model, không ghi dữ liệu vào database và lưu thống kê tại:

`artifacts/ingestion/dry_run_stats.json`

### 5.2. Embedding và lưu pgvector (cần Docker)

Kiểm tra PostgreSQL đang chạy, sau đó:

```powershell
python -m src.run
```

Pipeline đọc manifest và PDF, gắn section, tạo chunks A/B, embedding bằng `BAAI/bge-m3`, upsert vectors vào pgvector và chạy một lượt truy xuất kiểm tra. C dùng lại vectors của B và chỉ bổ sung filter lúc tìm kiếm.

Output:

- `artifacts/ingestion/stats.json`
- `artifacts/ingestion/smoke_retrieval.json`

**Không bắt buộc chạy lại ingestion nếu database đã có vectors phù hợp.** Vector được giữ trong Docker volume, không nằm trong file CSV/JSON của repository.

## 6. Chạy benchmark

Benchmark phải được chạy sau ingestion, trong lúc PostgreSQL hoạt động. Bộ câu hỏi dùng 15 câu DEV, 5 câu TEST; TEST chỉ chạy sau khi đã cố định lựa chọn cấu hình trên DEV.

### 6.1. DEV

```powershell
python -m src.run_benchmark --split dev
```

Lưu kết quả trong `artifacts/benchmark/dev/`:

- `retrieval_A.json`
- `retrieval_B.json`
- `retrieval_C.json`
- `summary.json`

### 6.2. TEST

```powershell
python -m src.run_benchmark --split test --confirm-frozen
```

Lưu cùng cấu trúc tại `artifacts/benchmark/test/`.

Chỉ số tự động bao gồm **Hit@1**, **Evidence Hit@3**, kiểm tra tuân thủ bộ lọc (nếu có) và thời gian truy xuất. Điểm evidence tự động dùng quy tắc khớp chặt nguồn/trang/đoạn trích; những trường hợp bị cắt giữa chunks hoặc diễn đạt tương đương cần được xem lại trong audit.

## 7. Đánh giá và báo cáo

Ba chiến lược được đánh giá trên cùng corpus, embedding model và bộ câu hỏi theo năm nhóm tiêu chí:

1. Retrieval Accuracy – Hit@1 và Evidence Hit@3.
2. Chunk Coherence – tính mạch lạc và đầy đủ của chunk.
3. Metadata Usefulness – tính đúng đắn và khả năng truy vết nguồn/trang/section.
4. Grounding Quality – mức độ evidence hỗ trợ trả lời.
5. Data Strategy Impact – so sánh kết quả, trường hợp lỗi, độ trễ, chi phí và đánh đổi của A/B/C.

Các file liên quan:

```text
artifacts/audit/coherence_review.csv
artifacts/audit/test_metadata_review.csv
artifacts/audit/test_grounding_review.csv
artifacts/audit/dev_false_negative_review.csv
artifacts/experiment_log.csv
report/individual/
```

Để tạo mẫu CSV đánh giá từ traces (nếu cần tái tạo), dùng script `starter/scripts/prepare_audit.py` theo hướng dẫn và tham số trong script; không ghi đè các file đã đánh giá trước khi sao lưu.

## 8. Dừng và khởi động lại Docker

Từ thư mục `starter/`, dừng container **mà vẫn giữ database và vectors**:

```powershell
docker compose -p day6_student_starter stop
```

Khi cần truy vấn hoặc chạy benchmark tiếp:

```powershell
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
```

Kiểm tra trạng thái:

```powershell
docker compose -p day6_student_starter ps
```

> **Không dùng `docker compose down -v`** nếu muốn giữ dữ liệu: tùy chọn `-v` xóa volume của database. Sau khi đã xuất đủ benchmark và audit, việc viết báo cáo hoặc chỉnh sửa CSV không cần chạy Docker.

## 9. Lưu ý khi tái lập

- Các script `starter/scripts/create_manifest.py` và `starter/scripts/check_pdf_quality.py` đang chứa giá trị `PROJECT_DIR` là đường dẫn tuyệt đối trên máy Windows nơi dự án được triển khai. Nếu chạy trên máy khác, cần chỉnh đường dẫn này hoặc chuyển sang tính đường dẫn tương đối trước khi chạy.
- `create_manifest.py` yêu cầu tham số phạm vi trang và thông tin nguồn; nếu manifest hiện tại đã đúng, không cần tạo lại.
- Nếu thay đổi PDF, phạm vi trang, section map, mô hình embedding hoặc phương pháp chunking, phải kiểm tra lại dữ liệu và chạy lại các bước liên quan; không so sánh với kết quả benchmark cũ như thể cùng cấu hình.
- Các chunk chứa đồ thị, công thức hoặc ký hiệu toán học có thể bị mất thông tin khi trích xuất văn bản bằng `pypdf`. Đây là hạn chế cần phản ánh trong báo cáo.
- Không commit `.env`, khóa API, thông tin nhạy cảm, hoặc file dữ liệu không có quyền chia sẻ.

