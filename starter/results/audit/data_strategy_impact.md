# Data Strategy Impact — Phân tích từ kết quả hiện có

## Phạm vi và phương pháp

Tập tài liệu gồm 50 trang PDF vật lý (51–100) từ *OpenStax Calculus Volume 1*. Cả ba chiến lược sử dụng cùng mô hình embedding `BAAI/bge-m3` (1024 chiều), cùng benchmark 15 câu DEV và 5 câu TEST, Top-3 retrieval bằng pgvector/cosine. Điểm Hit@1 và Evidence Hit@3 dưới đây là điểm **tự động nghiêm ngặt**, trong khi điểm coherence/metadata/grounding là kết quả từ các bảng audit đã cung cấp; các bảng audit được nhận xét dựa trên đoạn văn bản xem trước (preview), chưa thay thế việc kiểm tra toàn văn.

## Kết quả chính

| Chỉ số | A – fixed-size | B – paragraph | C – paragraph + filter |
|---|---:|---:|---:|
| Số chunks / vectors | 171 | 162 | 162 (dùng chung B) |
| DEV Hit@1 | 9/15 (60,00%) | 11/15 (73,33%) | 11/15 (73,33%) |
| DEV Evidence Hit@3 | 13/15 (86,67%) | 13/15 (86,67%) | 13/15 (86,67%) |
| TEST Hit@1 | 3/5 (60,00%) | 2/5 (40,00%) | 3/5 (60,00%) |
| TEST Evidence Hit@3 | 5/5 (100,00%) | 4/5 (80,00%) | 4/5 (80,00%) |
| Coherence (10 mẫu/chiến lược) | 1,50/2 | 1,50/2 | 1,50/2 |
| Metadata nhất quán (15 mẫu/chiến lược) | 15/15 | 15/15 | 15/15 |
| Grounding TEST (5 mẫu/chiến lược) | 1,80/2 | 1,60/2 | 1,60/2 |
| Filter compliance DEV / TEST | N/A | N/A | 2/2 và 1/1 |
| Thời gian truy vấn TB TEST | 29,51 ms | 25,17 ms | 23,36 ms |

## So sánh A và B

B tạo 162 chunks thay vì 171 của A (giảm 9 chunks, khoảng 5,3%) và tăng DEV Hit@1 từ 60,00% lên 73,33%. Tuy nhiên, trên TEST 5 câu, B đạt Hit@1 40% và Evidence Hit@3 80%, thấp hơn A (60% và 100%). Vì vậy không thể khẳng định chia đoạn luôn tốt hơn chia cố định; kết quả thay đổi theo phân phối câu hỏi và vị trí evidence. Hai phương án có cùng trung bình coherence theo bảng audit hiện tại (1,50/2). Phép đo truy vấn TEST ghi nhận B nhanh hơn A một chút (25,17 so với 29,51 ms/câu), nhưng tập đo nhỏ không đủ để suy ra ưu thế hiệu năng ổn định.

## So sánh B và C

C **tái sử dụng chunks, IDs và embeddings của B**, khác biệt tại lúc truy vấn khi có điều kiện `section`. Khi không có filter, C tương đương B. Điểm DEV Hit@1 và Evidence Hit@3 của B/C giống nhau. Ở TEST, C đạt Hit@1 60% so với 40% của B, trong khi Evidence Hit@3 cùng 80%; mức tăng Hit@1 có thể gắn với câu hỏi yêu cầu lọc mục, nhưng chỉ có 1 câu TEST có filter nên không thể khái quát rộng. C đạt filter compliance 2/2 trên DEV và 1/1 trên TEST. Không phát sinh chi phí embedding/index cho collection thứ ba trong thiết kế này.

## Hai tình huống cần phân tích lỗi

1. **Q007 (DEV, tr.61):** Bằng chứng về hiện tượng vật lý được mô hình hóa bằng hàm lượng giác nằm trong phần văn bản mà truy xuất strict evidence có thể không khớp trọn vẹn một chunk. Điểm Evidence Hit@3 tự động đánh dấu không đạt cho cả ba cấu hình. Cần xem lại full chunk và trích dẫn trước khi quyết định đây là lỗi truy xuất hay false negative của tiêu chí tự động.
2. **Q020 (TEST, tr.97):** B/C được đánh dấu cần rà soát vì bằng chứng “100 times” trong bài toán thang Richter có thể nằm ngoài phần preview hoặc qua ranh giới chunk; A đạt Evidence Hit@3. Không nên gọi đây là mất bằng chứng hoàn toàn khi chưa xem toàn văn chunk.

## Đánh đổi và kết luận

Về độ bao phủ trên bộ TEST nhỏ, A có kết quả tự động cao hơn. Về tính năng sản phẩm, C có lợi ích thiết thực là giới hạn kết quả theo `section` mà không tạo lại embeddings so với B. Không có một cấu hình vượt trội trên mọi chỉ số: A là lựa chọn hợp lý nếu ưu tiên Evidence Hit@3 trên chính benchmark hiện tại; C phù hợp khi câu hỏi thường xuyên nêu mục tài liệu và cần bảo đảm đúng phạm vi. Cần quyết định chiến lược dựa trên DEV trước khi dùng TEST để báo cáo kết quả cuối; không lựa chọn ngược theo điểm TEST.

## Hạn chế

- TEST chỉ có 5 câu, trong đó 1 câu filter; biến động 1 câu làm thay đổi 20 điểm phần trăm.
- Audit coherence và grounding sử dụng text preview, không phải toàn văn chunk/PDF.
- Công thức, đồ thị và bố cục toán học khi trích bằng `pypdf` có thể mất ký hiệu; các trang giàu hình ảnh có chất lượng text thấp.
- Thời gian tìm kiếm phản ánh thao tác retrieval, không đồng nhất với thời gian encode câu hỏi, ingest hay tổng thời gian RAG.
- Embedding chạy cục bộ nên không có phí API embedding trực tiếp theo token; nhưng vẫn tiêu thụ CPU/RAM, dung lượng DB và thời gian tính toán. Chưa có phép đo định lượng quy đổi tiền phần cứng.

## Nguồn đối chiếu

- `artifacts/benchmark/dev/summary.json`
- `artifacts/benchmark/test/summary.json`
- `artifacts/audit/coherence_review.csv`
- `artifacts/audit/test_metadata_review.csv`
- `artifacts/audit/test_grounding_review.csv`
- `artifacts/ingestion/stats.json`