import os
from datetime import datetime

import feedparser
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel("gemini-2.5-flash")

# Load knowledge files

with open("knowledge/content-universe.md", "r", encoding="utf-8") as f:
    content_universe = f.read()

with open("knowledge/content-strategy.md", "r", encoding="utf-8") as f:
    content_strategy = f.read()

with open("knowledge/content-sources.md", "r", encoding="utf-8") as f:
    content_sources = f.read()

with open("knowledge/platform-strategy.md", "r", encoding="utf-8") as f:
    platform_strategy = f.read()

with open("knowledge/content-decision-framework.md", "r", encoding="utf-8") as f:
    content_decision_framework = f.read()
    
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
ABHEDIT KNOWLEDGE BASE

CONTENT UNIVERSE:
{content_universe}

CONTENT STRATEGY:
{content_strategy}

CONTENT SOURCES:
{content_sources}

PLATFORM STRATEGY:
{platform_strategy}

CONTENT DECISION FRAMEWORK:
{content_decision_framework}

CONTENT SOURCES:
{content_sources}

PLATFORM STRATEGY:
{platform_strategy}

CONTENT DECISION FRAMEWORK:
{content_decision_framework}
You are Abhedit's Content Intelligence Engine.

CURRENT INDUSTRY SIGNALS:

{news_text}

Your job is NOT to select the biggest breach, malware campaign, ransomware incident, or vulnerability.

Using:

* Current industry signals
* Content Universe
* Content Strategy
* Content Sources

Determine the highest-value topic for today's audience.

Audience:

* CISOs
* Security Architects
* Security Engineers
* Privacy Leaders
* GRC Teams
* Cloud Security Teams
* DPOs
* Technology Leaders

Priority Topics:

1. AI Governance
2. AI Security
3. Data Privacy
4. Privacy Engineering
5. GRC
6. Security Architecture
7. Cloud Security
8. Risk Management
9. ISO 27001
10. ISO 27701
11. ISO 42001
12. DORA
13. NIS2
14. Cyber Resilience Act
15. Security Leadership
16. Security Operations
17. Incident Response
18. Security Certifications
19. Digital Trust
20. Strategic Threat Intelligence

Select the topic that provides the greatest educational value, business value, consulting value, and audience engagement value.

Avoid becoming a vulnerability news page.

Avoid choosing a breach or vulnerability unless it has major strategic business impact.

Before generating content:

1. Select the best topic.
2. Explain why it was selected.
3. Identify the best audience.
4. Identify the best content format.
5. Then generate the content.


Output EXACTLY in this format:

===CAROUSEL===
[6 slide carousel here]

===LINKEDIN===
[linkedin post here]

===FACEBOOK===
[facebook post here]

===INSTAGRAM===
[instagram caption here]

===HASHTAGS===
[20 hashtags here]

===IMAGE_PROMPTS===
[6 image prompts here]


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

import time

response = None

for attempt in range(3):
    try:
        response = model.generate_content(prompt)
        break

    except Exception as e:
        print(f"Attempt {attempt + 1} failed: {e}")

        if attempt < 2:
            print("Waiting 30 seconds before retry...")
            time.sleep(30)
        else:
            raise

content = response.text

sections = {}

current_section = None

for line in content.splitlines():
    if line.startswith("===") and line.endswith("==="):
        current_section = line.strip("=")
        sections[current_section] = []
    elif current_section:
        sections[current_section].append(line)
        
os.makedirs("output", exist_ok=True)

with open("output/content.md", "w", encoding="utf-8") as f:
    f.write(content)

mapping = {
    "CAROUSEL": "carousel.md",
    "LINKEDIN": "linkedin.md",
    "FACEBOOK": "facebook.md",
    "INSTAGRAM": "instagram.md",
    "HASHTAGS": "hashtags.md",
    "IMAGE_PROMPTS": "image_prompts.md"
}

for section, filename in mapping.items():
    with open(f"output/{filename}", "w", encoding="utf-8") as f:
        f.write("\n".join(sections.get(section, [])))

print("Content generated successfully.")
