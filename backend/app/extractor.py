"""
Layout-aware document understanding for invoices & receipts.

Input: pages of positioned words (from pdf.js text layer or Tesseract OCR in the browser):
    {"width": W, "height": H, "words": [{"text", "x0", "y0", "x1", "y1"}, ...]}  (top-left origin)

Pipeline:
  1. Reconstruct text lines from word geometry.
  2. Key-value extraction: label detection -> candidate values to the right or below ->
     type validation -> confidence scoring (label strength x geometry x parse quality).
  3. Table understanding: header detection, column inference, row parsing (with a
     receipt-style fallback for documents without a table header).
  4. Vendor detection from typography (largest text in the page header).
Every extracted value keeps its bounding box so the UI can highlight its source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

from . import parsing as P


# ------------------------------------------------------------------ geometry ---
@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int = 0

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    @property
    def h(self):
        return self.y1 - self.y0


@dataclass
class Line:
    words: list
    page: int

    @property
    def text(self):
        return " ".join(w.text for w in self.words)

    @property
    def low(self):
        return self.text.lower()

    @property
    def y0(self):
        return min(w.y0 for w in self.words)

    @property
    def y1(self):
        return max(w.y1 for w in self.words)

    @property
    def x0(self):
        return min(w.x0 for w in self.words)

    @property
    def x1(self):
        return max(w.x1 for w in self.words)

    @property
    def h(self):
        return median([w.h for w in self.words])


def bbox(words):
    return {
        "page": words[0].page,
        "x0": round(min(w.x0 for w in words), 2), "y0": round(min(w.y0 for w in words), 2),
        "x1": round(max(w.x1 for w in words), 2), "y1": round(max(w.y1 for w in words), 2),
    }


def build_lines(pages):
    lines = []
    for pi, pg in enumerate(pages):
        words = [Word(w["text"], w["x0"], w["y0"], w["x1"], w["y1"], pi)
                 for w in pg.get("words", []) if str(w.get("text", "")).strip()]
        if not words:
            continue
        mh = median([w.h for w in words]) or 10
        words.sort(key=lambda w: (w.cy, w.x0))
        cur, cur_y = [], None
        for w in words:
            if cur and abs(w.cy - cur_y) > mh * 0.45:
                lines.append(cur)
                cur = []
            cur.append(w)
            cur_y = sum(x.cy for x in cur) / len(cur)
        if cur:
            lines.append(cur)
    out = []
    for ws in lines:
        ws.sort(key=lambda w: w.x0)
        # split a visual line into segments when there is a big horizontal gap
        segs, seg = [], [ws[0]]
        gap_lim = max(median([w.h for w in ws]) * 3.2, 18)
        for a, b in zip(ws, ws[1:]):
            if b.x0 - a.x1 > gap_lim:
                segs.append(seg)
                seg = []
            seg.append(b)
        segs.append(seg)
        out.append({"line": Line(ws, ws[0].page), "segments": [Line(s, ws[0].page) for s in segs]})
    return out


# ------------------------------------------------------------- key / value ----
FIELD_LABELS = {
    "invoice_number": [
        (r"\binvoice\s*(number|no\.?|num|#)", 1.0), (r"\binv(oice)?\s*#", 1.0), (r"\breceipt\s*(#|no\.?|number)", 0.95),
        (r"\bbill\s*(number|no\.?|#)", 0.9), (r"\bstatement\s*(number|no\.?|#)", 0.85), (r"\breference\s*(#|no\.?)", 0.6),
        (r"\binvoice\b(?!\s*date)", 0.55)],
    "invoice_date": [
        (r"\binvoice\s*date", 1.0), (r"\bdate\s*issued", 1.0), (r"\bissue\s*date", 1.0), (r"\bdate\s*of\s*issue", 1.0),
        (r"\bbill(ing)?\s*date", 0.95), (r"\bstatement\s*date", 0.9), (r"^date\b|\bdate:", 0.75)],
    "due_date": [
        (r"\bdue\s*date", 1.0), (r"\bpayment\s*due", 0.95), (r"\bpay\s*by", 0.9), (r"\bdue\s*by", 0.9), (r"\bdue\b", 0.6)],
    "po_number": [(r"\bp\.?\s?o\.?\s*(number|no\.?|#)", 1.0), (r"\bpurchase\s*order", 1.0), (r"\border\s*(number|no\.?|#)", 0.7)],
    "subtotal": [(r"\bsub\s*-?\s*total", 1.0), (r"\bnet\s*amount", 0.8), (r"\bamount\s*before\s*tax", 0.9)],
    "tax": [(r"\b(sales\s*tax|vat|gst|hst|utility\s*tax|tax)\b", 1.0)],
    "shipping": [(r"\b(shipping|freight|delivery)\b", 1.0)],
    "discount": [(r"\bdiscount\b", 1.0)],
    "total": [
        (r"\b(total\s*due|amount\s*due|balance\s*due|grand\s*total|total\s*amount|amount\s*payable)\b", 1.0),
        (r"(?<!sub)(?<!sub )\btotal\b", 0.85)],
}
MONEY_FIELDS = {"subtotal", "tax", "shipping", "discount", "total"}
DATE_FIELDS = {"invoice_date", "due_date"}
ID_FIELDS = {"invoice_number", "po_number"}


def _value_words_right(seg_or_line, label_end_idx):
    return seg_or_line.words[label_end_idx:]


def _match_label(line_text, pattern):
    m = re.search(pattern, line_text, re.I)
    return m


def _words_after_char(line: Line, char_end: int):
    """Return words of the line whose start offset is >= char_end."""
    pos, out = 0, []
    for w in line.words:
        if pos >= char_end:
            out.append(w)
        pos += len(w.text) + 1
    return out


def _parse_for(field_name, words):
    """Try to read a typed value from the beginning of a word list."""
    if not words:
        return None
    text = " ".join(w.text for w in words)
    if field_name in DATE_FIELDS:
        d, sub = P.parse_date(text)
        if d:
            n = max(1, len(sub.split()))
            return d.isoformat(), words[:n], 1.0
        return None
    if field_name in MONEY_FIELDS:
        for i, w in enumerate(words[:4]):
            tok = w.text.strip().strip(":")
            if P.is_money_token(tok) or (P.parse_money(tok) is not None and re.search(r"\d", tok) and "%" not in tok):
                # skip "(8.25%)" style tokens and qty-like ints right after label
                if "%" in tok:
                    continue
                v = P.parse_money(tok)
                if v is None:
                    continue
                q = 1.0 if P.is_money_token(tok) else 0.7
                return round(v, 2), [w], q
        return None
    if field_name in ID_FIELDS:
        for w in words[:3]:
            tok = w.text.strip().strip(":").lstrip("#")
            if tok.lower() in {"number", "no", "no.", "#", "date"}:
                continue
            if P.looks_like_id(tok):
                return tok, [w], 1.0
            break
        return None
    return None


def extract_fields(lines):
    flat = [l["line"] for l in lines]
    found = {}
    for fname, labels in FIELD_LABELS.items():
        best = None
        for li, entry in enumerate(lines):
            for seg in entry["segments"]:
                for pattern, strength in labels:
                    m = _match_label(seg.text, pattern)
                    if not m:
                        continue
                    low = seg.low
                    if fname == "total" and re.search(r"sub\s*-?\s*total", low):
                        continue
                    if fname == "tax" and re.search(r"tax\s*id|vat\s*(no|number|reg)|\bvat\s*nl|tax\s*exempt", low):
                        continue
                    if fname == "invoice_date" and re.search(r"due|payment", low):
                        continue
                    if fname == "due_date" and re.search(r"amount|balance|total|past", low):
                        continue
                    # 1) value on the same visual line, to the right of the label
                    cand_words = _words_after_char(seg, m.end())
                    after = [w for w in entry["line"].words if w.x0 >= (cand_words[0].x0 if cand_words else seg.x1) - 1]
                    geo = 1.0
                    got = _parse_for(fname, cand_words) or _parse_for(fname, after)
                    if not got and fname not in MONEY_FIELDS:
                        # 2) value directly below the label (stacked layouts)
                        for nxt in flat[li + 1: li + 3]:
                            below = [w for w in nxt.words if w.x0 < seg.x1 + 40 and w.x1 > seg.x0 - 10]
                            got = _parse_for(fname, below)
                            if got:
                                geo = 0.9
                                break
                    if not got:
                        continue
                    value, vwords, quality = got
                    # labels nearer the start of a segment are more reliable
                    pos_pen = 1.0 if m.start() <= 2 else 0.9
                    conf = round(min(0.99, strength * geo * quality * pos_pen * 0.99), 3)
                    lower_bonus = (li / max(1, len(lines))) if fname == "total" else 0
                    score = conf + 0.05 * lower_bonus
                    if fname == "total" and best and best["_score"] >= score - 0.05 and best["value"] >= value:
                        pass
                    if not best or score > best["_score"] or (fname == "total" and score >= best["_score"] - 0.02
                                                                and value > best["value"]):
                        best = {"value": value, "confidence": conf, "_score": score,
                                "bbox": bbox(vwords), "label_bbox": bbox(seg.words[:max(1, len(seg.words) - len(cand_words))]),
                                "source": seg.text[:80]}
                    if fname == "tax":
                        rate = P.parse_pct(seg.text)
                        if rate is not None:
                            best = {**best, "rate": rate} if best and best["value"] == value else best
                    break
        if best:
            best.pop("_score", None)
            found[fname] = best
    return found


# -------------------------------------------------------------- party info ---
TITLE_WORDS = re.compile(r"^(tax\s+)?(invoice|receipt|bill|utility bill|statement|credit note|purchase order|quote|estimate)$", re.I)
NOISE = re.compile(r"(bill(ed)?\s*to|ship\s*to|date|invoice\s*(no|#|number)|page \d|www\.|@|\d{3}[) -]\d{3})", re.I)


def extract_vendor(lines):
    """Vendor = most prominent text block in the top of page 1 that isn't a document title."""
    first = [l for l in lines if l["line"].page == 0]
    if not first:
        return None
    page_h = max(l["line"].y1 for l in first) or 1
    top = [s for l in first for s in l["segments"] if s.y0 < page_h * 0.3]
    cands = []
    for s in top:
        t = s.text.strip(" :")
        if len(t) < 3 or TITLE_WORDS.match(t) or NOISE.search(t) or P.parse_date(t)[0] or re.fullmatch(r"[\d\W]+", t):
            continue
        if re.search(r"\binvoice\b|\breceipt\b", t, re.I) and len(t.split()) <= 3:
            continue
        letters = sum(c.isalpha() for c in t) / max(1, len(t))
        score = s.h * (0.7 + 0.3 * letters) * (1.15 if s.y0 < page_h * 0.15 else 1.0)
        cands.append((score, s))
    if not cands:
        return None
    cands.sort(key=lambda x: -x[0])
    best_score, best = cands[0]
    second = cands[1][0] if len(cands) > 1 else best_score * 0.5
    dominance = best_score / max(second, 1e-6)
    conf = round(min(0.98, 0.55 + 0.25 * min(dominance - 1, 1.6)), 3)
    name = re.sub(r"\s{2,}", " ", best.text).strip(" :")
    name = name.title() if name.isupper() and len(name) > 4 else name
    return {"value": name, "confidence": conf, "bbox": bbox(best.words), "source": best.text}


