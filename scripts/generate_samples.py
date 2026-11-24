"""
Generate realistic sample invoices / receipts for the LedgerLens demo.

All companies are fictional. Output goes to frontend/public/samples/.
Run:  python scripts/generate_samples.py
"""
import os
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "samples")
os.makedirs(OUT, exist_ok=True)
W, H = letter

BUYER = ["Orbit Labs Inc.", "Attn: Accounts Payable", "500 Market Street, Suite 1200", "San Francisco, CA 94105"]


def money(v, cur="$"):
    return f"{cur}{v:,.2f}"


def totals(items, tax_rate, shipping=0.0, discount=0.0):
    sub = round(sum(q * p for _, q, p in items), 2)
    tax = round((sub - discount) * tax_rate, 2)
    return sub, tax, round(sub - discount + tax + shipping, 2)


# ------------------------------------------------------------------ layouts ---
def layout_classic(path, d):
    c = canvas.Canvas(path, pagesize=letter)
    accent = HexColor(d["color"])
    c.setFillColor(accent)
    c.rect(0, H - 12, W, 12, fill=1, stroke=0)
    c.setFillColor(HexColor("#111111"))
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, H - 70, d["vendor"])
    c.setFont("Helvetica", 9.5)
    y = H - 86
    for line in d["vendor_addr"]:
        c.drawString(50, y, line); y -= 13
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(accent)
    c.drawRightString(W - 50, H - 72, d.get("title", "INVOICE"))
    c.setFillColor(HexColor("#111111"))
    c.setFont("Helvetica", 10)
    meta = [("Invoice Number:", d["number"]), ("Invoice Date:", d["date"].strftime("%B %d, %Y")),
            ("Due Date:", d["due"].strftime("%B %d, %Y"))]
    if d.get("po"):
        meta.append(("PO Number:", d["po"]))
    y = H - 100
    for k, v in meta:
        c.drawRightString(W - 150, y, k)
        c.drawRightString(W - 50, y, v)
        y -= 15
    y = H - 190
    c.setFont("Helvetica-Bold", 10); c.drawString(50, y, "Bill To:")
    c.setFont("Helvetica", 10)
    for line in BUYER:
        y -= 14; c.drawString(50, y, line)
    table(c, d, H - 290, accent)
    c.save()


def layout_band(path, d):
    c = canvas.Canvas(path, pagesize=letter)
    accent = HexColor(d["color"])
    c.setFillColor(accent)
    c.rect(0, H - 130, W, 130, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(50, H - 60, d["vendor"])
    c.setFont("Helvetica", 9.5)
    y = H - 78
    for line in d["vendor_addr"]:
        c.drawString(50, y, line); y -= 13
    c.setFont("Helvetica-Bold", 30)
    c.drawRightString(W - 50, H - 65, d.get("title", "INVOICE"))
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 50, H - 85, f"Invoice # {d['number']}")
    c.setFillColor(HexColor("#222222"))
    # meta grid
    y = H - 170
    cols = [("BILLED TO", BUYER), ("DATE ISSUED", [d["date"].strftime("%m/%d/%Y")]),
            ("PAYMENT DUE", [d["due"].strftime("%m/%d/%Y"), d.get("terms", "Net 30")])]
    x = 50
    for title, lines in cols:
        c.setFont("Helvetica-Bold", 8.5); c.setFillColor(HexColor("#777777")); c.drawString(x, y, title)
        c.setFillColor(HexColor("#222222")); c.setFont("Helvetica", 10)
        yy = y - 15
        for ln in lines:
            c.drawString(x, yy, ln); yy -= 13
        x += 190
    table(c, d, H - 280, accent)
    c.save()


