# Báo cáo cá nhân — Day 06: Data Ingestion Engineering

**Họ và tên:** Trần Nguyễn Anh Phong  
**MSSV:** 2A202603629  
**Lớp:** L3A  
**Chủ đề:** Truy xuất tri thức từ giáo trình Giải tích cơ bản  
**Repository:** https://github.com/anhphongtrng/K5-L3A-Day06-TranNguyenAnhPhong-2A202603629-DataIngestionEngineering

## 1. Dữ liệu và pipeline

### 1.1. Chủ đề, nguồn dữ liệu và quy tắc tính trang

Corpus sử dụng giáo trình *Calculus Volume 1* của OpenStax, tiếng Anh, tập trung vào kiến thức về hàm số, phép biến đổi đồ thị, hàm ngược, lượng giác, hàm mũ và logarit. File nguồn là `data/calculus_volume_1_openstax.pdf`, có tổng cộng **769 trang PDF vật lý**. Phạm vi thí nghiệm gồm **50 trang vật lý liên tiếp, từ trang 51 đến 100**; số trang được tính theo vị trí trang trong PDF (không theo số trang in ở chân trang). Sau chuẩn hóa, corpus có khoảng **66.034 ký tự**.

Nguồn chính: https://openstax.org/books/calculus-volume-1/pages/1-introduction. Metadata về nguồn, quyền sử dụng và phạm vi trang được ghi tại `data/manifest.json`.

### 1.2. Chuẩn hóa, kiểm tra chất lượng và giới hạn

Dữ liệu được trích xuất từ PDF bằng `pypdf`, làm sạch/chuẩn hóa văn bản và lưu metadata trang để truy vết. Các bước kiểm tra gồm: xác nhận trang có văn bản, thống kê độ dài, kiểm tra trang trùng lặp chính xác và rà soát các trang ít ký tự. Kết quả: cả 50 trang có văn bản trích xuất; không phát hiện cặp trang trùng lặp hoàn toàn. Các trang vật lý **64, 75, 76 và 85** có ít ký tự, do nội dung nhiều hình/đồ thị.

Một hạn chế quan trọng là trích xuất văn bản thuần chưa tái hiện đầy đủ biểu thức toán, chỉ số, ký hiệu đặc biệt và đồ thị. Vì thế một số câu hỏi có bằng chứng trong tài liệu nhưng phần văn bản trích xuất có thể thiếu công thức hoặc bị ngắt, dẫn tới sai lệch trong đánh giá khớp bằng chứng chính xác.

Từ 50 trang vật lý, pipeline tạo **52 phân đoạn theo mục** vì các trang chuyển tiếp giữa các mục cần tách văn bản. `data/section_map.json` xác định mục **1.2–1.5**; hai trang chuyển mục là 61 và 73. Quy trình xử lý chính: PDF → trích xuất trang → chuẩn hóa/tách mục → chunking → embedding → lưu pgvector → truy xuất Top-3 → benchmark/audit.

### 1.3. Embedding, vector store, độ đo, lệnh chạy và tài nguyên

- **Embedding model:** `BAAI/bge-m3`, chạy cục bộ qua thư viện `sentence-transformers`; vector **1.024 chiều**. Cần ghi bổ sung phiên bản chính xác của model/thư viện nếu muốn tái lập hoàn toàn (artifact hiện chỉ xác nhận tên model và số chiều).
- **Vector store:** PostgreSQL 16 và pgvector (trong cấu hình Docker của dự án); truy xuất theo **cosine similarity**. Phiên bản pgvector đã sử dụng trong quá trình triển khai là 0.8.7; có thể đối chiếu lại tại `starter/docker-compose.yml`.
- **Thông số:** `top_k = 3`, dữ liệu vector được lưu bền vững trong Docker volume.
- **Thời gian ingestion:** tổng **182,18 giây** theo `artifacts/ingestion/stats.json`; thời gian ghi riêng trong thống kê: A **97,198 giây**, B **36,884 giây**. Không cộng các thời gian này thành tổng vì còn các bước xử lý khác.
- **Chi phí:** không sử dụng API embedding có thu phí cho lượt chạy này; chi phí API embedding ghi nhận là **0**. CPU/RAM, điện năng và chi phí máy cục bộ **chưa được định lượng**, vì thế không thể kết luận tổng chi phí vận hành bằng không.

Các lệnh chính (thực hiện trong thư mục `starter/`):

```powershell
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
python -m src.run --dry-run
python -m src.run
python -m src.run_benchmark --split dev
python -m src.run_benchmark --split test --confirm-frozen
# Dừng database nhưng không xóa volume:
docker compose -p day6_student_starter stop
```

### 1.4. Metadata

