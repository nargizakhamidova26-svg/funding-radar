"""Keyword, geography and deadline logic."""
from __future__ import annotations

import re
from datetime import date, timedelta

from dateutil import parser as dateparser

# --------------------------------------------------------------------------
# Keyword matching
# --------------------------------------------------------------------------

def _kw_regex(words):
    words = [w.strip() for w in words if w and w.strip()]
    if not words:
        return None
    # word boundary at start, allow plural endings
    parts = []
    for w in sorted(words, key=len, reverse=True):
        if w.isascii():
            parts.append(r"\b" + re.escape(w) + r"(?:s|es)?\b")
        else:  # Korean/Russian etc.: match inside compound words too
            parts.append(re.escape(w))
    return re.compile("|".join(parts), re.IGNORECASE)


class KeywordFilter:
    def __init__(self, include, exclude):
        self.inc = _kw_regex(include)
        self.exc = _kw_regex(exclude)

    def excluded(self, text: str) -> bool:
        return bool(self.exc and self.exc.search(text))

    def included(self, text: str) -> bool:
        return bool(self.inc and self.inc.search(text))


# --------------------------------------------------------------------------
# Geography
# --------------------------------------------------------------------------

GEO_UZ = ["uzbekistan", "uzbek", "tashkent", "karakalpakstan", "samarkand",
          "bukhara", "fergana", "ferghana", "namangan", "andijan", "khorezm"]

GEO_REGION = ["central asia", "central asian", "europe and central asia", "eastern europe and central asia",
              "europe and the cis", "europe & cis", "ecis", "eca region", "commonwealth of independent states",
              "cis countries", "aral sea", "silk road", "caspian", "carec", "asia and the pacific",
              "asia-pacific", "asia pacific"]

GEO_GLOBAL = ["global", "worldwide", "world-wide", "all countries", "any country", "international applicants",
              "multi-country", "multiple countries", "developing countries", "developing country",
              "low- and middle-income", "low and middle income", "low-and-middle-income", "lmic", "lmics",
              "oda-eligible", "oda eligible", "dac list", "emerging markets", "global south",
              "open to all", "no geographic restriction", "all regions", "un member states",
              "programme countries", "program countries"]

OTHER_REGIONS = ["africa", "african", "sub-saharan", "latin america", "caribbean", "south america",
                 "central america", "north america", "middle east", "mena", "arab states", "gulf",
                 "pacific islands", "southeast asia", "south-east asia", "south asia", "asean",
                 "balkans", "western balkans", "european union member", "eu member states", "sahel",
                 "horn of africa", "great lakes", "oceania", "nordic", "scandinavia"]

COUNTRIES = """afghanistan albania algeria andorra angola antigua argentina armenia australia austria azerbaijan
bahamas bahrain bangladesh barbados belarus belgium belize benin bhutan bolivia bosnia botswana brazil brunei
bulgaria burkina burundi cabo verde cape verde cambodia cameroon canada chad chile china colombia comoros congo
costa rica croatia cuba cyprus czech czechia denmark djibouti dominica dominican ecuador egypt el salvador
equatorial guinea eritrea estonia eswatini ethiopia fiji finland france gabon gambia georgia germany ghana greece
grenada guatemala guinea guinea-bissau guyana haiti honduras hungary iceland india indonesia iran iraq ireland
israel italy jamaica japan jordan kazakhstan kenya kiribati korea kosovo kuwait kyrgyzstan kyrgyz laos lao latvia
lebanon lesotho liberia libya liechtenstein lithuania luxembourg madagascar malawi malaysia maldives mali malta
marshall mauritania mauritius mexico micronesia moldova monaco mongolia montenegro morocco mozambique myanmar
namibia nauru nepal netherlands new zealand nicaragua niger nigeria north macedonia norway oman pakistan palau
palestine panama papua new guinea paraguay peru philippines poland portugal qatar romania russia rwanda samoa
san marino saudi arabia senegal serbia seychelles sierra leone singapore slovakia slovenia solomon somalia
south africa south sudan spain sri lanka sudan suriname sweden switzerland syria taiwan tajikistan tanzania
thailand timor-leste togo tonga trinidad tunisia turkey türkiye turkiye turkmenistan tuvalu uganda ukraine
united arab emirates uae united kingdom uk united states usa u.s. uruguay vanuatu venezuela vietnam viet nam
yemen zambia zimbabwe scotland wales england"""

# multi-word names must be kept together
_MULTI = ["costa rica", "el salvador", "equatorial guinea", "new zealand", "north macedonia", "papua new guinea",
          "saudi arabia", "san marino", "sierra leone", "south africa", "south sudan", "sri lanka", "viet nam",
          "united arab emirates", "united kingdom", "united states", "cabo verde", "cape verde"]


