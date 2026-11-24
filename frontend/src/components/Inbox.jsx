import { useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, FileText, Image as ImageIcon, Loader2, Sparkles, Trash2, UploadCloud, XCircle, Download } from 'lucide-react'
import { SAMPLES, fmtDate, fmtMoney } from '../api'

export const STATUS = {
  auto_approved: { label: 'Auto-approved', cls: 'ok', icon: CheckCircle2 },
  approved: { label: 'Approved', cls: 'ok', icon: CheckCircle2 },
  needs_review: { label: 'Needs review', cls: 'warn', icon: AlertTriangle },
  flagged: { label: 'Flagged', cls: 'bad', icon: XCircle },
}

export function StatusPill({ status }) {
  const s = STATUS[status] || STATUS.needs_review
  return <span className={`pill ${s.cls}`}><s.icon size={13} /> {s.label}</span>
}

export function ConfBar({ value }) {
  const pct = Math.round((value || 0) * 100)
  const cls = pct >= 90 ? 'hi' : pct >= 75 ? 'mid' : 'lo'
  return (
    <span className={`conf ${cls}`} title={`${pct}% confidence`}>
      <span className="conf-track"><span style={{ width: `${pct}%` }} /></span>
      <span className="mono">{pct}%</span>
    </span>
  )
}

export function CategoryChip({ category, colors }) {
  if (!category) return <span className="muted">—</span>
  const c = colors?.[category.category] || '#64748b'
  return (
    <span className="cat" style={{ '--c': c }}>
      <i /> {category.category}
    </span>
  )
}

export default function Inbox({ docs, onFiles, onSamples, onOpen, onRemove, onExport, model }) {
  const input = useRef(null)
  const [drag, setDrag] = useState(false)
  const colors = Object.fromEntries((model?.categories || []).map((c) => [c.name, c.color]))
  const done = docs.filter((d) => d.state === 'done')

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Document inbox</h1>
          <p>Drop invoices, receipts or scanned bills. LedgerLens reads them, pulls out the key fields and line items, checks the math, and sorts them into accounting categories.</p>
        </div>
        {done.length > 0 && (
          <button className="btn primary" onClick={onExport}><Download size={16} /> Export {done.length} to Excel</button>
        )}
      </header>

      <div
        className={`drop ${drag ? 'drag' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files) }}
        onClick={() => input.current?.click()}
      >
        <input ref={input} type="file" hidden multiple accept=".pdf,image/png,image/jpeg,image/webp"
          onChange={(e) => { onFiles(e.target.files); e.target.value = '' }} />
        <div className="drop-icon"><UploadCloud size={28} /></div>
        <div className="drop-title">Drop documents here or <u>browse</u></div>
        <div className="drop-sub">PDF, PNG or JPG · digital PDFs and photos/scans (OCR) · batch upload supported</div>
      </div>

      <div className="samples">
        <span className="samples-label"><Sparkles size={15} /> No invoices handy? Try the samples:</span>
        <button className="btn accent" onClick={() => onSamples(SAMPLES)}>Process all {SAMPLES.length} samples</button>
        {SAMPLES.map((s) => (
          <button key={s.file} className="chip" onClick={() => onSamples([s])}>
            {s.file.endsWith('.pdf') ? <FileText size={13} /> : <ImageIcon size={13} />} {s.label}
          </button>
        ))}
      </div>

      <div className="card table-card">
        {docs.length === 0 ? (
          <div className="empty">
            <FileText size={34} />
            <h3>No documents yet</h3>
            <p>Processed documents will appear here with their extracted data, category and validation status.</p>
          </div>
        ) : (
          <table className="docs">
            <thead>
              <tr>
                <th>Document</th><th>Vendor</th><th>Invoice #</th><th>Date</th><th className="r">Total</th>
                <th>Category</th><th>Confidence</th><th>Status</th><th />
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => {
                const r = d.result
                const f = r?.fields || {}
                const busy = d.state !== 'done' && d.state !== 'error'
                return (
                  <tr key={d.id} className={d.state === 'done' ? 'clickable' : ''} onClick={() => d.state === 'done' && onOpen(d.id)}>
                    <td>
                      <div className="doc-name">
                        <span className="doc-ico">{/\.pdf$/i.test(d.name) ? <FileText size={15} /> : <ImageIcon size={15} />}</span>
                        <div>
                          <div className="fname">{d.name}</div>
                          <div className="fmeta">
                            {r ? `${r.document_type.type} · ${r.source === 'ocr' ? 'OCR' : 'Digital PDF'} · ${d.totalMs ? (d.totalMs / 1000).toFixed(1) + 's' : ''}` : d.step}
                          </div>
                        </div>
                      </div>
                    </td>
                    {busy ? (
                      <td colSpan={7}><span className="processing"><Loader2 size={14} className="spin" /> {d.step}…</span></td>
                    ) : d.state === 'error' ? (
                      <td colSpan={7}><span className="err-text">{d.step}</span></td>
                    ) : (
                      <>
                        <td className="strong">{f.vendor?.value || '—'}</td>
                        <td className="mono">{f.invoice_number?.value || '—'}</td>
                        <td>{fmtDate(f.invoice_date?.value)}</td>
                        <td className="r mono strong">{fmtMoney(f.total?.value, r.currency)}</td>
                        <td><CategoryChip category={r.category} colors={colors} /></td>
                        <td><ConfBar value={r.confidence} /></td>
                        <td><StatusPill status={r.status} /></td>
                      </>
                    )}
                    <td className="r">
                      <button className="icon-btn" title="Remove" onClick={(e) => { e.stopPropagation(); onRemove(d.id) }}><Trash2 size={15} /></button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
