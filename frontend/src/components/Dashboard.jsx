import { AlertTriangle, CheckCircle2, Clock, Download, FileStack, Wallet, XCircle } from 'lucide-react'
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { SAMPLES, fmtMoney } from '../api'
import { StatusPill } from './Inbox'

const TT = { contentStyle: { borderRadius: 10, border: '1px solid #e5e7eb', fontSize: 12, boxShadow: '0 8px 24px #0f172a14' } }

export default function Dashboard({ docs, model, onOpen, onExport, onSamples }) {
  if (!docs.length) {
    return (
      <div className="page">
        <header className="page-head"><div><h1>Spend insights</h1><p>Analytics across every processed document.</p></div></header>
        <div className="card empty">
          <FileStack size={34} />
          <h3>Nothing to analyse yet</h3>
          <p>Process a few documents to see spend by category and vendor, how many were auto-approved, and the issues it caught.</p>
          <button className="btn accent" onClick={() => onSamples(SAMPLES)}>Process the sample batch</button>
        </div>
      </div>
    )
  }
  const colors = Object.fromEntries((model?.categories || []).map((c) => [c.name, c.color]))
  const usd = docs.filter((d) => d.result.currency === 'USD')
  const other = docs.filter((d) => d.result.currency !== 'USD')
  const total = (d) => d.result.fields.total?.value || 0
  const spend = usd.reduce((a, d) => a + total(d), 0)

  const byCat = {}
  usd.forEach((d) => {
    const c = d.result.category?.category || 'Uncategorised'
    byCat[c] = (byCat[c] || 0) + total(d)
  })
  const catData = Object.entries(byCat).map(([name, value]) => ({ name, value: Math.round(value * 100) / 100 })).sort((a, b) => b.value - a.value)

  const byVendor = {}
  usd.forEach((d) => {
    const v = d.result.fields.vendor?.value || 'Unknown'
    byVendor[v] = (byVendor[v] || 0) + total(d)
  })
  const vendorData = Object.entries(byVendor).map(([name, value]) => ({ name, value: Math.round(value) })).sort((a, b) => b.value - a.value).slice(0, 8)

  const st = (s) => docs.filter((d) => d.result.status === s).length
  const auto = st('auto_approved') + st('approved')
  const flagged = st('flagged')
  const review = st('needs_review')
  const minutes = docs.length * (model?.minutes_saved_per_doc || 6.5)
  const issues = docs.filter((d) => ['flagged', 'needs_review'].includes(d.result.status))
  const avgConf = docs.reduce((a, d) => a + d.result.confidence, 0) / docs.length

  const kpis = [
    { icon: FileStack, label: 'Documents processed', value: docs.length, sub: `${Math.round(avgConf * 100)}% avg. confidence` },
    { icon: Wallet, label: 'Spend captured (USD)', value: fmtMoney(spend, 'USD'), sub: other.length ? `+ ${other.length} doc(s) in other currencies` : 'across all vendors' },
    { icon: CheckCircle2, label: 'Straight-through rate', value: `${Math.round((auto / docs.length) * 100)}%`, sub: `${auto} auto-approved, ${review} to review` },
    { icon: XCircle, label: 'Issues caught', value: flagged, sub: 'math errors, duplicates, missing data', tone: flagged ? 'bad' : '' },
    { icon: Clock, label: 'Manual work saved', value: minutes >= 60 ? `${(minutes / 60).toFixed(1)} h` : `${Math.round(minutes)} min`, sub: `≈ ${model?.minutes_saved_per_doc || 6.5} min per document` },
  ]

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Spend insights</h1><p>Live analytics across {docs.length} processed document{docs.length > 1 ? 's' : ''}.</p></div>
        <button className="btn primary" onClick={onExport}><Download size={16} /> Export to Excel</button>
      </header>

      <div className="kpis">
        {kpis.map((k) => (
          <div key={k.label} className={`kpi card ${k.tone || ''}`}>
            <div className="kpi-ico"><k.icon size={17} /></div>
            <div className="kpi-label">{k.label}</div>
            <div className="kpi-value">{k.value}</div>
            <div className="kpi-sub">{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="dash-grid">
        <div className="card">
          <div className="card-head"><h3>Spend by category</h3><span className="muted small">USD · AI-categorised</span></div>
          <div className="donut-wrap">
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie data={catData} dataKey="value" nameKey="name" innerRadius={62} outerRadius={100} paddingAngle={2} stroke="none">
                  {catData.map((c) => <Cell key={c.name} fill={colors[c.name] || '#94a3b8'} />)}
                </Pie>
                <Tooltip {...TT} formatter={(v) => fmtMoney(v, 'USD')} />
              </PieChart>
            </ResponsiveContainer>
            <ul className="legend">
              {catData.map((c) => (
                <li key={c.name}><i style={{ background: colors[c.name] }} /> <span>{c.name}</span> <b className="mono">{fmtMoney(c.value, 'USD')}</b> <em>{Math.round((c.value / spend) * 100)}%</em></li>
              ))}
            </ul>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3>Top vendors</h3><span className="muted small">USD</span></div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={vendorData} layout="vertical" margin={{ left: 10, right: 20 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={170} tick={{ fontSize: 12, fill: '#334155' }} axisLine={false} tickLine={false} />
              <Tooltip {...TT} cursor={{ fill: '#f1f5f9' }} formatter={(v) => fmtMoney(v, 'USD')} />
              <Bar dataKey="value" fill="#0f3d3e" radius={[0, 6, 6, 0]} barSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card span2">
          <div className="card-head"><h3>Exceptions queue</h3><span className="muted small">{issues.length} document(s) need attention</span></div>
          {issues.length === 0 ? <p className="muted">Everything reconciled, so no exceptions.</p> : (
            <ul className="exceptions">
              {issues.map((d) => {
                const bad = d.result.checks.filter((c) => c.status !== 'pass')
                return (
                  <li key={d.id} onClick={() => onOpen(d.id)}>
                    <AlertTriangle size={16} className={d.result.status === 'flagged' ? 'bad' : 'warn'} />
                    <div className="ex-main">
                      <b>{d.result.fields.vendor?.value}</b> <span className="mono muted">{d.result.fields.invoice_number?.value}</span>
                      <div className="muted small">{bad.map((c) => `${c.title}: ${c.detail}`).join(' · ')}</div>
                    </div>
                    <span className="mono">{fmtMoney(total(d), d.result.currency)}</span>
                    <StatusPill status={d.result.status} />
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
