# 📈 Personal AI Stock Advisor Agent

Runs daily at **9:00 AM ET (Mon–Fri)** via GitHub Actions. Screens S&P 500 stocks, 
analyzes picks with Claude AI, and sends a formatted **WhatsApp message** via CallMeBot.
You can reply to reconfigure it anytime.

---

## Architecture

| Component | Service | Cost |
|-----------|---------|------|
| Scheduler | GitHub Actions cron | Free (2000 min/month) |
| Market data | Yahoo Finance (yfinance) | Free, no key needed |
| News/sentiment | Finnhub free tier | Free, no credit card |
| AI analysis | Anthropic Claude API | ~$0.01–0.05/day |
| WhatsApp out | CallMeBot | Free |
| WhatsApp in | CallMeBot webhook → Render | Free |
| Config store | GitHub Gist | Free |

---

## One-Time Setup

### Step 1 — Fork / clone this repo to GitHub

```bash
git clone https://github.com/YOUR_USERNAME/stock-agent.git
cd stock-agent
```

### Step 2 — Activate CallMeBot (WhatsApp outbound)

1. Save the number **+34 644 60 47 17** in your WhatsApp contacts (name it "CallMeBot")
2. Send this exact message to that contact:
   ```
   I allow callmebot to send me messages
   ```
3. You'll receive a reply with your **API key** (looks like `1234567`)
4. Note your **full phone number with country code** (e.g. `19725551234` for US)

### Step 3 — Get a Finnhub API key (free)

1. Go to [finnhub.io](https://finnhub.io) → Sign Up (no credit card)
2. Copy your API key from the dashboard

### Step 4 — Create a GitHub Gist for config storage

1. Go to [gist.github.com](https://gist.github.com)
2. Create a **secret** gist named `config.json` with this content:
   ```json
   {
     "short_term_budget": 25,
     "long_term_budget": 50,
     "max_short_picks": 2,
     "max_long_picks": 3,
     "stop_loss_pct": 5,
     "target_gain_pct": 8,
     "enabled": true,
     "timezone": "America/New_York"
   }
   ```
3. Copy the **Gist ID** from the URL: `gist.github.com/YOUR_USERNAME/`**`THIS_PART`**

### Step 5 — Create a GitHub Personal Access Token

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Create token with **Gist read/write** permission (`gist` scope)
3. Copy the token

### Step 6 — Add GitHub Actions Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|-------------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `FINNHUB_API_KEY` | Your Finnhub API key |
| `CALLMEBOT_PHONE` | Your WhatsApp number e.g. `19725551234` |
| `CALLMEBOT_APIKEY` | Your CallMeBot API key |
| `GITHUB_GIST_TOKEN` | Your GitHub personal access token |
| `GIST_ID` | Your Gist ID from Step 4 |
| `WEBHOOK_SECRET` | Any random string e.g. `mySecret42!` |

### Step 7 — Test with a dry run

1. Go to **Actions** tab in your GitHub repo
2. Click **Daily Stock Picks** → **Run workflow**
3. Add env var `DRY_RUN=true` (or set it temporarily in the workflow YAML)
4. Watch the logs — the WhatsApp message will print but not send

### Step 8 — Deploy the webhook to Render (for WhatsApp commands)

1. Go to [render.com](https://render.com) → Sign up (free)
2. New → Web Service → Connect your GitHub repo
3. Render will auto-detect `render.yaml`
4. Add all 7 environment variables in Render's dashboard
5. Deploy — you'll get a URL like `https://stock-agent-webhook.onrender.com`
6. Test it:
   ```bash
   curl https://stock-agent-webhook.onrender.com/health
   ```

---

## Triggering Manually

1. Go to your repo → **Actions** → **Daily Stock Picks**
2. Click **Run workflow** → **Run workflow** (green button)
3. View the logs in real time

---

## WhatsApp Commands

Reply to any message from the bot with these commands:

| Command | Effect |
|---------|--------|
| `SET ST 30` | Set short-term budget to $30 |
| `SET LT 75` | Set long-term budget to $75 |
| `SET ST 30 LT 75` | Set both budgets at once |
| `PAUSE` | Stop daily picks |
| `RESUME` | Restart daily picks |
| `STATUS` | Show current configuration |
| `RESET` | Restore default config |
| `HELP` | Show command list |

Commands are **case-insensitive**.

---

## Project Structure

```
stock-agent/
├── agent.py              ← Main daily runner (GitHub Actions entry point)
├── screener.py           ← S&P 500 screening + short/long-term scoring
├── ai_analyzer.py        ← Claude API integration + Finnhub news
├── whatsapp.py           ← CallMeBot send/format + command parser
├── webhook.py            ← Flask app for inbound WhatsApp commands
├── config_manager.py     ← GitHub Gist config read/write
├── requirements.txt
├── render.yaml           ← Render.com deployment config
└── .github/
    └── workflows/
        ├── daily_run.yml      ← Cron job (Mon–Fri 9AM ET)
        └── webhook_deploy.yml ← Auto-deploy webhook on push
```

---

## DRY_RUN Mode

Set `DRY_RUN=true` as an environment variable to run the full pipeline 
(screener + Claude analysis) but **print** the WhatsApp message instead of sending it.

```bash
DRY_RUN=true python agent.py
```

---

## Cost Estimate

- **GitHub Actions**: ~5–8 min/run × 21 trading days = ~150 min/month (well under 2000 free)
- **Claude API**: ~1500 tokens/day × 21 days ≈ $0.50–1.00/month
- **Everything else**: Free

---

## Disclaimer

⚠ This tool is for **personal, informational use only**. It is not financial advice.
Always do your own research before making investment decisions.
