"""Connectors for portals whose listings are only reachable through a free public data API.

Each connector returns a list of {"title", "url", "summary", "deadline"(optional ISO), "geo_hint"(optional)}.
Use in sites.yaml with:   type: api   api: <name>   query: <search words>
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import date, datetime

import requests

from .fetch import HEADERS, _wait


def _iso(value: str | None, fmts=("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                                  "%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%b %d, %Y")) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    d = None
    for f in fmts:
        try:
            d = datetime.strptime(v, f).date()
            break
        except ValueError:
            continue
    if d is None:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None if d.year >= 2090 else d.isoformat()   # "2099-01-01" means "no deadline"


def _clean(text) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(text or "")).replace("\xa0", " ")).strip()


# Words that show an item is really about Uzbekistan / Central Asia
LOCAL = re.compile(r"uzbek|tashkent|central asia|kazakh|kyrgyz|tajik|turkmen|aral sea|samarkand|karakalpak",
                   re.IGNORECASE)


def _first(v):
    return v[0] if isinstance(v, list) and v else v


# --------------------------------------------------------------------------
# EU Funding & Tenders Portal (covers Horizon Europe, INTPA/EuropeAid calls and more)
# --------------------------------------------------------------------------

EU_SEARCH = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
EU_TOPIC = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{}"
EU_OPEN_STATUSES = ["31094501", "31094502"]  # forthcoming, open


def eu_funding_tenders(site: dict) -> list[dict]:
    items = []
    for text in _queries(site, default="Uzbekistan"):
        _wait()
        query = {"bool": {"must": [{"terms": {"status": EU_OPEN_STATUSES}}]}}
        r = requests.post(
            EU_SEARCH,
            params={"apiKey": "SEDIA", "text": text, "pageSize": 100, "pageNumber": 1},
            files={"query": ("blob", json.dumps(query), "application/json"),
                   "languages": ("blob", json.dumps(["en"]), "application/json"),
                   "sort": ("blob", json.dumps({"order": "DESC", "field": "startDate"}), "application/json")},
            headers={"User-Agent": HEADERS["User-Agent"]}, timeout=45)
        r.raise_for_status()
        for res in r.json().get("results", []):
            md = res.get("metadata") or {}
            ident = _first(md.get("identifier")) or _first(md.get("callIdentifier")) or res.get("reference")
            title = _first(md.get("title")) or res.get("title") or res.get("summary")
            if not ident or not title:
                continue
            call = _clean(_first(md.get("callTitle")))
            title = _clean(title)
            deadline = _iso(_first(md.get("deadlineDate")))
            if deadline and deadline < date.today().isoformat():
                continue   # closed
            items.append({
                "title": title if ident in title else f"{title} ({ident})",
                "url": EU_TOPIC.format(ident),
                "summary": " · ".join(x for x in (call, _clean(res.get("summary"))[:300]) if x),
                "deadline": deadline,
            })
    return items


# --------------------------------------------------------------------------
# Grants.gov (US federal grants, incl. U.S. Embassy / State Department calls abroad)
# --------------------------------------------------------------------------

GRANTS_GOV = "https://api.grants.gov/v1/api/search2"


def grants_gov(site: dict) -> list[dict]:
    items = []
    for kw in _queries(site, default="Uzbekistan"):
        _wait()
        r = requests.post(GRANTS_GOV, json={"keyword": kw, "oppStatuses": "forecasted|posted", "rows": 100},
                          headers={"User-Agent": HEADERS["User-Agent"]}, timeout=45)
        r.raise_for_status()
        data = r.json()
        if data.get("errorcode") not in (0, None):
            raise RuntimeError(f"Grants.gov API error: {data.get('msg')}")
        for h in (data.get("data") or {}).get("oppHits", []):
            if not h.get("id") or not h.get("title"):
                continue
            # The keyword search also matches words deep inside long documents, so keep only
            # opportunities whose title, agency or number point to Uzbekistan / Central Asia.
            where = " ".join(str(h.get(k) or "") for k in ("title", "agency", "agencyCode", "number"))
            if not (LOCAL.search(where) or re.search(r"\b(UZB|KAZ|KGZ|TJK|TKM|SCA)\b", where)):
                continue
            items.append({
                "title": _clean(h["title"]),
                "url": f"https://www.grants.gov/search-results-detail/{h['id']}",
                "summary": " · ".join(x for x in (h.get("agency") or h.get("agencyCode"), h.get("number"),
                                                   (h.get("oppStatus") or "").title()) if x),
                "deadline": _iso(h.get("closeDate")),
            })
    return items


# --------------------------------------------------------------------------
# World Bank procurement notices
# --------------------------------------------------------------------------

WB_API = "https://search.worldbank.org/api/v2/procnotices"
WB_API_OLD = "https://search.worldbank.org/api/procnotices"
WB_NOTICE = "https://projects.worldbank.org/en/projects-operations/procurement-detail/{}"


def world_bank(site: dict) -> list[dict]:
    items = []
    for q in _queries(site, default="Uzbekistan"):
        params = {"format": "json", "qterm": q, "rows": 100, "os": 0,
                  "srt": "noticedate", "order": "desc", "apilang": "en"}
        data, last = None, None
        for attempt, url in enumerate([WB_API, WB_API, WB_API_OLD]):  # the API is sometimes briefly busy
            _wait()
            try:
                r = requests.get(url, params=params, headers=HEADERS, timeout=45)
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as e:
                last = e
                time.sleep(10 * (attempt + 1))
        if data is None:
            raise RuntimeError(f"World Bank API not available today ({last})")
        notices = data.get("procnotices") or data.get("documents") or []
        if isinstance(notices, dict):
            notices = list(notices.values())
        for n in notices:
            if not isinstance(n, dict) or not n.get("id"):
                continue
            desc = _clean(n.get("bid_description") or n.get("project_name"))
            ntype = n.get("notice_type") or ""
            title = f"{ntype}: {desc}" if ntype and desc else (desc or ntype)
            if not title:
                continue
            items.append({
                "title": title[:300],
                "url": WB_NOTICE.format(n["id"]),
                "summary": " · ".join(x for x in (n.get("project_ctry_name"), n.get("project_name"),
                                                   n.get("procurement_method_name")) if x),
                "deadline": _iso(n.get("submission_deadline_date") or n.get("submission_date")),
            })
    return items


def _queries(site: dict, default: str) -> list[str]:
    q = site.get("query", default)
    return q if isinstance(q, list) else [q]


CONNECTORS = {
    "eu_funding_tenders": eu_funding_tenders,
    "grants_gov": grants_gov,
    "world_bank": world_bank,
}


def fetch_api(site: dict) -> list[dict]:
    name = site.get("api")
    if name not in CONNECTORS:
        raise RuntimeError(f"unknown api '{name}'. Available: {', '.join(CONNECTORS)}")
    seen, out = set(), []
    for it in CONNECTORS[name](site):
        if it["url"] not in seen:
            seen.add(it["url"])
            out.append(it)
    return out
