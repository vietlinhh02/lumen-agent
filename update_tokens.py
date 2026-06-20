import os
import re

files_to_update = [
    "app/agents/assistant/react/agent.py",
    "app/agents/assistant/graph/nodes.py",
    "app/agents/nodes.py",
    "app/agents/assistant/pipelines/research_pipeline.py",
    "app/agents/assistant/react/intent_classifier.py",
    "app/agents/assistant/react/router.py"
]

for filepath in files_to_update:
    if not os.path.exists(filepath):
        continue
    with open(filepath, "r") as f:
        content = f.read()

    # Replacements for agent.py, nodes.py, etc
    content = re.sub(r'max_tokens\s*=\s*\d+', 'max_tokens=32768', content)
    content = re.sub(r'_MAX_OUTPUT_TOKENS\s*=\s*\d+', '_MAX_OUTPUT_TOKENS = 32768', content)
    content = re.sub(r'_COLLABORATIVE_MATRIX_MAX_TOKENS\s*=\s*\d+', '_COLLABORATIVE_MATRIX_MAX_TOKENS = 32768', content)

    with open(filepath, "w") as f:
        f.write(content)

print("Done updating tokens.")
