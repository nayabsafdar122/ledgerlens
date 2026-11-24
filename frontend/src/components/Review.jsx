import { useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, CheckCircle2, AlertTriangle, XCircle, Download, Eye, EyeOff, ScanText, Mail, Phone, Hash, Clock } from 'lucide-react'
import { fmtDate, fmtMoney } from '../api'
import { CategoryChip, ConfBar, StatusPill } from './Inbox'

const FIELD_COLORS = {
  vendor: '#7c3aed', invoice_number: '#2563eb', invoice_date: '#0891b2', due_date: '#0d9488', po_number: '#4f46e5',
  bill_to: '#64748b', subtotal: '#ca8a04', discount: '#db2777', tax: '#ea580c', shipping: '#9333ea', total: '#16a34a',
}
const MONEY = new Set(['subtotal', 'discount', 'tax', 'shipping', 'total'])
const DATES = new Set(['invoice_date', 'due_date'])
const CHECK_ICON = { pass: CheckCircle2, warn: AlertTriangle, fail: XCircle }

function Box({ b, page, color, active, label }) {
  if (!b) return null
  const s = {
    left: `${(b.x0 / page.width) * 100}%`, top: `${(b.y0 / page.height) * 100}%`,
    width: `${((b.x1 - b.x0) / page.width) * 100}%`, height: `${((b.y1 - b.y0) / page.height) * 100}%`, '--c': color,
  }
  return <div className={`hl ${active ? 'on' : ''}`} style={s}>{active && label ? <span>{label}</span> : null}</div>
}

function FieldValue({ k, f, currency, onChange }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState('')
  const display = !f ? '—' : MONEY.has(k) ? fmtMoney(f.value, currency) : DATES.has(k) ? fmtDate(f.value) : f.value
  if (editing) {
    return (
      <form className="edit" onSubmit={(e) => {
        e.preventDefault()
        onChange(MONEY.has(k) ? parseFloat(val) : val)
        setEditing(false)
      }}>
        <input autoFocus value={val} type={DATES.has(k) ? 'date' : MONEY.has(k) ? 'number' : 'text'} step="0.01"
          onChange={(e) => setVal(e.target.value)} onBlur={() => setEditing(false)} />
      </form>
    )
  }
  return (
    <button className={`fval ${!f ? 'missing' : ''}`} title="Click to edit" onClick={() => { setVal(f?.value ?? ''); setEditing(true) }}>
      {display}{f?.edited && <em>edited</em>}{f?.inferred && <em>inferred</em>}
    </button>
  )
}

