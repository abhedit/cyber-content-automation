"""CLI.

  python -m content_engine generate --dry-run      # no network, no API key, no publishing
  python -m content_engine generate                # live research + Gemini (needs GEMINI_API_KEY)
  python -m content_engine approve PATH --by NAME [--ack-flags]
  python -m content_engine rehash PATH             # after editing copy by hand; clears approval
  python -m content_engine check PATH              # exit 0 only if safe to publish

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
    return 1 if v["errors"] else 0


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
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
