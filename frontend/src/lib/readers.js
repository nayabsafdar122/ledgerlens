// In-browser document reading. Files never leave the device except as positioned text
// sent to the extraction API.
//  - Digital PDFs: pdf.js text layer (exact positions)
//  - Images & scanned PDFs: Tesseract OCR (self-hosted WASM, see scripts/copy-ocr-assets.mjs)
import * as pdfjs from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { createWorker } from 'tesseract.js'

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker

const PREVIEW_SCALE = 1.6
let ocrWorkerPromise = null

function getOcrWorker(onProgress) {
  if (!ocrWorkerPromise) {
    ocrWorkerPromise = createWorker('eng', 1, {
      workerPath: '/ocr/worker.min.js',
      corePath: '/ocr/core',
      langPath: '/ocr/lang',
      gzip: true,
      logger: (m) => window.__ocrProgress && window.__ocrProgress(m),
    })
  }
  window.__ocrProgress = onProgress
  return ocrWorkerPromise
}

async function ocrImage(source, onProgress) {
  const worker = await getOcrWorker((m) => {
    if (m.status === 'recognizing text') onProgress?.(`Running OCR ${Math.round(m.progress * 100)}%`)
    else if (m.status) onProgress?.(m.status.replace(/^\w/, (c) => c.toUpperCase()))
  })
  const { data } = await worker.recognize(source, {}, { blocks: true, text: true })
  const words = []
  for (const b of data.blocks || [])
    for (const p of b.paragraphs || [])
      for (const l of p.lines || [])
        for (const w of l.words || []) {
          if (!w.text.trim() || w.confidence < 20) continue
          words.push({ text: w.text, x0: w.bbox.x0, y0: w.bbox.y0, x1: w.bbox.x1, y1: w.bbox.y1 })
        }
  return { words, confidence: data.confidence }
}

function canvasFor(viewport) {
  const c = document.createElement('canvas')
  c.width = Math.ceil(viewport.width)
  c.height = Math.ceil(viewport.height)
  return c
}

export async function readPdf(file, onProgress) {
  onProgress?.('Reading PDF')
  const pdf = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise
  const pages = []
  const images = []
  let usedOcr = false
  const ocrConf = []
  for (let n = 1; n <= Math.min(pdf.numPages, 5); n++) {
    const page = await pdf.getPage(n)
    const vp = page.getViewport({ scale: 1 })
    const content = await page.getTextContent()
    const words = []
    for (const it of content.items) {
      const str = it.str
      if (!str || !str.trim()) continue
      const [, , c, d, e, f] = it.transform
      const h = Math.hypot(c, d) || it.height || 10
      const [vx, vy] = vp.convertToViewportPoint(e, f)
      const charW = (it.width || str.length * h * 0.5) / str.length
      let offset = 0
      for (const token of str.split(/(\s+)/)) {
        if (token.trim()) {
          const x0 = vx + offset * charW
          words.push({ text: token, x0, y0: vy - h * 0.8, x1: x0 + token.length * charW, y1: vy + h * 0.2 })
        }
        offset += token.length
      }
    }
    // preview image
    const pvp = page.getViewport({ scale: PREVIEW_SCALE })
    const canvas = canvasFor(pvp)
    await page.render({ canvasContext: canvas.getContext('2d'), viewport: pvp }).promise
    images.push(canvas.toDataURL('image/jpeg', 0.9))

    if (words.length < 8) {
      // scanned page: OCR the rendered image, then map back to PDF units
      usedOcr = true
      const ocr = await ocrImage(canvas, onProgress)
      ocrConf.push(ocr.confidence)
      const s = 1 / PREVIEW_SCALE
      pages.push({ width: vp.width, height: vp.height,
        words: ocr.words.map((w) => ({ ...w, x0: w.x0 * s, y0: w.y0 * s, x1: w.x1 * s, y1: w.y1 * s })) })
    } else {
      pages.push({ width: vp.width, height: vp.height, words })
    }
  }
  return {
    pages, images,
    source: usedOcr ? 'ocr' : 'pdf-text',
    ocr_confidence: ocrConf.length ? ocrConf.reduce((a, b) => a + b, 0) / ocrConf.length : null,
    numPages: pdf.numPages,
  }
}

export async function readImage(file, onProgress) {
  onProgress?.('Loading image')
  const url = URL.createObjectURL(file)
  const img = await new Promise((res, rej) => {
    const i = new Image()
    i.onload = () => res(i)
    i.onerror = rej
    i.src = url
  })
  // upscale small photos for better OCR
  const scale = img.naturalWidth < 1200 ? 1600 / img.naturalWidth : 1
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(img.naturalWidth * scale)
  canvas.height = Math.round(img.naturalHeight * scale)
  const ctx = canvas.getContext('2d')
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  onProgress?.('Starting OCR engine')
  const ocr = await ocrImage(canvas, onProgress)
  const s = 1 / scale
  URL.revokeObjectURL(url)
  return {
    pages: [{ width: img.naturalWidth, height: img.naturalHeight,
      words: ocr.words.map((w) => ({ ...w, x0: w.x0 * s, y0: w.y0 * s, x1: w.x1 * s, y1: w.y1 * s })) }],
    images: [canvas.toDataURL('image/jpeg', 0.88)],
    source: 'ocr',
    ocr_confidence: ocr.confidence,
    numPages: 1,
  }
}

export function readDocument(file, onProgress) {
  const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name)
  return isPdf ? readPdf(file, onProgress) : readImage(file, onProgress)
}
