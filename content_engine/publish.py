"""Publish an APPROVED content package to Facebook, Instagram, Threads, LinkedIn and YouTube.

Safety:
- Refuses unless `package.is_publishable` (approved, live run, content unchanged since approval).
- Every image/video is checked against the SHA-256 recorded at approval before use,
  including the public URL copy that Meta fetches.
- Each platform is posted at most once per package (`pkg["published"]`).
- Tokens come from environment variables (GitHub Secrets) and are never printed;
  errors are reported without URLs, which can carry tokens.

Configuration (environment variables; a platform without its variables is skipped):
  Facebook  FB_PAGE_ID, FB_PAGE_TOKEN
  Instagram IG_USER_ID, IG_TOKEN            (IG_API_HOST: graph.instagram.com | graph.facebook.com)
  Threads   THREADS_USER_ID, THREADS_TOKEN
  LinkedIn  LINKEDIN_TOKEN, LINKEDIN_AUTHOR (urn:li:person:... or urn:li:organization:...)
  YouTube   YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN   (YT_PRIVACY: public|unlisted|private)
  Images    Instagram/Threads fetch images from a public URL. Either
            R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_BASE_URL
            (Cloudflare R2: only approved images are uploaded at publish time), or
            MEDIA_BASE_URL / MEDIA_ROOT_URL (public repo raw URLs).
  Shared    META_GRAPH_VERSION, LINKEDIN_VERSION
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone

from . import package as pk

PLATFORMS = ["facebook", "instagram", "threads", "linkedin", "youtube"]
REQUIRED = {
    "facebook": ["FB_PAGE_ID", "FB_PAGE_TOKEN"],
    "instagram": ["IG_USER_ID", "IG_TOKEN"],
    "threads": ["THREADS_USER_ID", "THREADS_TOKEN"],
    "linkedin": ["LINKEDIN_TOKEN", "LINKEDIN_AUTHOR"],
    "youtube": ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"],
}
NEEDS_PUBLIC_URLS = {"instagram", "threads"}
LINKEDIN_RESERVED = "\\|{}@[]()<>#*_~"
INSTAGRAM_CAPTION_MAX = 2200
LINKEDIN_COMMENTARY_MAX = 3000


class PublishError(Exception):
    pass


def configured(platform: str, env) -> bool:
    return all(env.get(k) for k in REQUIRED[platform])


def linkedin_escape(text: str) -> str:
    """LinkedIn 'little text' format: reserved characters need a backslash or the post is cut off."""
    return "".join("\\" + ch if ch in LINKEDIN_RESERVED else ch for ch in text)


def _default_linkedin_version(now: datetime) -> str:
    # LinkedIn versions are monthly (YYYYMM) and supported for about a year; use one ~2 months old.
    d = now - timedelta(days=60)
    return f"{d.year}{d.month:02d}"


def _call(http, method: str, url: str, what: str, ok=(200, 201, 202), **kw):
    resp = http.request(method, url, timeout=60, **kw)
    if resp.status_code not in ok:
        detail = ""
        try:
            body = resp.json()
            err = body.get("error", body)
            detail = err.get("message") if isinstance(err, dict) else str(err)
        except Exception:
            detail = (getattr(resp, "text", "") or "")[:200]
        raise PublishError(f"{what}: HTTP {resp.status_code}: {detail}")
    return resp


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Media:
    """Approved media: local bytes + public URLs, all verified against approval hashes."""

    def __init__(self, pkg: dict, folder: str, base_url: str | None, http, uploader=None):
        self.pkg, self.folder, self.base_url, self.http = pkg, folder, (base_url or "").rstrip("/"), http
        self.uploader = uploader  # callable(key, bytes) -> public URL (e.g. Cloudflare R2)
        self._urls: list[str] | None = None
        self.images = (pkg.get("media") or {}).get("images") or []
        self.video = (pkg.get("media") or {}).get("video")
        self._checked_urls: set[str] = set()

    def local_bytes(self, item: dict) -> bytes:
        with open(os.path.join(self.folder, item["file"]), "rb") as f:
            data = f.read()
        if _sha(data) != item["sha256"]:
            raise PublishError(f"{item['file']} differs from the approved file")
        return data

    def public_urls(self) -> list[str]:
        if not self.images:
            raise PublishError("package has no rendered images (run render before approval)")
        if self._urls is not None:
            return self._urls
        if not self.uploader and not self.base_url:
            raise PublishError("no public image hosting configured (set the R2_* secrets)")
        urls = []
        for item in self.images:
            if self.uploader:
                # Upload the verified approved bytes; the key includes the hash so it never collides.
                date = (self.pkg.get("generated_at") or "")[:10]
                key = f"abhedit/{date}/{item['sha256'][:16]}-{os.path.basename(item['file'])}"
                url = self.uploader(key, self.local_bytes(item))
            else:
                url = f"{self.base_url}/{item['file']}"
            if url not in self._checked_urls:
                resp = _call(self.http, "GET", url, f"fetch public copy of {item['file']}")
                if _sha(resp.content) != item["sha256"]:
                    raise PublishError(f"public copy of {item['file']} differs from the approved file")
                self._checked_urls.add(url)
            urls.append(url)
        self._urls = urls
        return urls


# ---------------- platforms ----------------

def _wait_ready(http, url: str, params: dict, field: str, done: str, what: str, sleep, tries: int = 12):
    for _ in range(tries):
        status = _call(http, "GET", url, f"{what} status", params={**params, "fields": field}).json().get(field)
        if status == done:
            return
        if status in ("ERROR", "EXPIRED"):
            raise PublishError(f"{what}: processing failed ({status})")
        sleep(5)
    raise PublishError(f"{what}: not ready after {tries * 5}s")


def post_facebook(pkg, media: Media, env, http, sleep) -> dict:
    g = f"https://graph.facebook.com/{env.get('META_GRAPH_VERSION', 'v25.0')}"
    page, token = env["FB_PAGE_ID"], env["FB_PAGE_TOKEN"]
    if not media.images:
        raise PublishError("package has no rendered images")
    photo_ids = []
    for item in media.images:  # direct upload of verified bytes: no public URL needed
        r = _call(http, "POST", f"{g}/{page}/photos", "facebook photo upload",
                  data={"published": "false", "access_token": token},
                  files={"source": (os.path.basename(item["file"]), media.local_bytes(item), "image/jpeg")})
        photo_ids.append(r.json()["id"])
    data = {"message": pkg["posts"]["facebook"], "access_token": token}
    for i, pid in enumerate(photo_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    post_id = _call(http, "POST", f"{g}/{page}/feed", "facebook post", data=data).json()["id"]
    return {"id": post_id, "url": f"https://www.facebook.com/{post_id}"}


def post_instagram(pkg, media: Media, env, http, sleep) -> dict:
    host = env.get("IG_API_HOST", "graph.instagram.com")
    g = f"https://{host}/{env.get('META_GRAPH_VERSION', 'v25.0')}"
    uid, token = env["IG_USER_ID"], env["IG_TOKEN"]
    caption = pkg["posts"]["instagram"]
    if len(caption) > INSTAGRAM_CAPTION_MAX:
        raise PublishError(f"instagram caption is {len(caption)} characters (max {INSTAGRAM_CAPTION_MAX})")
    children = []
    for url in media.public_urls():
        r = _call(http, "POST", f"{g}/{uid}/media", "instagram image container",
                  data={"image_url": url, "is_carousel_item": "true", "access_token": token})
        children.append(r.json()["id"])
    container = _call(http, "POST", f"{g}/{uid}/media", "instagram carousel container",
                      data={"media_type": "CAROUSEL", "children": ",".join(children),
                            "caption": caption, "access_token": token}).json()["id"]
    _wait_ready(http, f"{g}/{container}", {"access_token": token}, "status_code", "FINISHED", "instagram carousel", sleep)
    media_id = _call(http, "POST", f"{g}/{uid}/media_publish", "instagram publish",
                     data={"creation_id": container, "access_token": token}).json()["id"]
    return {"id": media_id, "url": None}


def post_threads(pkg, media: Media, env, http, sleep) -> dict:
    g = "https://graph.threads.net/v1.0"
    uid, token = env["THREADS_USER_ID"], env["THREADS_TOKEN"]
    text = pkg["posts"]["threads"]
    if len(text) > pk.THREADS_MAX:
        raise PublishError(f"threads text is {len(text)} characters (max {pk.THREADS_MAX})")
    children = []
    for url in media.public_urls():
        r = _call(http, "POST", f"{g}/{uid}/threads", "threads image container",
                  data={"media_type": "IMAGE", "image_url": url, "is_carousel_item": "true", "access_token": token})
        children.append(r.json()["id"])
    container = _call(http, "POST", f"{g}/{uid}/threads", "threads carousel container",
                      data={"media_type": "CAROUSEL", "children": ",".join(children),
                            "text": text, "access_token": token}).json()["id"]
    _wait_ready(http, f"{g}/{container}", {"access_token": token}, "status", "FINISHED", "threads carousel", sleep)
    post_id = _call(http, "POST", f"{g}/{uid}/threads_publish", "threads publish",
                    data={"creation_id": container, "access_token": token}).json()["id"]
    return {"id": post_id, "url": None}


def post_linkedin(pkg, media: Media, env, http, sleep) -> dict:
    base = "https://api.linkedin.com/rest"
    author = env["LINKEDIN_AUTHOR"]
    headers = {
        "Authorization": f"Bearer {env['LINKEDIN_TOKEN']}",
        "LinkedIn-Version": env.get("LINKEDIN_VERSION") or _default_linkedin_version(datetime.now(timezone.utc)),
        "X-Restli-Protocol-Version": "2.0.0",
    }
    commentary = linkedin_escape(pkg["posts"]["linkedin"])
    if len(commentary) > LINKEDIN_COMMENTARY_MAX:
        raise PublishError(f"linkedin text is {len(commentary)} characters (max {LINKEDIN_COMMENTARY_MAX})")
    if not media.images:
        raise PublishError("package has no rendered images")
    image_urns = []
    for item in media.images:
        data = media.local_bytes(item)
        init = _call(http, "POST", f"{base}/images?action=initializeUpload", "linkedin image init",
                     headers=headers, json={"initializeUploadRequest": {"owner": author}}).json()["value"]
        _call(http, "PUT", init["uploadUrl"], "linkedin image upload",
              headers={"Authorization": headers["Authorization"]}, data=data)
        image_urns.append(init["image"])
    body = {
        "author": author,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "content": {"multiImage": {"images": [
            {"id": urn, "altText": pk._fit(s, 120)} for urn, s in zip(image_urns, pkg["carousel"])
        ]}},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    last = None
    for _ in range(6):  # images can take a few seconds to become available
        resp = http.request("POST", f"{base}/posts", timeout=60, headers=headers, json=body)
        if resp.status_code == 201:
            post_urn = resp.headers.get("x-restli-id", "")
            return {"id": post_urn, "url": f"https://www.linkedin.com/feed/update/{post_urn}/" if post_urn else None}
        last = resp
        if resp.status_code not in (400, 422):
            break
        sleep(5)
    raise PublishError(f"linkedin post: HTTP {last.status_code}: {(getattr(last, 'text', '') or '')[:200]}")


def post_youtube(pkg, media: Media, env, http, sleep) -> dict:
    if not media.video:
        raise PublishError("package has no short.mp4 (ffmpeg missing at render time)")
    video = media.local_bytes(media.video)
    tok = _call(http, "POST", "https://oauth2.googleapis.com/token", "youtube token refresh",
                data={"client_id": env["YT_CLIENT_ID"], "client_secret": env["YT_CLIENT_SECRET"],
                      "refresh_token": env["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json()["access_token"]
    yt = pkg["posts"]["youtube"]
    meta = {
        "snippet": {"title": yt["title"], "description": yt["description"][:4900], "tags": yt["tags"], "categoryId": "28"},
        "status": {"privacyStatus": env.get("YT_PRIVACY", "public"), "selfDeclaredMadeForKids": False},
    }
    init = _call(http, "POST",
                 "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                 "youtube upload init",
                 headers={"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                          "X-Upload-Content-Length": str(len(video))}, json=meta)
    upload_url = init.headers.get("Location") or init.headers.get("location")
    if not upload_url:
        raise PublishError("youtube upload init: no upload URL returned")
    vid = _call(http, "PUT", upload_url, "youtube upload",
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"}, data=video).json()["id"]
    return {"id": vid, "url": f"https://youtube.com/shorts/{vid}"}


POSTERS = {
    "facebook": post_facebook,
    "instagram": post_instagram,
    "threads": post_threads,
    "linkedin": post_linkedin,
    "youtube": post_youtube,
}


def publish_package(pkg: dict, folder: str, platforms: list[str], env, http, base_url: str | None,
                    save=None, sleep=time.sleep, now=None, uploader=None) -> dict[str, str]:
    """Post to each platform. Returns {platform: outcome}. Raises if the package is not publishable."""
    ok, reason = pk.is_publishable(pkg)
    if not ok:
        raise PublishError(f"refusing to publish: {reason}")
    pkg.setdefault("published", {})
    media = Media(pkg, folder, base_url, http, uploader)
    outcome = {}
    for platform in platforms:
        if platform not in POSTERS:
            outcome[platform] = "unknown platform"
            continue
        if platform in pkg["published"]:
            outcome[platform] = "already published"
            continue
        if not configured(platform, env):
            outcome[platform] = "skipped (not configured)"
            continue
        try:
            result = POSTERS[platform](pkg, media, env, http, sleep)
        except PublishError as exc:
            outcome[platform] = f"FAILED: {exc}"
            continue
        except Exception as exc:  # network errors etc.; never include request details
            outcome[platform] = f"FAILED: {type(exc).__name__}"
            continue
        result["at"] = (now or datetime.now(timezone.utc)).isoformat()
        pkg["published"][platform] = result
        outcome[platform] = f"published {result.get('url') or result['id']}"
        if save:
            save(pkg)  # persist after each success so a later failure cannot cause a double post
    return outcome


# ---------------- read-only access check ----------------

ACCESS_KEYS = {  # token-only, so the check can also tell you the IDs to save
    "facebook": ["FB_PAGE_TOKEN"],
    "instagram": ["IG_TOKEN"],
    "threads": ["THREADS_TOKEN"],
    "linkedin": ["LINKEDIN_TOKEN"],
    "youtube": ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"],
}


def check_access(env, http) -> dict[str, str]:
    """Read-only: confirms each token works and prints the account name + ID to store."""
    ver = env.get("META_GRAPH_VERSION", "v25.0")
    checks = {
        "facebook": lambda: _who(_call(http, "GET", f"https://graph.facebook.com/{ver}/me", "facebook page",
                                       params={"fields": "id,name", "access_token": env["FB_PAGE_TOKEN"]}).json(),
                                 "name", "id", "FB_PAGE_ID"),
        "instagram": lambda: _who(_call(http, "GET", f"https://{env.get('IG_API_HOST', 'graph.instagram.com')}/{ver}/me",
                                        "instagram account",
                                        params={"fields": "user_id,username", "access_token": env["IG_TOKEN"]}).json(),
                                  "username", "user_id", "IG_USER_ID"),
        "threads": lambda: _who(_call(http, "GET", "https://graph.threads.net/v1.0/me", "threads account",
                                      params={"fields": "id,username", "access_token": env["THREADS_TOKEN"]}).json(),
                                "username", "id", "THREADS_USER_ID"),
        "linkedin": lambda: _linkedin_who(_call(http, "GET", "https://api.linkedin.com/v2/userinfo", "linkedin profile",
                                                headers={"Authorization": f"Bearer {env['LINKEDIN_TOKEN']}"}).json()),
        "youtube": lambda: _youtube_channel(env, http),
    }
    out = {}
    for platform in PLATFORMS:
        if not all(env.get(k) for k in ACCESS_KEYS[platform]):
            out[platform] = "not configured"
            continue
        try:
            out[platform] = f"OK ({checks[platform]()})"
        except PublishError as exc:
            out[platform] = f"FAILED: {exc}"
        except Exception as exc:
            out[platform] = f"FAILED: {type(exc).__name__}"
    return out


def _who(data: dict, name_key: str, id_key: str, var: str) -> str:
    return f"{data.get(name_key)}; {var}={data.get(id_key)}"


def _linkedin_who(data: dict) -> str:
    # 'sub' is the member id; posting as yourself uses LINKEDIN_AUTHOR=urn:li:person:<sub>
    return f"{data.get('name')}; personal LINKEDIN_AUTHOR=urn:li:person:{data.get('sub')}"


def _youtube_channel(env, http) -> str:
    tok = _call(http, "POST", "https://oauth2.googleapis.com/token", "youtube token refresh",
                data={"client_id": env["YT_CLIENT_ID"], "client_secret": env["YT_CLIENT_SECRET"],
                      "refresh_token": env["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json()["access_token"]
    items = _call(http, "GET", "https://www.googleapis.com/youtube/v3/channels", "youtube channel",
                  params={"part": "snippet", "mine": "true"}, headers={"Authorization": f"Bearer {tok}"}).json().get("items") or []
    return items[0]["snippet"]["title"] if items else "no channel"


# ---------------- dry run (no network) ----------------

class RecordingHttp:
    """Stands in for `requests`: serves approved media from disk for public URLs and
    returns fake IDs for API calls, recording each call (without secrets)."""

    def __init__(self, folder: str, base_url: str):
        self.folder, self.base_url, self.calls, self._n = folder, base_url.rstrip("/"), [], 0

    def request(self, method, url, **kw):
        class R:
            pass

        r = R()
        r.status_code, r.headers, r.text = 200, {}, ""
        if method == "GET" and url.startswith(self.base_url + "/"):
            with open(os.path.join(self.folder, url[len(self.base_url) + 1:]), "rb") as f:
                r.content = f.read()
            self.calls.append(f"GET  {url}  (verify approved image)")
            return r
        self._n += 1
        payload = {"id": f"dry{self._n}", "status": "FINISHED", "status_code": "FINISHED",
                   "access_token": "dry-token", "value": {"uploadUrl": f"https://upload.example/{self._n}",
                                                         "image": f"urn:li:image:dry{self._n}"}}
        r.json = lambda: payload
        if "upload/youtube" in url:
            r.headers = {"Location": "https://upload.example/yt"}
        if url.endswith("/rest/posts"):
            r.status_code, r.headers = 201, {"x-restli-id": "urn:li:share:dry"}
        fields = sorted((kw.get("data") or kw.get("json") or kw.get("params") or {}).keys()) if not isinstance(kw.get("data"), bytes) else ["<file bytes>"]
        fields += ["<file bytes>"] if kw.get("files") else []
        fields = [f for f in fields if f not in ("access_token", "client_secret", "refresh_token")]
        self.calls.append(f"{method:4} {url.split('?')[0]}  {fields}")
        return r


DRY_ENV = {
    "FB_PAGE_ID": "PAGE_ID", "FB_PAGE_TOKEN": "x", "IG_USER_ID": "IG_USER_ID", "IG_TOKEN": "x",
    "THREADS_USER_ID": "THREADS_USER_ID", "THREADS_TOKEN": "x", "LINKEDIN_TOKEN": "x",
    "LINKEDIN_AUTHOR": "urn:li:person:YOU", "YT_CLIENT_ID": "x", "YT_CLIENT_SECRET": "x", "YT_REFRESH_TOKEN": "x",
}


def dry_run(pkg: dict, folder: str, platforms: list[str]) -> tuple[str, dict, list[str]]:
    """Run every poster against RecordingHttp. Ignores the approval gate but reports it."""
    gate = pk.is_publishable(pkg)
    http = RecordingHttp(folder, "https://media.example/package")
    media = Media(pkg, folder, http.base_url, http)
    outcome = {}
    for p in platforms:
        try:
            r = POSTERS[p](pkg, media, DRY_ENV, http, lambda s: None)
            outcome[p] = f"would publish ({r['id']})"
        except PublishError as exc:
            outcome[p] = f"would FAIL: {exc}"
    return ("PUBLISHABLE" if gate[0] else f"BLOCKED ({gate[1]})"), outcome, http.calls


def r2_uploader(env):
    """Cloudflare R2 (S3-compatible) uploader, or None when R2 is not configured."""
    keys = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE_URL"]
    if not all(env.get(k) for k in keys):
        return None
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    base = env["R2_PUBLIC_BASE_URL"].rstrip("/")

    def upload(key: str, data: bytes) -> str:
        s3.put_object(Bucket=env["R2_BUCKET"], Key=key, Body=data, ContentType="image/jpeg")
        return f"{base}/{key}"

    return upload
