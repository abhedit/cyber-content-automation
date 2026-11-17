"""Render carousel slides to 1080x1080 PNGs with an HTML template + headless Chromium.

$0 per image, brand-consistent, and the text on the image is exactly the
validated slide text (no AI image model re-typing words).
"""

from __future__ import annotations

import html
import os

from .validate import word_count

SIZE = 1080
LABELS = ["", "What happened", "Why it matters", "Business impact", "Security recommendations", "Next step"]

# Abhedit brand: white background, dark blue cybersecurity theme, modern enterprise.
NAVY = "#0B2545"
BLUE = "#1D4ED8"
INK = "#0F172A"
MUTED = "#475569"
FONT = "'Inter','Segoe UI','Helvetica Neue',Arial,sans-serif"


def _font_px(text: str, headline: bool) -> int:
    n = word_count(text)
    if headline:
        return 92 if n <= 8 else 80 if n <= 12 else 68
    return 64 if n <= 12 else 56 if n <= 20 else 50


def slide_html(text: str, index: int, total: int, source_line: str = "") -> str:
    headline = index == 1
    label = "" if headline else LABELS[min(index - 1, len(LABELS) - 1)]
    body = html.escape(text.strip())
    foot_source = f'<div class="src">{html.escape(source_line)}</div>' if source_line and index == 2 else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{SIZE}px;height:{SIZE}px;background:#fff;font-family:{FONT};color:{INK}}}
.frame{{position:relative;width:100%;height:100%;padding:96px 96px 88px;display:flex;flex-direction:column}}
.bar{{position:absolute;left:0;top:0;width:24px;height:100%;background:{NAVY}}}
.top{{display:flex;justify-content:space-between;align-items:center;font-size:26px;font-weight:600;color:{BLUE};letter-spacing:.08em;text-transform:uppercase}}
.num{{color:{MUTED};letter-spacing:0}}
.body{{flex:1;display:flex;align-items:center}}
.text{{font-size:{_font_px(text, headline)}px;line-height:1.18;font-weight:{800 if headline else 650};color:{NAVY if headline else INK};letter-spacing:-.01em}}
.foot{{display:flex;justify-content:space-between;align-items:flex-end;gap:24px}}
.brand{{font-size:34px;font-weight:800;color:{NAVY};letter-spacing:.02em}}
.brand span{{color:{BLUE}}}
.src{{font-size:22px;color:{MUTED};max-width:640px;text-align:right}}
</style></head><body><div class="frame"><div class="bar"></div>
<div class="top"><div>{html.escape(label)}</div><div class="num">{index} / {total}</div></div>
<div class="body"><div class="text">{body}</div></div>
<div class="foot"><div class="brand">Abhedit<span>.</span></div>{foot_source}</div>
</div></body></html>"""


def render_slides(pkg: dict, folder: str) -> list[str]:
    """Write slides/slide-N.html and slide-N.png into the package folder.

    Returns PNG paths. Requires the `playwright` Python package and Chromium.
    """
    from playwright.sync_api import sync_playwright

    slides = pkg.get("carousel") or []
    story = pkg.get("story") or {}
    source_line = f"Source: {story.get('source', '')}, {story.get('published', '')[:10]}" if story else ""
    out_dir = os.path.join(folder, "slides")
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    launch = {}
    if os.environ.get("CHROMIUM_PATH"):
        launch["executable_path"] = os.environ["CHROMIUM_PATH"]
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": SIZE, "height": SIZE}, device_scale_factor=1)
        for i, text in enumerate(slides, start=1):
            doc = slide_html(text, i, len(slides), source_line)
            html_path = os.path.join(out_dir, f"slide-{i}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(doc)
            page.set_content(doc, wait_until="load")
            overflow = page.evaluate(
                "(() => { const t = document.querySelector('.text').getBoundingClientRect();"
                " const f = document.querySelector('.foot').getBoundingClientRect();"
                " const top = document.querySelector('.top').getBoundingClientRect();"
                f" return t.top < top.bottom || t.bottom > f.top || f.bottom > {SIZE} || t.right > {SIZE}; }})()"
            )
            if overflow:
                raise ValueError(f"slide {i} text does not fit on the image")
            png = os.path.join(out_dir, f"slide-{i}.png")
            page.screenshot(path=png, clip={"x": 0, "y": 0, "width": SIZE, "height": SIZE})
            paths.append(png)
        browser.close()
    return paths
