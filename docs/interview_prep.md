# Lumen (AI Literature Review Assistant) - Interview Preparation Guide

## 1. Tóm tắt dự án để Pitching (Elevator Pitch)

"Dự án Lumen là một trợ lý AI hỗ trợ nghiên cứu khoa học và viết tổng quan tài liệu (Literature Review). Khác với các chatbot AI thông thường hay bịa ra trích dẫn (hallucination), Lumen giải quyết triệt để vấn đề đó bằng cách xây dựng một quy trình khép kín: Người dùng tìm kiếm và lưu các bài báo thực tế vào dự án $\rightarrow$ Hệ thống dùng AI để trích xuất dữ liệu thành Ma trận tài liệu (Literature Matrix) $\rightarrow$ Sinh ra các báo cáo và phát hiện lỗ hổng nghiên cứu (Research Gaps) dựa **hoàn toàn** trên dữ liệu đã lưu. Bất kỳ trích dẫn nào AI sinh ra đều bị bắt buộc đối chiếu với cơ sở dữ liệu để đảm bảo tính xác thực 100%."

**Tech Stack cốt lõi:**
*   **Frontend:** Next.js 16 (App Router), React 19, Tailwind CSS v4, Zustand (State), SWR (Data fetching).
*   **Backend:** Python 3.13, FastAPI (Async), SQLAlchemy.
*   **Database:** PostgreSQL 16 với extension `pgvector` (HNSW index) để lưu trữ vector nội dung.
*   **AI/ML:** LangGraph cho luồng tác vụ đa bước, mô hình Hybrid RAG (kết hợp keyword & vector search), tích hợp nhiều LLM (Anthropic, OpenAI, DeepSeek).

---

## 2. Các kỹ thuật RAG được sử dụng & Lý do (Core AI Architecture)

Hệ thống **không sử dụng Naive RAG** (chỉ cắt text $\rightarrow$ nhúng vector $\rightarrow$ tìm cosine similarity), mà sử dụng kiến trúc tinh vi được thiết kế riêng cho bài toán học thuật:

### 2.1. Hybrid Retrieval (Vector Search + Relational Filtering)
Hệ thống kết hợp tìm kiếm ngữ nghĩa bằng vector (Vector Similarity Search) và lọc dữ liệu có cấu trúc (Metadata/Relational Filtering) thông qua PostgreSQL + `pgvector`.
*   **Cách hoạt động:** Câu lệnh SQL kết hợp mệnh đề `WHERE` (lọc theo `project_id`, lọc bỏ bài báo irrelevant) và hàm tính khoảng cách vector `HNSW`.
*   **Vì sao dùng?** 
    *   **Cô lập dữ liệu (Data Isolation):** Đảm bảo RAG chỉ lấy thông tin từ các bài báo *thuộc về Project hiện tại*, không bị rò rỉ sang project khác.
    *   **Khắc phục điểm yếu Vector Search:** Vector search rất dở trong việc tìm chính xác từ khóa (tên hóa chất, ID bài báo). Hybrid search giải quyết triệt để vấn đề này.

### 2.2. Semantic Chunking & Content Type Tagging
Thay vì cắt PDF mù quáng theo số lượng từ, hệ thống đánh nhãn cho từng chunk xem nó thuộc phần nào của bài báo (`abstract`, `method`, `results`, `limitation`, `reference`).
*   **Vì sao dùng?** Bài báo khoa học có cấu trúc khắt khe. Nếu user hỏi *"Điểm yếu của phương pháp là gì?"*, RAG có thể filter ưu tiên các chunk có nhãn `limitation`. Điều này giúp AI không lấy nhầm bối cảnh từ phần nghiên cứu của tác giả khác (phần reference) để trả lời.

### 2.3. Matrix-Augmented Context (RAG qua dữ liệu trung gian có cấu trúc)
Thay vì nhét trực tiếp raw text từ PDF vào prompt, luồng dữ liệu là: Text PDF $\rightarrow$ AI trích xuất thành **Literature Matrix** $\rightarrow$ User kiểm duyệt/chỉnh sửa trên UI $\rightarrow$ **Dùng Matrix làm Context** để sinh Report.
*   **Vì sao dùng?**
    *   **Chống GIGO (Garbage In, Garbage Out):** Tinh sạch dữ liệu, loại bỏ nhiễu từ PDF (header, footer, table rác).
    *   **Human-in-the-loop:** Đảm bảo RAG context cuối cùng để viết Báo cáo là 100% chuẩn xác vì đã được con người duyệt lại qua giao diện Matrix.

