# Prop Firm Rules Watchdog

Open-source, automatically-updated database of trading rules across major proprietary trading firms (FTMO, FundedNext, The5ers, FundingPips, and 16+ others). Detects changes in firms' Terms of Service and Prohibited Practices pages daily, commits diffs to this repo, and publishes a public Google Sheet with the live state of every firm's rules.

**Live data:** [Google Sheet — Prop Firm Rules Matrix](https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit)
**Companion analysis:** [Why Prop Firm Payouts Get Denied — 12 Rule Categories](https://hftarbitrageplatform.com/en/prop-firm-payout-denials/)

---

## What this does

Every 24 hours, GitHub Actions runs a scraper that:

1. Fetches each prop firm's rules page from the URL list in `firms.yaml`
2. Extracts the relevant text content (ignoring navigation, footers, ads)
3. Compares against the previously-saved version stored in `data/{firm-slug}.txt`
4. If the cleaned content has changed:
   - Commits the new version to this repo
   - Appends an entry to `data/changes.json` with timestamp and diff preview
   - Updates the public Google Sheet with the change
5. If unchanged: does nothing

The git history of `data/` becomes a verifiable audit trail of every prop firm rule change since the project started.

---

## Why this exists

Prop firms update their rules frequently and quietly. Traders who paid for a challenge under one set of rules can find — at payout time — that the rules changed mid-evaluation. Public reference data on these changes does not exist.

This project fills that gap. It is a non-commercial transparency tool. It does not endorse, recommend, or rank firms. It does not advise traders to use or avoid any specific firm. It records what each firm publicly says its rules are, on a daily cadence.

---

## Setup — deploy your own instance

### Prerequisites

- GitHub account
- Google account (for the Sheets dashboard)
- Python 3.10+ for local testing (optional)

### Step 1 — Fork or clone this repo

```bash
git clone https://github.com/hftarbitrage/prop-firm-rules-watchdog
cd prop-firm-rules-watchdog
```

### Step 2 — Create a Google Sheet

1. Create a new Google Sheet at [sheets.google.com](https://sheets.google.com)
2. Name it `Prop Firm Rules Watchdog`
3. Create three tabs: `Master`, `Changes`, `Compatibility`
4. Copy the sheet ID from the URL (the long string between `/d/` and `/edit`)

### Step 3 — Create a Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Enable the **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
5. Name it `prop-firm-watchdog`, grant role `Editor`
6. Create a JSON key, download it
7. Open the JSON file, copy the `client_email` field
8. Go back to your Google Sheet, click **Share**, paste the `client_email`, give it Editor access

### Step 4 — Configure GitHub Secrets

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

Add three secrets:

| Secret name | Value |
|---|---|
| `GOOGLE_CREDENTIALS_JSON` | The entire content of the JSON key file from Step 3 |
| `GOOGLE_SHEET_ID` | The sheet ID from Step 2 |
| `COMMIT_EMAIL` | `bot@hftarbitrageplatform.com` (or your preferred bot email) |

### Step 5 — Enable GitHub Actions

In your repo: **Actions → Enable Actions**. The workflow `daily-check.yml` will run automatically every 24 hours. To run immediately, go to **Actions → Daily Rule Check → Run workflow**.

### Step 6 — First run seeds the database

The first run will detect "changes" for every firm because there's no previous version stored. After that, only real changes are logged.

---

## Adding or editing firms

Edit `firms.yaml`. Each entry needs:

```yaml
- name: "FTMO"
  slug: "ftmo"
  url: "https://ftmo.com/en/all-rules/"
  selector: "main"
  category: "evaluation"
```

- `name` — display name in the sheet
- `slug` — used as the data filename (lowercase, no spaces)
- `url` — full URL to the rules page
- `selector` — CSS selector for the main content (defaults to `main` or `body`); use this to skip nav/footer noise
- `category` — informational (`evaluation`, `instant`, `futures`, etc.)

After editing, commit and push. The next scheduled run will pick up new firms.

---

## Project structure

```
prop-firm-rules-watchdog/
├── README.md                    ← this file
├── LICENSE                      ← MIT
├── firms.yaml                   ← list of firms to monitor
├── requirements.txt             ← Python dependencies
├── scraper.py                   ← main scraper
├── sheets_updater.py            ← Google Sheets integration
├── data/                        ← saved snapshots (auto-managed)
│   ├── changes.json             ← chronological log of detected changes
│   ├── ftmo.txt                 ← cleaned text content per firm
│   └── ...
├── .github/
│   └── workflows/
│       └── daily-check.yml      ← cron workflow
└── .gitignore
```

---

## Methodology — what counts as a "change"

The scraper extracts visible text content from the rules page using a CSS selector that targets the main content area (`<main>`, `<article>`, or a firm-specific div). It strips:

- Whitespace differences (collapsed)
- Cookie consent banners
- Navigation menus and footers (excluded by selector)
- Tracking scripts

A change is registered when the cleaned text differs from the previous run by any character. False positives can occur if a firm injects dynamic content (timestamps, A/B test variants) into the main content area; these get filtered out over time as the selector list improves.

---

## Limitations

- **Public rules only.** Some firms have rules behind login walls or in PDFs. This tool only sees the public web pages.
- **No semantic understanding.** A change in punctuation or wording is logged equally to a substantive rule change. The cleaned diff in `changes.json` shows what changed; humans interpret severity.
- **Coverage gaps.** Not every prop firm is in `firms.yaml` yet. Pull requests welcome.
- **Not legal or financial advice.** This is a data transparency tool. Always read the original rules at the firm's website before paying for a challenge.

---

## Contributing

Pull requests welcome. Common improvements:

- Adding new firms to `firms.yaml`
- Tightening CSS selectors to reduce noise
- Adding language-specific scrapers (most firms publish English; some have local-language equivalents with subtly different rules)
- Adding additional output formats (CSV, JSON-LD)

---

## License

MIT. Use the data freely, including commercially, without restriction. Attribution appreciated but not required.

---

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by any prop firm listed. All rule citations are fetched from each firm's publicly accessible web pages. The recorded text is the firm's own publication; this tool merely archives and surfaces changes. If a firm believes its rules are being misrepresented or wishes to be removed from monitoring, please open an issue or contact the maintainer.

Built and maintained by [HFT Arbitrage Platform](https://hftarbitrageplatform.com/).
