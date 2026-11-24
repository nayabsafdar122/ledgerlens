// Copies the Tesseract OCR engine + English model into public/ocr so OCR runs fully self-hosted
// (no third-party CDN at runtime). Executed automatically before `vite build`.
import { cpSync, mkdirSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const nm = join(root, 'node_modules')
const out = join(root, 'public', 'ocr')
mkdirSync(join(out, 'core'), { recursive: true })
mkdirSync(join(out, 'lang'), { recursive: true })

cpSync(join(nm, 'tesseract.js/dist/worker.min.js'), join(out, 'worker.min.js'))
for (const f of ['tesseract-core-lstm.wasm.js', 'tesseract-core-lstm.wasm', 'tesseract-core-simd-lstm.wasm.js', 'tesseract-core-simd-lstm.wasm']) {
  cpSync(join(nm, 'tesseract.js-core', f), join(out, 'core', f))
}
const lang = join(nm, '@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz')
cpSync(existsSync(lang) ? lang : join(nm, '@tesseract.js-data/eng/4.0.0/eng.traineddata.gz'), join(out, 'lang', 'eng.traineddata.gz'))
console.log('OCR assets copied to public/ocr')
