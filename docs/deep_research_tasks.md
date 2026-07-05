# Deep Research Implementation Tasks

Dựa trên tài liệu thiết kế `docs/deep_research.md`, tôi đã chia nhỏ các công việc cần thiết để dễ dàng triển khai tính năng Deep Research.

## 1. Backend - Database & Data Models
- [x] **Tạo model `DeepResearchJob`:** Định nghĩa schema `DeepResearchJob` bằng SQLAlchemy. Các trường cần thiết: `id`, `session_id`, `project_id`, `query`, `status`, `stage`, `progress`, `message`, `progress_json`, `report`, `papers_saved`, `created_at`, `updated_at`.
- [x] **Tạo DB Migration:** Khởi tạo và chạy script migration (Alembic) để tạo bảng `deep_research_jobs` trong cơ sở dữ liệu.

## 2. Backend - Core Logic & Agent Routing (PHASE 0 & 1)
- [x] **Cập nhật hàm `session_service.chat_with_graph()`:** 
  - Thêm logic kiểm tra: Nếu `session.project_id` đã tồn tại, tự động chuyển (bypass) sang luồng chat QA bình thường (không kích hoạt Deep Research).
- [x] **Intent Classification:** Nếu là New Chat, phân loại câu hỏi (chitchat/đơn giản vs. deep research).
- [x] **Trích xuất Metadata:** Viết prompt/logic `_extract_project_metadata(message)` để trích xuất Title, Topic, Research Question từ câu lệnh của User.
- [x] **HITL (Human-in-the-loop):** Gửi phản hồi về FE yêu cầu User xác nhận thông tin project:
  - `emit MessageEvent("Em đã phân tích...")`
  - `emit ActionEvent(type="confirm_project", data={title, topic, rq})`
- [x] **Xử lý Action Xác nhận (POST `/sessions/{id}/chat`):** 
  - Bổ sung việc tiếp nhận payload action `start_deep_research`.
  - Thực hiện lưu database cho Project (tạo Project mới).
  - Link `project_id` vào session hiện tại.
  - Khởi tạo 1 record `DeepResearchJob` mới trong DB.
  - Trigger job chạy nền và báo về FE `MessageEvent("Đã bắt đầu nghiên cứu...")`.

## 3. Backend - Background Worker Pipeline (PHASE 2)
- [x] **Tạo hàm Background Task:** Tạo `_run_deep_research(job_id, project_id, user_id, query)` chạy độc lập khỏi request hiện tại (VD dùng `asyncio.ensure_future`).
- [x] **Tích hợp các Core Services (Step 1-4):**
  - Thực thi `auto_search_and_save(target_count=20)` cho Step 1.
  - Gọi hàm `_generate_matrix_impl()` cho Step 2.
  - Gọi hàm `_detect_gaps_impl()` cho Step 3.
  - Gọi hàm `_generate_report_impl()` để tạo báo cáo cuối cùng cho Step 4.
- [x] **Cập nhật Progress DB:** Tại mỗi Step, cần cập nhật liên tục tiến độ (progress float từ 0.0 -> 1.0, stage hiện tại, message log) vào trường `progress_json` và status của `DeepResearchJob`.

## 4. Backend - API Endpoints & SSE Stream (PHASE 3)
- [x] **API Trạng thái tức thời:** Tạo endpoint `GET /sessions/{id}/research/{job_id}` để frontend có thể poll lấy thông tin (nếu cần xử lý reconnect).
- [x] **API Stream SSE:** Tạo endpoint `GET /sessions/{id}/research/{job_id}/stream`
  - Setup vòng lặp `while True` kết nối trực tiếp với DB record.
  - Trả về `ProgressEvent` chứa các step stream.
  - Khi hoàn thành, đọc `job.report` và yield về thành từng chunk qua `AssistantDeltaEvent` để FE làm hiệu ứng typing.

## 5. Frontend - UI/UX & Flow (PHASE 0, 1, 3, 4)
- [x] **Xử lý Layout Bố cục (Split View):** 
  - Chia màn hình thành 2 phần khi Deep Research kích hoạt: Cột trái (Chat/Report) và Cột phải (Project Info + Terminal Logs).
- [x] **Nút Toggle Sidebar:** Thêm chức năng đóng/mở sidebar "Recent Chats" để người dùng mở rộng không gian đọc nghiên cứu.
- [x] **Project Preview Card & Confirm Button:** 
  - Bắt sự kiện `ActionEvent(confirm_project)`.
  - Hiển thị UI Confirm Project Card (Title, Topic, RQ).
  - Thêm nút [Bắt đầu Deep Research] gọi về backend với action xác nhận.
- [x] **Consume SSE & Terminal Log UI:**
  - Gọi GET `/stream` API.
  - Cập nhật UI thanh tiến trình và danh sách "Terminal-like logs" phản hồi thời gian thực từ `progress_json` của backend.
- [x] **Hiển thị Báo cáo Final & Trạng thái Linked:**
  - Bắt sự kiện `AssistantDeltaEvent` stream về từ Deep Research để hiển thị nội dung báo cáo dạng markdown.
  - Cập nhật trạng thái session sang "Linked" để những lần chat sau gọi trực tiếp vào luồng QA RAG bình thường (disable Deep Research cho lần hỏi kế).
