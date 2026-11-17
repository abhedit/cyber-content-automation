"""Fetch candidate news stories from RSS feeds, keeping URL and publication date.

The model is only allowed to pick a story by its candidate ID. The URL, title,
source and date always come from the feed, never from model output, so a cited
source cannot be invented.
"""

from __future__ import annotations

import calendar
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser

USER_AGENT = "AbheditContentBot/0.1 (+https://github.com/abhedit/cyber-content-automation)"


def read_feed_list(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    return None


def parse_feed(raw, feed_url: str, per_feed: int = 8) -> list[dict]:
    """Parse feed content (bytes/str/URL) into candidate dicts.

    Entries without a link or a publication date are dropped: AGENTS.md
    requires both for every story we publish.
    """
    parsed = feedparser.parse(raw)
    source_name = (parsed.feed.get("title") or urlparse(feed_url).netloc).strip()
    out = []
    for entry in parsed.entries[:per_feed]:
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        published = _entry_datetime(entry)
        if not link.startswith(("http://", "https://")) or not title or published is None:
            continue
        summary = (entry.get("summary") or "").strip()
        out.append(
            {
                "title": title,
                "url": link,
                "published": published.isoformat(),
                "source": source_name,
                "feed": feed_url,
                "summary": _strip_html(summary)[:600],
            }
        )
    return out


def _strip_html(text: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_candidates(
    feeds: list[str],
    now: datetime | None = None,
    max_age_hours: int = 48,
    per_feed: int = 8,
    fetch=None,
) -> tuple[list[dict], list[str]]:
    """Return (candidates newest-first with stable IDs, list of feed errors).

    `fetch(url) -> bytes` can be injected for tests; defaults to requests.
    """
    now = now or datetime.now(timezone.utc)
    if fetch is None:
        fetch = _http_fetch
    seen: set[str] = set()
    candidates: list[dict] = []
    errors: list[str] = []
    for feed in feeds:
        try:
            items = parse_feed(fetch(feed), feed, per_feed=per_feed)
        except Exception as exc:  # one broken feed must not stop the run
            errors.append(f"{feed}: {exc}")
            continue
        for item in items:
            key = item["url"].split("#")[0].rstrip("/").lower()
            if key in seen:
                continue
            age_h = (now - datetime.fromisoformat(item["published"])).total_seconds() / 3600
            if age_h > max_age_hours or age_h < -2:  # too old, or dated in the future
                continue
            seen.add(key)
            candidates.append(item)
    candidates.sort(key=lambda c: c["published"], reverse=True)
    for c in candidates:
        c["id"] = "S" + hashlib.sha256(c["url"].encode()).hexdigest()[:8]
    return candidates, errors


def _http_fetch(url: str) -> bytes:
    import requests

    resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.content
