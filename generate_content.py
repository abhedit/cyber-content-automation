import os
from datetime import datetime
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"]
)

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

prompt = """
You are Abhedit's cybersecurity content creator.

Create:

1. Cybersecurity headline
2. LinkedIn post
3. Instagram caption
4. 10 hashtags

Topic:
Latest cybersecurity threat trends.

Professional tone.
Business focused.
"""

response = client.responses.create(
    model=MODEL,
    input=prompt
)

content = response.output_text

os.makedirs("output", exist_ok=True)

with open("output/content.md", "w", encoding="utf-8") as f:
    f.write(f"# Abhedit Daily Content\n\n")
    f.write(f"Generated on: {datetime.utcnow()}\n\n")
    f.write(content)

print("Content generated successfully.")
