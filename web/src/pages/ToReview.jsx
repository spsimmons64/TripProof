import { useState } from 'react'
import { Eye, Inbox } from 'lucide-react'
import { api } from '../lib/api.js'
import SignedDocViewer from '../components/SignedDocViewer.jsx'
import { Loading, useLoad } from '../components/ui.jsx'
import { useRefreshOnFocus, useWatch } from '../lib/live.js'
import { date } from '../lib/format.js'
import { properName } from '../lib/names.js'

// What came in while nobody was watching, and has not been read.
//
// A document that arrives on its own is work rather than news: a driver signed something, an
// application was submitted, a report came back. The toast says so once, for whoever happened to be
// at their desk; this is the list for everyone else, and it stays until somebody has actually
// opened the thing and said they have read it.
//
// It is the front of a queue, so it is ordered oldest first - the one that has been waiting longest
// is the one that matters.

export default function ToReview() {
  const [data, error, reload] = useLoad(() => api.get('/arrivals'), [])
  const [showing, setShowing] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  // New arrivals land here without anybody reloading: the same feed the toast listens to.
  useRefreshOnFocus(reload)
  useWatch(null, 'all', reload, { seconds: 20 })

  // Opening it is reading it, and it opens here: the office is working a queue, not touring the
  // file. Nothing is marked for TripProof staff - the server decides that, since a review is the
  // company's act - so a staff session can read the same document without clearing anybody's work.
  const open = async (item) => {
    setBusy(item.recordid); setErr(null)
    try {
      if (item.kind === 'signed' && item.detail) {
        setShowing(await api.get(`/drivers/${item.subjectid}/signed/${item.detail}`))
      }
      await api.post(`/arrivals/${item.recordid}/reviewed`, {})
      reload()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  if (!data) return <Loading error={error} page />
  const items = data.items || []

  return (
    <div className="stack">
      <div className="pagehead">
        <h1>To Review</h1>
      </div>

      {err && <div className="notice bad">{err}</div>}

      {!items.length ? (
        <div className="card emptyqueue">
          <Inbox size={22} />
          <p>Nothing is waiting to be read.</p>
        </div>
      ) : (
        <div className="card qualcard">
          {items.map((item) => (
            <div key={item.recordid} className="qualitem">
              <div className="qualmark"><span className="bubble ordered"><Eye size={15} /></span></div>
              <div className="qualbody">
                <div className="qualname">{item.label || 'A document arrived'}</div>
                <div className="qualmeta">
                  {[properName(item.firstname, item.lastname), `Arrived ${date(item.arrivedon)}`]
                    .filter(Boolean).join(' · ')}
                </div>
              </div>
              <div className="qualdo">
                <button type="button" className="primary" disabled={busy === item.recordid}
                onClick={() => open(item)}><Eye size={13} /> Open</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
