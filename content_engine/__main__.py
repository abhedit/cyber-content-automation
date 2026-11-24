"""CLI.

  python -m content_engine generate --dry-run      # no network, no API key, no publishing
  python -m content_engine generate                # live research + Gemini (needs GEMINI_API_KEY)
  python -m content_engine approve PATH --by NAME [--ack-flags]
  python -m content_engine rehash PATH             # after editing copy by hand; clears approval
  python -m content_engine check PATH              # exit 0 only if safe to publish
  python -m content_engine render PATH             # carousel PNGs into <package>/slides/
  python -m content_engine sources                 # live feed check only (no API key)
  python -m content_engine publish PATH|--latest-approved [--platforms facebook,instagram,...] [--dry-run]
  python -m content_engine check-access            # read-only token check for every configured platform

Nothing in this package posts to any social network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import package as pk
from .model import DEFAULT_MODEL, call_gemini, parse_json
from .prompt import build_prompt
from .sources import fetch_candidates, read_feed_list
from .validate import validate

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(os.path.dirname(HERE), "tests", "fixtures")
DRY_RUN_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _dry_run_fetch(_url: str) -> bytes:
    with open(os.path.join(FIXTURES, "sample_feed.xml"), "rb") as f:
        return f.read()


def generate(args) -> int:
    if args.dry_run:
        now = DRY_RUN_NOW
        candidates, feed_errors = fetch_candidates(["fixture://sample"], now=now, fetch=_dry_run_fetch)
        with open(os.path.join(FIXTURES, "sample_draft.json"), "r", encoding="utf-8") as f:
            draft = json.load(f)
        mode, model = "dry-run", "fixture"
    else:
        now = datetime.now(timezone.utc)
        candidates, feed_errors = fetch_candidates(read_feed_list(args.feeds), now=now, max_age_hours=args.max_age_hours)
        for e in feed_errors:
            print(f"WARNING feed error: {e}")
        if not candidates:
            print("No usable stories (need link + publication date within the age window). Nothing generated.")
            return 2
        mode, model = "live", args.model
        draft, feedback = {}, None
        for attempt in range(1, args.max_rounds + 1):
            raw = call_gemini(build_prompt(candidates, feedback=feedback), model=model)
            try:
                draft = parse_json(raw)
            except ValueError as exc:
                feedback = [f"Output was not valid JSON: {exc}"]
                continue
            errors, _ = validate(draft, candidates, now=now)
            if not errors:
                break
            print(f"Round {attempt}: {len(errors)} validation errors; asking the model to fix them")
            feedback = errors

    pkg = pk.build_package(draft, candidates, run_mode=mode, now=now, feed_errors=feed_errors, model=model)
    folder = pk.write_package(pkg, out_root=args.out)
    v = pkg["validation"]
    print(f"Package written: {folder}/package.json and review.md")
    print(f"Status: {pkg['status']} | errors: {len(v['errors'])} | review flags: {len(v['review_flags'])}")
    for e in v["errors"]:
        print(f"  ERROR {e}")
    if args.render and not v["errors"]:
        _render_media(pkg, folder)
    return 1 if v["errors"] else 0


def _render_media(pkg: dict, folder: str) -> None:
    """Slides (PNG + JPEG), Shorts video, then bind their hashes into the package."""
    from .render import build_short, render_slides

    n = len(render_slides(pkg, folder))
    video = build_short(folder)
    pk.attach_media(pkg, folder)
    pk.save(pkg, os.path.join(folder, "package.json"))
    with open(os.path.join(folder, "review.md"), "w", encoding="utf-8") as f:
        f.write(pk.review_markdown(pkg))
    print(f"Rendered {n} slide images" + (" and short.mp4" if video else " (no ffmpeg: no video)") + f" into {folder}")
    print("Media hashes recorded; approval (if any) was cleared and must be given again.")


def render(args) -> int:
    path = os.path.abspath(args.path)
    pkg = pk.load(path)
    if pkg["validation"]["errors"]:
        print("Package has validation errors; not rendering.")
        return 1
    _render_media(pkg, os.path.dirname(path))
    return 0


def _find_latest_approved(root: str) -> str | None:
    if not os.path.isdir(root):
        return None
    for name in sorted(os.listdir(root), reverse=True):
        path = os.path.join(root, name, "package.json")
        if name.endswith("-dry-run") or not os.path.exists(path):
            continue
        if pk.is_publishable(pk.load(path))[0]:
            return path
    return None


def publish(args) -> int:
    from . import publish as pub

    path = _find_latest_approved(args.root) if args.latest_approved else args.path
    if not path:
        print("No approved, unchanged package found. Nothing to publish.")
        return 0
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    pkg = pk.load(path)
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    if args.dry_run:
        gate, outcome, calls = pub.dry_run(pkg, folder, platforms)
        print(f"DRY RUN (no network). Approval gate: {gate}")
        for c in calls:
            print("  " + c)
        for p, o in outcome.items():
            print(f"{p:10} {o}")
        return 0
    base = os.environ.get("MEDIA_BASE_URL")
    if not base and os.environ.get("MEDIA_ROOT_URL"):
        rel = os.path.relpath(folder, os.getcwd()).replace(os.sep, "/")
        base = os.environ["MEDIA_ROOT_URL"].rstrip("/") + "/" + rel

    def save(p):
        pk.save(p, path)
        with open(os.path.join(folder, "review.md"), "w", encoding="utf-8") as f:
            f.write(pk.review_markdown(p))

    import requests

    try:
        outcome = pub.publish_package(pkg, folder, platforms, os.environ, requests.Session(), base, save=save,
                                      uploader=pub.r2_uploader(os.environ))
    except pub.PublishError as exc:
        print(str(exc))
        return 1
    print(f"Package: {path}")
    for p, o in outcome.items():
        print(f"{p:10} {o}")
    return 1 if any(o.startswith("FAILED") for o in outcome.values()) else 0


def check_access(args) -> int:
    import requests

    from . import publish as pub

    results = pub.check_access(os.environ, requests.Session())
    for p, r in results.items():
        print(f"{p:10} {r}")
    return 1 if any(r.startswith("FAILED") for r in results.values()) else 0


def sources(args) -> int:
    candidates, errors = fetch_candidates(read_feed_list(args.feeds), max_age_hours=args.max_age_hours)
    for e in errors:
        print(f"FEED ERROR {e}")
    for c in candidates:
        print(f"{c['id']} {c['published'][:16]} [{c['source']}] {c['title']}\n    {c['url']}")
    print(f"{len(candidates)} usable stories, {len(errors)} feed errors")
    return 0 if candidates else 2


def approve(args) -> int:
    pkg = pk.load(args.path)
    try:
        pk.approve(pkg, args.by, acknowledge_flags=args.ack_flags)
    except ValueError as exc:
        print(f"NOT APPROVED: {exc}")
        return 1
    pk.save(pkg, args.path)
    print(f"Approved by {args.by}. Hash {pkg['content_sha256'][:16]}...")
    return 0


def rehash(args) -> int:
    pkg = pk.rehash(pk.load(args.path))
    pk.save(pkg, args.path)
    print(f"Rehashed; status {pkg['status']}. Review and approve again.")
    return 0


def check(args) -> int:
    ok, reason = pk.is_publishable(pk.load(args.path))
    print(("PUBLISHABLE: " if ok else "BLOCKED: ") + reason)
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="content_engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--feeds", default="news_sources.txt")
    g.add_argument("--out", default="output/packages")
    g.add_argument("--model", default=DEFAULT_MODEL)
    g.add_argument("--max-age-hours", type=int, default=48)
    g.add_argument("--max-rounds", type=int, default=2, help="model calls allowed to fix validation errors")
    g.add_argument("--render", action="store_true", help="also render carousel PNGs")
    g.set_defaults(fn=generate)
    a = sub.add_parser("approve")
    a.add_argument("path")
    a.add_argument("--by", required=True)
    a.add_argument("--ack-flags", action="store_true")
    a.set_defaults(fn=approve)
    r = sub.add_parser("rehash")
    r.add_argument("path")
    r.set_defaults(fn=rehash)
    c = sub.add_parser("check")
    c.add_argument("path")
    c.set_defaults(fn=check)
    rd = sub.add_parser("render")
    rd.add_argument("path")
    rd.set_defaults(fn=render)
    pb = sub.add_parser("publish")
    pb.add_argument("path", nargs="?")
    pb.add_argument("--latest-approved", action="store_true")
    pb.add_argument("--root", default="output/packages")
    pb.add_argument("--platforms", default="facebook,instagram,threads,linkedin,youtube")
    pb.add_argument("--dry-run", action="store_true")
    pb.set_defaults(fn=publish)
    ca = sub.add_parser("check-access")
    ca.set_defaults(fn=check_access)
    so = sub.add_parser("sources")
    so.add_argument("--feeds", default="news_sources.txt")
    so.add_argument("--max-age-hours", type=int, default=48)
    so.set_defaults(fn=sources)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
