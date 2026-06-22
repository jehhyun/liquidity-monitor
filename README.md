# Fat Cat Capital — Liquidity Pressure Monitor

Auto-updates twice daily (8am + 4pm ET on weekdays) via GitHub Actions.
Pulls 10 FRED series and publishes a static dashboard to GitHub Pages.

**Live URL:** `https://jehhyun.github.io/liquidity-monitor/`

---

## Setup (one-time, ~5 minutes)

### 1. Create the repo on GitHub
- Go to github.com → New repository
- Name: `liquidity-monitor`
- Set to **Public** (required for free GitHub Pages)
- Do NOT initialize with README (you're pushing this code)

### 2. Push this code
```bash
cd liquidity-monitor
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/jehhyun/liquidity-monitor.git
git push -u origin main
```

### 3. Add your FRED API key as a secret
- Go to your repo on GitHub
- Settings → Secrets and variables → Actions → New repository secret
- Name: `FRED_API_KEY`
- Value: your FRED API key
- Click Add secret

### 4. Enable GitHub Pages
- Go to your repo → Settings → Pages
- Source: **Deploy from a branch**
- Branch: `main` → folder: `/docs`
- Click Save

### 5. Run the action manually to build the first page
- Go to your repo → Actions → Update Liquidity Monitor
- Click **Run workflow**
- Wait ~30 seconds
- Your dashboard is live at `https://jehhyun.github.io/liquidity-monitor/`

---

## Schedule
Runs automatically Monday–Friday at 8am ET and 4pm ET.
To trigger manually: Actions → Update Liquidity Monitor → Run workflow.

## Series tracked
| Series | What | Cadence |
|---|---|---|
| WTREGEN | Treasury General Account | Weekly Wed |
| RRPONTSYD | Overnight Reverse Repo | Daily |
| WRESBAL | Reserve Balances | Weekly Wed |
| SOFR | Secured Overnight Rate | Daily |
| BAMLH0A0HYM2 | HY Corporate OAS | Daily |
| DGS3MO | 3-month yield | Daily |
| DGS6MO | 6-month yield | Daily |
| DGS2 | 2-year yield | Daily |
| DGS10 | 10-year yield | Daily |
| T10Y2Y | 2s10s spread | Daily |

ABS prime/subprime are manually maintained (not on FRED).
