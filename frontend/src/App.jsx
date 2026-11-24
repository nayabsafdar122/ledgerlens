import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BarChart3, Cpu, FileSearch, Inbox as InboxIcon, Lock, ScanLine } from 'lucide-react'
import { api } from './api'
import { readDocument } from './lib/readers'
import Inbox from './components/Inbox'
import Review from './components/Review'
import Dashboard from './components/Dashboard'
import Engine from './components/Engine'

let seq = 0

function summary(d) {
  const f = d.result?.fields || {}
  return {
    file: d.name, vendor: f.vendor?.value || '', invoice_number: f.invoice_number?.value || '',
    total: f.total?.value ?? null, invoice_date: f.invoice_date?.value || null,
  }
}

export default function App() {
  const [docs, setDocs] = useState([])
  const [view, setView] = useState('inbox')
  const [selected, setSelected] = useState(null)
  const [model, setModel] = useState(null)
  const [apiError, setApiError] = useState(null)
  const queue = useRef(Promise.resolve())
  const docsRef = useRef(docs)
  docsRef.current = docs

  useEffect(() => {
    api.model().then(setModel).catch((e) => setApiError(`Can't reach the LedgerLens API (${e.message}).`))
  }, [])

  const patch = (id, p) => setDocs((ds) => ds.map((d) => (d.id === id ? { ...d, ...(typeof p === 'function' ? p(d) : p) } : d)))

  const process = useCallback((file) => {
    const id = `doc-${++seq}`
    setDocs((ds) => [{ id, name: file.name, size: file.size, state: 'queued', step: 'Queued', addedAt: Date.now() }, ...ds])
    // sequential queue: duplicates are checked against everything processed before
    queue.current = queue.current.then(async () => {
      const t0 = performance.now()
      try {
        patch(id, { state: 'reading', step: 'Reading document' })
        const read = await readDocument(file, (step) => patch(id, { step }))
        patch(id, { state: 'extracting', step: 'AI extraction', images: read.images, pages: read.pages })
        const history = docsRef.current.filter((d) => d.state === 'done' && d.id !== id).map(summary)
        const result = await api.extract({
          file_name: file.name, source: read.source, ocr_confidence: read.ocr_confidence, pages: read.pages, history,
        })
        patch(id, { state: 'done', step: 'Done', result, totalMs: Math.round(performance.now() - t0) })
      } catch (e) {
        patch(id, { state: 'error', step: e.message || 'Failed' })
      }
    })
    return id
  }, [])

  const addFiles = (files) => {
    const ids = [...files].map(process)
    if (files.length === 1) {
      setSelected(ids[0])
    }
  }

  const loadSamples = async (list) => {
    for (const s of list) {
      const blob = await fetch(`/samples/${s.file}`).then((r) => r.blob())
      process(new File([blob], s.file, { type: blob.type || (s.file.endsWith('.pdf') ? 'application/pdf' : 'image/png') }))
    }
  }

  const updateField = (id, key, value) =>
    patch(id, (d) => ({
      result: { ...d.result, fields: { ...d.result.fields, [key]: { ...(d.result.fields[key] || {}), value, edited: true, confidence: 1 } } },
    }))

  const setStatus = (id, status) => patch(id, (d) => ({ result: { ...d.result, status } }))
  const remove = (id) => {
    setDocs((ds) => ds.filter((d) => d.id !== id))
    if (selected === id) setSelected(null)
  }

  const done = useMemo(() => docs.filter((d) => d.state === 'done'), [docs])
  const current = docs.find((d) => d.id === selected) || null

  const exportAll = async (list = done) => {
    const blob = await api.exportXlsx(list.map((d) => d.result))
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'ledgerlens-export.xlsx'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const open = (id) => {
    setSelected(id)
    setView('review')
  }

  const nav = [
    { key: 'inbox', label: 'Inbox', icon: InboxIcon, badge: docs.length || null },
    { key: 'review', label: 'Review', icon: FileSearch, disabled: !current },
    { key: 'dashboard', label: 'Spend insights', icon: BarChart3 },
    { key: 'engine', label: 'AI engine', icon: Cpu },
  ]

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <div className="brand-mark"><ScanLine size={18} strokeWidth={2.6} /></div>
          <div>
            <div className="brand-name">LedgerLens</div>
            <div className="brand-sub">Document AI</div>
          </div>
        </div>
        <nav>
          {nav.map((n) => (
            <button key={n.key} className={`nav ${view === n.key ? 'active' : ''}`} disabled={n.disabled}
              onClick={() => setView(n.key)}>
              <n.icon size={17} /> <span>{n.label}</span>
              {n.badge ? <em>{n.badge}</em> : null}
            </button>
          ))}
        </nav>
        <div className="side-foot">
          <Lock size={14} />
          <span>Files are read in your browser. Only extracted text is sent for analysis.</span>
        </div>
      </aside>

      <main className="main">
        {apiError && <div className="api-error">{apiError}</div>}
        {view === 'inbox' && (
          <Inbox docs={docs} onFiles={addFiles} onSamples={loadSamples} onOpen={open} onRemove={remove}
            onExport={() => exportAll()} model={model} />
        )}
        {view === 'review' && current && (
          <Review doc={current} docs={done} onField={updateField} onStatus={setStatus} onExport={(d) => exportAll([d])}
            onNavigate={open} />
        )}
        {view === 'dashboard' && <Dashboard docs={done} model={model} onOpen={open} onExport={() => exportAll()} onSamples={loadSamples} />}
        {view === 'engine' && <Engine model={model} />}
      </main>
    </div>
  )
}
