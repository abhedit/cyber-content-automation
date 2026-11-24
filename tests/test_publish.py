import json
import os

import pytest

from content_engine import package as pk
from content_engine import publish as pub
from content_engine.__main__ import DRY_RUN_NOW
from content_engine.sources import fetch_candidates

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASE = "https://raw.example/pkg"
ENV = {
    "FB_PAGE_ID": "123", "FB_PAGE_TOKEN": "SECRET-FB", "IG_USER_ID": "456", "IG_TOKEN": "SECRET-IG",
    "THREADS_USER_ID": "789", "THREADS_TOKEN": "SECRET-TH", "LINKEDIN_TOKEN": "SECRET-LI",
    "LINKEDIN_AUTHOR": "urn:li:person:abc", "YT_CLIENT_ID": "cid", "YT_CLIENT_SECRET": "SECRET-YT",
    "YT_REFRESH_TOKEN": "SECRET-RT",
}


class FakeHttp(pub.RecordingHttp):
    """RecordingHttp plus: optional failing URL fragments and tampered public media."""

    def __init__(self, folder, fail=None, tamper=False):
        super().__init__(folder, BASE)
        self.fail, self.tamper, self.raw = fail or {}, tamper, []

    def request(self, method, url, **kw):
        self.raw.append((method, url, kw))
        for frag, code in self.fail.items():
            if frag in url:
                class R:
                    status_code = code
                    headers = {}
                    text = "bad"

                    def json(self):
                        return {"error": {"message": f"denied for {url}"}}
                return R()
        r = super().request(method, url, **kw)
        if self.tamper and method == "GET" and url.startswith(BASE):
            r.content = b"tampered"
        return r


@pytest.fixture
def approved(tmp_path):
    def _feed(_):
        return open(os.path.join(FIX, "sample_feed.xml"), "rb").read()

    cands, _ = fetch_candidates(["x"], now=DRY_RUN_NOW, fetch=_feed)
    draft = json.load(open(os.path.join(FIX, "sample_draft.json")))
    pkg = pk.build_package(draft, cands, run_mode="live", now=DRY_RUN_NOW)
    folder = tmp_path / "2026-01-15"
    (folder / "slides").mkdir(parents=True)
    for i in range(1, 7):
        (folder / "slides" / f"slide-{i}.jpg").write_bytes(f"jpeg-{i}".encode())
    (folder / "short.mp4").write_bytes(b"mp4-bytes")
    pk.attach_media(pkg, str(folder))
    pk.approve(pkg, "Reviewer", acknowledge_flags=True)
    return pkg, str(folder)


def run(pkg, folder, http, platforms=None, env=ENV, saves=None):
    return pub.publish_package(pkg, folder, platforms or pub.PLATFORMS, env, http, BASE,
                               save=(saves.append if saves is not None else None), sleep=lambda s: None)


def test_publishes_to_all_five_once(approved):
    pkg, folder = approved
    saves = []
    out = run(pkg, folder, FakeHttp(folder), saves=saves)
    assert all(o.startswith("published") for o in out.values()), out
    assert set(pkg["published"]) == set(pub.PLATFORMS) and len(saves) == 5
    assert pkg["published"]["youtube"]["url"].startswith("https://youtube.com/shorts/")
    # recording publications does not void the approval
    assert pk.is_publishable(pkg)[0]
    http2 = FakeHttp(folder)
    out2 = run(pkg, folder, http2)
    assert set(out2.values()) == {"already published"} and http2.raw == []


def test_refuses_unapproved_changed_or_dry_run(approved):
    pkg, folder = approved
    pkg["posts"]["facebook"] += " edited"
    with pytest.raises(pub.PublishError, match="content changed"):
        run(pkg, folder, FakeHttp(folder))
    pkg2 = dict(pkg, run_mode="dry-run")
    with pytest.raises(pub.PublishError, match="dry-run"):
        run(pkg2, folder, FakeHttp(folder))


def test_swapping_an_image_after_approval_is_caught(approved):
    pkg, folder = approved
    # changing the recorded hash voids approval
    pkg2 = json.loads(json.dumps(pkg))
    pkg2["media"]["images"][0]["sha256"] = "0" * 64
    assert pk.is_publishable(pkg2) == (False, "content changed after approval")
    # replacing the file itself is caught before upload
    with open(os.path.join(folder, "slides", "slide-1.jpg"), "wb") as f:
        f.write(b"replaced")
    http = FakeHttp(folder)
    out = run(pkg, folder, http, ["linkedin", "youtube"])
    assert "differs from the approved file" in out["linkedin"] and out["youtube"].startswith("published")
    assert not any("rest/posts" in u for _, u, _ in http.raw)


def test_tampered_public_copy_blocks_instagram_and_threads(approved):
    pkg, folder = approved
    http = FakeHttp(folder, tamper=True)
    out = run(pkg, folder, http, ["instagram", "threads"])
    assert all("public copy" in o for o in out.values()), out
    assert not any(m == "POST" for m, _, _ in http.raw)  # nothing was sent to any platform


def test_facebook_uploads_verified_bytes_without_public_urls(approved):
    pkg, folder = approved
    http = FakeHttp(folder)
    out = pub.publish_package(pkg, folder, ["facebook"], ENV, http, None, sleep=lambda s: None)
    assert out["facebook"].startswith("published")
    uploads = [kw for m, u, kw in http.raw if u.endswith("/123/photos")]
    assert len(uploads) == 6 and uploads[0]["files"]["source"][1] == b"jpeg-1"
    assert "url" not in uploads[0]["data"]


