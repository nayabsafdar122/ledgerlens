"""LedgerLens API — AI invoice & document intelligence."""
from __future__ import annotations

import io
import time
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .classifier import CATEGORIES, Classifiers
from .extractor import extract
from .validation import run_checks

app = FastAPI(title="LedgerLens API", version="1.0.0",
              description="Extract, validate and categorise invoices & receipts from positioned text.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# trained at import time (works on serverless platforms without lifespan events)
CLF = Classifiers()

FIELD_ORDER = ["vendor", "invoice_number", "invoice_date", "due_date", "po_number", "bill_to",
               "subtotal", "discount", "tax", "shipping", "total"]
FIELD_LABELS = {"vendor": "Vendor", "invoice_number": "Invoice #", "invoice_date": "Invoice date",
                "due_date": "Due date", "po_number": "PO #", "bill_to": "Bill to", "subtotal": "Subtotal",
                "discount": "Discount", "tax": "Tax", "shipping": "Shipping", "total": "Total"}
MINUTES_SAVED_PER_DOC = 6.5  # typical manual AP keying time


class WordIn(BaseModel):
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


class PageIn(BaseModel):
    width: float
    height: float
    words: list[WordIn] = Field(default_factory=list)


class ExtractIn(BaseModel):
    file_name: str = "document"
    source: str = "pdf-text"  # or "ocr"
    ocr_confidence: Optional[float] = None
    pages: list[PageIn]
    history: list[dict[str, Any]] = Field(default_factory=list)


@app.get("/api/health")
def health():
    return {"status": "ok", "models_ready": True}


@app.get("/api/model")
def model_info():
    return {**CLF.info(), "fields": [{"key": k, "label": FIELD_LABELS[k]} for k in FIELD_ORDER],
            "minutes_saved_per_doc": MINUTES_SAVED_PER_DOC}


@app.post("/api/extract")
def extract_doc(body: ExtractIn):
    t0 = time.perf_counter()
    pages = [p.model_dump() for p in body.pages]
    if not any(p["words"] for p in pages):
        raise HTTPException(422, "No readable text found in this document.")
    r = extract(pages)
    fields, items = r["fields"], r["line_items"]

    cats = CLF.categorize([i["description"] for i in items])
    for it, c in zip(items, cats):
        it.update(c)
    doc_cat = CLF.document_category(fields.get("vendor", {}).get("value"), items)
    doc_type = CLF.document_type(r["text"])

    checks, health = run_checks(fields, items, body.history)

    # overall confidence blends field confidences, OCR quality and validation health
    key = [fields[k]["confidence"] for k in ("vendor", "invoice_number", "invoice_date", "total") if k in fields]
    field_conf = sum(key) / 4 if key else 0
    ocr_q = (body.ocr_confidence / 100) if (body.source == "ocr" and body.ocr_confidence) else 1.0
    confidence = round(field_conf * (0.75 + 0.25 * ocr_q) * (0.7 + 0.3 * health), 3)
    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    status = "flagged" if fails else ("needs_review" if warns or confidence < 0.8 else "auto_approved")

    return {
        "file_name": body.file_name,
        "source": body.source,
        "currency": r["currency"],
        "document_type": doc_type,
        "category": doc_cat,
        "fields": fields,
        "field_order": FIELD_ORDER,
        "field_labels": FIELD_LABELS,
        "line_items": items,
        "table_mode": r["table_mode"],
        "contacts": r["contacts"],
        "checks": checks,
        "health": health,
        "confidence": confidence,
        "status": status,
        "issues": len(fails) + len(warns),
        "processing_ms": round((time.perf_counter() - t0) * 1000, 1),
        "page_sizes": [{"width": p["width"], "height": p["height"]} for p in pages],
    }


class ExportIn(BaseModel):
    documents: list[dict[str, Any]]


@app.post("/api/export")
def export_xlsx(body: ExportIn):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="0F3D3E")
    head_font = Font(bold=True, color="FFFFFF")

    def sheet(ws, headers, rows, money_cols=(), widths=None):
        ws.append(headers)
        for c in ws[1]:
            c.fill, c.font = head_fill, head_font
            c.alignment = Alignment(vertical="center")
        for r in rows:
            ws.append(r)
        for col in money_cols:
            for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                for c in row:
                    c.number_format = "#,##0.00"
        for i, h in enumerate(headers, 1):
            ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(h, max(12, len(h) + 4))
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    def fv(d, k):
        f = d.get("fields", {}).get(k)
        return f.get("value") if f else None

    ws = wb.active
    ws.title = "Documents"
    rows = []
    for d in body.documents:
        rows.append([d.get("file_name"), (d.get("document_type") or {}).get("type"), fv(d, "vendor"), fv(d, "invoice_number"),
                     fv(d, "invoice_date"), fv(d, "due_date"), fv(d, "po_number"), d.get("currency"), fv(d, "subtotal"),
                     fv(d, "tax"), fv(d, "shipping"), fv(d, "total"), (d.get("category") or {}).get("category"),
                     (d.get("category") or {}).get("gl_code"), d.get("status"), round((d.get("confidence") or 0) * 100, 1),
                     d.get("issues")])
    sheet(ws, ["File", "Type", "Vendor", "Invoice #", "Invoice date", "Due date", "PO #", "Currency", "Subtotal", "Tax",
               "Shipping", "Total", "Category", "GL code", "Status", "Confidence %", "Issues"], rows,
          money_cols=(9, 10, 11, 12), widths={"File": 34, "Vendor": 28, "Category": 24, "Invoice #": 18})

    ws2 = wb.create_sheet("Line items")
    rows = []
    for d in body.documents:
        for it in d.get("line_items", []):
            rows.append([fv(d, "vendor"), fv(d, "invoice_number"), it.get("description"), it.get("quantity"),
                         it.get("unit_price"), it.get("amount"), it.get("category"), it.get("gl_code"),
                         round((it.get("confidence") or 0) * 100, 1)])
    sheet(ws2, ["Vendor", "Invoice #", "Description", "Qty", "Unit price", "Amount", "Category", "GL code", "Cat. conf %"],
          rows, money_cols=(5, 6), widths={"Description": 46, "Vendor": 28, "Category": 24})

    ws3 = wb.create_sheet("Validation")
    rows = [[d.get("file_name"), c["title"], c["status"].upper(), c["detail"]]
            for d in body.documents for c in d.get("checks", [])]
    sheet(ws3, ["File", "Check", "Result", "Detail"], rows, widths={"File": 34, "Check": 40, "Detail": 70})
    colors = {"PASS": "DCFCE7", "WARN": "FEF3C7", "FAIL": "FEE2E2"}
    for row in ws3.iter_rows(min_row=2, min_col=3, max_col=3):
        for c in row:
            c.fill = PatternFill("solid", fgColor=colors.get(c.value, "FFFFFF"))

    ws4 = wb.create_sheet("Spend by category")
    agg = {}
    for d in body.documents:
        cat = (d.get("category") or {}).get("category") or "Uncategorised"
        agg[cat] = agg.get(cat, 0) + (fv(d, "total") or 0)
    sheet(ws4, ["Category", "GL code", "Total spend"],
          [[k, CATEGORIES.get(k, {}).get("gl"), round(v, 2)] for k, v in sorted(agg.items(), key=lambda t: -t[1])],
          money_cols=(3,), widths={"Category": 28})

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="ledgerlens-export.xlsx"'})


# serve the built frontend when running as a single server
import os as _os
from fastapi.staticfiles import StaticFiles as _Static

_DIST = _os.path.join(_os.path.dirname(__file__), "..", "..", "frontend", "dist")
if _os.path.isdir(_DIST):
    app.mount("/", _Static(directory=_DIST, html=True), name="web")