def layout_minimal(path, d):
    c = canvas.Canvas(path, pagesize=letter)
    accent = HexColor(d["color"])
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(accent)
    c.drawString(50, H - 60, d["vendor"].upper())
    c.setFillColor(HexColor("#555555"))
    c.setFont("Helvetica", 9)
    c.drawString(50, H - 74, "  ·  ".join(d["vendor_addr"]))
    c.setFillColor(HexColor("#111111"))
    c.setFont("Helvetica", 34)
    c.drawString(50, H - 130, d.get("title", "Invoice").title())
    c.setFont("Helvetica", 10)
    rows = [("Invoice No.", d["number"]), ("Issue date", d["date"].strftime("%d %b %Y")),
            ("Due date", d["due"].strftime("%d %b %Y"))]
    if d.get("po"):
        rows.append(("Purchase Order", d["po"]))
    y = H - 165
    for k, v in rows:
        c.setFillColor(HexColor("#777777")); c.drawString(50, y, k)
        c.setFillColor(HexColor("#111111")); c.drawString(150, y, v)
        y -= 15
    y = H - 165
    c.setFillColor(HexColor("#777777")); c.drawString(340, y, "Billed to")
    c.setFillColor(HexColor("#111111"))
    for ln in BUYER:
        y -= 14; c.drawString(340, y, ln)
    table(c, d, H - 270, accent, lines_only=True)
    c.save()


