import os
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel("gemini-2.5-flash")

prompt = """
You are Abhedit's cybersecurity content creator.

Create:

1. Cybersecurity Headline
2. LinkedIn Post
3. Facebook Post
4. Instagram Caption
5. 20 Hashtags

Audience:
- CISOs
- Security Architects
- Security Engineers
- GRC Teams
- Privacy Professionals

Tone:
Professional
Business-focused
Actionable

Topic:
Latest cybersecurity threat trends and enterprise security risks.
"""

response = model.generate_content(prompt)

content = response.text

os.makedirs("output", exist_ok=True)

with open("output/content.md", "w", encoding="utf-8") as f:
    f.write("# Abhedit Daily Cybersecurity Content\n\n")
    f.write(f"Generated on: {datetime.utcnow()}\n\n")
    f.write(content)

print("Content generated successfully.")
