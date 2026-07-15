# Putting EquiSphere online (shareable link)

Goal: turn the local app into a private web link (like `clearshelf.streamlit.app`) you and shop owners can open from any browser. It's free. The three accounts/steps below are the only parts I can't do for you (they need your login).

**Time:** ~20–30 minutes, once.

---

## What's already done for you
- `requirements.txt` — tells the host what to install (Streamlit, pandas, altair, openpyxl).
- `.gitignore` — makes sure your **real client numbers never get uploaded**. Only the synthetic `demo_data/` ships. Your Casa files stay on your Mac.
- The project is already a git repository with a first commit, ready to push.

---

## Step 1 — Get the code onto GitHub

**The easy, no-terminal way (GitHub Desktop):**
1. Make a free account at **github.com** (if you don't have one).
2. Download **GitHub Desktop** (desktop.github.com) and sign in.
3. In GitHub Desktop: **File → Add Local Repository →** choose the folder
   `Documents/All brands/System/dead-stock-predictor`.
4. Click **Publish repository**. Tick **"Keep this code private"**. Publish.

That uploads everything (minus the ignored real-data files) to a private GitHub repo.

---

## Step 2 — Deploy on Streamlit Community Cloud
1. Go to **share.streamlit.io** and click **Sign in with GitHub** (authorize it).
2. Click **Create app → Deploy a public app from GitHub** (private repos work too).
3. Fill in:
   - **Repository:** `your-username/dead-stock-predictor`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Click **Deploy**. Wait ~2–3 minutes while it installs and boots.
5. You get a URL like `https://clearshelf-xxxx.streamlit.app` — that's your live app.

---

## Step 3 — Keep it private (recommended)
Your app lets anyone who opens it upload data, so lock it down:
1. In the app's **⋮ menu → Settings → Sharing**.
2. Set it to **"Only specific people can view this app"** and add your email
   (and any client emails you want to give access to).

Now only invited people can open it. Uploaded files are processed in memory and
**not stored** by Streamlit, but restricting viewers is still the safe default.

---

## Updating the app later
When I change the code, just open **GitHub Desktop → Commit → Push**. Streamlit
Cloud redeploys automatically within a minute. No re-setup.

---

## Enabling "Email the list" (optional)
The dead-stock report can email the filtered product list as a CSV. That needs an
SMTP account, added as a **secret** so no password ever goes in the code or through
chat. In Streamlit Cloud: **app → Settings → Secrets**, paste:

```toml
[email]
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = "you@yourdomain.com"
smtp_pass = "an-app-password"      # use an app password, not your real one
from = "EquiSphere <you@yourdomain.com>"
```

Until that's set, the Email button politely tells the user to download the CSV/Excel
instead — it never errors. (To test locally, put the same block in
`.streamlit/secrets.toml`, which is gitignored.)

## Customer logins ("pay first, then log in")
The app is gated by a login **when logins are configured** (otherwise it's open, for
local testing). Logins live in secrets, so passwords never touch the code or the repo.

In Streamlit Cloud: **app → Settings → Secrets**, add a line per paying shop:

```toml
[auth.users]
willowfarm  = "a-password-you-give-them"
sunnyside   = "another-password"
```

Flow: a shop **pays on your WordPress site** → you **add a line here** and email them
their username + password → they log in. To cancel a shop, delete their line.
(This is the manual MVP; automating "payment → auto-create login" is a later step.)

Locally, `.streamlit/secrets.toml` already has a demo login — **username `demo`,
password `demo`** — so you can see the login screen. Change/remove it for real use.

## Notes
- **Cost:** free on Streamlit Community Cloud for this size of app.
- **The `.streamlit/config.toml`** (theme) and `demo_data/` are included, so the
  hosted app looks identical to your local one and the "Try demo data" button works.
- If deploy fails, it's almost always a missing package — tell me the error and
  I'll fix `requirements.txt`.
