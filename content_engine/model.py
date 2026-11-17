"""Gemini client. Prefers the supported `google-genai` SDK; falls back to the
deprecated `google-generativeai` package that generate_content.py still uses."""

from __future__ import annotations

import json
import os
import re
import time

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def call_gemini(prompt: str, model: str = DEFAULT_MODEL, attempts: int = 3, wait_s: int = 30) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set (use --dry-run to test without it)")
    last = None
    for attempt in range(attempts):
        try:
            return _generate(prompt, model, api_key)
        except Exception as exc:  # network / quota / 5xx
            last = exc
            print(f"Gemini attempt {attempt + 1} failed: {exc}")
            if _is_permanent(exc):
                break
            if attempt < attempts - 1:
                time.sleep(wait_s)
    raise RuntimeError(f"Gemini failed: {last}")


def _is_permanent(exc: Exception) -> bool:
    """400/401/403/404 will not succeed on retry; 429 and 5xx might."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code in (400, 401, 403, 404)
    return any(t in str(exc) for t in ("INVALID_ARGUMENT", "PERMISSION_DENIED", "API_KEY_INVALID"))


def _generate(prompt: str, model: str, api_key: str) -> str:
    try:
        from google import genai
        from google.genai import types

        # JSON mode is only available on v1beta (v1 returns 400 INVALID_ARGUMENT).
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version="v1beta"))
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4),
        )
        return resp.text
    except ImportError:
        import google.generativeai as legacy

        legacy.configure(api_key=api_key)
        resp = legacy.GenerativeModel(model).generate_content(
            prompt, generation_config={"response_mime_type": "application/json", "temperature": 0.4}
        )
        return resp.text


def parse_json(text: str) -> dict:
    """Parse model output, tolerating ```json fences."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data