def table(c, d, top, accent, lines_only=False):
    cur = d.get("cur", "$")
    xs = [50, 340, 420, W - 50]
    if lines_only:
        c.setStrokeColor(HexColor("#111111")); c.setLineWidth(1)
        c.line(50, top + 16, W - 50, top + 16)
        c.line(50, top - 8, W - 50, top - 8)
        c.setFillColor(HexColor("#111111"))
    else:
        c.setFillColor(accent)
        c.rect(50, top - 6, W - 100, 22, fill=1, stroke=0)
        c.setFillColor(white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(xs[0] + 8, top, "Description")
    c.drawRightString(xs[1] + 40, top, "Qty")
    c.drawRightString(xs[2] + 60, top, "Unit Price")
    c.drawRightString(xs[3] - 8, top, "Amount")
    c.setFillColor(HexColor("#222222"))
    c.setFont("Helvetica", 10)
    y = top - 26
    for desc, q, p in d["items"]:
        c.drawString(xs[0] + 8, y, desc)
        c.drawRightString(xs[1] + 40, y, f"{q:g}")
        c.drawRightString(xs[2] + 60, y, money(p, cur) if round(p, 2) == p else f"{cur}{p:,.3f}")
        c.drawRightString(xs[3] - 8, y, money(q * p, cur))
        c.setStrokeColor(HexColor("#e5e5e5")); c.setLineWidth(0.5)
        c.line(50, y - 7, W - 50, y - 7)
        y -= 22
    sub, tax, tot = totals(d["items"], d["tax"], d.get("shipping", 0), d.get("discount", 0))
    if d.get("override_total"):
        tot = d["override_total"]
    y -= 12
    rows = [("Subtotal", sub)]
    if d.get("discount"):
        rows.append(("Discount", -d["discount"]))
    rows.append((f"{d.get('tax_label', 'Tax')} ({d['tax'] * 100:g}%)", tax))
    if d.get("shipping"):
        rows.append(("Shipping", d["shipping"]))
    for k, v in rows:
        c.drawRightString(W - 150, y, k)
        c.drawRightString(W - 58, y, money(v, cur) if v >= 0 else "-" + money(-v, cur))
        y -= 17
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(W - 150, y - 4, d.get("total_label", "Total Due"))
    c.drawRightString(W - 58, y - 4, money(tot, cur))
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#666666"))
    yy = 110
    for ln in d.get("footer", []):
        c.drawString(50, yy, ln); yy -= 13


# ------------------------------------------------------------------ data ------
base = date(2026, 10, 1)
SAMPLES = [
    ("nimbus-cloud-invoice.pdf", layout_band, dict(
        vendor="Nimbus Cloud Services", color="#4f46e5",
        vendor_addr=["1450 Harbor Blvd, Seattle, WA 98101", "billing@nimbuscloud.example", "Tax ID: 91-4827713"],
        number="NCS-2026-10418", date=base + timedelta(days=2), due=base + timedelta(days=32), terms="Net 30",
        items=[("Compute instances - Standard (720 hrs)", 3, 186.40), ("Managed PostgreSQL - Business tier", 1, 420.00),
               ("Object storage - 4.2 TB", 4.2, 23.00), ("Data transfer egress - 1.8 TB", 1.8, 90.00),
               ("Premium support plan - October", 1, 299.00)],
        tax=0.0825, footer=["Thank you for building with Nimbus.", "Pay online at pay.nimbuscloud.example or by ACH: routing 000000000."])),
    ("atlas-office-supply-invoice.pdf", layout_classic, dict(
        vendor="Atlas Office Supply Co.", color="#0f766e",
        vendor_addr=["88 Industrial Way", "Oakland, CA 94607", "(510) 555-0142"],
        number="AOS-55821", po="PO-7731", date=base + timedelta(days=6), due=base + timedelta(days=36),
        items=[("Ergonomic office chair - mesh back", 4, 249.00), ("Standing desk frame, dual motor", 2, 389.00),
               ("Copy paper, letter, 10-ream case", 6, 54.99), ("Wireless keyboard and mouse set", 5, 59.50),
               ("Whiteboard markers, assorted 12-pack", 8, 14.25), ("Desk organizer, bamboo", 5, 22.00)],
        tax=0.095, shipping=65.00, footer=["Payment terms: Net 30. Late payments subject to 1.5% monthly fee."])),
    ("brightpath-marketing-invoice.pdf", layout_minimal, dict(
        vendor="Brightpath Marketing Studio", color="#db2777",
        vendor_addr=["212 Sunset Ave, Los Angeles, CA 90026", "hello@brightpath.example"],
        number="BP-0937", po="PO-7802", date=base + timedelta(days=12), due=base + timedelta(days=27),
        items=[("Paid social campaign management - October", 1, 3200.00), ("Ad creative production (6 assets)", 6, 275.00),
               ("SEO audit and keyword strategy", 1, 1450.00), ("Landing page copywriting", 2, 380.00)],
        tax=0.0, tax_label="Sales Tax", footer=["Brightpath Marketing Studio · Wire or card accepted"])),
    ("cascade-energy-bill.pdf", layout_classic, dict(
        vendor="Cascade Energy Utilities", color="#ca8a04", title="UTILITY BILL",
        vendor_addr=["PO Box 4410", "Portland, OR 97208", "Customer care: 1-800-555-0199"],
        number="CEU-88310452", date=base + timedelta(days=15), due=base + timedelta(days=36),
        items=[("Electricity usage - 14,280 kWh", 14280, 0.142), ("Natural gas - 612 therms", 612, 1.31),
               ("Demand charge (peak kW)", 1, 310.00), ("Grid connection fee", 1, 45.00)],
        tax=0.04, tax_label="Utility Tax", total_label="Amount Due", footer=["Account 4410-2291-07 · Service address: 500 Market St"])),
    ("skyline-travel-invoice.pdf", layout_band, dict(
        vendor="Skyline Travel Partners", color="#0284c7", cur="€",
        vendor_addr=["Keizersgracht 210, 1016 DZ Amsterdam", "invoices@skylinetravel.example", "VAT NL812345678B01"],
        number="STP-24-3318", date=base + timedelta(days=20), due=base + timedelta(days=34), terms="Net 14",
        items=[("Return flight SFO-AMS, economy plus", 2, 1240.00), ("Hotel Canal View - 4 nights", 8, 189.00),
               ("Airport transfers", 2, 65.00), ("Travel insurance - business", 2, 48.00)],
        tax=0.09, tax_label="VAT", footer=["Skyline Travel Partners B.V. · IBAN NL00 BANK 0000 0000 00"])),
    ("metro-catering-invoice.pdf", layout_minimal, dict(
        vendor="Metro Catering & Events", color="#ea580c",
        vendor_addr=["9 Pier Street, San Francisco, CA 94111", "orders@metrocatering.example"],
        number="MCE-7710", date=base + timedelta(days=22), due=base + timedelta(days=37),
        items=[("Team offsite lunch buffet (45 guests)", 45, 32.00), ("Coffee & pastry service", 45, 9.50),
               ("Event staff (4 hrs x 3)", 12, 38.00)],
        tax=0.08625, override_total=2391.40,  # deliberately wrong total -> validation flag
        footer=["Gratuity not included."])),
    ("atlas-office-supply-duplicate.pdf", layout_classic, dict(
        vendor="Atlas Office Supply Co.", color="#0f766e",
        vendor_addr=["88 Industrial Way", "Oakland, CA 94607", "(510) 555-0142"],
        number="AOS-55821", po="PO-7731", date=base + timedelta(days=6), due=base + timedelta(days=36),
        items=[("Ergonomic office chair - mesh back", 4, 249.00), ("Standing desk frame, dual motor", 2, 389.00),
               ("Copy paper, letter, 10-ream case", 6, 54.99), ("Wireless keyboard and mouse set", 5, 59.50),
               ("Whiteboard markers, assorted 12-pack", 8, 14.25), ("Desk organizer, bamboo", 5, 22.00)],
        tax=0.095, shipping=65.00, footer=["Payment terms: Net 30. Late payments subject to 1.5% monthly fee."])),
]


def receipt_png(path):
    """A slightly skewed, blurred photo-like receipt to exercise the OCR path."""
    w, h = 620, 1040
    img = Image.new("RGB", (w, h), (250, 248, 242))
    dr = ImageDraw.Draw(img)

    def font(size, bold=False):
        for f in (["DejaVuSansMono-Bold.ttf", "DejaVuSansMono.ttf"] if bold else ["DejaVuSansMono.ttf"]):
            for d in ("/usr/share/fonts/truetype/dejavu/", ""):
                try:
                    return ImageFont.truetype(d + f, size)
                except OSError:
                    pass
        return ImageFont.load_default()

    y = 40
    def line(t, size=24, bold=False, center=False):
        nonlocal y
        f = font(size, bold)
        tw = dr.textlength(t, font=f)
        dr.text(((w - tw) / 2 if center else 40, y), t, fill=(30, 30, 30), font=f)
        y += size + 14

    def row(l, r, bold=False):
        nonlocal y
        f = font(24, bold)
        dr.text((40, y), l, fill=(30, 30, 30), font=f)
        dr.text((w - 40 - dr.textlength(r, font=f), y), r, fill=(30, 30, 30), font=f)
        y += 38

    line("CORNER BEAN CAFE", 34, True, True)
    line("742 Valencia St, San Francisco", 20, center=True)
    line("Tel (415) 555-0123", 20, center=True)
    y += 10
    line("Receipt #: R-20261028-0457", 22)
    line("Date: 10/28/2026  09:14", 22)
    line("-" * 38, 22)
    items = [("Oat Latte", 2, 5.75), ("Cold Brew", 1, 4.95), ("Avocado Toast", 2, 11.50),
             ("Blueberry Muffin", 3, 3.95), ("Sparkling Water", 2, 2.75)]
    for n, q, p in items:
        row(f"{q} x {n}", f"${q * p:.2f}")
    sub = sum(q * p for _, q, p in items)
    tax = round(sub * 0.08625, 2)
    line("-" * 38, 22)
    row("Subtotal", f"${sub:.2f}")
    row("Tax 8.625%", f"${tax:.2f}")
    row("TOTAL", f"${sub + tax:.2f}", bold=True)
    y += 10
    line("VISA **** 4821", 22)
    line("Thank you! Come again.", 22, center=True)
    img = img.rotate(1.2, expand=True, fillcolor=(205, 200, 190), resample=Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img.save(path)


if __name__ == "__main__":
    for name, fn, d in SAMPLES:
        fn(os.path.join(OUT, name), d)
        sub, tax, tot = totals(d["items"], d["tax"], d.get("shipping", 0), d.get("discount", 0))
        print(f"{name:40s} sub={sub:>10,.2f} tax={tax:>8,.2f} total={d.get('override_total', tot):>10,.2f}")
    receipt_png(os.path.join(OUT, "corner-bean-receipt.png"))
    print("corner-bean-receipt.png")
