"""Assemble, store, approve and gate a content package.

Approval is bound to a SHA-256 of the publishable content. Any edit after
approval changes the hash, so `is_publishable` returns False until re-approved.
Publishers (e.g. the n8n workflow) must only post when `is_publishable` is True,
i.e. status == "approved" and approval.content_sha256 == content_sha256.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from .validate import validate

SCHEMA_VERSION = 1


def _source_line(story: dict, with_url: bool = True) -> str:
    date = story["published"][:10]
    if with_url:
        return f"Source: {story['source']} ({date}) {story['url']}"
    return f"Source: {story['source']} ({date}). Link in bio."


def strip_hashtags(text: str) -> str:
    """Hashtags belong only in the approved list. Drop hashtag-only lines and
    turn inline tags into plain words ("#AIGovernance rules" -> "AIGovernance rules")."""
    lines = [ln for ln in text.splitlines() if not re.fullmatch(r"\s*(#\w+\s*)+", ln)]
    cleaned = re.sub(r"(?<![\w&])#(\w+)", r"\1", "\n".join(lines))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def render_posts(draft: dict, story: dict) -> dict:
    """Final platform text: model copy + the verified source citation.
    Only the 20 validated hashtags are used, once, on Instagram."""
    tags = " ".join(draft.get("hashtags") or [])
    return {
        "linkedin": f"{strip_hashtags(draft['linkedin'])}\n\n{_source_line(story)}",
        "facebook": f"{strip_hashtags(draft['facebook'])}\n\n{_source_line(story)}",
        "instagram": f"{strip_hashtags(draft['instagram'])}\n\n{_source_line(story, with_url=False)}\n\n{tags}",
    }


def content_hash(pkg: dict) -> str:
    publishable = {k: pkg.get(k) for k in ("story", "carousel", "posts", "hashtags", "image_prompts")}
    blob = json.dumps(publishable, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()


def build_package(draft: dict, candidates: list[dict], run_mode: str, now: datetime | None = None,
                  feed_errors: list[str] | None = None, model: str = "") -> dict:
    now = now or datetime.now(timezone.utc)
    errors, flags = validate(draft, candidates, now=now)
    sel = draft.get("selection") or {}
    story_src = next((c for c in candidates if c["id"] == sel.get("candidate_id")), None)
    story = None
    if story_src:
        story = {
            "id": story_src["id"],
            "title": story_src["title"],
            "url": story_src["url"],
            "source": story_src["source"],
            "published": story_src["published"],
            "why_it_matters": sel.get("why_it_matters", ""),
            "why_selected": sel.get("why_selected", ""),
            "confidence": str(sel.get("confidence", "")).lower(),
            "confidence_reason": sel.get("confidence_reason", ""),
            "service_angle": sel.get("service_angle", ""),
        }
    pkg = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "run_mode": run_mode,  # "dry-run" packages must never be published
        "model": model,
        "story": story,
        "carousel": draft.get("carousel"),
        "posts": render_posts(draft, story) if story and not errors else None,
        "hashtags": draft.get("hashtags"),
        "image_prompts": draft.get("image_prompts"),
        "claims_to_verify": draft.get("claims_to_verify") or [],
        "validation": {"errors": errors, "review_flags": flags},
        "feed_errors": feed_errors or [],
        "candidates_considered": len(candidates),
        "status": "rejected" if errors else "pending_review",
        "approval": None,
    }
    pkg["content_sha256"] = content_hash(pkg)
    return pkg


def approve(pkg: dict, reviewer: str, acknowledge_flags: bool = False, now: datetime | None = None) -> dict:
    if not reviewer.strip():
        raise ValueError("reviewer name is required")
    if pkg.get("run_mode") != "live":
        raise ValueError("dry-run packages cannot be approved for publishing")
    if pkg["validation"]["errors"]:
        raise ValueError("package has validation errors; regenerate or fix it first")
    if content_hash(pkg) != pkg.get("content_sha256"):
        raise ValueError("content changed since generation; re-run `rehash` after editing, then review again")
    if pkg["validation"]["review_flags"] and not acknowledge_flags:
        raise ValueError(f"{len(pkg['validation']['review_flags'])} review flags must be checked; pass --ack-flags once verified")
    pkg["status"] = "approved"
    pkg["approval"] = {
        "approved_by": reviewer.strip(),
        "approved_at": (now or datetime.now(timezone.utc)).isoformat(),
        "content_sha256": pkg["content_sha256"],
        "flags_acknowledged": len(pkg["validation"]["review_flags"]),
    }
    return pkg


def rehash(pkg: dict) -> dict:
    """After a human edits copy in package.json: new hash, approval cleared."""
    pkg["content_sha256"] = content_hash(pkg)
    pkg["approval"] = None
    if pkg["status"] == "approved":
        pkg["status"] = "pending_review"
    return pkg


def is_publishable(pkg: dict) -> tuple[bool, str]:
    if pkg.get("run_mode") != "live":
        return False, "dry-run package"
    if pkg.get("status") != "approved" or not pkg.get("approval"):
        return False, f"status is {pkg.get('status')!r}, not approved"
    if pkg["validation"]["errors"]:
        return False, "validation errors present"
    current = content_hash(pkg)
    if current != pkg["approval"].get("content_sha256") or current != pkg.get("content_sha256"):
        return False, "content changed after approval"
    return True, "approved and unchanged"


def review_markdown(pkg: dict) -> str:
    s = pkg.get("story") or {}
    v = pkg["validation"]
    lines = [
        f"# Content review - {pkg['generated_at'][:10]} ({pkg['run_mode']})",
        "",
        f"**Status:** {pkg['status']}  ",
        f"**Content SHA-256:** `{pkg['content_sha256'][:16]}...`",
        "",
        "## Primary story",
        f"- **Title:** {s.get('title', '-')}",
        f"- **Source URL:** {s.get('url', '-')}",
        f"- **Publication date:** {s.get('published', '-')}",
        f"- **Publisher:** {s.get('source', '-')}",
        f"- **Why it matters:** {s.get('why_it_matters', '-')}",
        f"- **Confidence:** {s.get('confidence', '-')} - {s.get('confidence_reason', '')}",
        f"- **Service angle:** {s.get('service_angle', '-')}",
        "",
        "## Blocking errors",
        *([f"- {e}" for e in v["errors"]] or ["- none"]),
        "",
        "## Check before approving",
        *([f"- [ ] {f}" for f in v["review_flags"]] or ["- nothing flagged"]),
        "",
        "## Carousel",
    ]
    for i, slide in enumerate(pkg.get("carousel") or [], start=1):
        lines.append(f"{i}. {slide}")
    if pkg.get("posts"):
        for name in ("linkedin", "facebook", "instagram"):
            lines += ["", f"## {name.title()}", "", pkg["posts"][name]]
    lines += ["", "## Image prompts", *[f"{i}. {p}" for i, p in enumerate(pkg.get("image_prompts") or [], 1)]]
    if pkg.get("feed_errors"):
        lines += ["", "## Feed errors", *[f"- {e}" for e in pkg["feed_errors"]]]
    return "\n".join(lines) + "\n"


def write_package(pkg: dict, out_root: str = "output/packages") -> str:
    folder = os.path.join(out_root, pkg["generated_at"][:10] + ("-dry-run" if pkg["run_mode"] != "live" else ""))
    os.makedirs(folder, exist_ok=True)
    save(pkg, os.path.join(folder, "package.json"))
    with open(os.path.join(folder, "review.md"), "w", encoding="utf-8") as f:
        f.write(review_markdown(pkg))
    return folder


def load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(pkg: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pkg, f, indent=2, ensure_ascii=False)
        f.write("\n")
