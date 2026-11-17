import copy
import re
import json
import os
from datetime import datetime, timezone

import pytest

from content_engine import package as pk
from content_engine.__main__ import DRY_RUN_NOW, main
from content_engine.prompt import build_prompt
from content_engine.sources import fetch_candidates
from content_engine.validate import validate, word_count

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
STORY_ID = "S52bad1a7"


def _feed(_url):
    with open(os.path.join(FIX, "sample_feed.xml"), "rb") as f:
        return f.read()


@pytest.fixture
def candidates():
    c, errors = fetch_candidates(["fixture"], now=DRY_RUN_NOW, fetch=_feed)
    assert errors == []
    return c


@pytest.fixture
def draft():
    with open(os.path.join(FIX, "sample_draft.json"), encoding="utf-8") as f:
        return json.load(f)


# ---------- sources ----------

def test_candidates_keep_only_dated_linked_fresh_unique_stories(candidates):
    titles = [c["title"] for c in candidates]
    assert len(candidates) == 2
    assert titles[0].startswith("Regulator publishes")  # newest first
    assert not any("no publication date" in t or "no link" in t or "Old story" in t or "Duplicate" in t for t in titles)
    for c in candidates:
        assert c["url"].startswith("https://") and c["published"] and c["source"]
    assert candidates[0]["id"] == STORY_ID


def test_one_broken_feed_does_not_stop_the_run():
    def fetch(url):
        if url == "bad":
            raise ConnectionError("blocked")
        return _feed(url)

    c, errors = fetch_candidates(["bad", "good"], now=DRY_RUN_NOW, fetch=fetch)
    assert len(c) == 2 and len(errors) == 1 and "blocked" in errors[0]


# ---------- validation ----------

def test_sample_draft_is_valid(draft, candidates):
    errors, flags = validate(draft, candidates, now=DRY_RUN_NOW)
    assert errors == []
    assert any("60 days" in f for f in flags)  # claims surface for review


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda d: d["selection"].update(candidate_id="S00000000"), "not one of the fetched candidates"),
        (lambda d: d["selection"].update(confidence="certain"), "confidence must be"),
        (lambda d: d["selection"].update(why_it_matters=""), "why_it_matters is empty"),
        (lambda d: d["carousel"].pop(), "exactly 6 slides"),
        (lambda d: d["carousel"].__setitem__(2, "word " * 31), "slide 3 has 31 words"),
        (lambda d: d["carousel"].__setitem__(5, "Thanks for reading."), "slide 6 must include"),
        (lambda d: d["hashtags"].pop(), "exactly 20 unique hashtags"),
        (lambda d: d["hashtags"].__setitem__(1, "#aigovernance"), "exactly 20 unique hashtags"),
        (lambda d: d["hashtags"].__setitem__(0, "AI Governance"), "invalid hashtags"),
        (lambda d: d["image_prompts"].pop(), "6 image prompts"),
        (lambda d: d.update(facebook=""), "facebook post is empty"),
        (lambda d: d.update(linkedin=d["linkedin"] + " See https://evil.example.net/x"), "unverified link"),
    ],
)
def test_rule_violations_are_blocking(draft, candidates, mutate, expected):
    mutate(draft)
    errors, _ = validate(draft, candidates, now=DRY_RUN_NOW)
    assert any(expected in e for e in errors), errors


def test_source_url_in_copy_is_allowed(draft, candidates):
    draft["linkedin"] += " https://news.example.com/2026/01/ai-risk-guidance"
    errors, _ = validate(draft, candidates, now=DRY_RUN_NOW)
    assert errors == []


@pytest.mark.parametrize(
    "text, label",
    [
        ("The company was fined $5 million.", "money amount"),
        ("Attacks rose 300% this year.", "percentage/statistic"),
        ("Patch CVE-2026-12345 now.", "CVE identifier"),
        ("The attack was attributed to a nation-state group.", "threat-actor attribution"),
        ("Our platform guarantees compliance.", "absolute/compliance promise"),
    ],
)
def test_sensitive_claims_are_flagged(draft, candidates, text, label):
    draft["facebook"] = text
    errors, flags = validate(draft, candidates, now=DRY_RUN_NOW)
    assert errors == []
    assert any(label in f and f.startswith("facebook") for f in flags), flags


