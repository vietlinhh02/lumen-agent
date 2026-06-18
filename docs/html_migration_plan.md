# 🚀 Migration Plan: Nâng cấp Trích xuất Full-text HTML/XML

Kế hoạch này vạch ra các bước cụ thể để tích hợp khả năng trích xuất toàn văn (Full-text) cực nhanh và siêu sạch từ **arXiv HTML** và **Europe PMC XML**, giúp giảm bớt sự phụ thuộc vào các công cụ OCR nặng nề như `pdf_oxide` và `pypdf`.

## 📌 Phase 1: Xây dựng Module Extractor (Trích xuất)
**Mục tiêu:** Xây dựng các hàm tải và làm sạch HTML/XML độc lập để dễ bảo trì.

- [x] **Task 1.1:** Cài đặt (hoặc kiểm tra) thư viện `beautifulsoup4` trong `pyproject.toml`.
- [x] **Task 1.2:** Viết hàm `fetch_arxiv_html(arxiv_id: str) -> str | None`
  - Quét `https://arxiv.org/html/{arxiv_id}`.
  - Dùng BeautifulSoup bóc tách nội dung chính, loại bỏ các thẻ `<figure>`, `<math>` phức tạp (nếu cần).
- [x] **Task 1.3:** Viết hàm `fetch_europepmc_xml(pmc_id: str) -> str | None`
  - Gọi API `https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc_id}/fullTextXML`.
  - Lọc nội dung từ thẻ `<body>` của XML, giữ nguyên cấu trúc Heading, Paragraph.

## 📌 Phase 2: Nâng cấp Luồng Tải Dữ liệu (`pdf_downloader.py`)
**Mục tiêu:** Tích hợp Extractor vào luồng tải file hiện tại.

- [x] **Task 2.1:** Cập nhật hàm `resolve_pdf_url` hoặc tạo hàm mới `resolve_and_download`.
- [x] **Task 2.2:** Cài đặt logic ưu tiên (Routing logic):
  1. **Thử lấy HTML/XML:** Nhận diện `arxiv_id` hoặc `pmc_id` (nếu có từ metadata). Nếu thành công, lưu nội dung vào thư mục với đuôi `.txt` (ví dụ: `2501.18444.txt`).
  2. **Fallback:** Nếu bài quá cũ không có HTML, hoặc không tìm thấy nội dung, tự động rơi về cơ chế tải PDF truyền thống.
- [x] **Task 2.3:** Trả về đường dẫn `Path` của file (có thể là `.txt` hoặc `.pdf`).

## 📌 Phase 3: Tích hợp vào Luồng Ingestion (`pdf_fulltext.py`)
**Mục tiêu:** Bỏ qua bước OCR không cần thiết nếu đã có raw text sạch.

- [x] **Task 3.1:** Sửa logic hàm `process_pdf(..., pdf_path: Path)`.
  - Thêm điều kiện check đuôi file:
    ```python
    if pdf_path.suffix == '.txt':
        text = pdf_path.read_text(encoding='utf-8')
    else:
        text = extract_text(pdf_path) # Chạy luồng OCR cũ
    ```
- [x] **Task 3.2:** Đảm bảo `chunk_text()` nhận raw text từ file `.txt` hoạt động mượt mà như khi nhận text từ OCR. (Vì hàm này chỉ yêu cầu string đầu vào).

## 📌 Phase 4: Điều chỉnh Luồng Nền và DB (`project.py`)
**Mục tiêu:** Đảm bảo hệ thống background jobs không bị ảnh hưởng.

- [x] **Task 4.1:** Rà soát hàm `_download_and_ingest_bg`. Đảm bảo biến `pdf_result` (bây giờ có thể trỏ tới file `.txt`) vẫn qua được bước kiểm tra `pdf_result.exists()`.
- [x] **Task 4.2:** Cập nhật trạng thái `full_text_status` thành `completed` khi quá trình trích xuất HTML/XML thành công.

## 📌 Phase 5: Kiểm thử (Testing)
**Mục tiêu:** Đảm bảo độ ổn định của toàn hệ thống trước khi vận hành thực tế.

- [x] **Test Case 1:** Tải thử 1 bài arXiv có bản HTML -> Xác nhận Ingestion siêu tốc và bỏ qua OCR.
- [x] **Test Case 2:** Tải thử 1 bài PubMed Central có PMCID -> Xác nhận trích xuất XML hoàn hảo.
- [x] **Test Case 3:** Tải thử 1 bài không có HTML/XML -> Xác nhận fallback về tải PDF và chạy OCR mượt mà.