def _country_list():
    text = COUNTRIES.replace("\n", " ")
    for m in _MULTI:
        text = text.replace(m, "")
    singles = [w for w in text.split() if w]
    return _MULTI + singles


def _rx(words):
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
                      + r")(?![\w-])", re.IGNORECASE)


RX_UZ = _rx(GEO_UZ)
RX_REGION = _rx(GEO_REGION)
RX_GLOBAL = _rx(GEO_GLOBAL)
RX_OTHER = _rx(_country_list() + OTHER_REGIONS)

GEO_LABELS = {
    "uz": "Uzbekistan",
    "region": "Central Asia / region",
    "global": "Global / multi-country",
    "unknown": "Geography not stated",
    "other": "Other countries",
}
GEO_ORDER = {"uz": 0, "region": 1, "global": 2, "unknown": 3, "other": 4}


def _distinct_countries(text: str) -> int:
    return len({m.lower() for m in RX_OTHER.findall(text or "")})


def classify_geography(headline: str, body: str = "", title: str = "") -> str:
    """headline = title + listing snippet (reliable); body = detail page main text (noisier);
    title = the opportunity title alone (most reliable)."""
    head = headline or ""
    title = title or head
    # A page that names many countries is usually a country drop-down or a sidebar, not eligibility.
    if body and _distinct_countries(body) >= 12:
        body = ""
    full = head + " \n " + (body or "")
    if RX_UZ.search(full):
        return "uz"
    if RX_REGION.search(full):
        return "region"
    if RX_OTHER.search(title):          # "Grants for SMEs (Malta)" beats a generic "global" elsewhere
        return "other"
    if RX_GLOBAL.search(head):
        return "global"
    if RX_OTHER.search(head):
        return "other"
    # body evidence is weaker: only use it when the headline is silent
    if body:
        g = len(RX_GLOBAL.findall(body))
        o = len(RX_OTHER.findall(body))
        if g and g >= o:
            return "global"
        if o >= 2 and not g:
            return "other"
    return "unknown"


def geography_passes(geo: str, mode: str) -> bool:
    mode = (mode or "relaxed").lower()
    if mode == "off":
        return True
    if mode == "local":      # only calls that explicitly name Uzbekistan or the region
        return geo in ("uz", "region")
    if mode == "strict":
        return geo in ("uz", "region", "global")
    return geo != "other"


RX_YEAR = re.compile(r"\b(20[1-3]\d)\b")


def is_stale_title(title: str, today: date | None = None) -> bool:
    """True when every year mentioned in the title is in the past, e.g. 'Grants 2023'."""
    years = [int(y) for y in RX_YEAR.findall(title or "")]
    return bool(years) and max(years) < (today or date.today()).year


# --------------------------------------------------------------------------
# Deadline extraction
# --------------------------------------------------------------------------

_MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE = (
    r"(?:\d{4}-\d{1,2}-\d{1,2}"                                   # 2026-10-15
    r"|\d{1,2}(?:st|nd|rd|th)?[\s\-]+" + _MONTHS + r"\.?,?[\s\-]+\d{2,4}"  # 15 October 2026 / 15-Oct-26
    r"|" + _MONTHS + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"   # October 15, 2026
    r"|\d{1,2}[./]\d{1,2}[./]\d{2,4})"                            # 15/10/2026, 15.10.2026
)
_TRIGGER = (r"(?:deadline|closing date|close date|closes|closing|close on|due date|due by|due on|submission date|"
            r"submit by|apply by|applications? (?:are )?due|last date|end date|until|no later than|expires?)")
RX_DEADLINE = re.compile(_TRIGGER + r"[^0-9a-z]{0,6}(?:[^\n]{0,60}?)(" + _DATE + r")", re.IGNORECASE)
RX_ANYDATE = re.compile(_DATE, re.IGNORECASE)


def _parse(s: str):
    s = re.sub(r"(\d)(st|nd|rd|th)", r"\1", s, flags=re.I)
    try:
        iso = bool(re.match(r"\d{4}-", s))
        return dateparser.parse(s, dayfirst=not iso, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def extract_deadline(*texts: str, today: date | None = None) -> str | None:
    today = today or date.today()
    lo, hi = today - timedelta(days=60), today + timedelta(days=3 * 365)
    for text in texts:
        if not text:
            continue
        for m in RX_DEADLINE.finditer(text):
            d = _parse(m.group(1))
            if d and lo <= d <= hi:
                return d.isoformat()
    return None
