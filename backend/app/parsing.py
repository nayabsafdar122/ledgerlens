"""Low-level value parsers: money, dates, identifiers, percentages."""
from __future__ import annotations

import re
from datetime import date, datetime

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
CURRENCY_CODES = {"USD", "EUR", "GBP", "CAD", "AUD", "INR", "JPY", "CHF", "PKR", "AED"}

MONEY_RE = re.compile(r"^-?\(?[$€£¥₹]?\s?-?\d{1,3}(?:[,.\s]\d{3})*(?:[.,]\d{1,2})?\)?$|^-?[$€£¥₹]?\d+(?:[.,]\d{1,2})?$")
PCT_RE = re.compile(r"(\d{1,2}(?:[.,]\d{1,3})?)\s?%")
ID_RE = re.compile(r"^[A-Z0-9#][A-Z0-9\-][A-Z0-9\-/_.]{1,24}$", re.I)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_money(text: str):
    """Parse '$1,234.56', '€ 1.234,56', '(120.00)', '1234' -> float, or None."""
    if not text:
        return None
    t = text.strip().replace("O", "0") if re.search(r"\d", text) else text.strip()
    t = t.replace(" ", "")
    neg = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("()-")
    for s in CURRENCY_SYMBOLS:
        t = t.replace(s, "")
    for c in CURRENCY_CODES:
        t = t.replace(c, "")
    if not t or not re.fullmatch(r"[\d.,]+", t):
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):  # 1.234,56 (EU)
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        parts = t.split(",")
        if len(parts[-1]) == 2 and len(parts) == 2:  # 12,50 (EU decimals)
            t = t.replace(",", ".")
        else:
            t = t.replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def is_money_token(text: str) -> bool:
    t = text.strip()
    if not re.search(r"\d", t):
        return False
    has_sym = any(s in t for s in CURRENCY_SYMBOLS)
    has_dec = bool(re.search(r"[.,]\d{2}\)?$", t))
    return (has_sym or has_dec) and parse_money(t) is not None


def detect_currency(text: str) -> str:
    for s, code in CURRENCY_SYMBOLS.items():
        if s in text:
            return code
    for code in CURRENCY_CODES:
        if re.search(rf"\b{code}\b", text):
            return code
    return "USD"


DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b"), "mdy"),
    (re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2})\b"), "mdy2"),
    (re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b"), "Mdy"),
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"), "dMy"),
]


def parse_date(text: str):
    """Return (date, matched_substring) or (None, None)."""
    if not text:
        return None, None
    for rx, kind in DATE_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                d = date(int(m[1]), int(m[2]), int(m[3]))
            elif kind in ("mdy", "mdy2"):
                a, b, y = int(m[1]), int(m[2]), int(m[3])
                y = y + 2000 if kind == "mdy2" else y
                mo, dd = (a, b) if a <= 12 else (b, a)  # US first, fall back to D/M
                d = date(y, mo, dd)
            elif kind == "Mdy":
                mo = MONTHS.get(m[1][:3].lower())
                if not mo:
                    continue
                d = date(int(m[3]), mo, int(m[2]))
            else:
                mo = MONTHS.get(m[2][:3].lower())
                if not mo:
                    continue
                d = date(int(m[3]), mo, int(m[1]))
            if 1990 <= d.year <= 2100:
                return d, m[0]
        except ValueError:
            continue
    return None, None


def parse_pct(text: str):
    m = PCT_RE.search(text or "")
    if not m:
        return None
    return float(m[1].replace(",", ".")) / 100.0


def parse_qty(text: str):
    t = (text or "").strip().lower().rstrip("x")
    try:
        v = float(t.replace(",", ""))
        return v if 0 < v < 1e7 else None
    except ValueError:
        return None


def looks_like_id(text: str) -> bool:
    t = text.strip().strip(":#")
    return bool(ID_RE.match(t)) and bool(re.search(r"\d", t)) and parse_date(t)[0] is None