def extract_contacts(lines):
    text = "\n".join(l["line"].text for l in lines)
    out = {}
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if m:
        out["email"] = m[0]
    m = re.search(r"(\+?1?[ (-]*\d{3}[) .-]*\d{3}[ .-]\d{4})", text)
    if m:
        out["phone"] = m[0].strip()
    m = re.search(r"(tax\s*id|vat(\s*(no|number|reg\.?))?|ein|gstin)[:\s#]*([A-Z]{0,2}[\d-]{6,}[A-Z0-9]*)", text, re.I)
    if m:
        out["tax_id"] = m[4]
    m = re.search(r"\bnet\s*(\d{1,3})\b", text, re.I)
    if m:
        out["payment_terms"] = f"Net {m[1]}"
    return out


def extract_bill_to(lines):
    for i, entry in enumerate(lines):
        for seg in entry["segments"]:
            if re.search(r"\b(bill(ed)?\s*to|sold\s*to|invoice\s*to)\b", seg.low):
                rest = re.sub(r"(?i).*?(bill(ed)?\s*to|sold\s*to|invoice\s*to)\s*:?", "", seg.text).strip()
                out, words = ([rest] if rest else []), (seg.words if rest else [])
                for nxt in lines[i + 1: i + 6]:
                    col = [s for s in nxt["segments"] if abs(s.x0 - seg.x0) < 25]
                    if not col:
                        if out:
                            break
                        continue
                    t = col[0].text
                    if re.search(r"description|qty|amount|date|invoice", t, re.I):
                        break
                    out.append(t)
                    words += col[0].words
                    if len(out) >= 4:
                        break
                if out:
                    return {"value": out[0], "lines": out, "confidence": 0.9, "bbox": bbox(words)}
    return None


