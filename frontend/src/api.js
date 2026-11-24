const BASE = import.meta.env.VITE_API_URL || ''

async function json(res) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || res.statusText)
  return data
}

export const api = {
  model: () => fetch(`${BASE}/api/model`).then(json),
  extract: (payload) =>
    fetch(`${BASE}/api/extract`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(json),
  exportXlsx: async (documents) => {
    const res = await fetch(`${BASE}/api/export`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ documents }),
    })
    if (!res.ok) throw new Error('Export failed')
    return res.blob()
  },
}

export const SAMPLES = [
  { file: 'nimbus-cloud-invoice.pdf', label: 'Cloud services invoice' },
  { file: 'atlas-office-supply-invoice.pdf', label: 'Office supplies (PO)' },
  { file: 'brightpath-marketing-invoice.pdf', label: 'Marketing agency' },
  { file: 'cascade-energy-bill.pdf', label: 'Utility bill' },
  { file: 'skyline-travel-invoice.pdf', label: 'Travel (EUR, VAT)' },
  { file: 'metro-catering-invoice.pdf', label: 'Catering (has an error)' },
  { file: 'corner-bean-receipt.png', label: 'Photo receipt (OCR)' },
  { file: 'atlas-office-supply-duplicate.pdf', label: 'Duplicate invoice' },
]

export function fmtMoney(v, cur = 'USD') {
  if (v === null || v === undefined || v === '') return '—'
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: cur || 'USD' }).format(v)
  } catch {
    return Number(v).toFixed(2)
  }
}

export function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso + 'T00:00:00')
  return isNaN(d) ? iso : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
