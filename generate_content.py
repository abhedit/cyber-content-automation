import os
from datetime import datetime

import feedparser
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel("gemini-2.5-flash")

# Read RSS feeds
with open("news_sources.txt", "r") as f:
    feeds = [line.strip() for line in f if line.strip()]

articles = []

for feed in feeds:
    try:
        rss = feedparser.parse(feed)

        for entry in rss.entries[:5]:
            articles.append({
                "title": entry.title,
                "link": entry.link
            })

    except Exception as e:
        print(f"Error reading feed {feed}: {e}")

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
4. LinkedIn Post
5. Facebook Post
6. Instagram Caption
7. 20 Hashtags
8. 6 Image Prompts

Audience:
- CISOs
- Security Architects
- Security Engineers
- GRC Teams
- Privacy Professionals

Tone:
- Professional
- Business-focused
- Actionable

For Image Prompts:

Generate one prompt for each carousel slide.

Requirements:
- White background
- Dark blue cybersecurity theme
- Modern enterprise design
- LinkedIn carousel style
- Modern typography
- Minimalist layout
- Premium corporate appearance
- High-end corporate branding
- Suitable for CISOs and Security Architects
- 1080x1080

Format:

Slide 1 Prompt:
...

Slide 2 Prompt:
...

Slide 3 Prompt:
...

Slide 4 Prompt:
...

Slide 5 Prompt:
...

Slide 6 Prompt:
...

Output in markdown.
"""

response = model.generate_content(prompt)

content = response.text

os.makedirs("output", exist_ok=True)

files = [
    "content.md",
    "carousel.md",
    "linkedin.md",
    "facebook.md",
    "instagram.md",
    "hashtags.md",
    "image_prompts.md"
]

for filename in files:
    with open(f"output/{filename}", "w", encoding="utf-8") as f:
        f.write(content)

print("Content generated successfully.")
