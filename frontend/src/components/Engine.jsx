import { Binary, Brain, FileScan, ListChecks, ScanText, Table2, Tags } from 'lucide-react'

const STEPS = [
  { icon: FileScan, title: 'Read', text: 'pdf.js text layer for digital PDFs; Tesseract OCR (WebAssembly, runs in your browser) for photos and scans.' },
  { icon: ScanText, title: 'Layout', text: 'Words are rebuilt into lines and column segments from their coordinates, so labels and values pair up correctly in any layout.' },
  { icon: Binary, title: 'Key fields', text: 'The engine finds labels, reads candidate values to the right of or below them, checks each value\'s type, and gives every field a confidence score with its location on the page.' },
  { icon: Table2, title: 'Tables', text: 'It detects the header row, works out the columns, and reads each line item. Receipts without a table header use a fallback parser.' },
  { icon: Tags, title: 'Classify', text: 'ML models tag each line item with an expense category and GL code, and identify the document type.' },
  { icon: ListChecks, title: 'Validate', text: 'It checks the arithmetic, tax rate and dates, catches duplicates, and flags amounts unusual for that vendor, then decides whether to auto-approve.' },
]

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><b className="mono">{value}</b></div>
}

export default function Engine({ model }) {
  const e = model?.expense_classifier
  const d = model?.doctype_classifier
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>AI engine</h1><p>How LedgerLens turns a document into clean, validated accounting data, without sending files to a third-party AI service.</p></div>
      </header>

      <div className="pipeline">
        {STEPS.map((s, i) => (
          <div key={s.title} className="step card">
            <div className="step-n">{String(i + 1).padStart(2, '0')}</div>
            <s.icon size={20} />
            <h4>{s.title}</h4>
            <p>{s.text}</p>
          </div>
        ))}
      </div>

      <div className="dash-grid">
        <div className="card">
          <div className="card-head"><h3><Brain size={16} /> Expense categoriser</h3></div>
          {e ? (
            <>
              <p className="muted small">{e.model}. Evaluated on {e.eval}.</p>
              <div className="metrics">
                <Metric label="Accuracy" value={`${(e.accuracy * 100).toFixed(1)}%`} />
                <Metric label="Macro F1" value={e.macro_f1.toFixed(3)} />
                <Metric label="Classes" value={e.classes} />
                <Metric label="Train / test" value={`${e.n_train.toLocaleString()} / ${e.n_test}`} />
              </div>
            </>
          ) : <p className="muted">Loading…</p>}
        </div>
        <div className="card">
          <div className="card-head"><h3><ScanText size={16} /> Document-type classifier</h3></div>
          {d ? (
            <>
              <p className="muted small">{d.model}. Invoice, receipt, utility bill, purchase order or credit note.</p>
              <div className="metrics">
                <Metric label="Accuracy" value={`${(d.accuracy * 100).toFixed(1)}%`} />
                <Metric label="Macro F1" value={d.macro_f1.toFixed(3)} />
                <Metric label="Classes" value={d.classes} />
                <Metric label="Train / test" value={`${d.n_train.toLocaleString()} / ${d.n_test}`} />
              </div>
            </>
          ) : <p className="muted">Loading…</p>}
        </div>
        <div className="card span2">
          <div className="card-head"><h3><Tags size={16} /> Chart of accounts mapping</h3></div>
          <div className="coa">
            {(model?.categories || []).map((c) => (
              <div key={c.name} className="coa-item"><i style={{ background: c.color }} /><span>{c.name}</span><b className="mono">GL {c.gl_code}</b></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