Mỗi chunk giữ ID ổn định và các trường để truy xuất ngược nguồn, tối thiểu gồm **source/document ID, đường dẫn nguồn, trang PDF vật lý, mục (`section`)** và nội dung chunk. Trang là định vị bằng chứng, còn `section` là trường lọc giúp giới hạn miền tìm kiếm theo chủ đề của từng câu hỏi. `section` được gán từ `data/section_map.json`, không suy ra từ nội dung câu hỏi hoặc gold answer. C dùng trường này để áp dụng điều kiện lọc khi đề bài yêu cầu.

## 2. Cấu hình và benchmark

### 2.1. Ba cấu hình A/B/C

| Cấu hình | Chunking | Độ dài | Overlap | Điều kiện lọc | Số chunk/vector |
|---|---|---|---|---|---:|
| **A** | Fixed-size theo ký tự | 500 ký tự | 50 ký tự | Không | 171 |
| **B** | Paragraph-aware | Tối đa 500 ký tự | Không | Không | 162 |
| **C** | Dùng lại chính chunks của B | Tối đa 500 ký tự | Không | Lọc theo `section` khi được yêu cầu | 162 (tái sử dụng B) |

A và B cùng dùng corpus, embedding model và vector store; thay đổi chủ yếu là **chiến lược chia chunk**. B và C dùng chung văn bản, `chunk_id` và vector: **khác biệt duy nhất là metadata filter tại thời điểm truy xuất**, không phải tạo index hay embedding thứ ba. Với câu hỏi không có filter, C thực hiện cùng thao tác tìm kiếm với B.

### 2.2. Bộ câu hỏi và nguyên tắc chấm

Bộ benchmark ở `starter/benchmark/benchmark_calculus_v1.json` gồm **20 câu** (15 DEV, 5 TEST), trong đó có **3 câu yêu cầu filter**, gồm **2 DEV và 1 TEST**. Mỗi câu có ID, câu hỏi, đáp án kỳ vọng, nguồn, trang PDF và `evidence_quote`; trường `filter` được khai báo trước nếu cần. Mỗi cấu hình truy xuất Top-3.

Hai chỉ số tự động:

- **Hit@1 (strict):** kết quả hạng 1 thỏa điều kiện khớp nguồn, trang và bằng chứng theo quy tắc chấm.
- **Evidence Hit@3 (strict):** ít nhất một trong ba chunks truy xuất thỏa đủ điều kiện bằng chứng nghiêm ngặt.

Ngoài ra có audit tính mạch lạc của chunk, metadata, grounding và tỷ lệ tuân thủ filter. Đánh giá nghiêm ngặt bằng chuỗi có nguy cơ false negative khi bằng chứng tương đương về nghĩa nhưng không trùng nguyên văn hoặc nằm qua ranh giới chunk.

### 2.3. Nguyên tắc lựa chọn cấu hình

Việc lựa chọn cần dựa trên DEV, khả năng giữ bằng chứng, truy vết nguồn, yêu cầu filter, thời gian chạy và tài nguyên. Chọn B làm **mốc chất lượng chunking** khi DEV Hit@1 cao hơn A; dùng C khi cần bắt buộc giới hạn theo section. TEST được dùng để đánh giá sau khi cấu hình đã cố định, **không dùng để thay đổi cấu hình rồi báo cáo như một phép kiểm tra độc lập**. Các số liệu TEST bên dưới cần được diễn giải thận trọng do chỉ có 5 câu.

## 3. Kết quả

### 3.1. Độ chính xác truy xuất

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Tìm kiếm trung bình / câu | Chi phí API embedding |
|---|---|---|---|---:|---:|---|
| A | DEV | 9/15 (60,00%) | 13/15 (86,67%) | 171 | 30,671 ms | 0 |
| B | DEV | 11/15 (73,33%) | 13/15 (86,67%) | 162 | 29,440 ms | 0 |
| C | DEV | 11/15 (73,33%) | 13/15 (86,67%) | 162 | 32,130 ms | 0 |
| A | TEST | 3/5 (60,00%) | 5/5 (100,00%) | 171 | 29,514 ms | 0 |
| B | TEST | 2/5 (40,00%) | 4/5 (80,00%) | 162 | 25,166 ms | 0 |
| C | TEST | 3/5 (60,00%) | 4/5 (80,00%) | 162 | 23,364 ms | 0 |

*Thời gian trong bảng là thời gian **truy vấn vector trung bình** theo `summary.json`, không bao gồm đầy đủ thời gian embedding câu hỏi hoặc khởi tạo model. Thời gian ingestion được ghi riêng ở mục 1.3.*

Nguồn số liệu: `artifacts/benchmark/dev/summary.json`, `artifacts/benchmark/test/summary.json`, `artifacts/ingestion/stats.json`.

