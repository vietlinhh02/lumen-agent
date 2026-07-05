# Tài liệu Thiết kế: Deep Research (Background Job + Reconnectable SSE)

## 1. Tổng quan

Deep Research là trải nghiệm **nghiên cứu học thuật tự động, toàn diện** — tái tạo cảm giác của **Gemini Deep Research**, tích hợp hoàn toàn với hệ thống backend hiện có (Projects, Papers, Matrix).

**Nguyên tắc cốt lõi & Ràng buộc UI:**
1. **Chỉ kích hoạt ở New Chat (Chưa link project):** Tính năng này chỉ xuất hiện ở các conversation mới tinh. Nếu conversation đã link với 1 project, Deep Research bị disable hoàn toàn (chỉ còn chat QA bình thường).
2. **Intent dựa trên ngữ cảnh:** Hỏi linh tinh/đơn giản → Chat bình thường. Hỏi nghiên cứu sâu → Kích hoạt Deep Research flow.
3. **Human-In-The-Loop (HITL):** Xác nhận thông tin Project (Title, Topic) trước khi chạy.
4. **Pipeline chạy nền:** Chạy ngầm, không chết khi user đóng tab.
5. **Full Progress Stream:** Stream chi tiết mọi hoạt động của agent ra UI.

---

## 2. Vấn đề: SSE + Long-running pipeline

Pipeline Deep Research mất **5-10 phút**. Nếu giữ SSE connection mở suốt:
- User đóng tab → TCP disconnect → `asyncio.CancelledError` → **pipeline bị kill**.
- Do đó, cần tách riêng Background Job ghi DB và SSE Stream đọc DB.

---

## 3. Luồng End-to-End Mới (Có Xác nhận User)

```
[PHASE 0 — Phân loại & Xác nhận (HITL)]

User tạo New Chat (session.project_id == NULL)
User nhắn: "Nghiên cứu về transformer models"

session_service.chat_with_graph():
  ├─ session.project_id != None? 
  │     → Bỏ qua Deep Research, route thẳng vào chat QA.
  │
  ├─ Classify intent:
  │     → Nếu là "chitchat", "ambiguous" → Route vào chat bình thường.
  │     → Nếu là "search/research" → Tiến hành setup Deep Research.
  │
  ├─ _extract_project_metadata(message):
  │     → LLM trích xuất Title, Topic, Research Question
  │
  └─ Trả về UI yêu cầu xác nhận (Không tạo Project ngay):
        emit MessageEvent: "Em đã phân tích yêu cầu. Anh xem qua project info nhé:"
        emit ActionEvent(type="confirm_project", data={title, topic, rq})
        → END luồng chat.

[PHASE 1 — User Xác nhận & Bắt đầu chạy ngầm]

User bấm nút [Bắt đầu Deep Research] trên UI → Gửi POST /chat với payload xác nhận.

session_service.chat_with_graph(action="start_deep_research"):
  ├─ create_project(title, topic, rq) → Lưu DB
  ├─ session.project_id = project.id (Link project vào Repo/Conversation luôn)
  ├─ Tạo DeepResearchJob(project_id, session_id, query)
  ├─ ensure_future(_run_deep_research(...))
  ├─ emit MessageEvent: "Đã bắt đầu nghiên cứu... Job ID: abc. Anh có thể đóng tab."
  └─ emit DoneEvent()

[PHASE 2 — Background chạy nền & Stream DB độc lập]

_run_deep_research(job_id, project_id, user_id, query):
  async with async_session_factory() as db:
      STEP 1: Auto Search & Save (ALL-IN-ONE)
        → Gọi auto_search_and_save(target_count=20)
        → Cập nhật DeepResearchJob: {progress: 0.1~0.65, stage:"search", chi tiết full log}

      STEP 2: Generate Matrix
        → Gọi _generate_matrix_impl()
        → Cập nhật DeepResearchJob: {progress: 0.65~0.85, stage:"matrix"}

      STEP 3: Detect Research Gaps
        → Gọi _detect_gaps_impl()
        → Cập nhật DeepResearchJob: {progress: 0.85~0.92, stage:"gap"}

      STEP 4: Generate Full Report
        → Gọi _generate_report_impl()
        → Cập nhật DeepResearchJob: {
              progress: 1.0, stage:"done", status:"done",
              report: report.content_markdown
          }

[PHASE 3 — Frontend hiển thị Full Stream]

Frontend gọi: GET /sessions/{id}/research/{job_id}/stream

SSE /stream endpoint:
  while True:
      job = DB.get(job_id)
      yield ProgressEvent(job.stage, job.progress, job.message)
      # Progress event sẽ chứa dầy đủ full stream (tìm thấy bao nhiêu bài, đang chấm bài nào...)
      if job.status == "done":
          for chunk in split_chunks(job.report):
              yield AssistantDeltaEvent(delta=chunk)
          yield DoneEvent()
          break
      await sleep(1)

[PHASE 4 — Kết thúc]
Từ giờ trở đi, conversation này đã có session.project_id != None.
Mọi câu hỏi tiếp theo của User sẽ chỉ rơi vào luồng Hỏi đáp (QA/React) bình thường trên dữ liệu đã thu thập. Deep Research KHÔNG kích hoạt lại nữa.
```