def test_low_confidence_and_stale_story_are_flagged(draft, candidates):
    draft["selection"]["confidence"] = "low"
    later = datetime(2026, 1, 17, 12, 0, tzinfo=timezone.utc)
    _, flags = validate(draft, candidates, now=later)
    assert any("confidence is low" in f for f in flags)
    assert any("h old" in f for f in flags)


def test_word_count_ignores_punctuation_tokens():
    assert word_count("Build an inventory - now.") == 4


# ---------- package / approval gate ----------

def _live_pkg(draft, candidates):
    return pk.build_package(draft, candidates, run_mode="live", now=DRY_RUN_NOW)


def test_package_cites_verified_source(draft, candidates):
    pkg = _live_pkg(draft, candidates)
    url = "https://news.example.com/2026/01/ai-risk-guidance"
    assert pkg["status"] == "pending_review"
    assert pkg["story"]["url"] == url and pkg["story"]["published"].startswith("2026-01-15")
    assert url in pkg["posts"]["linkedin"] and url in pkg["posts"]["facebook"]
    assert "Link in bio" in pkg["posts"]["instagram"] and "#Abhedit" in pkg["posts"]["instagram"]


def test_not_publishable_until_approved(draft, candidates):
    pkg = _live_pkg(draft, candidates)
    assert pk.is_publishable(pkg)[0] is False
    with pytest.raises(ValueError, match="review flags"):
        pk.approve(pkg, "Reviewer")
    pk.approve(pkg, "Reviewer", acknowledge_flags=True)
    assert pk.is_publishable(pkg) == (True, "approved and unchanged")


def test_edit_after_approval_blocks_publishing(draft, candidates):
    pkg = pk.approve(_live_pkg(draft, candidates), "Reviewer", acknowledge_flags=True)
    pkg["posts"]["facebook"] += " Extra unreviewed sentence."
    assert pk.is_publishable(pkg) == (False, "content changed after approval")
    pk.rehash(pkg)
    assert pkg["status"] == "pending_review" and pk.is_publishable(pkg)[0] is False


def test_invalid_or_dry_run_packages_cannot_be_approved(draft, candidates):
    bad = copy.deepcopy(draft)
    bad["carousel"].pop()
    rejected = _live_pkg(bad, candidates)
    assert rejected["status"] == "rejected" and rejected["posts"] is None
    with pytest.raises(ValueError, match="validation errors"):
        pk.approve(rejected, "Reviewer", acknowledge_flags=True)
    dry = pk.build_package(draft, candidates, run_mode="dry-run", now=DRY_RUN_NOW)
    with pytest.raises(ValueError, match="dry-run"):
        pk.approve(dry, "Reviewer", acknowledge_flags=True)
    assert pk.is_publishable(dry)[0] is False


# ---------- prompt ----------

def test_prompt_contains_rules_candidates_and_feedback(candidates):
    root = os.path.dirname(os.path.dirname(FIX))
    p = build_prompt(candidates, root=root, feedback=["slide 3 has 40 words (max 30)"])
    assert STORY_ID in p and "Follow Abhedit" in p and "Confidence Level" in p
    assert "slide 3 has 40 words" in p
    assert "news.example.com" not in p  # model never sees URLs, so it cannot alter them


# ---------- end to end ----------

def test_dry_run_cli_end_to_end(tmp_path, capsys):
    assert main(["generate", "--dry-run", "--out", str(tmp_path)]) == 0
    folder = tmp_path / "2026-01-15-dry-run"
    pkg = json.loads((folder / "package.json").read_text())
    review = (folder / "review.md").read_text()
    assert pkg["run_mode"] == "dry-run" and pkg["status"] == "pending_review"
    assert "Source URL:** https://news.example.com/2026/01/ai-risk-guidance" in review
    assert main(["approve", str(folder / "package.json"), "--by", "X", "--ack-flags"]) == 1
    assert main(["check", str(folder / "package.json")]) == 1
    assert "dry-run" in capsys.readouterr().out


