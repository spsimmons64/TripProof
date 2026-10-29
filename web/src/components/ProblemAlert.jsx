import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, time, tzDateTime } from '../lib/format.js'
import { Modal } from '../admin/common.jsx'
import { alarm } from './TopBar.jsx'

// A driver has reported a problem and nobody in the office has seen it yet: it comes up over
// whatever page is open, with the chime, once. Seen says the office has it (the driver's app shows
// when); Deal With It also goes to Dispatch and opens the problem. After that it waits in Needs
// Attention on Dispatch until it is resolved - not as a strip across the top of every page.
const POLL = 15000

export default function ProblemAlert() {
  const [items, setItems] = useState([])
  const [kinds, setKinds] = useState({})
  const [busy, setBusy] = useState(false)
  const rung = useRef(new Set())        // problems the chime has already sounded for
  const navigate = useNavigate()

  const load = () => api.get('/issues/unseen').then((got) => {
    setItems(got.items || [])
    setKinds(got.kinds || {})
    if ((got.items || []).some((i) => !rung.current.has(i.recordid))) alarm()
    for (const i of got.items || []) rung.current.add(i.recordid)
  }).catch(() => {})
  useEffect(() => {
    load()
    const t = setInterval(() => { if (document.visibilityState === 'visible') load() }, POLL)
    const back = () => { if (document.visibilityState === 'visible') load() }
    document.addEventListener('visibilitychange', back)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', back) }
  }, [])

  const one = items[0]
  if (!one) return null
  const seen = async (then) => {
    setBusy(true)
    try { await api.post(`/issues/${one.recordid}/seen`, {}) } catch { /* shown again next poll */ }
    setItems((was) => was.filter((i) => i.recordid !== one.recordid))
    setBusy(false)
    then?.()
  }
  return (
    <Modal title="A Driver Reported A Problem" onClose={() => seen()} width={560}
      footer={<>
        <button type="button" disabled={busy} onClick={() => seen()}>Seen</button>
        <button type="button" className="primary" disabled={busy}
          onClick={() => seen(() => navigate('/dispatch', { state: {
            issue: one.recordid, day: one.pickupat ? String(one.pickupat).slice(0, 10) : undefined } }))}>
          {busy ? <Loader2 size={15} className="spin" /> : <><AlertTriangle size={14} /> Deal With It</>}
        </button>
      </>}>
      <div className="stack">
        <div className="problemalert">
          <AlertTriangle size={26} />
          <div>
            <b>{kinds[one.kind] || one.kind}</b>
            {one.note && <p>{one.note}</p>}
          </div>
        </div>
        <div className="kv">
          <dt>Driver</dt><dd>{one.drivername || 'Not recorded'}</dd>
          <dt>Trip</dt><dd>{one.externalid} · {one.passenger}</dd>
          {one.pickupat && <><dt>Pickup</dt><dd>{date(one.pickupat)} {time(one.pickupat)}</dd></>}
          <dt>Reported</dt><dd>{tzDateTime(one.raisedon)}</dd>
        </div>
        {items.length > 1 && <div className="muted">{items.length - 1} more after this one.</div>}
      </div>
    </Modal>
  )
}
