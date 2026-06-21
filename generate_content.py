import os
from datetime import datetime

import feedparser
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel("gemini-2.5-flash")

# Read RSS feeds

feeds = []

with open("news_sources.txt", "r") as f:
    feeds = [line.strip() for line in f if line.strip()]

articles = []

for feed in feeds:
try:
rss = feedparser.parse(feed)

```
    for entry in rss.entries[:5]:
        articles.append({
            "title": entry.title,
            "link": entry.link
        })

except Exception:
    pass
```

news_text = ""

for i, article in enumerate(articles[:20], start=1):
news_text += f"{i}. {article['title']}\n"

prompt = f"""
You are Abhedit's Cybersecurity Intelligence Agent.

Select the single most important cybersecurity story from these headlines:

{news_text}

Create:

1. Story Selection Reason
2. Source Headline
3. 6 Slide Carousel

Slide 1 - Breaking News
Slide 2 - What Happened
Slide 3 - Key Findings
Slide 4 - Business Impact
Slide 5 - Recommendations
Slide 6 - Follow Abhedit

4. LinkedIn Post
5. Facebook Post
6. Instagram Caption
7. 20 Hashtags

Audience:

* CISOs
* Security Architects
* Security Engineers
* GRC Teams
* Privacy Professionals

Tone:
Professional
Business-focused
Actionable

Output in markdown.
"""

response = model.generate_content(prompt)

content = response.text

os.makedirs("output", exist_ok=True)

with open("output/content.md", "w", encoding="utf-8") as f:
f.write("# Abhedit Daily Cybersecurity Content\n\n")
f.write(f"Generated on: {datetime.utcnow()}\n\n")
f.write(content)

print("Content generated successfully.")
