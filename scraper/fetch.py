"""Polite HTTP fetching, with optional headless-browser rendering for JavaScript sites."""
from __future__ import annotations

import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36 UNDPFundingRadar/1.0")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,ru;q=0.6"}
DELAY_SECONDS = 1.5

_session = requests.Session()
_session.headers.update(HEADERS)
_last = 0.0
_browser = None
_pw = None


def _wait():
    global _last
    gap = time.time() - _last
    if gap < DELAY_SECONDS:
        time.sleep(DELAY_SECONDS - gap)
    _last = time.time()


def get(url: str, js: bool = False, timeout: int = 30) -> tuple[bytes, str]:
    """Return (content bytes, content-type)."""
    _wait()
    if js:
        return _get_js(url), "text/html"
    err = None
    for attempt in range(3):
        try:
            r = _session.get(url, timeout=timeout)
            if r.status_code in (429, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.content, r.headers.get("content-type", "")
        except requests.RequestException as e:
            err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"could not download ({err})")


def _get_js(url: str) -> bytes:
    global _browser, _pw
    if _browser is None:
        from playwright.sync_api import sync_playwright  # installed only when a site needs js
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch()
    page = _browser.new_page(user_agent=UA)
    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)
        return page.content().encode("utf-8")
    finally:
        page.close()


def close():
    global _browser, _pw
    if _browser:
        _browser.close()
        _pw.stop()
        _browser = _pw = None
