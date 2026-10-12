import { useEffect, useRef, useState } from 'react'
import { Camera, CheckCircle2, RefreshCw, X } from 'lucide-react'
import { readBarcodes, prepareZXingModule } from 'zxing-wasm/reader'
// The decoder's WebAssembly is named explicitly so the build carries it and serves it from our own
// origin. Left to itself the library asks for it next to the bundle, where it is not, and then every
// frame fails with nothing said.
import wasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url'

prepareZXingModule({ overrides: { locateFile: (path, prefix) => (path.endsWith('.wasm') ? wasmUrl : prefix + path) } })

// Reading the barcode on the back of a licence, live from the camera.
//
// A single photograph of a licence often will not decode - held at an angle, with a light across
// it, the bars smear. A camera does not have that problem: it gets a new frame every few
// hundredths of a second and only one of them has to be good. So this keeps reading frames until
// one comes back, which is why it succeeds where photographing the card and hoping does not.
//
// Nothing is uploaded and no frame is kept. What the barcode says goes to the applicant to check.

const OPTIONS = { formats: ['PDF417'], tryHarder: true, tryRotate: true, tryInvert: true,
  tryDownscale: true, maxNumberOfSymbols: 1 }

// The reader hands back the record either as bytes or as text with the control characters written
// out as <LF> and <CR> - and those characters are exactly what separates one field from the next.
function readable(hit) {
  if (hit.bytes?.length) return new TextDecoder().decode(new Uint8Array(hit.bytes))
  return (hit.text || '').replace(/<LF>/g, '\n').replace(/<CR>/g, '\r').replace(/<RS>/g, '\x1e')
}

// The AAMVA record, in the shape the licence dialog uses. The same parsing lives on the server for
// photographs that are uploaded rather than scanned; this is the copy the camera path uses.
const CLASSES = new Set(['A', 'B', 'C', 'D', 'E', 'M'])
const ENDORSEMENTS = new Set(['H', 'T', 'N', 'S', 'P', 'X'])

function aamvaDate(v) {
  if (!v || v.length !== 8 || !/^\d+$/.test(v)) return ''
  const head = Number(v.slice(0, 4))
  const [y, m, d] = head >= 1900 && head <= 2100
    ? [v.slice(0, 4), v.slice(4, 6), v.slice(6, 8)]
    : [v.slice(4, 8), v.slice(0, 2), v.slice(2, 4)]
  const iso = `${y}-${m}-${d}`
  return Number.isNaN(Date.parse(iso)) ? '' : iso
}

export function parseLicense(text) {
  const fields = {}
  // The record proper starts at the subfile marker - the "DL" immediately in front of the first
  // element. Everything before it is the header and its offsets, and the first element shares that
  // line with them.
  const start = /DL(?=[A-Z]{3})/.exec(text)
  for (const line of (start ? text.slice(start.index + 2) : text).split(/[\r\n]+/)) {
    const t = line.trim()
    if (t.length > 3 && /^[A-Z]{3}/.test(t)) fields[t.slice(0, 3)] ??= t.slice(3).trim()
  }
  if (!fields.DAQ) return null
  const klass = (fields.DCA || '').toUpperCase()
  const letter = [...klass].find((c) => CLASSES.has(c)) || (klass ? 'O' : '')
  const ends = /^(NONE|N\/A|NA|-)?$/.test((fields.DCD || '').trim().toUpperCase())
    ? []
    : [...new Set([...(fields.DCD || '').toUpperCase()].filter((c) => ENDORSEMENTS.has(c)))].sort()
  return {
    number: (fields.DAQ || '').toUpperCase(),
    state: (fields.DAJ || '').toUpperCase().slice(0, 2),
    classification: letter,
    endorsements: ends,
    issued: aamvaDate(fields.DBD),
    expires: aamvaDate(fields.DBA),
    name: [fields.DAC, fields.DAD, fields.DCS].filter(Boolean).join(' ').toUpperCase(),
  }
}

