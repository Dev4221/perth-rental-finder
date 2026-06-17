# Deploying Perth Rental Finder (free, on Render)

This gets the app live at a public URL, on Render's free tier, with the
13.5MB `data/rental.duckdb` warehouse committed straight into the repo
(no paid persistent disk needed — see the reasoning below).

## Why this approach

DuckDB needs a real file on disk, but Render's free tier has no persistent
disk — any file written while the app is *running* gets wiped on every
restart or redeploy. The warehouse, though, is never written to at
runtime: it's built once by the ETL scripts and only ever *read* by the
running app (`get_connection()` in `database.py` opens it with
`read_only=True`). That means it can simply be committed to the Git repo
like any other file. Render rebuilds the deployed image from the repo on
every deploy, so the warehouse is always there, fresh, for free.

The one real tradeoff of the free tier: the service spins down after about
15 minutes of no traffic, and the next request triggers a ~1 minute cold
start. Step 4 below sets up a free uptime ping to substantially reduce how
often this happens — not a 100% guarantee, but a well-established,
low-effort mitigation.

## Step 1 — Get the code into a GitHub repo

If the project isn't in Git yet:

```powershell
cd C:\perth-rental-tracker
git init
git add .
git commit -m "Initial commit"
```

Check `.gitignore` (included in this batch of files) is in place *before*
the `git add .` — it keeps `.env` (your local API key file) and
`__pycache__` out of the repo. Double check with:

```powershell
git status
```

`.env` should NOT appear in the list of files to be committed. If it does,
something's wrong with `.gitignore` — stop and fix that before pushing
anywhere, since committing an API key to a public repo means it needs to be
revoked and rotated immediately.

Then create a new repository on GitHub (via the website, no need to
initialize it with a README) and push:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/perth-rental-finder.git
git branch -M main
git push -u origin main
```

Confirm `data/rental.duckdb` actually appears in the repo on GitHub's web
interface afterward — GitHub will warn if a file is unusually large, but
13.5MB is well within normal limits and shouldn't trigger anything.

## Step 2 — Create the Render service

1. Go to [render.com](https://render.com) and sign up (GitHub login is the
   easiest path, since it can read your repos directly).
2. Click **New** → **Web Service**.
3. Connect the `perth-rental-finder` repo.
4. Configure:
   - **Name**: anything, e.g. `perth-rental-finder`
   - **Region**: closest to you or your audience (Singapore is closest to
     Perth, if available; otherwise Oregon is Render's default)
   - **Branch**: `main`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
5. Do NOT click "Create Web Service" yet — first add the environment
   variable in step 3.

## Step 3 — Add the API key as an environment variable

Still on the service creation screen (or afterward, under the service's
**Environment** tab):

- **Key**: `ANTHROPIC_API_KEY`
- **Value**: your actual API key from the Anthropic Console

This is the one secret the app needs. It's read via `os.getenv(...)` in
`main.py` already — no code change needed, just this one dashboard entry.
Never put this in the code or commit it to the repo.

Once that's added, click **Create Web Service**. The first build will take
a few minutes — Render installs everything in `requirements.txt`, then
starts the app. Watch the build logs; if anything fails, the error will be
near the bottom of the log.

When it succeeds, Render gives you a URL like
`https://perth-rental-finder.onrender.com`. Visit it — you should see the
chat interface. Visit `/dashboard` too, to confirm that route works in this
new environment (it depends on the same warehouse file, so if the chat
works, the dashboard should too).

## Step 4 — Keep it from sleeping too often (free, optional but recommended)

1. Go to [uptimerobot.com](https://uptimerobot.com) and create a free
   account.
2. Add a new **HTTP(s)** monitor.
3. URL: `https://YOUR-APP.onrender.com/healthz` (the lightweight endpoint
   added to `main.py` specifically for this — it doesn't touch the
   database, so it's as cheap a ping as possible).
4. Interval: every 5 minutes (UptimeRobot's free plan supports this).
5. Save.

This isn't an officially-supported trick and isn't a 100% guarantee against
cold starts (Render could change behavior, a ping could be missed, etc.) —
but it's a well-established, free mitigation that meaningfully reduces how
often anyone hits a cold service. If reliability becomes more important
later (e.g. actively sending this link out for interviews this week),
Render's paid Starter plan ($7/month) removes the sleep behavior entirely.

## After deploying

- Update `README.md`'s "Running it" section with the live URL, so anyone
  reading the repo sees it immediately rather than having to find it.
- Test the actual workflows live, not just that the homepage loads — try
  a deep-dive query, the dashboard, and a few of the bug-fix verification
  prompts from earlier in this project (e.g. asking about Cannington,
  checking a sparse suburb like Maylands doesn't show fabricated stats).
- Consider a custom domain later if useful, but the default
  `onrender.com` URL is perfectly fine to send to a hiring manager as-is.
