"""Financial validation & anomaly detection for extracted documents."""
from __future__ import annotations

from datetime import date
from statistics import mean, pstdev

TOL = 0.02  # currency rounding tolerance


def _close(a, b, tol=TOL):
    return a is not None and b is not None and abs(a - b) <= max(tol, abs(b) * 0.0005)


def _v(fields, k):
    f = fields.get(k)
    return f["value"] if f else None


def run_checks(fields, items, history):
    checks = []

    def add(cid, title, status, detail):
        checks.append({"id": cid, "title": title, "status": status, "detail": detail})

    # required fields
    missing = [k for k in ("vendor", "invoice_number", "invoice_date", "total") if k not in fields]
    add("required", "Required fields present", "fail" if missing else "pass",
        f"Missing: {', '.join(missing)}" if missing else "Vendor, number, date and total all found")

    # line-item arithmetic
    if items:
        bad = [i for i in items if i.get("quantity") and i.get("unit_price") is not None
               and not _close(round(i["quantity"] * i["unit_price"], 2), i["amount"], 0.05)]
        add("line_math", "Line items: qty × unit price = amount", "warn" if bad else "pass",
            f"{len(bad)} line(s) don't multiply out: " + "; ".join(b["description"][:30] for b in bad[:3]) if bad
            else f"All {len(items)} line items reconcile")

    sub, tax, total = _v(fields, "subtotal"), _v(fields, "tax"), _v(fields, "total")
    ship, disc = _v(fields, "shipping") or 0, abs(_v(fields, "discount") or 0)
    if items and sub is not None and not fields["subtotal"].get("inferred"):
        s = round(sum(i["amount"] for i in items), 2)
        add("subtotal", "Line items sum to subtotal", "pass" if _close(s, sub) else "fail",
            f"Items {s:,.2f} vs subtotal {sub:,.2f}" + ("" if _close(s, sub) else f" (diff {s - sub:+,.2f})"))
    if total is not None and sub is not None:
        expect = round(sub - disc + (tax or 0) + ship, 2)
        ok = _close(expect, total)
        add("total", "Subtotal + tax + shipping = total", "pass" if ok else "fail",
            f"Expected {expect:,.2f}, document says {total:,.2f}" + ("" if ok else f" (diff {total - expect:+,.2f})"))
    rate = fields.get("tax", {}).get("rate") if fields.get("tax") else None
    if rate is not None and sub and tax is not None:
        implied = tax / max(sub - disc, 1e-9)
        ok = abs(implied - rate) < 0.0015
        add("tax_rate", "Tax amount matches stated rate", "pass" if ok else "warn",
            f"Stated {rate * 100:.3g}%, implied {implied * 100:.3g}%")
    elif tax is not None and sub:
        implied = tax / sub
        add("tax_rate", "Tax rate plausible", "pass" if implied <= 0.27 else "warn", f"Implied rate {implied * 100:.3g}%")

    inv_d, due_d = _v(fields, "invoice_date"), _v(fields, "due_date")
    if inv_d and due_d:
        a, b = date.fromisoformat(inv_d), date.fromisoformat(due_d)
        days = (b - a).days
        add("dates", "Due date after invoice date", "pass" if 0 <= days <= 120 else "warn",
            f"Payment window {days} days")

    # duplicates & outliers vs previously processed documents
    vendor, number = (_v(fields, "vendor") or "").lower(), (_v(fields, "invoice_number") or "").lower()
    dupes = [h for h in history if (number and h.get("invoice_number", "").lower() == number
                                    and h.get("vendor", "").lower() == vendor)
             or (vendor and h.get("vendor", "").lower() == vendor and total is not None
                 and _close(h.get("total") or -1, total) and h.get("invoice_date") == inv_d)]
    add("duplicate", "Not a duplicate of a processed document", "fail" if dupes else "pass",
        f"Matches {dupes[0].get('file', 'an earlier document')} (same vendor & invoice number)" if dupes
        else f"Checked against {len(history)} processed document(s)")
    prior = [h["total"] for h in history if h.get("vendor", "").lower() == vendor and h.get("total")]
    if len(prior) >= 2 and total:
        mu, sd = mean(prior), pstdev(prior) or max(mean(prior) * 0.1, 1)
        z = (total - mu) / sd
        add("outlier", "Amount in line with vendor history", "warn" if abs(z) > 3 else "pass",
            f"z-score {z:+.1f} vs {len(prior)} prior invoices (avg {mu:,.2f})")

    score = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    health = round(sum(score[c["status"]] for c in checks) / max(1, len(checks)), 3)
    return checks, health