def test_live_path_retries_with_validation_feedback(tmp_path, monkeypatch, draft):
    """Simulated Gemini: first answer breaks rules, second is valid. No network."""
    from content_engine import __main__ as cli

    bad = copy.deepcopy(draft)
    bad["carousel"][1] = "word " * 45
    answers = ["```json\n" + json.dumps(bad) + "\n```", json.dumps(draft)]
    prompts = []

    def fake_gemini(prompt, model):
        prompts.append(prompt)
        return answers[len(prompts) - 1]

    feeds = tmp_path / "feeds.txt"
    feeds.write_text("fixture://sample\n")
    monkeypatch.setattr(cli, "call_gemini", fake_gemini)
    monkeypatch.setattr(cli, "fetch_candidates", lambda f, now, max_age_hours: fetch_candidates(f, now=DRY_RUN_NOW, fetch=_feed))
    monkeypatch.setattr(cli, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: DRY_RUN_NOW)}))

    assert main(["generate", "--feeds", str(feeds), "--out", str(tmp_path / "out")]) == 0
    assert len(prompts) == 2 and "slide 2 has 45 words" in prompts[1]
    pkg = json.loads((tmp_path / "out" / "2026-01-15" / "package.json").read_text())
    assert pkg["run_mode"] == "live" and pkg["status"] == "pending_review"


# ---------- rendering ----------

def test_slide_html_escapes_text_and_shows_source_on_slide_2():
    from content_engine.render import slide_html

    doc = slide_html("<script>x</script> & more", 2, 6, "Source: Example, 2026-01-15")
    assert "<script>x" not in doc and "&lt;script&gt;" in doc
    assert "Source: Example, 2026-01-15" in doc and "2 / 6" in doc and "What happened" in doc
    assert "Source:" not in slide_html("Headline", 1, 6, "Source: Example")


def test_render_pngs_from_dry_run(tmp_path):
    pytest.importorskip("playwright")
    assert main(["generate", "--dry-run", "--render", "--out", str(tmp_path)]) == 0
    slides = sorted((tmp_path / "2026-01-15-dry-run" / "slides").glob("*.png"))
    assert len(slides) == 6
    for png in slides:
        data = png.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        assert (w, h) == (1080, 1080)


def test_too_much_text_is_refused_not_cropped(tmp_path):
    pytest.importorskip("playwright")
    from content_engine.render import render_slides

    pkg = {"carousel": ["Headline"] + ["overflowing " * 120] + ["x"] * 4, "story": None}
    with pytest.raises(ValueError, match="slide 2 text does not fit"):
        render_slides(pkg, str(tmp_path))


# ---------- model client ----------

def test_permanent_errors_are_not_retried(monkeypatch):
    from content_engine import model

    calls = []

    class Bad(Exception):
        code = 400

    def boom(prompt, m, key):
        calls.append(1)
        raise Bad("400 INVALID_ARGUMENT")

    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(model, "_generate", boom)
    with pytest.raises(RuntimeError, match="INVALID_ARGUMENT"):
        model.call_gemini("p", wait_s=0)
    assert len(calls) == 1


def test_transient_errors_are_retried(monkeypatch):
    from content_engine import model

    calls = []

    def flaky(prompt, m, key):
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("503 UNAVAILABLE")
        return "{}"

    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(model, "_generate", flaky)
    assert model.call_gemini("p", wait_s=0) == "{}" and len(calls) == 3


# ---------- regressions from the first live run (2026-11-17) ----------

def test_inline_hashtags_removed_so_only_20_approved_tags_appear(draft, candidates):
    draft["instagram"] = "Apple boosts #AIAgent security for #AIGovernance.\n\n#Cybersecurity #GRC #TechNews"
    draft["linkedin"] += "\n\n#CISO #InfoSec"
    pkg = _live_pkg(draft, candidates)
    ig = pkg["posts"]["instagram"]
    assert "Apple boosts AIAgent security for AIGovernance." in ig
    assert "#TechNews" not in ig and "#CISO" not in pkg["posts"]["linkedin"]
    assert len(re.findall(r"#\w+", ig)) == 20


def test_third_party_logo_in_image_prompt_is_flagged(draft, candidates):
    draft["image_prompts"][0] = "Bold headline with an Apple logo subtly in the background"
    _, flags = validate(draft, candidates, now=DRY_RUN_NOW)
    assert any("image prompt 1" in f and "logo" in f for f in flags)
    _, flags = validate(json.loads(open(os.path.join(FIX, "sample_draft.json")).read()), candidates, now=DRY_RUN_NOW)
    assert not any("logo" in f for f in flags)  # "Abhedit wordmark" prompts are fine
