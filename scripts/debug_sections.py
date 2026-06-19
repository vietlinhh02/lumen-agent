from app.services.pdf_ingestion import _detect_sections
from pathlib import Path

txt_path = Path("data/papers/2604.04185.txt")
if txt_path.exists():
    text = txt_path.read_text()
    sections = _detect_sections(text)
    print(f"Detected {len(sections)} sections:")
    for s in sections:
        print(f" - {s.name} (lines {s.start_line}-{s.end_line})")
else:
    print("File not found.")