### 2.4. Data Guardrails & Strict Filtering (Chống Hallucination)
Mô hình phòng thủ 3 lớp (3-layered defense) khắt khe:
*   **Vì sao dùng?** Lỗi kinh điển nhất của LLM là "chế" ra nguồn trích dẫn.
*   **Cách hoạt động:** 
    1. UI chặn user lưu các bài báo bị AI đánh giá là `low relevance`.
    2. Nếu lọt vào Database, query SQLAlchemy của RAG sẽ có điều kiện gạt bỏ cứng (`WHERE relevance_label != 'low'`).
    3. Output của AI khi viết Báo cáo bị ép trích xuất `Citation ID`. Backend quét các ID này, nếu ID không tồn tại trong `project_paper_id`, kết quả lập tức bị Reject.

---

## 3. Câu hỏi phỏng vấn dự kiến & Hướng dẫn trả lời

### 🎤 Q1: Làm thế nào bạn giải quyết vấn đề AI bịa ra thông tin hoặc trích dẫn sai (Hallucination)?
**Trả lời:** "Dự án áp dụng mô hình phòng thủ 3 lớp. (1) Cảnh báo UI khi user lưu bài báo không liên quan. (2) Tự động tag 'low confidence' trong Literature Matrix để user dễ xóa. (3) Quan trọng nhất: Chặn truy xuất ở tầng Database. Trong query SQLAlchemy sinh context cho AI viết Report, hệ thống loại bỏ cứng các bài báo bị gán nhãn irrelevant. Đồng thời, backend validate ngược các Citation ID do AI sinh ra, đảm bảo ID phải khớp với database."

### 🎤 Q2: Hệ thống search bài báo từ nhiều nguồn (arXiv, OpenAlex, Exa...). Thiết kế logic như thế nào để hệ thống không sập khi 1 nguồn chết?
**Trả lời:** "Sử dụng Adapter Pattern và gọi API bất đồng bộ (async HTTP Client) qua `asyncio.gather` kèm timeout. Nếu một nguồn bị lỗi (ví dụ 500 từ OpenAlex), hệ thống bắt Exception cục bộ và áp dụng Graceful Degradation: vẫn trả về kết quả từ các nguồn còn sống. Sau đó, dữ liệu đi qua hàm Deduplication để gộp các bài báo trùng lặp dựa trên DOI hoặc Title."

### 🎤 Q3: Vì sao bạn lại chọn PostgreSQL + pgvector thay vì các Vector DB chuyên dụng như Milvus hay Pinecone?
**Trả lời:** "Do yêu cầu cốt lõi của dự án là Hybrid RAG (kết hợp Relational filtering và Vector similarity). Dùng chung PostgreSQL giúp em giữ được tính ACID cho transaction, tránh rủi ro lệch data (data mismatch) giữa DB SQL chứa thông tin User/Project và DB Vector bên ngoài. Lệnh query của em có thể vừa lọc cứng `WHERE project_id = X` vừa `ORDER BY vector_distance`, cực kỳ gọn, dễ maintain và đáp ứng đủ hiệu năng."

### 🎤 Q4: LangGraph đóng vai trò gì trong hệ thống này? Có phải là một dạng AutoGPT tự chạy không?
**Trả lời:** "Không ạ. Mục tiêu của dự án là Assistant, không phải Agent tự trị. LangGraph ở đây được dùng để định nghĩa các **Controlled Workflows** (luồng tác vụ có kiểm soát), ví dụ: Normalize Paper $\rightarrow$ Enrich $\rightarrow$ Matrix Extract $\rightarrow$ Detect Gap. LangGraph giúp quản lý State giữa các bước gọi AI phức tạp và dễ dàng thực hiện Retry/Structured Output, trong khi con người (user) vẫn là người quyết định dữ liệu cuối cùng trên UI."

---
**💡 Câu chốt ăn điểm (Punchline):**
> *"Kiến trúc của dự án chuyển dịch từ 'AI sinh văn bản xác suất' sang một hệ thống 'truy xuất thông tin có cấu trúc, có xác thực và cho phép con người can thiệp (Human-in-the-loop)'. Đây là cách tiếp cận duy nhất khả thi cho bài toán học thuật vốn đòi hỏi độ chính xác tuyệt đối."*
