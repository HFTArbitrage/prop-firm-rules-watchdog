"""
Prop Firm Rules Watchdog — Google Sheets updater

Reads run_summary.json (produced by scraper.py) and pushes data to a
Google Sheet with three tabs:

  Master       — current state of every firm: name, URL, last checked, status
  Changes      — chronological log of detected changes (last 90 days)
  Compatibility — strategy x firm matrix (manually curated; this script
                  does not overwrite, only ensures the tab exists)

Auth: service account JSON in env var GOOGLE_CREDENTIALS_JSON.
Sheet ID: env var GOOGLE_SHEET_ID.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import gspread
import yaml
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CHANGES_RETENTION_DAYS = 90


def get_client() -> gspread.Client:
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        print("GOOGLE_CREDENTIALS_JSON not set", file=sys.stderr)
        sys.exit(2)

    info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_or_create_worksheet(spreadsheet, title: str, rows: int = 200, cols: int = 20):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def update_master_tab(spreadsheet, firms: list[dict], last_run: str) -> None:
    """Master tab: one row per firm with current status."""
    ws = get_or_create_worksheet(spreadsheet, "Master")

    headers = [
        "Firm",
        "Category",
        "Rules URL",
        "Last Checked (UTC)",
        "Snapshot File",
    ]
    rows = [headers]

    for firm in firms:
        rows.append(
            [
                firm.get("name", ""),
                firm.get("category", ""),
                firm.get("url", ""),
                last_run,
                f"data/{firm.get('slug', '')}.txt",
            ]
        )

    ws.clear()
    ws.update("A1", rows)
    ws.format(
        "A1:E1",
        {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}},
    )


def update_changes_tab(spreadsheet) -> None:
    """Changes tab: chronological log of detected changes from data/changes.json."""
    ws = get_or_create_worksheet(spreadsheet, "Changes")

    changes_path = Path("data/changes.json")
    if not changes_path.exists():
        ws.clear()
        ws.update("A1", [["No changes recorded yet."]])
        return

    try:
        all_changes = json.loads(changes_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        ws.clear()
        ws.update("A1", [["changes.json invalid"]])
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=CHANGES_RETENTION_DAYS)
    recent = []
    for c in all_changes:
        try:
            ts = datetime.fromisoformat(c.get("detected_at_utc", "").replace("Z", "+00:00"))
            if ts >= cutoff:
                recent.append(c)
        except (ValueError, TypeError):
            continue

    headers = [
        "Detected (UTC)",
        "Firm",
        "Category",
        "Char Diff",
        "Rules URL",
        "Diff Preview",
    ]
    rows = [headers]

    for c in recent[:500]:  # cap at 500 rows for sheet performance
        preview = (c.get("diff_preview", "") or "").strip()
        if len(preview) > 800:
            preview = preview[:800] + "…"
        rows.append(
            [
                c.get("detected_at_utc", ""),
                c.get("firm", ""),
                c.get("category", ""),
                str(c.get("char_diff", "")),
                c.get("url", ""),
                preview,
            ]
        )

    ws.clear()
    ws.update("A1", rows)
    ws.format(
        "A1:F1",
        {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}},
    )


def ensure_compatibility_tab(spreadsheet) -> None:
    """Compatibility tab is manually curated; ensure it exists with headers if empty."""
    ws = get_or_create_worksheet(spreadsheet, "Compatibility")

    existing = ws.get_all_values()
    if existing and any(any(cell for cell in row) for row in existing):
        return  # already populated, do nothing

    seed = [
        [
            "Strategy",
            "FTMO",
            "FundedNext",
            "The5ers",
            "FundingPips",
            "Notes",
        ],
        [
            "Manual swing trading",
            "Allowed",
            "Allowed",
            "Allowed",
            "Allowed",
            "Standard discretionary; no special restrictions.",
        ],
        [
            "Manual scalping (5+ sec holds)",
            "Allowed",
            "Restricted",
            "Restricted",
            "Restricted",
            "Some firms flag short holding times even if not arbitrage.",
        ],
        [
            "EA / algo (general)",
            "Allowed",
            "Allowed",
            "Restricted",
            "Restricted",
            "Verify each program; some firms restrict EAs on funded phase.",
        ],
        [
            "Tick scalping / 1-leg latency arbitrage",
            "Prohibited",
            "Prohibited",
            "Prohibited",
            "Prohibited",
            "Universal ban across major firms.",
        ],
        [
            "Hedge arbitrage (2-legs latency 3 variant)",
            "Restricted",
            "Restricted",
            "Restricted",
            "Restricted",
            "Configurable for compliance; trader responsibility.",
        ],
        [
            "Copy trading / signals",
            "Prohibited",
            "Prohibited",
            "Prohibited",
            "Prohibited",
            "Cross-account signal-driven entries flagged automatically.",
        ],
        [
            "News trading inside blackout",
            "Prohibited",
            "Restricted",
            "Restricted",
            "Prohibited",
            "Window varies; verify per program.",
        ],
        [
            "Martingale / grid",
            "Restricted",
            "Prohibited",
            "Prohibited",
            "Restricted",
            "Most firms ban or heavily restrict.",
        ],
    ]

    ws.clear()
    ws.update("A1", seed)
    ws.format(
        "A1:F1",
        {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}},
    )


def run() -> int:
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("GOOGLE_SHEET_ID not set", file=sys.stderr)
        return 2

    summary_path = Path("run_summary.json")
    if not summary_path.exists():
        print("run_summary.json not found; run scraper.py first", file=sys.stderr)
        return 2
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    firms = yaml.safe_load(Path("firms.yaml").read_text(encoding="utf-8"))
    if not isinstance(firms, list):
        print("firms.yaml invalid", file=sys.stderr)
        return 2

    client = get_client()
    spreadsheet = client.open_by_key(sheet_id)

    update_master_tab(spreadsheet, firms, summary.get("run_at_utc", ""))
    update_changes_tab(spreadsheet)
    ensure_compatibility_tab(spreadsheet)

    print(
        f"Sheet updated. Firms: {len(firms)}, "
        f"changes this run: {summary.get('changes_detected', 0)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