---

## 4. Tại sao cấu trúc này đáp ứng yêu cầu UI/UX?

1. **Lọc câu hỏi linh tinh:** Bước Phân loại (Intent Classification) diễn ra trước. Hỏi "Chào em" thì LLM trả lời "Chào anh", không sinh project, không hiện nút.
2. **Xác nhận trước khi chạy (HITL):** Tránh việc user gõ nhầm xong hệ thống tự tạo project rác. UI sẽ render một thẻ Project Preview, bấm "Chạy" mới bắt đầu.
3. **Link ngay lập tức:** Khi user bấm "Chạy", `session.project_id` được gán luôn. Trạng thái conversation chuyển sang "Linked".
4. **Khóa Deep Research:** Các câu chat sau sẽ thấy `session.project_id` đã tồn tại → Intent "search" cũng chỉ gọi tool search bình thường (RAG), không trigger Deep Research pipeline. Muốn Deep Research tiếp? User phải tạo New Chat.
5. **Full Stream:** Endpoint `/stream` lấy trực tiếp `job.progress_json`, frontend sẽ map cái json này ra các dòng log chi tiết nhất (đang search query gì, đang chấm điểm bài nào, tải PDF nào...).

---

## 5. API Endpoints cần bổ sung/chỉnh sửa

| Endpoint | Chức năng |
|---|---|
| `POST /sessions/{id}/chat` | Cần bắt thêm payload (ví dụ action object) khi user bấm nút Confirm |
| `GET /sessions/{id}/research/{job_id}` | Poll lấy trạng thái tức thời |
| `GET /sessions/{id}/research/{job_id}/stream` | Stream chi tiết 100% quá trình |

---

## 7. Yêu cầu UI/UX (Layout & Sidebar)

Để trải nghiệm giống Gemini Deep Research:
1. **Bố cục màn hình (Split View):**
   - Khi bấm "Bắt đầu nghiên cứu", giao diện chia làm 2 phần.
   - **Bên Trái:** Khung Chat (hiển thị typing effect của Báo cáo cuối cùng và các trao đổi với agent).
   - **Bên Phải:** Thẻ (Card) Info của Project + Giao diện Terminal/Log chi tiết quá trình Deep Research đang chạy (Stream).
2. **Sidebar (Recent Chat):**
   - Phải có nút Toggle (Đóng/Mở) để ẩn Sidebar Recent Chat đi. Việc này giúp mở rộng không gian tối đa cho 2 khung (Chat & Info Card) khi đang làm Deep Research.

---

## 8. Cấu trúc Payload Siêu Chi tiết (progress_json)

## 6. Data Model: DeepResearchJob

```python
class DeepResearchJob(Base):
    __tablename__ = "deep_research_jobs"

    id: UUID
    session_id: UUID
    project_id: UUID
    query: str
    status: str                     # "running" | "done" | "failed"
    stage: str                      # "init" | "search" | "matrix" | "gap" | "done"
    progress: float                 # 0.0 → 1.0
    message: str                    # Dòng log ngắn nhất
    progress_json: dict             # Full log chi tiết để stream lên UI
    report: str | None              # Báo cáo Markdown
    papers_saved: int
    created_at: datetime
    updated_at: datetime
```
