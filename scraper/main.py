"""UNDP Funding Radar: daily run.

    python -m scraper.main                 normal run (scrape, save, send Telegram)
    python -m scraper.main --dry-run       print the Telegram message instead of sending it
    python -m scraper.main --test-telegram send a test message only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from . import fetch
from .apis import fetch_api
from .extract import extract_html, extract_rss, item_id, main_text
from .filters import GEO_ORDER, KeywordFilter, classify_geography, extract_deadline, geography_passes
from .notify import build_messages, send

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "sites.yaml"
SEEN = ROOT / "data" / "seen.json"
OPPS = ROOT / "docs" / "data" / "opportunities.json"
STATUS = ROOT / "docs" / "data" / "status.json"
MAX_STORED = 3000


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def dashboard_url() -> str | None:
    if os.environ.get("DASHBOARD_URL"):
        return os.environ["DASHBOARD_URL"]
    repo = os.environ.get("GITHUB_REPOSITORY")  # "owner/name", set automatically on GitHub
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return None


def process_site(site: dict, settings: dict, kw: KeywordFilter, seen_ids: dict, today: str,
                 first_time: bool = False) -> tuple[list, list]:
    """Returns (accepted new items, all listings found on the page)."""
    js = bool(site.get("js"))
    stype = (site.get("type") or "").lower()
    content = ctype = None
    if stype != "api":
        content, ctype = fetch.get(site["url"], js=js)
        stype = stype or ("rss" if "xml" in ctype or "rss" in ctype else "html")
    if stype == "api":
        items = fetch_api(site)
        require_default = False
    elif stype == "rss":
        items = extract_rss(content, site["url"])
        require_default = False
    else:
        html = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
        items = extract_html(html, site["url"], site)
        require_default = not (site.get("link_pattern") or site.get("item_selector"))
    require_kw = site.get("require_keywords", require_default)

    found = items
    fresh = [it for it in items if item_id(it["url"]) not in seen_ids]
    accepted = []
    details_left = int(settings.get("max_details_per_site", 25))
    if first_time:  # the first scan only builds a baseline, so keep it quick
        details_left = min(details_left, 10)
    if stype == "api":  # APIs already give deadline and country
        details_left = 0
    for it in fresh:
        iid = item_id(it["url"])
        seen_ids[iid] = today
        head = f"{it['title']} \n {it.get('summary', '')}"
        if kw.excluded(it["title"]):
            continue
        if require_kw and not kw.included(head):
            continue
        body = ""
        if settings.get("fetch_details", True) and details_left > 0 and not it["url"].lower().endswith(".pdf"):
            details_left -= 1
            try:
                raw, _ = fetch.get(it["url"], js=js)
                body = main_text(raw.decode("utf-8", errors="replace"))
            except Exception as e:  # a broken detail page should not stop the run
                print(f"   detail page failed: {it['url']} ({e})")
        geo = classify_geography(head, body)
        if not geography_passes(geo, site.get("geography_mode", settings.get("geography_mode", "relaxed"))):
            continue
        accepted.append({
            "id": iid, "title": it["title"], "url": it["url"], "source": site["name"],
            "summary": (it.get("summary") or body)[:400], "geo": geo,
            "deadline": it.get("deadline") or extract_deadline(it.get("summary", ""), body, it["title"]),
            "found": today,
        })
    return accepted, found


def run(dry_run: bool = False) -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    settings = cfg.get("settings") or {}
    sites = [s for s in (cfg.get("sites") or []) if s and s.get("url") and s.get("enabled", True) is not False]
    kw = KeywordFilter(settings.get("opportunity_keywords", []), settings.get("exclude_keywords", []))

    seen = load_json(SEEN, {"sites": {}, "ids": {}})
    opps = load_json(OPPS, [])
    today = date.today().isoformat()

    new_items, new_sites, failed, status = [], [], [], []
    for site in sites:
        name = site.get("name") or site["url"]
        site["name"] = name
        first_time = name not in seen["sites"]
        print(f"→ {name}{' (first run)' if first_time else ''}")
        try:
            accepted, listings = process_site(site, settings, kw, seen["ids"], today, first_time)
            found = len(listings)
            if first_time:
                seen["sites"][name] = today
                new_sites.append((name, len(accepted)))
            else:
                new_items.extend(accepted)
            opps.extend(accepted)
            status.append({"site": name, "url": site["url"], "ok": True, "listings": found,
                           "new": len(accepted), "error": "",
                           "sample": [x["title"][:120] for x in listings[:3]]})
            print(f"   {found} listings on page, {len(accepted)} new relevant")
            if found == 0:
                status[-1]["error"] = "no links found: page may need js: true, a link_pattern or item_selector"
        except Exception as e:
            traceback.print_exc()
            failed.append(name)
            status.append({"site": name, "url": site["url"], "ok": False, "listings": 0, "new": 0,
                           "error": str(e)[:200]})
    fetch.close()

    new_items.sort(key=lambda x: (GEO_ORDER.get(x["geo"], 9), x.get("deadline") or "9999"))
    opps = sorted(opps, key=lambda x: x["found"], reverse=True)[:MAX_STORED]

    save_json(OPPS, opps)
    save_json(STATUS, {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "sites": status})
    save_json(SEEN, seen)

    if new_items or new_sites or failed or settings.get("notify_when_empty"):
        messages = build_messages(new_items, new_sites, failed, dashboard_url())
        if dry_run:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        send(messages)
    else:
        print("Nothing new; no message sent.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-telegram", action="store_true")
    a = ap.parse_args()
    if a.test_telegram:
        send(["✅ <b>UNDP Funding Radar is connected.</b>\nYou will receive new funding calls here every morning."])
        return 0
    return run(dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
