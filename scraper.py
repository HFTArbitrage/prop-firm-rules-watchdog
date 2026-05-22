"""
Prop Firm Rules Watchdog — scraper

Fetches each firm's rules page, extracts cleaned text content, compares
against the previous run, and records detected changes to data/changes.json
plus per-firm snapshots in data/{slug}.txt.

Designed to run once per day via GitHub Actions. Local execution works
identically; GitHub Actions just provides the cron and the commit hook.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup

# -----------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------

DATA_DIR = Path("data")
FIRMS_FILE = Path("firms.yaml")
CHANGES_FILE = DATA_DIR / "changes.json"
MAX_CHANGES_RETAINED = 1000
MAX_DIFF_PREVIEW_LINES = 60
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 2  # polite pause between firms

USER_AGENT = (
    "Mozilla/5.0 (compatible; PropFirmRulesWatchdog/1.0; "
    "+https://github.com/hftarbitrage/prop-firm-rules-watchdog)"
)

# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


def normalize_text(raw: str) -> str:
    """Collapse whitespace, strip surrounding noise. Stable across runs."""
    text = re.sub(r"[ \t]+", " ", raw)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_page(url: str) -> str | None:
    """Fetch a URL with realistic User-Agent. Returns HTML or None on error."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  fetch error: {e}", file=sys.stderr)
        return None


def extract_content(html: str, selector: str) -> str:
    """Extract main content text from HTML using a CSS selector."""
    soup = BeautifulSoup(html, "html.parser")

    # Strip tags that produce noise even inside the main content.
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    # Strip common cookie banners and ad regions.
    for sel in [
        "[class*=cookie]",
        "[id*=cookie]",
        "[class*=consent]",
        "[id*=consent]",
        "[class*=banner]",
        "[class*=newsletter]",
        "footer",
        "nav",
    ]:
        for el in soup.select(sel):
            el.decompose()

    target = soup.select_one(selector) or soup.select_one("main") or soup.body
    if target is None:
        return ""

    text = target.get_text(separator="\n")
    return normalize_text(text)


def load_previous(slug: str) -> str:
    path = DATA_DIR / f"{slug}.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def save_current(slug: str, content: str) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / f"{slug}.txt").write_text(content, encoding="utf-8")


def compute_diff_preview(prev: str, curr: str) -> str:
    diff_lines = list(
        difflib.unified_diff(
            prev.split("\n"),
            curr.split("\n"),
            fromfile="previous",
            tofile="current",
            lineterm="",
            n=2,
        )
    )
    return "\n".join(diff_lines[:MAX_DIFF_PREVIEW_LINES])


def append_change_record(record: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    existing: list[dict] = []
    if CHANGES_FILE.exists():
        try:
            existing = json.loads(CHANGES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    existing.insert(0, record)
    existing = existing[:MAX_CHANGES_RETAINED]
    CHANGES_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------


def run() -> int:
    if not FIRMS_FILE.exists():
        print(f"firms.yaml not found", file=sys.stderr)
        return 1

    firms = yaml.safe_load(FIRMS_FILE.read_text(encoding="utf-8"))
    if not isinstance(firms, list):
        print("firms.yaml must contain a list", file=sys.stderr)
        return 1

    detected_changes: list[dict] = []
    fetch_failures: list[str] = []

    for i, firm in enumerate(firms):
        name = firm.get("name", "?")
        slug = firm.get("slug", "")
        url = firm.get("url", "")
        selector = firm.get("selector", "main")

        print(f"[{i+1}/{len(firms)}] {name} ({url})")

        if not slug or not url:
            print("  skipped (missing slug or url)")
            continue

        html = fetch_page(url)
        if html is None:
            fetch_failures.append(name)
            continue

        current = extract_content(html, selector)
        if not current:
            print(f"  warning: no content extracted")
            fetch_failures.append(name)
            continue

        previous = load_previous(slug)

        if previous and previous != current:
            preview = compute_diff_preview(previous, current)
            change = {
                "firm": name,
                "slug": slug,
                "url": url,
                "category": firm.get("category", ""),
                "detected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "char_diff": len(current) - len(previous),
                "diff_preview": preview,
            }
            detected_changes.append(change)
            print(f"  CHANGE detected ({change['char_diff']:+d} chars)")
        elif not previous:
            print("  seeded (no previous version)")
        else:
            print("  no change")

        save_current(slug, current)
        time.sleep(REQUEST_DELAY_SECONDS)

    for change in detected_changes:
        append_change_record(change)

    print(
        f"\nSummary: {len(detected_changes)} change(s) detected, "
        f"{len(fetch_failures)} fetch failure(s)"
    )
    if fetch_failures:
        print(f"Failures: {', '.join(fetch_failures)}")

    # Emit JSON summary for downstream steps (sheets_updater, GitHub Actions)
    summary = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_firms": len(firms),
        "changes_detected": len(detected_changes),
        "fetch_failures": fetch_failures,
        "changes": detected_changes,
    }
    Path("run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return 0


if __name__ == "__main__":
    sys.exit(run())