# ------------------------------------------------------------------- tables ---
HEADER_KEYS = {
    "description": r"^(description|item|items|product|service|details|particulars)$",
    "qty": r"^(qty|quantity|units?|hrs|hours)$",
    "unit_price": r"^(unit|price|rate|unit\s*price|unit\s*cost|cost)$",
    "amount": r"^(amount|total|line\s*total|ext\.?\s*price|subtotal)$",
}
STOP_ROW = re.compile(r"\b(sub\s*-?\s*total|total|tax|vat|shipping|balance|amount due|discount)\b", re.I)


def _header_columns(line: Line):
    cols = {}
    words = line.words
    i = 0
    while i < len(words):
        w = words[i]
        t = w.text.lower().strip(":")
        two = (t + " " + words[i + 1].text.lower()) if i + 1 < len(words) else None
        if two and re.match(HEADER_KEYS["unit_price"], two) and two.startswith("unit"):
            cols["unit_price"] = (w.x0, words[i + 1].x1)
            i += 2
            continue
        for k, rx in HEADER_KEYS.items():
            if k not in cols and re.match(rx, t):
                cols[k] = (w.x0, w.x1)
                break
        i += 1
    return cols


def extract_line_items(lines):
    header_idx, cols = None, None
    for i, entry in enumerate(lines):
        c = _header_columns(entry["line"])
        if len(c) >= 3 and "description" in c or (len(c) >= 3 and "amount" in c):
            header_idx, cols = i, c
            break
    items = []
    if header_idx is not None:
        num_cols = {k: v for k, v in cols.items() if k != "description"}
        for entry in lines[header_idx + 1:]:
            ln = entry["line"]
            if STOP_ROW.search(ln.low) and not re.search(r"[a-z]{4,}.*\d.*\d", ln.low.split("total")[0] if "total" in ln.low else ""):
                if STOP_ROW.match(ln.low.strip()) or len([w for w in ln.words if P.is_money_token(w.text)]) <= 2:
                    break
            nums, desc = {}, []
            for w in ln.words:
                is_num = P.parse_money(w.text) is not None and re.search(r"\d", w.text)
                if is_num and num_cols:
                    # nearest numeric column by right edge (numbers are usually right-aligned)
                    k = min(num_cols, key=lambda c: min(abs(w.x1 - num_cols[c][1]), abs(w.cx - sum(num_cols[c]) / 2)))
                    dist = min(abs(w.x1 - num_cols[k][1]), abs(w.cx - sum(num_cols[k]) / 2))
                    if dist < 60 and k not in nums:
                        nums[k] = w
                        continue
                desc.append(w)
            if not desc and not nums:
                continue
            if "amount" not in nums and len(nums) < 2:
                # continuation of previous description
                if items and desc and not nums:
                    items[-1]["description"] += " " + " ".join(w.text for w in desc)
                    continue
                if not nums:
                    continue
            row = _make_row(desc, nums)
            if row:
                items.append(row)
        if items:
            return items, "table"
    # receipt fallback: "<qty> x <desc> <money>" or "<desc> <money>"
    for entry in lines:
        ln = entry["line"]
        if STOP_ROW.search(ln.low) or len(ln.words) < 2:
            continue
        last = ln.words[-1]
        if not P.is_money_token(last.text):
            continue
        body = ln.words[:-1]
        qty = 1.0
        if len(body) >= 2 and P.parse_qty(body[0].text) and body[1].text.lower() in {"x", "@", "×"}:
            qty = P.parse_qty(body[0].text)
            body = body[2:]
        elif body and re.fullmatch(r"\d+x", body[0].text.lower()):
            qty = P.parse_qty(body[0].text)
            body = body[1:]
        desc_txt = " ".join(w.text for w in body)
        if len(re.sub(r"[^A-Za-z]", "", desc_txt)) < 3 or re.search(r"visa|mastercard|amex|change|cash|card|tip", desc_txt, re.I):
            continue
        amt = P.parse_money(last.text)
        items.append({"description": desc_txt, "quantity": qty, "unit_price": round(amt / qty, 2) if qty else amt,
                      "amount": amt, "bbox": bbox(ln.words)})
    return items, "receipt" if items else "none"


