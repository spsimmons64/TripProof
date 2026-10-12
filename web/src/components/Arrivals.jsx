import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, X } from 'lucide-react'
import { api } from '../lib/api.js'

// Work that came back while somebody was looking at something else.
//
// A driver signing from a link, an application submitted, a report returned: nobody in the office
// made these happen, so nobody in the office knows unless they are told. This watches the change
// feed for the account and says so - once, quietly, in the corner - and the same arrivals are in
// the bell afterwards for anyone who was not at their desk.
//
// Deliberately not every change. A toast for something you did yourself is noise, and noise is how
// people learn to ignore the corner of the screen.

// The kinds that mean something ARRIVED, as opposed to something being changed by somebody at
// their desk. This list must match `ARRIVED` in app/events.py, which decides what goes in the bell:
// a kind in one list and not the other produces exactly what happened here - a medical certificate
// sitting unread in the inbox with nothing on screen to say it had come.
const ARRIVED = ['signed', 'application-submitted', 'report-returned', 'uploaded']
const ASK_EVERY = 25000
const SHOWN_FOR = 30000

export default function Arrivals() {
  const [toasts, setToasts] = useState([])
  const cursor = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    let live = true
    let timer = null
    const ask = async () => {
      // Nothing is asked of a tab nobody is looking at; it catches up when it is looked at again.
      if (document.visibilityState === 'visible') {
        try {
          const query = cursor.current === null ? '' : `?since=${cursor.current}`
          const r = await api.get(`/events${query}`)
          if (!live) return
          const first = cursor.current === null
          cursor.current = r.cursor
          if (!first) {
            const news = (r.events || []).filter((e) => ARRIVED.includes(e.kind) && e.label)
            if (news.length) {
              setToasts((held) => [...held, ...news].slice(-4))
              // Tell the bell, which polls on a slower clock of its own.
              window.dispatchEvent(new CustomEvent('tripproof:arrived'))
            }
          }
        } catch { /* a feed that cannot be reached is not worth saying anything about */ }
      }
      if (live) timer = setTimeout(ask, ASK_EVERY)
    }
    ask()
    return () => { live = false; if (timer) clearTimeout(timer) }
  }, [])

  const dismiss = (seq) => setToasts((held) => held.filter((t) => t.seq !== seq))

  if (!toasts.length) return null
  return (
    <div className="arrivals" role="status" aria-live="polite">
      {toasts.map((t) => (
        <Arrival key={t.seq} note={t} onClose={() => dismiss(t.seq)}
          onOpen={() => {
            dismiss(t.seq)
            if (t.subject !== 'driver' || !t.subjectid) return
            // A signature that just arrived is worth opening, not just navigating near.
            const show = t.kind === 'signed' && t.detail ? `?signed=${encodeURIComponent(t.detail)}` : ''
            navigate(`/drivers/${t.subjectid}${show}`)
          }} />
      ))}
    </div>
  )
}

function Arrival({ note, onOpen, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, SHOWN_FOR)
    return () => clearTimeout(t)
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="arrival">
      <span className="arrivalmark"><Check size={15} strokeWidth={3} /></span>
      <button type="button" className="arrivalsay" onClick={onOpen}>{note.label}</button>
      <button type="button" className="iconbtn" onClick={onClose} aria-label="Dismiss">
        <X size={15} />
      </button>
    </div>
  )
}