### 3.2. Audit chất lượng dữ liệu và khả năng truy vết

| Strategy | Coherence trung bình /2 (n=10) | Metadata đủ và đúng (n/N) | Filter tuân thủ | Grounding trung bình /2 (5 câu TEST) |
|---|---:|---:|---:|---:|
| A | 1,50 | 15/15 | N/A | 1,80 |
| B | 1,50 | 15/15 | N/A | 1,60 |
| C | 1,50 | 15/15 | 3/3 (2 DEV + 1 TEST) | 1,60 |

Các giá trị coherence/metadata/grounding nêu trên là **điểm được ghi trong CSV audit**, được tổng hợp từ các lượt đánh giá đã chuẩn bị. Đối với metadata, 15/15 có nghĩa là **15 bản ghi Top-3 trong 5 câu TEST** được đánh dấu đủ và đúng cho từng chiến lược; tỷ lệ này phản ánh nhãn đã điền, không có nghĩa đã kiểm chứng lại độc lập toàn bộ PDF. Tương tự, grounding phản ánh mức độ hỗ trợ đáp án của evidence đã truy xuất, không phải độ chính xác của câu trả lời do LLM sinh ra.

Việc B và C bằng điểm coherence và có cùng `chunk_id` là phù hợp với thiết kế vì C tái sử dụng đúng tập chunks của B. Tỷ lệ lọc của C được tính trên 3 câu hỏi có yêu cầu filter, không tính các câu không yêu cầu lọc.

### 3.3. Traces và cách chọn mẫu audit

- **Corpus/manifest:** `data/calculus_volume_1_openstax.pdf`, `data/manifest.json`, `data/section_map.json`.
- **Ingestion:** `artifacts/ingestion/stats.json`, `artifacts/ingestion/smoke_retrieval.json`.
- **Benchmark:** `artifacts/benchmark/dev/` và `artifacts/benchmark/test/`, trong đó có `retrieval_A.json`, `retrieval_B.json`, `retrieval_C.json`, `summary.json`.
- **Coherence:** `artifacts/audit/coherence_review.csv`, gồm 10 vị trí nguồn chung × 3 chiến lược = 30 lượt đánh giá, thang 0–2.
- **Metadata:** `artifacts/audit/test_metadata_review.csv`, kiểm tra Top-3 của 5 câu TEST × 3 chiến lược = 45 bản ghi.
- **Grounding:** `artifacts/audit/test_grounding_review.csv`, gồm 5 câu TEST × 3 chiến lược = 15 lượt chấm, thang 0–2.
- **Rà soát lỗi DEV:** `artifacts/audit/dev_false_negative_review.csv`.

## 4. Phân tích và kết luận — Data Strategy Impact

### 4.1. So sánh A–B (chiến lược chunking)

A tạo **171 chunks**, B tạo **162 chunks** (ít hơn 9 chunks, khoảng **5,3%** so với A). Trên DEV, B cải thiện Hit@1 từ **60,00% lên 73,33%** (tăng 2/15 câu) nhưng Evidence Hit@3 đều **13/15**. Điều đó gợi ý chia đoạn theo cấu trúc ngữ nghĩa có lợi cho vị trí xếp hạng đầu ở bộ DEV, chưa chứng minh tăng khả năng lấy được bằng chứng trong Top-3.

Trên TEST, A đạt Hit@1 **3/5** và Evidence Hit@3 **5/5**, trong khi B đạt **2/5** và **4/5**. Kết quả này **không nhất quán với xu hướng DEV**; số câu TEST quá nhỏ để kết luận A luôn tốt hơn B. Coherence audit trung bình đều **1,50/2** trong các mẫu đã chấm, nên các kết quả hiện có chưa chứng minh B có ưu thế coherence ở bộ mẫu này. B tìm kiếm TEST nhanh hơn A theo log (25,166 so với 29,514 ms/câu), nhưng chênh lệch vài mili giây có thể chịu ảnh hưởng tải máy và điều kiện chạy.

### 4.2. So sánh B–C (metadata filter)

C không thay đổi chunk hay embedding, vì vậy **không phát sinh 162 vectors mới** và không được tính thêm chi phí tạo embedding. Với câu không filter, kết quả C có thể trùng với B. Điểm khác biệt rõ nhất là khả năng giới hạn phạm vi truy xuất ở các câu có điều kiện `section`.

C đạt **filter compliance 2/2 trên DEV và 1/1 trên TEST**; B không áp dụng điều kiện filter nên không có tỷ lệ tương ứng. Trên TEST, Hit@1 của C **3/5** so với **2/5** của B, còn Evidence Hit@3 đều **4/5**. Kết quả gợi ý filter giúp tránh chọn sai phần trong một số câu, nhưng không thể khẳng định cải thiện toàn cục vì chỉ có 3 câu filter trong cả bộ câu hỏi.

