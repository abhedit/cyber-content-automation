import os
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel("gemini-2.5-flash")

prompt = """
You are Abhedit's Daily Cybersecurity Intelligence Agent.

Company:
Abhedit

Audience:

* CISOs
* Security Architects
* Security Engineers
* GRC Teams
* Privacy Professionals

Your task is to generate a DAILY cybersecurity intelligence package.

Requirements:

1. Select ONE major cybersecurity incident, breach, vulnerability, ransomware campaign, nation-state attack, supply chain attack, or security advisory from the last 7 days.

2. Explain the incident accurately.

3. Create:

## 6-Slide Carousel

Slide 1:
Breaking Cybersecurity News

Slide 2:
What Happened

Slide 3:
Key Findings

Slide 4:
Business Impact

Slide 5:
Recommendations

Slide 6:
Follow Abhedit

## LinkedIn Post

Professional and executive-focused.

## Facebook Post

Awareness-focused.

## Instagram Caption

Short and engaging.

## 20 Hashtags

Requirements:

* Business focused
* Actionable
* Professional
* Modern
* No fluff
* No emojis except where useful
* Write for enterprise security leaders

Output in markdown format.
"""


response = model.generate_content(prompt)

content = response.text

os.makedirs("output", exist_ok=True)

with open("output/content.md", "w", encoding="utf-8") as f:
    f.write("# Abhedit Daily Cybersecurity Content\n\n")
    f.write(f"Generated on: {datetime.utcnow()}\n\n")
    f.write(content)

print("Content generated successfully.")
