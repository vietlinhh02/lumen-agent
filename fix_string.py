with open("app/services/assistant/session_service.py", "r") as f:
    text = f.read()

text = text.replace('content=f"Đã bắt đầu nghiên cứu sâu cho: **{title}**.\nJob ID: `{job_id}`\nTiến trình sẽ được cập nhật tự động."', 'content=f"Đã bắt đầu nghiên cứu sâu cho: **{title}**.\\nJob ID: `{job_id}`\\nTiến trình sẽ được cập nhật tự động."')

with open("app/services/assistant/session_service.py", "w") as f:
    f.write(text)