def _make_row(desc, nums):
    def val(k, money=True):
        if k not in nums:
            return None
        return P.parse_money(nums[k].text) if money else P.parse_qty(nums[k].text)
    qty = val("qty", money=False)
    price = val("unit_price")
    amount = val("amount")
    if amount is None and qty is not None and price is not None:
        amount = round(qty * price, 2)
    if price is None and amount is not None and qty:
        price = round(amount / qty, 4)
    if qty is None and amount is not None and price:
        qty = round(amount / price, 3)
    if amount is None:
        return None
    words = desc + list(nums.values())
    return {"description": " ".join(w.text for w in desc).strip(" -"), "quantity": qty if qty is not None else 1.0,
            "unit_price": price if price is not None else amount, "amount": amount, "bbox": bbox(words)}


# -------------------------------------------------------------------- main ---
def extract(pages):
    lines = build_lines(pages)
    full_text = "\n".join(l["line"].text for l in lines)
    fields = extract_fields(lines)
    vendor = extract_vendor(lines)
    if vendor:
        fields["vendor"] = vendor
    bt = extract_bill_to(lines)
    if bt:
        fields["bill_to"] = bt
    items, mode = extract_line_items(lines)
    contacts = extract_contacts(lines)
    currency = P.detect_currency(full_text)
    # infer missing subtotal / total from items
    if "subtotal" not in fields and items:
        fields["subtotal"] = {"value": round(sum(i["amount"] for i in items), 2), "confidence": 0.6,
                              "inferred": True, "bbox": None}
    return {
        "fields": fields,
        "line_items": items,
        "table_mode": mode,
        "contacts": contacts,
        "currency": currency,
        "text": full_text,
        "n_lines": len(lines),
    }