export default function Review({ doc, docs, onField, onStatus, onExport, onNavigate }) {
  const r = doc.result
  const [hover, setHover] = useState(null)
  const [showAll, setShowAll] = useState(true)
  const idx = docs.findIndex((d) => d.id === doc.id)

  if (!r) {
    return <div className="page"><div className="card empty"><p>{doc.step}…</p></div></div>
  }
  const pages = r.page_sizes
  const fields = r.fields
  const cur = r.currency
  const itemsTotal = r.line_items.reduce((a, b) => a + (b.amount || 0), 0)
  const counts = r.checks.reduce((a, c) => ({ ...a, [c.status]: (a[c.status] || 0) + 1 }), {})

  return (
    <div className="page review">
      <header className="review-head">
        <div className="rh-left">
          <div className="rh-title">
            <h1>{fields.vendor?.value || doc.name}</h1>
            <StatusPill status={r.status} />
          </div>
          <div className="rh-meta">
            <span><ScanText size={14} /> {r.document_type.type} <b>{Math.round(r.document_type.confidence * 100)}%</b></span>
            <span>{doc.name}</span>
            <span>{r.source === 'ocr' ? 'OCR' : 'Digital PDF'} · {r.processing_ms} ms AI · {(doc.totalMs / 1000).toFixed(1)} s total</span>
          </div>
        </div>
        <div className="rh-actions">
          <button className="icon-btn bordered" disabled={idx <= 0} onClick={() => onNavigate(docs[idx - 1].id)} title="Previous"><ArrowLeft size={16} /></button>
          <span className="muted small">{idx + 1} / {docs.length}</span>
          <button className="icon-btn bordered" disabled={idx >= docs.length - 1} onClick={() => onNavigate(docs[idx + 1].id)} title="Next"><ArrowRight size={16} /></button>
          <button className="btn ghost" onClick={() => onExport(doc)}><Download size={15} /> Excel</button>
          <button className="btn primary" disabled={r.status === 'approved'} onClick={() => onStatus(doc.id, 'approved')}>
            <Check size={16} /> {r.status === 'approved' ? 'Approved' : 'Approve'}
          </button>
        </div>
      </header>

      <div className="review-grid">
        <section className="viewer card">
          <div className="viewer-bar">
            <span className="muted small">Hover a field to see where the AI found it</span>
            <button className="btn tiny ghost" onClick={() => setShowAll(!showAll)}>
              {showAll ? <EyeOff size={14} /> : <Eye size={14} />} {showAll ? 'Hide' : 'Show'} detections
            </button>
          </div>
          <div className="pages">
            {(doc.images || []).map((src, pi) => (
              <div className="page-img" key={pi}>
                <img src={src} alt={`Page ${pi + 1}`} />
                {r.field_order.map((k) => fields[k]?.bbox?.page === pi && (showAll || hover === k) && (
                  <Box key={k} b={fields[k].bbox} page={pages[pi]} color={FIELD_COLORS[k]} active={hover === k} label={r.field_labels[k]} />
                ))}
                {r.line_items.map((it, i) => it.bbox?.page === pi && (showAll || hover === `item-${i}`) && (
                  <Box key={`it${i}`} b={it.bbox} page={pages[pi]} color="#0f3d3e" active={hover === `item-${i}`} />
                ))}
              </div>
            ))}
          </div>
        </section>

        <section className="panel-r">
          <div className="card">
            <div className="card-head">
              <h3>Extracted fields</h3>
              <CategoryChip category={r.category} colors={{ [r.category?.category]: '#0f766e' }} />
            </div>
            <div className="fields">
              {r.field_order.map((k) => {
                const f = fields[k]
                if (!f && ['discount', 'shipping', 'po_number'].includes(k)) return null
                if (!f && r.document_type.type === 'Receipt' && ['due_date', 'bill_to'].includes(k)) return null
                return (
                  <div key={k} className={`frow ${hover === k ? 'hover' : ''}`} onMouseEnter={() => setHover(k)} onMouseLeave={() => setHover(null)}>
                    <span className="fdot" style={{ background: FIELD_COLORS[k] }} />
                    <span className="flabel">{r.field_labels[k]}</span>
                    <FieldValue k={k} f={f} currency={cur} onChange={(v) => onField(doc.id, k, v)} />
                    {f ? <ConfBar value={f.confidence} /> : <span className="pill bad tiny">missing</span>}
                  </div>
                )
              })}
            </div>
            {r.category && (
              <div className="gl">
                Suggested ledger account <b className="mono">GL {r.category.gl_code}</b> · {r.category.category}
                <span className="muted"> ({Math.round(r.category.confidence * 100)}% · alt: {r.category.alternatives.slice(1).map((a) => a.category).join(', ')})</span>
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-head">
              <h3>Line items <span className="muted">· {r.line_items.length}</span></h3>
              <span className="muted small">Σ {fmtMoney(itemsTotal, cur)}</span>
            </div>
            <table className="items">
              <thead><tr><th>Description</th><th className="r">Qty</th><th className="r">Unit</th><th className="r">Amount</th><th>Category</th></tr></thead>
              <tbody>
                {r.line_items.map((it, i) => (
                  <tr key={i} onMouseEnter={() => setHover(`item-${i}`)} onMouseLeave={() => setHover(null)} className={hover === `item-${i}` ? 'hover' : ''}>
                    <td>{it.description}</td>
                    <td className="r mono">{it.quantity}</td>
                    <td className="r mono">{fmtMoney(it.unit_price, cur)}</td>
                    <td className="r mono strong">{fmtMoney(it.amount, cur)}</td>
                    <td><span className="mini-cat" title={`${Math.round(it.confidence * 100)}% · GL ${it.gl_code}`}>{it.category}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <div className="card-head">
              <h3>Validation</h3>
              <span className="check-sum">
                <b className="ok">{counts.pass || 0} passed</b>{counts.warn ? <b className="warn">{counts.warn} warning</b> : null}{counts.fail ? <b className="bad">{counts.fail} failed</b> : null}
              </span>
            </div>
            <ul className="checks">
              {r.checks.map((c) => {
                const I = CHECK_ICON[c.status]
                return (
                  <li key={c.id} className={c.status}>
                    <I size={16} />
                    <div><div className="ct">{c.title}</div><div className="cd">{c.detail}</div></div>
                  </li>
                )
              })}
            </ul>
          </div>

          <div className="card details">
            {r.contacts.email && <span><Mail size={13} /> {r.contacts.email}</span>}
            {r.contacts.phone && <span><Phone size={13} /> {r.contacts.phone}</span>}
            {r.contacts.tax_id && <span><Hash size={13} /> Tax ID {r.contacts.tax_id}</span>}
            {r.contacts.payment_terms && <span><Clock size={13} /> {r.contacts.payment_terms}</span>}
            <span>Currency {cur}</span>
            <span>Overall confidence <b>{Math.round(r.confidence * 100)}%</b></span>
          </div>
        </section>
      </div>
    </div>
  )
}
