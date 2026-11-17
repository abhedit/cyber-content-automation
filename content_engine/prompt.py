"""Build the model prompt from AGENTS.md, the knowledge base and fetched candidates."""

from __future__ import annotations

import json
import os

KNOWLEDGE_FILES = [
    "content-universe.md",
    "content-strategy.md",
    "content-sources.md",
    "platform-strategy.md",
    "content-decision-framework.md",
]

OUTPUT_CONTRACT = """
Return ONE JSON object and nothing else, with exactly these keys:

{
  "selection": {
    "candidate_id": "<ID of exactly one candidate story from the list, e.g. S1a2b3c4d>",
    "why_selected": "<1-2 sentences>",
    "why_it_matters": "<1-3 sentences on business impact for CISOs/GRC/privacy teams>",
    "confidence": "high | medium | low",
    "confidence_reason": "<why: source quality, how much is confirmed in the summary>",
    "service_angle": "compliance software | consulting | training"
  },
  "carousel": ["<slide 1>", "<slide 2>", "<slide 3>", "<slide 4>", "<slide 5>", "<slide 6>"],
  "linkedin": "<LinkedIn post>",
  "facebook": "<Facebook post>",
  "instagram": "<Instagram caption>",
  "hashtags": ["#Tag1", "... exactly 20 unique hashtags"],
  "image_prompts": ["<one prompt per slide, 6 total>"],
  "claims_to_verify": ["<every specific fact, number, name, date or attribution used in the posts>"]
}
""".strip()

RULES = """
HARD RULES (the output is machine-validated; violations are rejected):
1. Use ONE primary story only, chosen by its candidate ID. Never mix unrelated stories.
2. Carousel = exactly 6 plain-text slides, each at most 30 words, one key message each:
   Slide 1 headline only; 2 what happened; 3 why it matters; 4 business impact;
   5 security recommendations; 6 call to action that includes "Follow Abhedit for cybersecurity insights."
3. Only state facts that appear in the chosen candidate's title or summary. Do not invent numbers,
   victims, threat actors, fines, CVEs or quotes. If you are unsure, phrase it as general guidance.
4. List every specific factual claim you used in "claims_to_verify" so a human can check it.
5. Exactly 20 unique hashtags, each starting with #, no spaces.
6. Do not include the source URL in the posts; the system appends the verified source itself.
7. Tone: professional, business-focused, actionable, clear, modern. No fear-mongering.
""".strip()


def load_knowledge(root: str = ".") -> str:
    parts = []
    for name in KNOWLEDGE_FILES:
        path = os.path.join(root, "knowledge", name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f"## {name}\n{f.read().strip()}")
    return "\n\n".join(parts)


def load_agents(root: str = ".") -> str:
    path = os.path.join(root, "AGENTS.md")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def format_candidates(candidates: list[dict]) -> str:
    slim = [
        {k: c[k] for k in ("id", "title", "source", "published", "summary")}
        for c in candidates
    ]
    return json.dumps(slim, indent=2, ensure_ascii=False)


def build_prompt(candidates: list[dict], root: str = ".", feedback: list[str] | None = None) -> str:
    prompt = f"""You are Abhedit's Content Intelligence Engine.

# AGENTS.md (mandatory)
{load_agents(root)}

# ABHEDIT KNOWLEDGE BASE
{load_knowledge(root)}

# CANDIDATE STORIES (fetched from RSS; the only stories you may use)
{format_candidates(candidates)}

Choose the candidate with the highest strategic value for Abhedit's audience
(AI governance, privacy, GRC, ISO 27001/27701/42001, DORA, NIS2, cloud security, security leadership).
Prefer stories with business or regulatory impact over routine vulnerability news.

{RULES}

{OUTPUT_CONTRACT}
"""
    if feedback:
        prompt += "\n\nYOUR PREVIOUS ANSWER WAS REJECTED. Fix ALL of these problems:\n- " + "\n- ".join(feedback)
    return prompt
