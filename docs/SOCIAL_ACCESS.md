# Social Media Access: Fully Cloud Setup

_Updated 2026-11-24. Platform menus change often; if a name differs, look for the closest match._

## How the automation runs (no laptop needed)

```
GitHub Actions (free, cloud)
  Generate Content Package ──> you review review.md ──> Approve Content Package
                                                              │ (automatic)
                                                              ▼
                                         Publish Approved Content ──> Facebook, Instagram,
                                                                      Threads, LinkedIn, YouTube
  Social Access Check (every Monday) ──> emails you if any token stopped working
```

- Your tokens are stored as **GitHub Secrets**. You paste them in GitHub's settings page;
  GitHub encrypts them, and nobody (including Claude) can read them back.
- Nothing posts until **you** run *Approve Content Package*, and only if the content,
  images and video are unchanged since approval.
- A platform whose secrets are missing is simply skipped, so you can connect them one at a time.

### Where to paste each secret

GitHub → repository **abhedit/cyber-content-automation** → **Settings → Secrets and variables
→ Actions → New repository secret**. Use exactly these names:

| Platform | Secret names |
|---|---|
| Facebook | `FB_PAGE_TOKEN`, `FB_PAGE_ID` |
| Instagram | `IG_TOKEN`, `IG_USER_ID` |
| Threads | `THREADS_TOKEN`, `THREADS_USER_ID` |
| LinkedIn | `LINKEDIN_TOKEN`, `LINKEDIN_AUTHOR` |
| YouTube | `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` |

**You don't need to hunt for the IDs.** Add the token first, then run **Actions → Social
Access Check → Run workflow**. It prints the account name and the exact ID value to save,
for example `THREADS_USER_ID=1234`. IDs are not secret, but store them as secrets too
for simplicity.

Never paste tokens into chat, email, Slack, n8n notes or any file in the repo.

### Before you start (needed by Meta, LinkedIn and Google)

- An email address on Abhedit's domain.
- An Abhedit website with a **Privacy Policy** page.
- Admin access to the Abhedit Facebook Page, LinkedIn Company Page and YouTube channel.
- Two-factor login turned on for all accounts.

---

## 1. Facebook Page

Permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `read_insights`.

1. **business.facebook.com:** create the Business Portfolio "Abhedit" and add your Page.
2. **developers.facebook.com → My Apps → Create App:** name it "Abhedit Publisher", choose
   the use case for managing a Page, connect it to the portfolio, and add your privacy
   policy URL.
3. Add the four permissions above.
4. **Business Settings → Users → System users → Add** "abhedit-publisher":
   - *Assign assets*: add the Page (create content) and the app.
   - *Generate token*: tick only the four permissions. This token does not expire.
5. Save it as GitHub secret `FB_PAGE_TOKEN`, run *Social Access Check*, and save the
   printed `FB_PAGE_ID`.

## 2. Instagram

1. In the Instagram app, switch to a **Professional → Business** account.
2. In the same Meta app, add **Instagram → API setup with Instagram business login**.
3. Permissions: `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_insights`.
4. Add the Instagram account to the app and accept the invite in Instagram.
5. Generate the token, save it as `IG_TOKEN`, run *Social Access Check*, and save `IG_USER_ID`.

**Token life:** about 60 days. Generate a new one when the Monday check fails, or set a
calendar reminder every 50 days.

## 3. Threads

1. In developers.facebook.com, open your app and add the **Threads API** use case. Meta may
   ask you to create a separate app for Threads; that's fine.
2. Permissions: `threads_basic`, `threads_content_publish` (and `threads_manage_insights` for reports).
3. Under *Roles*, add your Threads account as a **Threads tester**, then accept the invite in
   Threads (**Settings → Account → Website permissions → Invites**).
4. Generate a **long-lived** token from the Threads use case's token tool, save it as
   `THREADS_TOKEN`, run *Social Access Check*, and save `THREADS_USER_ID`.

Token life is about 60 days, the same as Instagram.

## 4. LinkedIn

### A. Personal profile (same day)
1. **linkedin.com/developers → Create app** "Abhedit Publisher", linked to the Abhedit
   Company Page. Approve the page verification as admin.
2. *Products*: add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**.
3. Go to **Docs and tools → OAuth Token Tools → Create token**. Pick the app and tick
   `openid`, `profile`, `w_member_social`, then sign in.
