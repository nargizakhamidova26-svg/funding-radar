"""Turn raw pages / feeds into lists of candidate opportunities."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import feedparser
from bs4 import BeautifulSoup

GENERIC_LINK_TEXT = {"read more", "learn more", "more", "details", "view", "view details", "apply", "apply now",
                     "click here", "here", "download", "more info", "more information", "see more", "open",
                     "continue reading", "full details", "view call", "view more"}
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "#")
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".mp4", ".mp3")
TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|source$)", re.I)


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower().removeprefix("www."), path, "", urlencode(q), ""))


def item_id(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()[:16]


def html_to_text(html: str) -> str:
    return clean(BeautifulSoup(html or "", "lxml").get_text(" "))


# --------------------------------------------------------------------------
# RSS / Atom
# --------------------------------------------------------------------------

def extract_rss(content: bytes, base_url: str) -> list[dict]:
    feed = feedparser.parse(content)
    items = []
    for e in feed.entries:
        link = e.get("link") or ""
        title = clean(e.get("title"))
        if not link or not title:
            continue
        summary = html_to_text(e.get("summary") or e.get("description") or "")
        items.append({"title": title, "url": urljoin(base_url, link), "summary": summary[:600]})
    return items


# --------------------------------------------------------------------------
# HTML pages
# --------------------------------------------------------------------------

def _strip_chrome(soup: BeautifulSoup):
    for tag in soup(["script", "style", "noscript", "nav", "footer", "form", "iframe", "svg"]):
        tag.decompose()
    for h in soup.find_all("header"):
        if h.find("nav") or h.parent is None or h.parent.name in ("body", "html"):
            h.decompose()
    for sel in ['[role="navigation"]', '[class*="breadcrumb"]', '[class*="cookie"]', '[id*="cookie"]',
                '[class*="menu"]', '[id*="menu"]', '[class*="social"]', '[class*="share"]']:
        for tag in soup.select(sel):
            if tag.name in ("html", "body", "main", "article") or tag.find(["main", "article"]):
                continue
            tag.decompose()


def _container(a):
    """Closest element that represents one listing row/card."""
    node = a
    for _ in range(6):
        node = node.parent
        if node is None:
            return a
        if node.name in ("li", "tr", "article", "dd") or (
            node.name == "div" and any(k in " ".join(node.get("class", [])).lower()
                                       for k in ("card", "item", "teaser", "result", "views-row", "entry", "post", "listing"))):
            return node
    return a.parent or a


def _title_for(a, container) -> str:
    text = clean(a.get_text(" "))
    if text.lower() in GENERIC_LINK_TEXT or len(text) < 12:
        for cand in (a.get("title"), a.get("aria-label")):
            if cand and len(clean(cand)) >= 12:
                return clean(cand)
        h = container.find(["h1", "h2", "h3", "h4", "h5", "strong"]) if container is not a else None
        if h and len(clean(h.get_text(" "))) >= 12:
            return clean(h.get_text(" "))
    return text


def main_text(html: str) -> str:
    """Main readable text of a detail page (without menus, footers, sidebars)."""
    soup = BeautifulSoup(html, "lxml")
    _strip_chrome(soup)
    for tag in soup.select("aside, [class*='sidebar'], [id*='sidebar'], [class*='related'], [class*='widget']"):
        tag.decompose()
    node = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body or soup
    return clean(node.get_text(" "))[:20000]


def extract_html(html: str, base_url: str, site: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    _strip_chrome(soup)
    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup

    selector = site.get("item_selector")
    anchors = root.select(selector) if selector else root.find_all("a", href=True)
    if selector:  # selector may point at a card instead of the <a>
        anchors = [x if x.name == "a" else x.find("a", href=True) for x in anchors]
        anchors = [a for a in anchors if a is not None and a.get("href")]

    pattern = site.get("link_pattern")
    pat_rx = re.compile(pattern, re.I) if pattern else None
    base_host = urlparse(base_url).netloc.lower().removeprefix("www.")
    page_norm = normalize_url(base_url)

    found: dict[str, dict] = {}
    for a in anchors:
        href = (a.get("href") or "").strip()
        if not href or href.lower().startswith(SKIP_SCHEMES):
            continue
        url = urljoin(base_url, href)
        if urlparse(url).scheme not in ("http", "https") or url.lower().split("?")[0].endswith(SKIP_EXT):
            continue
        norm = normalize_url(url)
        if norm == page_norm:
            continue
        if pat_rx and not pat_rx.search(url):
            continue
        if not pat_rx and not selector and not site.get("allow_external"):
            host = urlparse(url).netloc.lower().removeprefix("www.")
            if host != base_host and not host.endswith("." + base_host) and not url.lower().endswith(".pdf"):
                continue
        cont = _container(a)
        title = _title_for(a, cont)
        if len(title) < 12 or title.lower() in GENERIC_LINK_TEXT:
            continue
        summary = clean(cont.get_text(" ")) if cont is not a else ""
        if summary.startswith(title):
            summary = summary[len(title):].strip(" ·-–|:")
        summary = re.sub(r"\b(read more|learn more|view details|more info)\s*$", "", summary, flags=re.I).strip()
        prev = found.get(norm)
        if prev is None or len(title) > len(prev["title"]):
            found[norm] = {"title": title[:300], "url": url, "summary": summary[:600]}
    return list(found.values())
