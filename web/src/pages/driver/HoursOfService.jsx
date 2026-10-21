// Driver page - HoursOfService. Moved out of
// pages/DriverReview.jsx, which had grown too large to work in safely.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../../lib/states.js'
import { api } from '../../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../../lib/live.js'
import { date } from '../../lib/format.js'
import { Bubble, Loading, useLoad } from '../../components/ui.jsx'
import { Modal } from '../../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../../components/Pager.jsx'
import { useUser } from '../../App.jsx'
import SignatureBlock from '../../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../../components/DocumentViewer.jsx'
import ApplicantForm from '../../components/ApplicantForm.jsx'
import SignedDocViewer from '../../components/SignedDocViewer.jsx'
import { PhoneInput } from '../../components/MaskedInput.jsx'
import LicenseDialog from '../../components/LicenseDialog.jsx'
import TestDialog from '../../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../../components/WithdrawDialog.jsx'
import { Email, Phone } from '../../components/Contact.jsx'
import { usePlaygroundHeight } from './common.jsx'

const hhmm = (m) => (m === null || m === undefined ? '-'
  : `${Math.floor(m / 60)} h${m % 60 ? ` ${String(m % 60).padStart(2, '0')}` : ''}`)

export function HoursOfService({ id, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/duty-days`), [id])
  const [page, setPage] = useState(1)
  const [pagesize, setPagesize] = useState(PAGE_SIZES[0])
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const today = new Date().toISOString().slice(0, 10)
  const [f, setF] = useState({ dutydate: today, dutystart: '', dutyend: '',
    drivehours: '', driveminutes: '', dutyhours: '', dutyminutes: '', note: '' })

  function act(fn) {
    return (async () => {
      setBusy(true); setErr(null)
      try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(false) }
    })()
  }
  const mins = (h, m) => (Number(h || 0) * 60) + Number(m || 0)
  const save = () => act(async () => {
    await api.post(`/drivers/${id}/duty-days`, {
      dutydate: f.dutydate,
      dutystart: f.dutystart || null, dutyend: f.dutyend || null,
      drivingminutes: mins(f.drivehours, f.driveminutes),
      ondutyminutes: mins(f.dutyhours, f.dutyminutes),
      note: f.note.trim().toUpperCase() || null,
    })
    setAdding(false)
    setF({ ...f, dutystart: '', dutyend: '', drivehours: '', driveminutes: '',
      dutyhours: '', dutyminutes: '', note: '' })
    reload(); onChanged?.()
  })
  // A day of duty hours is a kept record too - 49 CFR 395.8(k)(1), six months - so taking one
  // back asks for a reason like the other two, rather than silently changing the arithmetic of
  // somebody's week.
  const [pulling, setPulling] = useState(null)
  const remove = (d, reason) => act(async () => {
    await api.del(`/drivers/${id}/duty-days/${d}?reason=${encodeURIComponent(reason)}`)
    setPulling(null)
    reload(); onChanged?.()
  })

  const days = data?.days || []
  const pages = Math.max(1, Math.ceil(days.length / pagesize))
  const at = Math.min(page, pages)
  const shown = days.slice((at - 1) * pagesize, at * pagesize)

  // A grid fills the room it is given. Measured against the playground the same way the other
  // driver panels are, so the rows scroll inside the card and the page itself never does.
  const card = useRef(null)
  const room = usePlaygroundHeight(card, [id, data])

  if (!data) {
    return <div className="card qualcard"><h3>Hours Of Service</h3><Loading error={error} /></div>
  }

  return (
    <>
      {/* The same card every other section of a driver's file is: the heading band, the rows
          scrolling beneath it, the pager pinned at the bottom. What acts on the list sits at the
          right-hand end of the heading, which is the only part of the band that was empty. */}
      <div className="card qualcard activitycard" ref={card}
        style={room ? { height: room } : undefined}>
        <h3 className="withact">
          <span>Hours Of Service</span>
          <button type="button" onClick={() => setAdding(true)}>
            <Plus size={13} /> Record A Day
          </button>
        </h3>
        {err && <div className="notice bad">{err}</div>}
        {/* The band Trip History uses, for the reason Trip History uses it: `.hireempty` is a
            flex child that centres itself in the room it is given, and a plain block container
            gives it none - which is how it ended up as a short grey line at the top of an
            otherwise empty card. */}
        <div className="hireband">
          {!days.length ? <div className="hireempty">No days recorded</div> : (
            <table className="residencetable recordtable">
              <thead><tr><th>Day</th><th>On duty</th><th>Driving</th>
                <th className="growcol">Within the limits</th><th /></tr></thead>
              <tbody>
                {shown.map((x) => (
                  <tr key={x.dutydate}>
                    <td>{date(x.dutydate)}</td>
                    <td>{hhmm(x.ondutyminutes)}{x.dutystart && x.dutyend
                      ? ` \u00b7 ${String(x.dutystart).slice(0, 5)}-${String(x.dutyend).slice(0, 5)}`
                      : ''}</td>
                    <td>{hhmm(x.drivingminutes)}</td>
                    <td className={`growcol ${x.breaches.length ? 'st-expired' : 'st-active'}`}>
                      {x.breaches.length ? x.breaches.join('; ') : 'Yes'}
                    </td>
                    <td className="actions">
                      <button type="button" className="linkbtn edit" disabled={busy}
                        onClick={() => setPulling(x)}>Withdraw</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <Pager total={days.length} page={at} pagesize={pagesize} noun="days"
          onPage={setPage} onPageSize={(n) => { setPagesize(n); setPage(1) }} />
      </div>

      {pulling && (
        <WithdrawDialog title="Withdraw This Day" busy={busy} err={err}
          what={`The duty hours recorded for ${date(pulling.dutydate)} will be withdrawn.`}
          warn="The seven-day and duty-hour arithmetic for this driver changes with it."
          onClose={() => setPulling(null)}
          onConfirm={(reason) => remove(pulling.dutydate, reason)} />
      )}

      {adding && (
        <Modal title="Record A Day Of Work" onClose={() => setAdding(false)} width={620}
          footer={<>
            <button type="button" className="primary" disabled={busy} onClick={save}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setAdding(false)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-2">Day *
                <input type="date" value={f.dutydate} max={today}
                  onChange={(e) => setF({ ...f, dutydate: e.target.value })} />
              </label>
              <label className="field span-2">On Duty From
                <input type="time" value={f.dutystart}
                  onChange={(e) => setF({ ...f, dutystart: e.target.value })} />
              </label>
              <label className="field span-2">Until
                <input type="time" value={f.dutyend}
                  onChange={(e) => setF({ ...f, dutyend: e.target.value })} />
              </label>
              {/* Hours and minutes rather than a decimal. Nobody works 7.75 hours; they work
                  7 hours 45, and asking for it the way it is read stops the arithmetic
                  happening in somebody's head. */}
              <label className="field span-3">On duty, total *
                <span className="row">
                  <input type="number" min="0" max="24" placeholder="h" value={f.dutyhours}
                    onChange={(e) => setF({ ...f, dutyhours: e.target.value })} />
                  <input type="number" min="0" max="59" placeholder="min" value={f.dutyminutes}
                    onChange={(e) => setF({ ...f, dutyminutes: e.target.value })} />
                </span>
              </label>
              <label className="field span-3">Of which driving *
                <span className="row">
                  <input type="number" min="0" max="24" placeholder="h" value={f.drivehours}
                    onChange={(e) => setF({ ...f, drivehours: e.target.value })} />
                  <input type="number" min="0" max="59" placeholder="min" value={f.driveminutes}
                    onChange={(e) => setF({ ...f, driveminutes: e.target.value })} />
                </span>
              </label>
              <label className="field span-6">Note
                <textarea value={f.note}
                  onChange={(e) => setF({ ...f, note: e.target.value.toUpperCase() })} />
              </label>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}