4. Save the token as `LINKEDIN_TOKEN` and run *Social Access Check*. It prints
   `LINKEDIN_AUTHOR=urn:li:person:…`; save that as `LINKEDIN_AUTHOR`.

Token life is about 60 days.

### B. Company Page (application review, days to weeks)

Apply for the **Community Management API** on a **new, separate app**. Requirements:
- a verified organization and business email;
- a website and privacy policy;
- a screen recording of the tool working.

**A rejected application cannot be resubmitted on the same app**, so prepare it fully first.

Use-case text:

> Abhedit is a cybersecurity compliance and consulting company. This internal tool
> publishes educational cybersecurity posts to Abhedit's own LinkedIn Page only.
> A system drafts each post from public news sources; a named Abhedit employee reviews
> and approves every post before it is published. We use w_organization_social to create
> posts on our own Page and r_organization_social to read engagement on those posts for
> internal reporting. We do not access member data, send messages, or post to any other
> organization's Page.

Once approved, set `LINKEDIN_AUTHOR=urn:li:organization:<your company page id>`. The page
id is the number in your page's admin URL.

## 5. YouTube (Shorts)

The system turns each approved carousel into a 24-second vertical video (`short.mp4`) and
uploads it as a Short.

1. **console.cloud.google.com:** create the project "Abhedit Publisher" and enable
   **YouTube Data API v3**.
2. **APIs & Services → OAuth consent screen:**
   - User type *External*, app name "Abhedit Publisher", your privacy policy URL.
   - Scopes `youtube.upload` and `youtube.readonly`.
   - **Set publishing status to "In production".** Apps left in *Testing* have refresh
     tokens that expire after about 7 days.
   - Google will show an "unverified app" warning; as the owner you can continue.
3. **Credentials → Create OAuth client ID → Web application.** Add the redirect URI
   `https://developers.google.com/oauthplayground`. Save the Client ID and Client Secret
   as `YT_CLIENT_ID` and `YT_CLIENT_SECRET`.
4. **developers.google.com/oauthplayground:**
   - Gear icon → tick *Use your own OAuth credentials* and enter the ID and secret.
   - Authorize the scopes `https://www.googleapis.com/auth/youtube.upload` and
     `https://www.googleapis.com/auth/youtube.readonly`, signing in as the Abhedit
     channel owner.
   - Click *Exchange authorization code for tokens* and copy the **refresh token** into
     `YT_REFRESH_TOKEN`.
5. Run *Social Access Check*. It should print your channel name.

**Important:** Google keeps uploads from **unaudited** API projects **private** until you
pass its free *YouTube API Services audit* (apply through the YouTube API Services Audit and
Quota Extension Form). Until then, Shorts upload as private and you can switch them to
public by hand in YouTube Studio.

---

## Turning it on, step by step

1. Merge the development branch into `main`. Workflows only run from `main`.
2. Add the secrets for **one** platform (start with Facebook) and run *Social Access Check*.
3. Run **Publish Approved Content** with *Dry run* ticked to see the exact API calls.
4. Generate → review → approve a package. Publishing then starts automatically. Check the
   post on the platform.
5. Add the next platform's secrets. Repeat.

## Can Claude in the cloud do this instead of GitHub?

Yes, but it isn't the best choice for the daily posting:

| | GitHub Actions (recommended) | Claude cloud session |
|---|---|---|
| Where tokens live | GitHub Secrets (you paste them in GitHub) | The environment's network secrets: Claude shows you a secure form, and a proxy adds the token to requests. Claude never sees it. |
| Cost per day | $0 | Uses your Claude plan for every run |
| Reliability | Same code path every time | A conversation; better for judgment work |
| YouTube | Works | Awkward: Google's token refresh puts the secret in the request body, which the proxy cannot fill in |

Use GitHub Actions for posting. Use Claude for research tuning, reviewing drafts, fixing
failures and reading the weekly report.

## Sources

- Meta Pages API: https://developers.facebook.com/docs/pages-api/posts
- Instagram content publishing (JPEG only, public URLs): https://developers.facebook.com/docs/instagram-platform/content-publishing/
- Threads publishing: https://developers.facebook.com/docs/threads/posts/
- LinkedIn posts, multi-image and little-text escaping: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api , https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/multiimage-post-api
- LinkedIn Community Management review: https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review
- YouTube videos.insert (unaudited uploads are private): https://developers.google.com/youtube/v3/docs/videos/insert