### 4.3. Ví dụ lỗi và khó khăn cụ thể

**Trường hợp 1 — Q007 (DEV):** `summary.json` đánh dấu Q007 cần rà soát bằng chứng thủ công ở cả A/B/C. Tình huống minh họa hạn chế của bộ chấm strict: câu trả lời hoặc bằng chứng có thể bị chia qua ranh giới chunk, khiến không có một chunk đơn lẻ khớp đầy đủ `evidence_quote`. Khi phân tích, cần đối chiếu `retrieval_A/B/C.json` và trang nguồn gắn trong benchmark trước khi kết luận thiếu thông tin.

**Trường hợp 2 — Q020 (TEST):** B và C có tên trong danh sách `questions_needing_manual_evidence_review`, trong khi A không có. Evidence Hit@3 strict của B/C vì vậy thấp hơn A. Đây là ví dụ cần kiểm tra liệu bằng chứng bị tách giữa chunks hoặc thiếu khi trích xuất/hiển thị preview; **không suy diễn tự động là hệ thống không có kiến thức để trả lời**. Nguồn truy vết chính là `starter/benchmark/benchmark_calculus_v1.json` cùng `artifacts/benchmark/test/retrieval_B.json` và `retrieval_C.json`.

### 4.4. Chiến lược đề xuất và đánh đổi

**Khuyến nghị thực tiễn: sử dụng B làm cấu hình paragraph-aware cơ sở, bật cơ chế lọc như C khi yêu cầu có section rõ ràng và đáng tin cậy.** Lựa chọn này dựa trên Hit@1 DEV cao hơn A, việc C giữ nguyên chi phí embedding của B, và filter tuân thủ đầy đủ trên 3 câu thử nghiệm. Tuy vậy, nếu mục tiêu ưu tiên là Evidence Hit@3 strict trên bộ TEST hiện tại, **A đang cho kết quả cao hơn**. Vì vậy cần nêu cả hai mặt, không tuyên bố một phương án thắng tuyệt đối.

Đánh đổi chính: fixed-size đơn giản nhưng có thể cắt ý; paragraph-aware giảm ngắt đoạn nhưng phụ thuộc chất lượng trích xuất và dấu phân đoạn; metadata filter tăng độ chính xác phạm vi khi `section` đúng, nhưng có thể loại bỏ bằng chứng hợp lệ nếu metadata bị gán sai hoặc yêu cầu lọc không phù hợp.

### 4.5. Hạn chế và cải tiến nếu làm lại

1. **Tăng kích thước TEST** và bổ sung nhiều câu phân biệt hai section, giảm biến động do chỉ 5 câu.
2. **Kiểm tra thủ công full chunk và trang PDF**, nhất là những câu strict miss, rồi ghi rõ nhãn nào đã được xác minh trực tiếp.
3. **Cải thiện trích xuất toán học:** bổ sung xử lý công thức, hình và chú thích đồ thị; cân nhắc phương pháp trích xuất chuyên biệt cho PDF toán.
4. **Đo latency có kiểm soát:** chạy lặp nhiều lần, tách thời gian tạo query embedding, truy vấn database, khởi tạo model và ingestion; ghi phần cứng, RAM, phiên bản môi trường.
5. **Bảo đảm tái lập:** cố định phiên bản model/thư viện và quyền nguồn; đóng băng cấu hình bằng commit và lưu script/chỉ số cùng trace.
6. **Phân tích trường hợp lọc sai:** bổ sung câu filter theo những section dễ nhầm và kiểm tra ảnh hưởng của metadata không chính xác.

## 5. Tóm tắt

Pipeline đã xử lý **50 trang PDF**, tạo **171 vectors A** và **162 vectors B**, trong khi C tái sử dụng vectors B để lọc theo `section`. Kết quả DEV ưu tiên B/C về Hit@1, nhưng TEST ghi nhận A có Evidence Hit@3 cao hơn. Metadata filtering của C đạt **3/3 yêu cầu lọc** trong benchmark. Kết luận phù hợp nhất là **chunking, metadata và chất lượng nguồn cùng ảnh hưởng đến retrieval**; cần kết hợp chỉ số tự động, audit bằng chứng và đo tài nguyên, thay vì chỉ dựa vào một tỉ lệ trên tập TEST nhỏ.

---

**Tài liệu và minh chứng:** `REPORT_TEMPLATE.md`, `BENCHMARK.md`, `RULES.md`, `SUBMISSION.md`, `data/manifest.json`, `artifacts/ingestion/stats.json`, `artifacts/benchmark/{dev,test}/summary.json`, `artifacts/audit/*.csv` trong repository liên kết ở đầu báo cáo.