export default function LicenseScanner({ onRead, onClose, token }) {
  const video = useRef(null)
  const canvas = useRef(null)
  const photo = useRef(null)
  const [err, setErr] = useState(null)
  const [tries, setTries] = useState(0)
  const [size, setSize] = useState('')
  // A decoder that will not start is a silent failure otherwise: every frame throws and the dialog
  // sits there saying "Reading" for ever. The first fault is kept and shown.
  const [fault, setFault] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let stream = null
    let stop = false
    let timer = null

    const frame = async () => {
      if (stop) return
      const v = video.current
      if (v && v.videoWidth) {
        const c = canvas.current
        c.width = v.videoWidth
        c.height = v.videoHeight
        const ctx = c.getContext('2d', { willReadFrequently: true })
        ctx.drawImage(v, 0, 0)
        setSize(`${v.videoWidth}x${v.videoHeight}`)
        try {
          const frame = ctx.getImageData(0, 0, c.width, c.height)
          const hit = (await readBarcodes(frame, OPTIONS)).find((r) => r.text || r.bytes)
          if (hit) {
            const licence = parseLicense(readable(hit))
            if (licence) { stop = true; onRead(licence); return }
          }
        } catch (e) {
          // A frame that will not decode returns nothing; a throw means the decoder itself is unwell.
          setFault(String(e?.message || e))
        }
        setTries((n) => n + 1)
      }
      timer = setTimeout(frame, 250)
    }

    navigator.mediaDevices?.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1920 } } })
      .then((s) => {
        stream = s
        if (video.current) { video.current.srcObject = s; video.current.play() }
        frame()
      })
      .catch(() => setErr('The camera could not be opened. Take a photograph of the back of your license instead.'))

    return () => {
      stop = true
      if (timer) clearTimeout(timer)
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="backdrop">
      <div className="modal scanner" role="dialog" aria-modal="true" aria-label="Scan your license">
        <header>
          <h2>Scan Your License</h2>
          <button className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="body">
          {err ? <div className="notice bad">{err}</div> : (
            <>
              <p className="scanhow">
                Hold the <b>back</b> of your license flat inside the frame, filling it, with no glare
                across the barcode.
              </p>
              <div className="scanframe">
                <video ref={video} playsInline muted />
                <span className="scanguide" />
              </div>
              <p className="scanstate">
                {tries ? <><RefreshCw size={13} /> Reading… {tries} frames{size ? ` · ${size}` : ''}</>
                  : <><Camera size={13} /> Starting the camera…</>}
              </p>
              {fault && <div className="notice warn">The reader reported: {fault}</div>}
            </>
          )}
          <canvas ref={canvas} hidden />
        </div>
        <footer>
          <button type="button" onClick={onClose}>Type it instead</button>
          {/* A still photograph, read on the server, where it can be turned and cropped harder than
              a live frame is worth doing. */}
          <button type="button" disabled={busy} onClick={() => photo.current?.click()}>
            {busy ? 'Reading…' : 'Use a photo'}
          </button>
          <input ref={photo} type="file" accept="image/*" capture="environment" hidden
            onChange={async (e) => {
              const file = e.target.files?.[0]
              if (!file) return
              setBusy(true); setErr(null)
              try {
                const body = new FormData()
                body.append('file', file)
                const r = await fetch('/api/driverapply/session/scan',
                  { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body })
                const found = await r.json()
                if (!r.ok) throw new Error(found.detail || 'That photograph could not be read')
                if (!found.read) setErr('No barcode could be read in that photograph. Try the camera, '
                  + 'or type the license in.')
                else onRead(found.license)
              } catch (ex) { setErr(ex.message) } finally { setBusy(false); e.target.value = '' }
            }} />
        </footer>
      </div>
    </div>
  )
}

// What the applicant is shown after a read: everything found, to check before it is kept.
export function ScanResult({ found, onUse, onClose }) {
  return (
    <div className="backdrop">
      <div className="modal" role="dialog" aria-modal="true" aria-label="Read from your license">
        <header><h2>Read From Your License</h2>
          <button className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="body stack">
          <p className="scanhow"><CheckCircle2 size={14} /> Check these against the card in your hand.
            Anything wrong can be corrected on the next screen.</p>
          <dl className="scanfound">
            <dt>License number</dt><dd>{found.number || '-'}</dd>
            <dt>State</dt><dd>{found.state || '-'}</dd>
            <dt>Class</dt><dd>{found.classification || '-'}</dd>
            <dt>Issued</dt><dd>{found.issued || '-'}</dd>
            <dt>Expires</dt><dd>{found.expires || '-'}</dd>
            <dt>Endorsements</dt><dd>{found.endorsements?.length ? found.endorsements.join(', ') : 'None'}</dd>
          </dl>
        </div>
        <footer>
          <button type="button" onClick={onClose}>Scan again</button>
          <button type="button" className="primary" onClick={onUse}>Use these details</button>
        </footer>
      </div>
    </div>
  )
}
