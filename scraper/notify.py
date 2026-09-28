"""Telegram notifications via the free Bot API."""
from __future__ import annotations

import html
import os
from datetime import date

import requests

from .filters import GEO_LABELS

GEO_ICON = {"uz": "🇺🇿", "region": "🌏", "global": "🌍", "unknown": "❔", "other": "🚫"}
LIMIT = 3900  # Telegram max is 4096 characters per message


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "not found"
    d = date.fromisoformat(iso)
    return d.strftime("%d %b %Y").lstrip("0")


def _item_block(n: int, it: dict) -> str:
    e = html.escape
    lines = [f"<b>{n}. {e(it['title'])}</b>",
             f"🏛 {e(it['source'])}  ·  {GEO_ICON.get(it['geo'], '')} {e(GEO_LABELS.get(it['geo'], ''))}",
             f"⏰ Deadline: {_fmt_date(it.get('deadline'))}",
             f"🔗 <a href=\"{e(it['url'], quote=True)}\">Open</a>"]
    return "\n".join(lines)


def build_messages(new_items: list[dict], new_sites: list[tuple[str, int]], failed: list[str],
                   dashboard_url: str | None) -> list[str]:
    today = date.today().strftime("%d %b %Y").lstrip("0")
    n = len(new_items)
    head = (f"🔔 <b>{n} new funding opportunit{'y' if n == 1 else 'ies'}</b> · {today}" if n
            else f"📭 No new funding opportunities today · {today}")
    footer = []
    for name, count in new_sites:
        footer.append(f"➕ New site added: <b>{html.escape(name)}</b> ({count} current listings saved to the dashboard)")
    if failed:
        footer.append("⚠️ Could not read: " + ", ".join(html.escape(f) for f in failed))
    if dashboard_url:
        footer.append(f"📊 <a href=\"{html.escape(dashboard_url, quote=True)}\">Open dashboard</a>")

    messages, cur = [], head
    for i, it in enumerate(new_items, 1):
        block = _item_block(i, it)
        if len(cur) + len(block) + 2 > LIMIT:
            messages.append(cur)
            cur = block
        else:
            cur += "\n\n" + block
    tail = "\n\n" + "\n".join(footer) if footer else ""
    if len(cur) + len(tail) > LIMIT:
        messages.append(cur)
        cur = tail.strip()
    else:
        cur += tail
    messages.append(cur)
    return messages


def send(messages: list[str]) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if not token or not chats:
        print("Telegram secrets are not set; printing instead:\n")
        for m in messages:
            print(m, "\n" + "-" * 40)
        return
    for chat in chats:
        for m in messages:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": chat, "text": m, "parse_mode": "HTML",
                                    "disable_web_page_preview": True}, timeout=30)
            if not r.ok:
                raise RuntimeError(f"Telegram error for chat {chat}: {r.status_code} {r.text[:300]}")