def test_r2_hosting_uploads_each_approved_image_once(approved):
    pkg, folder = approved
    stored = {}

    def uploader(key, data):
        stored[key] = data
        return f"{BASE}/{key}"

    class R2Http(FakeHttp):
        def request(self, method, url, **kw):
            if method == "GET" and url.startswith(BASE):
                self.raw.append((method, url, kw))

                class R:
                    status_code, headers, text = 200, {}, ""
                r = R()
                r.content = stored[url[len(BASE) + 1:]]
                return r
            return super().request(method, url, **kw)

    http = R2Http(folder)
    out = pub.publish_package(pkg, folder, ["instagram", "threads"], ENV, http, None,
                              sleep=lambda s: None, uploader=uploader)
    assert all(o.startswith("published") for o in out.values()), out
    assert len(stored) == 6  # shared by Instagram and Threads, uploaded once
    assert all(k.startswith("abhedit/2026-01-15/") for k in stored)


def test_no_image_hosting_fails_clearly(approved):
    pkg, folder = approved
    out = pub.publish_package(pkg, folder, ["instagram"], ENV, FakeHttp(folder), None, sleep=lambda s: None)
    assert "no public image hosting configured" in out["instagram"]


def test_unconfigured_platforms_are_skipped(approved):
    pkg, folder = approved
    env = {k: v for k, v in ENV.items() if k.startswith("FB_")}
    out = run(pkg, folder, FakeHttp(folder), env=env)
    assert out["facebook"].startswith("published")
    assert all(out[p] == "skipped (not configured)" for p in ("instagram", "threads", "linkedin", "youtube"))


def test_one_failure_does_not_block_others_and_leaks_no_token(approved):
    pkg, folder = approved
    out = run(pkg, folder, FakeHttp(folder, fail={"graph.instagram.com": 400}))
    assert out["instagram"].startswith("FAILED") and "instagram" not in pkg["published"]
    assert all(out[p].startswith("published") for p in ("facebook", "threads", "linkedin", "youtube"))
    assert not any("SECRET" in o for o in out.values())


def test_request_payloads(approved):
    pkg, folder = approved
    http = FakeHttp(folder)
    run(pkg, folder, http)
    feed = next(kw for m, u, kw in http.raw if u.endswith("/123/feed"))
    assert len([k for k in feed["data"] if k.startswith("attached_media")]) == 6
    assert "news.example.com" in feed["data"]["message"]
    carousel = next(kw for m, u, kw in http.raw if u.endswith("/456/media") and kw["data"].get("media_type") == "CAROUSEL")
    assert len(carousel["data"]["children"].split(",")) == 6
    li = next(kw for m, u, kw in http.raw if u.endswith("/rest/posts"))
    assert li["headers"]["X-Restli-Protocol-Version"] == "2.0.0"
    assert len(li["json"]["content"]["multiImage"]["images"]) == 6
    yt = next(kw for m, u, kw in http.raw if "upload/youtube" in u)
    assert yt["json"]["snippet"]["title"].endswith("#Shorts") and yt["json"]["status"]["privacyStatus"] == "public"


def test_linkedin_escape():
    assert pub.linkedin_escape("Risk (AI) #x @y a_b") == "Risk \\(AI\\) \\#x \\@y a\\_b"
    assert pub.linkedin_escape("a\\b") == "a\\\\b"


def test_threads_and_youtube_text_limits(approved):
    pkg, _ = approved
    story = pkg["story"]
    long_slide = "word " * 200
    draft = {"carousel": [long_slide] * 6, "linkedin": "x", "facebook": "y", "instagram": "z", "hashtags": ["#A"]}
    posts = pk.render_posts(draft, story)
    assert len(posts["threads"]) <= pk.THREADS_MAX and story["url"] in posts["threads"]
    assert len(posts["youtube"]["title"]) <= pk.YOUTUBE_TITLE_MAX


def test_check_access_is_read_only(approved):
    _, folder = approved
    http = FakeHttp(folder)
    out = pub.check_access(ENV, http)
    assert all(v.startswith("OK") for v in out.values()), out
    writes = [u for m, u, _ in http.raw if m != "GET"]
    assert writes == ["https://oauth2.googleapis.com/token"] * 1  # token refresh only


def test_dry_run_reports_gate_and_plan(approved):
    pkg, folder = approved
    gate, outcome, calls = pub.dry_run(pkg, folder, pub.PLATFORMS)
    assert gate == "PUBLISHABLE" and all(o.startswith("would publish") for o in outcome.values())
    assert not any("SECRET" in c or "dry-token" in c for c in calls)


def test_check_access_needs_only_tokens_and_reports_ids(approved):
    _, folder = approved
    out = pub.check_access({"THREADS_TOKEN": "SECRET-TH", "LINKEDIN_TOKEN": "SECRET-LI"}, FakeHttp(folder))
    assert "THREADS_USER_ID=" in out["threads"] and "urn:li:person:" in out["linkedin"]
    assert out["facebook"] == "not configured"
    assert not any("SECRET" in v for v in out.values())
