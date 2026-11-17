"""Validate a generated draft against AGENTS.md and flag sensitive claims.

errors       -> blocking: the package cannot be approved until fixed/regenerated.
review_flags -> not blocking, but shown prominently to the human reviewer.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

MAX_SLIDE_WORDS = 30
SLIDE_COUNT = 6
HASHTAG_COUNT = 20
CONFIDENCE_LEVELS = {"high", "medium", "low"}
CTA_PHRASE = "follow abhedit"

SENSITIVE_PATTERNS = [
    (r"[$€£₹]\s?\d|\b\d[\d,.]*\s?(million|billion|crore|lakh)\b", "money amount"),
    (r"\b\d+(\.\d+)?\s?%", "percentage/statistic"),
    (r"\bCVE-\d{4}-\d{3,}\b", "CVE identifier"),
    (r"\b(fined|fines? of|penalt(y|ies)|lawsuit|sued|class action|settlement|indicted|arrested|charged with)\b", "legal/enforcement claim"),
    (r"\b(attributed to|state[- ]sponsored|nation[- ]state|APT\s?\d+|linked to)\b", "threat-actor attribution"),
    (r"\b(guarantee[sd]?|100% (secure|compliant)|fully compliant|ensures? compliance|certified compliant)\b", "absolute/compliance promise"),
    (r"\b(breach(ed)?|leaked|exposed|stolen)\b", "breach/exposure claim"),
]

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def word_count(text: str) -> int:
    return sum(1 for tok in text.split() if re.search(r"\w", tok))


def _text_fields(draft: dict) -> dict[str, str]:
    fields = {f"slide {i + 1}": s for i, s in enumerate(draft.get("carousel") or []) if isinstance(s, str)}
    for key in ("linkedin", "facebook", "instagram"):
        if isinstance(draft.get(key), str):
            fields[key] = draft[key]
    return fields


def validate(draft: dict, candidates: list[dict], now: datetime | None = None) -> tuple[list[str], list[str]]:
    now = now or datetime.now(timezone.utc)
    errors: list[str] = []
    flags: list[str] = []

    sel = draft.get("selection") or {}
    by_id = {c["id"]: c for c in candidates}
    story = by_id.get(sel.get("candidate_id"))
    if story is None:
        errors.append(f"selection.candidate_id {sel.get('candidate_id')!r} is not one of the fetched candidates")
    if str(sel.get("confidence", "")).lower() not in CONFIDENCE_LEVELS:
        errors.append("selection.confidence must be high, medium or low")
    for key in ("why_it_matters", "why_selected", "confidence_reason"):
        if not str(sel.get(key, "")).strip():
            errors.append(f"selection.{key} is empty")

    slides = draft.get("carousel")
    if not isinstance(slides, list) or len(slides) != SLIDE_COUNT:
        errors.append(f"carousel must have exactly {SLIDE_COUNT} slides")
        slides = slides if isinstance(slides, list) else []
    for i, slide in enumerate(slides, start=1):
        if not isinstance(slide, str) or not slide.strip():
            errors.append(f"slide {i} is empty")
            continue
        n = word_count(slide)
        if n > MAX_SLIDE_WORDS:
            errors.append(f"slide {i} has {n} words (max {MAX_SLIDE_WORDS})")
    if len(slides) == SLIDE_COUNT and CTA_PHRASE not in str(slides[-1]).lower():
        errors.append('slide 6 must include "Follow Abhedit for cybersecurity insights."')

    for key in ("linkedin", "facebook", "instagram"):
        if not str(draft.get(key) or "").strip():
            errors.append(f"{key} post is empty")

    tags = draft.get("hashtags") or []
    if not isinstance(tags, list):
        tags = []
    bad = [t for t in tags if not re.fullmatch(r"#\w+", str(t))]
    if bad:
        errors.append(f"invalid hashtags: {bad[:5]}")
    if len({str(t).lower() for t in tags}) != HASHTAG_COUNT or len(tags) != HASHTAG_COUNT:
        errors.append(f"need exactly {HASHTAG_COUNT} unique hashtags (got {len(tags)}, {len({str(t).lower() for t in tags})} unique)")

    prompts = draft.get("image_prompts")
    if not isinstance(prompts, list) or len(prompts) != SLIDE_COUNT:
        errors.append(f"need exactly {SLIDE_COUNT} image prompts")

    # Links in copy must be the verified source; anything else may be invented.
    allowed = {story["url"].rstrip("/")} if story else set()
    for name, text in _text_fields(draft).items():
        for url in URL_RE.findall(text):
            if url.rstrip("/.,") not in allowed:
                errors.append(f"{name} contains an unverified link: {url}")

    # ---- review flags (human attention, not blocking) ----
    if str(sel.get("confidence", "")).lower() in {"medium", "low"}:
        flags.append(f"Model confidence is {sel.get('confidence')}: {sel.get('confidence_reason', '')}")
    if story:
        age_h = (now - datetime.fromisoformat(story["published"])).total_seconds() / 3600
        if age_h > 24:
            flags.append(f"Story is {age_h:.0f}h old (TASKS.md targets the last 24 hours)")
    for name, text in _text_fields(draft).items():
        hits = sorted({label for pattern, label in SENSITIVE_PATTERNS if re.search(pattern, text, re.I)})
        if hits:
            flags.append(f"{name}: contains {', '.join(hits)} - verify against the source")
    for claim in draft.get("claims_to_verify") or []:
        flags.append(f"Verify claim: {claim}")

    return errors, flags
