# Lumen Technical Q&A (Bộ Câu Hỏi & Đáp Kỹ Thuật Cho Demo Day)

Tài liệu này tổng hợp các câu hỏi kỹ thuật chuyên sâu về cấu trúc hệ thống (Tech Stack) và logic mã nguồn (Code Logic) của **Lumen**. Các câu hỏi được thiết kế dựa trên kiến trúc thực tế của dự án nhằm giúp nhóm chuẩn bị tốt nhất cho các câu hỏi chất vấn từ Hội đồng Ban giám khảo công nghệ (Tech Judges) trong Demo Day.

---

## 🛠️ PHẦN 1: CÂU HỎI VỀ TECH STACK & KIẾN TRÚC HỆ THỐNG

### 🎤 Q1: Tại sao nhóm lại lựa chọn FastAPI (Python) cho Backend mà không phải Express.js (Node.js) hay Spring Boot (Java)?
**Trả lời:**
1. **Hỗ trợ sinh thái AI/ML mạnh mẽ:** Ecosystem của Python là tốt nhất cho các bài toán AI, xử lý ngôn ngữ tự nhiên (NLP) và RAG (với các thư viện như LangGraph, OpenAI SDK, pgvector driver).
2. **Hiệu năng cao nhờ AsyncIO:** FastAPI được xây dựng trên nền tảng Starlette và Uvicorn, hỗ trợ xử lý bất đồng bộ (`async`/`await`) cực kỳ mạnh mẽ. Đối với các tác vụ có độ trễ I/O cao như gọi API của LLM, API tìm kiếm bài báo (arXiv, Semantic Scholar), việc chạy bất đồng bộ giúp backend của Lumen xử lý hàng chục kết nối song song mà không bị nghẽn (blocking).
3. **Tự động sinh tài liệu API (OpenAPI/Swagger):** Tiết kiệm thời gian đồng bộ tài liệu giữa Frontend và Backend.

---

### 🎤 Q2: Frontend sử dụng Next.js 16 (App Router) và React 19. Những tính năng mới nào của phiên bản này đã được áp dụng?
**Trả lời:**
* **React Server Components (RSC):** Chúng tôi tận dụng Server Components để render các giao diện tĩnh và tải dữ liệu ban đầu trực tiếp trên server, giúp giảm tối đa dung lượng Javascript tải về client, cải thiện chỉ số FCP (First Contentful Paint).
* **React 19 Actions:** Sử dụng cơ chế xử lý form và tương tác bất đồng bộ mới giúp tối ưu hóa state loading và quản lý lỗi dễ dàng hơn mà không cần viết quá nhiều code Boilerplate.
* **Tailwind CSS v4:** Sử dụng engine Lightning CSS mới giúp build style nhanh hơn gấp 10 lần, đồng thời cấu hình CSS hoàn toàn bằng CSS variables hiện đại thay vì file `tailwind.config.js` cồng kềnh.

---

### 🎤 Q3: Tại sao nhóm chọn PostgreSQL + `pgvector` thay vì một cơ sở dữ liệu Vector chuyên dụng như Pinecone, Milvus hay Qdrant?
**Trả lời:**
1. **Tính nhất quán dữ liệu (ACID):** Lumen quản lý dữ liệu có cấu trúc quan hệ chặt chẽ (Users, Projects, Papers, MatrixRows, ResearchGaps). Việc dùng chung PostgreSQL giúp thực hiện các giao dịch (Transactions) an toàn, tránh tình trạng lệch pha dữ liệu giữa thông tin bài báo và vector nhúng.
2. **Hybrid Query mạnh mẽ:** pgvector cho phép viết các câu truy vấn SQL kết hợp giữa lọc quan hệ và tìm kiếm ngữ nghĩa cực kỳ gọn nhẹ. Ví dụ: Lọc các bài báo thuộc dự án X, trạng thái đã lưu, rồi tìm vector gần nhất. Điều này rất khó thực hiện hiệu quả và nhất quán nếu dùng Vector DB rời.
3. **Tiết kiệm chi phí & Dễ vận hành:** Không cần phải duy trì và trả phí cho 2 dịch vụ database riêng biệt. pgvector với chỉ mục HNSW (Hierarchical Navigable Small World) cung cấp hiệu năng tìm kiếm tương đương các Vector DB chuyên dụng cho tập dữ liệu trung bình và lớn.

---

