# Social Media API Access: Step-by-Step Setup

_Checked against platform docs and guides on 2026-11-18. The platforms change these
screens often, so if a menu name differs, look for the closest match._

## Ground rules

- **You** do every login, approval and token step in the platform's own website.
- Tokens are pasted **only** into n8n → *Credentials*, or into GitHub → *Settings → Secrets*
  if GitHub ever posts directly. Never paste them into chat, email, Slack or a repo file.
- Grant only the permissions listed below. Don't grant ads, messaging or "manage everything".
- Nothing posts unless the content package is approved (see `STATUS.md`, section 3).

## Before you start (about 30 minutes, needed by Meta and LinkedIn)

| Item | Why |
|---|---|
| An email address on Abhedit's own domain (e.g. `you@abhedit.com`) | LinkedIn requires a verified business email; Meta business verification prefers it |
| Abhedit website with a **Privacy Policy** page and a contact page | Meta needs a privacy policy URL to switch the app to Live; LinkedIn reviewers check it |
| Admin access to the Abhedit **Facebook Page** and **LinkedIn Company Page** | Only Page admins can connect apps |
| Two-factor authentication on Facebook, Instagram and LinkedIn | Meta requires it for Business Manager admins; it also protects the brand |

---

## 1. Facebook Page (do first; 1–2 hours, same day)

**Permissions:** `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, and
`read_insights` for weekly reports. Posts go to `POST /{page-id}/feed` with a **Page access token**.

1. **Business Portfolio:** go to business.facebook.com → create a Business Portfolio named
   "Abhedit" → *Accounts → Pages → Add* → choose your Page.
2. **Developer app:** go to developers.facebook.com → *My Apps → Create App*.
   - Choose the use case for managing a Page / Pages API.
   - Name it "Abhedit Publisher" and connect it to the Abhedit Business Portfolio.
   - Add your privacy policy URL under *App settings → Basic*.
3. **Add the permissions above** to the app's use case.
4. **Quick test (no posting):** open *Tools → Graph API Explorer*, pick your app, generate a
   User token with those permissions, and run `GET /me/accounts`. Your Page should appear.
   This confirms the setup works.
5. **Permanent token, using a system user:**
   - In business.facebook.com go to *Settings → Users → System users → Add* and name it
     "abhedit-publisher".
   - *Assign assets:* add your **Page**, allowing content creation, and your **App**.
   - Click *Generate token*, choose the app, and tick only the four permissions above.
   - System-user tokens don't expire, so they won't silently stop working.
6. **Put the token in n8n:** *Credentials → New → Facebook Graph API* → paste the token →
   *Test*. Keep a note of which credential it is; don't store the token anywhere else.
7. **Safe first post:** create an **unpublished** post (`published=false`) on the Page.
   It doesn't appear on the timeline. Check it in Meta Business Suite, then delete it.
   Only then switch to real posting.

Advanced Access and App Review are mainly for apps that post to Pages the business does
**not** own. Posting to your own Page normally doesn't need them. If Meta asks for
business verification, upload your company registration document in Business Settings →
*Security Center*.

---

## 2. Instagram (after Facebook; about 1 hour plus image hosting)

**Requirement:** a **Professional (Business or Creator)** account. Personal accounts can't
post through the API. In the Instagram app go to *Settings → Account type and tools →
Switch to professional account → Business*.

**Recommended route, "Instagram API with Instagram Login":** this needs no Facebook Page link.

1. In your **same** Meta app (*Abhedit Publisher*), add the **Instagram** product and choose
   the Business Login for Instagram setup.
2. Permissions: `instagram_business_basic`, `instagram_business_content_publish`, and
   `instagram_business_manage_insights` for reports.
3. Add your Instagram account as an *Instagram tester* or role on the app, accept the
   invite inside Instagram, and generate the token in the app dashboard.
4. Put the token in n8n credentials (HTTP Request node with header auth) and test with
   `GET /me?fields=id,username`.

The alternative route goes through Facebook Login, using `instagram_basic` and
`instagram_content_publish` and a Facebook Page linked to the Instagram account. Use
whichever matches the token you created; the permission names must match the login route.

**How a carousel is posted:** create one container per slide image, then a carousel
container, then `POST /{ig-id}/media_publish`. **Every image must be at a public URL when
publishing.** This is the one engineering task left on our side: approved slides need
to be uploaded somewhere public first, either this public repo or Cloudflare R2.

Limit: about 50–100 API posts per 24 hours, and a carousel counts as one. That is far
above our needs.

---

## 3. LinkedIn

There are two separate levels of access. Start A today, and apply for B in parallel.

### A. Post as your personal profile (self-serve, same day)

1. Go to linkedin.com/developers → *Create app*. LinkedIn requires the app to be linked to a
   Company Page, so pick Abhedit's page and approve the verification request as page admin.
2. *Products*: add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**.
3. Scope: `w_member_social` (plus `openid profile`).
4. In n8n: *Credentials → LinkedIn OAuth2*. Paste the app's Client ID and Client Secret,
   add n8n's redirect URL to the app's *Auth* tab, then click *Connect*.
5. LinkedIn tokens normally last about 60 days. Reconnect in n8n when it warns you.

### B. Post as the Abhedit Company Page (application review, days to weeks, can be refused)

Needs the **Community Management API**, which grants `w_organization_social` and
`r_organization_social`. The posting member must also be a page **Super/Content admin**.

- Create a **new, separate app** just for this product. LinkedIn has required this API to
  be the only product on the app.
- Requirements LinkedIn lists: a verified organization, a verified business email, an
  organization website and domain, a valid privacy policy, the app verified by the
  Abhedit LinkedIn Page, and a **screen recording** of the tool working.
- **A rejected application cannot be resubmitted on the same app**, so prepare it fully first.

Draft use-case text you can adapt:

> Abhedit is a cybersecurity compliance and consulting company. This internal tool
> publishes educational cybersecurity posts to Abhedit's own LinkedIn Page only.
> A system drafts each post from public news sources; a named Abhedit employee reviews
> and approves every post before it is published. We use w_organization_social to create
> posts on our own Page and r_organization_social to read engagement on those posts for
> internal reporting. We do not access member data, send messages, or post to any other
> organization's Page.

The screen recording should show a draft in `review.md`, the approval step, and a post
appearing on the Page. Record it once Facebook publishing works end to end.

---

## 4. When you're done

| Platform | Credential lives in | Tell Claude (no secrets) |
|---|---|---|
| Facebook Page | n8n credential "Facebook Graph API" | "Facebook credential added and tested" + Page name |
| Instagram | n8n credential (header auth) | "Instagram credential added" + account handle |
| LinkedIn personal | n8n credential "LinkedIn OAuth2" | "LinkedIn personal connected" |
| LinkedIn company | same, after approval | "Community Management API approved" |

After that, the remaining build work is:
- Wire the n8n approval gate.
- Host approved slides publicly for Instagram.
- Add the weekly insights report.
- Write a short note in `STATUS.md` for each platform that went live.

## Sources

- Meta Pages API, posts and getting started: https://developers.facebook.com/docs/pages-api/posts , https://developers.facebook.com/docs/pages-api/getting-started
- Instagram content publishing: https://developers.facebook.com/docs/instagram-platform/content-publishing/
- LinkedIn Community Management app review: https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review
- LinkedIn increasing access: https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access
- LinkedIn Community Management API product page: https://developer.linkedin.com/product-catalog/marketing/community-management-api
