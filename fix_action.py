import re

with open("app/services/assistant/session_service.py", "r") as f:
    code = f.read()

# Thay vì tìm cách sửa bằng sed, ta dùng python regex để chèn đoạn xử lý action vào sau user loading
# Tìm dòng "# Get tools" để chèn lên trước

action_logic = """
            if action == "start_deep_research":
                import json
                try:
                    action_data = json.loads(message)
                except Exception:
                    action_data = {}
                    
                title = action_data.get("title", "Deep Research")
                topic = action_data.get("topic", "Topic")
                research_question = action_data.get("research_question", None)
                query = action_data.get("message", "start")
                
                from app.schemas.project import ProjectCreate
                from app.services.project import create_project
                from app.db.models import DeepResearchJob
                import asyncio
                from app.services.assistant.deep_research_worker import run_deep_research
                
                # 1. Create project
                auto_project = await create_project(
                    self.db,
                    user,
                    ProjectCreate(title=title, topic=topic, research_question=research_question)
                )
                session.project_id = auto_project.id
                await self.db.commit()
                
                # 2. Create job
                job_id = uuid.uuid4()
                job = DeepResearchJob(
                    id=job_id,
                    session_id=session.id,
                    project_id=auto_project.id,
                    query=query,
                    status="running"
                )
                self.db.add(job)
                await self.db.commit()
                
                # 3. Trigger worker
                asyncio.create_task(run_deep_research(str(job_id), str(auto_project.id), str(user.id), query))
                
                yield MessageEvent(
                    role="assistant",
                    content=f"Đã bắt đầu nghiên cứu sâu cho: **{title}**.\nJob ID: `{job_id}`\nTiến trình sẽ được cập nhật tự động."
                )
                yield DoneEvent(summary="Deep research started.")
                return

"""

code = code.replace("            # Get tools", action_logic + "            # Get tools")

with open("app/services/assistant/session_service.py", "w") as f:
    f.write(code)