### 🎤 Q4: LangGraph đóng vai trò gì trong kiến trúc Agent của hệ thống? Tại sao không dùng LangChain thông thường?
**Trả lời:**
* **Kiểm soát luồng trạng thái phức tạp (Stateful Multi-Agent Workflows):** Quy trình của Lumen không phải là một chuỗi tuần tự đơn giản. Nó yêu cầu các bước lặp (Loops), kiểm tra điều kiện (Conditional Edges), và con người can thiệp (Human-in-the-loop). 
* **LangGraph** định nghĩa luồng xử lý dưới dạng Đồ thị có hướng (Directed Graph) nơi mỗi Node là một hàm xử lý (Enrich, Matrix, Gap, Report) và mỗi Edge quy định luồng di chuyển của State dự án. LangGraph giúp quản lý State nhất quán qua các bước và hỗ trợ cơ chế lưu vết (Persistence) để khôi phục/sửa đổi khi cần thiết.

---

## 💻 PHẦN 2: CÂU HỎI VỀ LOGIC CODE & THUẬT TOÁN CỐT LÕI

### 🎤 Q5: Logic của công nghệ Hybrid Retrieval (Tìm kiếm kết hợp) hoạt động như thế nào trong Code?
**Trả lời:**
Hệ thống sử dụng quy trình 5 bước được triển khai tại file [hybrid_retrieval.py](file:///home/eddiesngu/Desktop/VinUni/C2-App-053/app/services/hybrid_retrieval.py) (Hàm `retrieve_project_evidence`):
1. **Mở rộng truy vấn (Query Expansion):** AI dựa trên đồ thị tri thức hiện tại của dự án để làm phong phú câu truy vấn của người dùng.
2. **Tìm kiếm ngữ nghĩa (Vector Search):** Sử dụng hàm khoảng cách cosine của `pgvector` trên SQL để lấy ra các chunk văn bản có độ tương đồng ngữ nghĩa cao nhất thuộc dự án hiện tại (bỏ qua các bài báo bị gắn nhãn `low relevance`).
3. **Tính điểm từ khóa (Keyword Scoring - BM25-like):** Tính tần suất xuất hiện của các token truy vấn trong tiêu đề và nội dung chunk.
4. **Trộn điểm (Score Blending):** Kết hợp điểm vector và điểm từ khóa theo trọng số, đồng thời nhân hệ số tăng cường (Section Boosts) cho các phần quan trọng như `limitation` (hệ số tăng 0.16) hay `results` (hệ số tăng 0.12).
5. **Reranking (Tái xếp hạng):** Chạy qua mô hình Cross-Encoder để chọn ra top $K$ chunks làm ngữ cảnh (Context) tối ưu nhất cho LLM.

---

### 🎤 Q6: Hệ thống bảo vệ trích dẫn (Citation Guardrail) hoạt động thế nào để cam kết 0% trích dẫn bịa đặt?
**Trả lời:**
Hệ thống phòng ngự bằng code backend nghiêm ngặt, cụ thể nằm ở hàm `_validate_citations` trong [report_generation.py](file:///home/eddiesngu/Desktop/VinUni/C2-App-053/app/services/report_generation.py#L934-L985):
1. **Ép cấu trúc đầu ra (Structured Output):** LLM bắt buộc phải trả về dữ liệu có cấu trúc JSON (sử dụng Pydantic schema `ReviewOutput`), trong đó mỗi phân đoạn văn bản phải đi kèm danh sách các ID của bài báo được trích dẫn (`citation_paper_ids`).
2. **Đối chiếu CSDL quan hệ:** Khi LLM trả về kết quả, backend sẽ truy vấn trực tiếp bảng `project_papers` để lấy tập hợp các UUID bài báo hợp lệ đang được lưu trữ trong dự án (`valid_pp_ids`).
3. **Lọc và Loại bỏ cứng:** Backend duyệt qua từng đoạn văn, kiểm tra xem `citation_paper_ids` do LLM sinh ra có nằm trong tập `valid_pp_ids` hay không. 
   - Nếu ID trích dẫn không hợp lệ (không tồn tại trong dự án), ID đó sẽ bị xóa bỏ khỏi đoạn văn.
   - Nếu một đoạn văn hoàn toàn chứa các trích dẫn ảo giác (không có ID nào hợp lệ), đoạn văn đó sẽ bị xóa bỏ hoàn toàn khỏi báo cáo để đảm bảo tính xác thực học thuật.

---

### 🎤 Q7: Logic kiểm duyệt phát biểu số liệu (Numeric Claim Grounding Audit) hoạt động như thế nào?
**Trả lời:**
Đây là tính năng độc đáo được triển khai ở hàm `_audit_claim_grounding` trong [report_generation.py](file:///home/eddiesngu/Desktop/VinUni/C2-App-053/app/services/report_generation.py#L1656-L1730):
1. **Trích xuất số liệu bằng Regex:** Backend dùng Regex quét qua văn bản báo cáo để bắt các tuyên bố chứa số liệu định lượng (phần trăm, tỷ lệ, con số cụ thể, số lượng tokens...).
2. **Quét đối chiếu ngữ cảnh gốc:** Với mỗi số liệu tìm thấy trong một đoạn văn, hệ thống sẽ đối chiếu trực tiếp với toàn bộ các chunks văn bản gốc đã trích xuất từ PDF của bài báo được trích dẫn trong đoạn văn đó.
3. **Đánh giá Grounding:** Nếu con số đó hoàn toàn không xuất hiện trong bất kỳ chunk tài liệu gốc nào của bài báo được trích dẫn, hệ thống sẽ đánh nhãn số liệu này là `ungrounded` (chưa được xác thực) và ghi nhận vào log báo cáo kiểm định để người dùng nhận biết và chỉnh sửa.

---

### 🎤 Q8: Hệ thống giải quyết bài toán tải & xử lý PDF lớn một cách đồng thời (High Concurrency) như thế nào để tránh tràn bộ nhớ hoặc nghẽn mạng?
**Trả lời:**
Hệ thống sử dụng các kỹ thuật xử lý bất đồng bộ tiên tiến:
1. **Bất đồng bộ hóa I/O:** Sử dụng thư viện `httpx` bất đồng bộ để tải các file PDF từ Internet.
2. **Quản lý luồng bằng Semaphore:** Trong quá trình sinh các phần khác nhau của báo cáo tổng quan một cách song song (Parallel Section Generation), hệ thống giới hạn mức độ chạy đồng thời bằng một biến `asyncio.Semaphore(concurrency_limit)` (ở đây thiết lập bằng 4). Điều này giúp hệ thống không gọi LLM dồn dập vượt quá rate limit của API và kiểm soát tốt lượng RAM tiêu thụ khi phân tích cú pháp PDF.
3. **Xử lý nền (Background Tasks):** Các tác vụ tốn thời gian như phân tích cấu trúc PDF và nhúng vector được chuyển vào chạy dưới dạng Background Task của FastAPI hoặc hàng đợi Celery, giúp API trả về phản hồi lập tức cho UI để hiển thị trạng thái tải (Loading) mà không bắt người dùng đợi phản hồi HTTP đồng bộ.

---

### 🎤 Q9: Làm thế nào để gộp các bài viết trùng lặp (Deduplication) khi tìm kiếm từ nhiều API học thuật khác nhau?
**Trả lời:**
Trong dịch vụ tìm kiếm bài báo, hệ thống sử dụng thuật toán chuẩn hóa và so khớp mã định danh:
1. **So khớp mã định danh cứng:** Nếu hai bài báo từ 2 nguồn khác nhau có chung mã `DOI` (Digital Object Identifier) hoặc `arxiv_id` hoặc `semantic_scholar_id`, chúng lập tức được gộp làm một.
2. **So khớp mềm (Normalized Title Matching):** Nếu không có mã định danh cứng, hệ thống sẽ chuẩn hóa tiêu đề bằng cách viết thường, loại bỏ toàn bộ khoảng trắng thừa và ký tự đặc biệt. Nếu chuỗi tiêu đề chuẩn hóa trùng khớp hoàn toàn hoặc đạt độ tương đồng cao (Levenshtein distance), hệ thống sẽ coi chúng là một bài báo và gộp siêu dữ liệu (metadata) lại, ưu tiên hiển thị nguồn có nhiều thông tin chi tiết hơn.

---

### 🎤 Q10: Làm thế nào hệ thống hỗ trợ Custom Extraction Schema (T4) trong Code? Khi người dùng tùy chỉnh các trường của Ma trận tài liệu, làm thế nào LLM có thể trích xuất chính xác theo schema động đó?
**Trả lời:**
1. **Sinh Pydantic Model động (Dynamic Pydantic Models):** Thay vì sử dụng một Pydantic model tĩnh cho tất cả các dự án, backend sử dụng hàm `pydantic.create_model` tại thời điểm chạy (runtime) để tạo ra schema đầu ra động dựa trên danh sách các trường (`FieldDefinition`) được cấu hình trong database cho dự án đó (bao gồm tên trường, kiểu dữ liệu: string/number/boolean/enum, và mô tả chi tiết).
2. **Trích xuất có cấu trúc qua JSON Schema (Structured Output):** Pydantic model động này được chuyển thành JSON Schema và truyền vào API của các LLM hỗ trợ `response_format` dạng JSON Schema (ví dụ: `response_format={"type": "json_object", "schema": ...}` của OpenAI hoặc thông qua các công cụ ép kiểu cấu trúc như Instructor). Điều này ép buộc LLM phải trả về định dạng JSON chính xác khớp với cấu hình tùy chỉnh của người dùng.
3. **Lưu trữ linh hoạt (Flexible JSONB Storage):** Dữ liệu được trích xuất sẽ được lưu vào một trường JSONB `custom_fields` trong bảng `LiteratureMatrixRow`, cho phép truy vấn nhanh và lọc dữ liệu linh hoạt trên SQL mà không cần thay đổi cấu trúc bảng (schema migrations) của database.

---

### 🎤 Q11: Thuật toán gom cụm (Clustering) và đồng thuận hóa (Consensus Synthesis - T7) hoạt động như thế nào để tổng hợp các phát biểu nghiên cứu tương tự nhau từ nhiều bài báo?
**Trả lời:**
1. **Gom cụm bằng Nhúng & Học máy (Embedding & Clustering):** Các ứng viên phát biểu (candidate claims) trích xuất từ Ma trận và các phát hiện mâu thuẫn được nhúng thành vector (embeddings). Hệ thống sử dụng thuật toán gom cụm mật độ (như HDBSCAN hoặc Agglomerative Clustering với khoảng cách Cosine) để nhóm các phát biểu có ngữ nghĩa tương tự nhau lại thành một cụm (Cluster), loại bỏ các điểm nhiễu (noise).
2. **Đồng thuận hóa qua LLM (LLM Canonicalization):** Với mỗi cụm thu được, backend truyền các phát biểu con cùng thông tin bài báo tương ứng vào LLM để sinh ra một phát biểu chuẩn duy nhất (Canonical Claim), phân loại tính chất đồng thuận của cụm (`support`, `contradict`, `mixed`, `weak`), và lưu vết trích dẫn ngược về từng bài viết gốc thông qua bảng `ClaimEvidence`.
3. **Công thức tính điểm tin cậy (Confidence Scoring Formula):** Điểm tin cậy của một phát biểu được tính toán dựa trên số lượng nguồn đồng thuận, độ tin cậy trích xuất trung bình từ ma trận, và tuổi của bài viết (áp dụng phân rã lũy thừa theo thời gian - recency decay) nhằm ưu tiên các kết luận mới và được kiểm chứng nhiều nhất.

---

### 🎤 Q12: Làm thế nào hệ thống tối ưu hóa hiệu năng tìm kiếm Vector (Vector Search) bằng pgvector trong PostgreSQL để đạt độ trễ cực thấp (< 1.8 giây)?
**Trả lời:**
1. **Chỉ mục HNSW (Hierarchical Navigable Small World):** Chúng tôi xây dựng chỉ mục HNSW trên cột vector của bảng `project_paper_chunks` bằng cách chạy lệnh SQL tạo index: `CREATE INDEX ON project_paper_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`. Chỉ mục HNSW cho tốc độ tìm kiếm nhanh vượt trội và độ chính xác (recall) tốt hơn so với chỉ mục IVFFlat truyền thống.
2. **Giới hạn không gian tìm kiếm (Pre-filtering):** Tận dụng lọc cứng theo `project_id` và `relevance_label` trước khi tính toán khoảng cách vector. Điều này thu hẹp phạm vi quét từ hàng triệu dòng xuống còn vài trăm dòng thuộc dự án hiện tại, giúp câu lệnh SQL thực thi trong mili-giây.
3. **Tuning tham số `hnsw.ef_search`:** Thiết lập giá trị `ef_search` thích hợp ở mức 32 đến 64 trong phiên kết nối database để cân bằng giữa độ chính xác của kết quả và tốc độ tìm kiếm.

---

### 🎤 Q13: PDF khoa học thường có cấu trúc phức tạp (cột kép, bảng biểu, công thức toán học). Làm thế nào Lumen parse PDF để thu được dữ liệu sạch cho RAG?
**Trả lời:**
1. **Layout-aware Extraction (Trích xuất theo bố cục):** Thay vì đọc văn bản tuần tự từ trái sang phải làm lẫn lộn dữ liệu giữa hai cột, hệ thống sử dụng thư viện trích xuất nhận biết layout (như `PyMuPDF` hoặc tích hợp API parser chuyên dụng như LlamaParse/Unstructured) để nhận diện các khối văn bản (blocks) và sắp xếp chúng theo đúng thứ tự đọc của con người.
2. **Lọc và chuẩn hóa công thức (Math & Equation Normalization):** Nhận diện các ký tự đặc biệt, ký hiệu toán học và chuyển đổi chúng sang định dạng văn bản chuẩn (như LaTeX hoặc Unicode đơn giản) để bộ mã hóa (Embedding model) có thể hiểu được ngữ nghĩa thay vì biến thành các ký tự rác.
3. **Trích xuất bảng biểu có cấu trúc:** Đối với bảng dữ liệu, hệ thống chuyển đổi chúng thành định dạng Markdown Table hoặc cấu trúc JSON để đưa vào chunk RAG, giữ nguyên được mối liên hệ hàng-cột của số liệu.

---

### 🎤 Q14: Làm thế nào hệ thống kiểm soát được chi phí gọi API LLM (chỉ ~$0.002/bài viết) và tránh bị lỗi Rate Limit khi xử lý nhiều tài liệu cùng lúc?
**Trả lời:**
1. **Sử dụng mô hình lai (Hybrid LLM Architecture):** Chúng tôi phân tách nhiệm vụ dựa trên độ khó. Các tác vụ cần tư duy phức tạp (như phân tích lỗ hổng nghiên cứu, đồng thuận hóa) được giao cho mô hình cao cấp (như mimo-v2.5-pro). Các tác vụ xử lý lặp đi lặp lại có lượng token lớn (như trích xuất ma trận ban đầu, tóm tắt sơ bộ từng chunk) được giao cho mô hình tối ưu chi phí (mimo-v2.5).
2. **Bộ nhớ đệm thông minh (Semantic Caching & DB Cache):** Các chunk PDF sau khi trích xuất và kết quả xử lý ma trận của từng bài báo được lưu trữ lâu dài trong cơ sở dữ liệu. Khi có yêu cầu tạo báo cáo mới, hệ thống tái sử dụng hoàn toàn dữ liệu có sẵn thay vì bắt AI trích xuất lại từ đầu.
3. **Kiểm soát luồng gọi API (Rate-Limiting & Backoff):** Triển khai cơ chế Exponential Backoff với Jitter khi gọi API của LLM providers, kết hợp sử dụng `asyncio.Semaphore` để giới hạn số lượng request chạy đồng thời (concurrency limit = 4).

---

### 🎤 Q15: Nhóm đánh giá và đo lường chất lượng hệ thống RAG (Retrieval-Augmented Generation) như thế nào để đảm bảo hệ thống luôn cải tiến?
**Trả lời:**
1. **Bộ chỉ số RAG Triad (Đo lường 3 góc):** Chúng tôi sử dụng framework đánh giá tự động (như Ragas/TruLens) để chấm điểm trên 3 trục cốt lõi:
   - **Context Relevance (Độ liên quan ngữ cảnh):** Đảm bảo RAG chỉ lấy ra các chunk thực sự trả lời cho câu hỏi.
   - **Faithfulness (Độ trung thực):** Đảm bảo câu trả lời của AI được rút ra hoàn toàn từ ngữ cảnh trích xuất, không tự ý suy diễn (Grounding).
   - **Answer Relevance (Độ liên quan của câu trả lời):** Đảm bảo câu trả lời giải quyết trực tiếp truy vấn của người dùng.
2. **Bộ dữ liệu kiểm thử Offline (Golden Dataset):** Xây dựng một tập hợp hơn 50 cặp (Query - Context - Ground Truth) được viết tay bởi các nghiên cứu sinh nhằm chạy benchmark tự động mỗi khi cập nhật Prompt hoặc thuật toán RAG.
3. **Thu thập phản hồi từ người dùng (Implicit & Explicit Feedback):** Tích hợp nút Thumbs Up/Down trên mỗi ô của Literature Matrix và từng đoạn văn bản của báo cáo, lưu log phản hồi của người dùng vào database để liên tục hiệu chỉnh thuật toán thu hồi (retrieval heuristics).
