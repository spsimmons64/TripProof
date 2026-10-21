import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, ClipboardCheck, History, Pencil, Printer, Undo2, UserX, X } from 'lucide-react'
import { api, auth } from '../lib/api.js'
import { count, date, money } from '../lib/format.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'
import Credentials from '../components/Credentials.jsx'
import { APPLYING, DriverForm } from './Drivers.jsx'
import DriverReview, { Requirements } from './DriverReview.jsx'
import { VehicleForm } from './Vehicles.jsx'
import { VehicleRequirements } from './VehicleCompliance.jsx'
import { properName } from '../lib/names.js'

// What the office can do with an application in front of it. Each is a decision with consequences,
// so each says plainly what it means and asks once before it is made.
const DECISIONS = [
  {
    action: 'pending',
    label: 'Move Driver To Pending Status',
    icon: ClipboardCheck,
    tone: 'go',
    blurb: 'The driver\u2019s application has been reviewed but is not yet ready for final hiring approval. '
      + 'The application may be placed in Pending status while required documents, screenings, verifications '
      + 'or other pre-employment requirements are being completed. A driver in Pending status is not yet '
      + 'approved to operate as an active driver.',
    ask: 'Move this driver to Pending status?',
  },
  {
    action: 'corrections',
    leaves: true,
    label: 'Send Back For Corrections',
    icon: Undo2,
    tone: 'warn',
    blurb: 'Returns the application to the driver so they can put something right. It reopens where they left '
      + 'it, with everything they entered still there, and they sign again when they submit it. Say what needs '
      + 'correcting and it is kept with the application.',
    ask: 'Send this application back to the driver?',
    note: 'What needs correcting',
  },
  {
    action: 'decline',
    leaves: true,
    label: 'Do Not Hire This Driver',
    icon: UserX,
    tone: 'stop',
    blurb: 'Marks the applicant as not approved for employment. Use this status when the company has determined '
      + 'that the driver does not meet its hiring requirements or will not be considered for the position. The '
      + 'application is retained for recordkeeping but cannot proceed to active driver status.',
    ask: 'Mark this driver as not hired?',
    note: 'Reason (kept on the record)',
  },
]

function ApplicationActions({ id, onDone }) {
  const navigate = useNavigate()
  const [asking, setAsking] = useState(null)
  const [history, setHistory] = useState(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading] = useState(false)
  const [err, setErr] = useState(null)

  const decide = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/drivers/${id}/application/decision`, { action: asking.action, note })
      setAsking(null); setNote('')
      // Pending keeps the application open to work on; the other two are the end of this review.
      if (asking.leaves) navigate('/drivers')
      else onDone()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card actionpanel">
      <h2>Driver Actions</h2>
      {DECISIONS.map((d) => (
        <div key={d.action} className="action">
          <button type="button" className={`bigaction ${d.tone}`} onClick={() => { setAsking(d); setNote('') }}>
            <d.icon size={22} /> <span>{d.label}</span>
          </button>
          <p>{d.blurb}</p>
        </div>
      ))}
      <div className="action activity">
        <button type="button" onClick={() => setHistory([])} disabled={loading}>
          <History size={16} /> Application Activity
        </button>
      </div>

      {history && (
        <ActivityDialog id={id} onClose={() => setHistory(null)} />
      )}

      {asking && (
        <div className="backdrop">
          <div className="modal" role="dialog" aria-modal="true" aria-label={asking.ask}>
            <header><h2>{asking.ask}</h2>
              <button className="iconbtn" onClick={() => setAsking(null)} aria-label="Close"><X size={18} /></button>
            </header>
            <div className="body">
              <p>{asking.blurb}</p>
              {asking.note && (
                <label className="field">{asking.note}
                  <textarea rows={4} value={note} onChange={(e) => setNote(e.target.value)} />
                </label>
              )}
              {err && <div className="error">{err}</div>}
            </div>
            <footer>
              <button type="button" onClick={() => setAsking(null)}>Cancel</button>
              <button className="primary" disabled={busy} onClick={decide}>
                {busy ? 'Saving…' : asking.label}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  )
}


// Everything that has happened to this application, newest first: what the driver did, what they
// signed and uploaded, and what the office has done with it.
function ActivityDialog({ id, onClose }) {
  const [data, error] = useLoad(() => api.get(`/drivers/${id}/application/activity`), [id])
  return (
    <div className="backdrop">
      <div className="modal wide" role="dialog" aria-modal="true" aria-label="Application activity">
        <header><h2>Application Activity</h2>
          <button className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="body activitybody">
          {!data ? <Loading error={error} /> : (
            <ol className="activitylist">
              {data.events.map((e, i) => (
                <li key={i}>
                  <span className="when">{stamp(e.at)}</span>
                  <span className="what">
                    {e.what}
                    <span className="who">{e.who}{e.ip ? ` · ${e.ip}` : ''}</span>
                    {e.note && <span className="note">{e.note}</span>}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
        <footer><button type="button" onClick={onClose}>Close</button></footer>
      </div>
    </div>
  )
}

// 09/24/2026 15:27 UTC - times are recorded in UTC, and shown as they were recorded.
const stamp = (v) => `${String(v).slice(5, 7)}/${String(v).slice(8, 10)}/${String(v).slice(0, 4)}`
  + ` ${String(v).slice(11, 16)} UTC`

// The online application, rendered by the server as printed sheets - the form, the documents that
// were signed, and the files that were uploaded, all carried inside the page. The server sends its
// own stylesheet with it, so what is on screen is exactly what saves and prints.
function DriverApplication({ id }) {
  const [view, error] = useLoad(() => api.get(`/drivers/${id}/application`), [id])
  const [printing, setPrinting] = useState(false)
  const sheets = useRef(null)

  // Each exhibit's save link takes the picture already on the sheet, so the page carries one copy
  // of a file rather than two.
  useEffect(() => {
    if (!view || !sheets.current) return
    for (const link of sheets.current.querySelectorAll('a.avsave')) {
      const file = link.closest('.sheet')?.querySelector('img, embed')
      if (!file) { link.remove(); continue }
      link.href = file.getAttribute('src')
      link.download = link.dataset.name || 'attachment'
    }
  }, [view])

  if (error) return null                    // a driver with no application simply has nothing to show
  if (!view) return <div className="card"><Loading /></div>

  // Printing is the server's PDF of the same sheets, opened in a tab to read or print from.
  const print = async () => {
    setPrinting(true)
    try {
      const r = await fetch(`/api/drivers/${id}/application.pdf`,
        { headers: { Authorization: `Bearer ${auth.get()}` } })
      if (!r.ok) throw new Error('The PDF could not be made')
      window.open(URL.createObjectURL(await r.blob()), '_blank', 'noopener')
    } catch (e) { alert(e.message) } finally { setPrinting(false) }
  }

  return (
    <div className="card appviewcard">
      <div className="appviewhead">
        <h2>Online application</h2>
        <button type="button" disabled={printing} onClick={print}>
          <Printer size={14} /> {printing ? 'Preparing…' : 'Print'}
        </button>
      </div>
      <style>{view.css}</style>
      <div className="appview" ref={sheets} dangerouslySetInnerHTML={{ __html: view.html }} />
    </div>
  )
}

// One driver or one vehicle: who/what it is, what it's exposed to, and its credential history.
export default function SubjectDetail({ kind }) {
  const { id } = useParams()
  const path = kind === 'driver' ? 'drivers' : 'vehicles'
  const [s, error, reload] = useLoad(() => api.get(`/${path}/${id}`), [id])
  // A vehicle is a short list of measurements that are read and corrected in the same breath, so
  // its page is simply open: opening one from the list puts you in it, with no button in between.
  const [editing, setEditing] = useState(kind === 'vehicle')

  // A driver who came through the online application: their application is the page, not a dialog,
  // and there is no editor for them at all - what the record says is what they signed.
  const applied = kind === 'driver' && s && APPLYING.includes(s.status)
  // Under review: the screenings and the qualification file are the page, and the decision sits
  // above them. Editing is closed here too - nothing is agreed until they are hired.
  // A hired driver keeps the same file, with the same menu down the side. Only a PENDING driver
  // was getting it, so the moment somebody was taken on their whole page changed shape - the
  // dashboard, the tabs and the panels all went, and they were left with a bare list. Hiring
  // somebody does not end their file; it is where the file starts earning its keep.
  const reviewing = kind === 'driver' && s && ['pending', 'hired'].includes(s.status)
  if (!s) return <Loading error={error} />
  const title = kind === 'driver' ? properName(s.firstname, s.lastname) : (s.externalid || s.vin || 'Vehicle')
  const details = (kind === 'driver'
    ? [s.externalid && `Dispatch ID ${s.externalid}`,
       s.licensenumber && `License ${s.licensestate || ''} ${s.licensenumber}`,
       s.hiredon && `Hired ${date(s.hiredon)}`]
    : [[s.modelyear, s.make, s.model].filter(Boolean).join(' '), s.vin && `VIN ${s.vin}`,
       s.plate && `Plate ${s.plate}`, s.seats && `${s.seats} seats including the driver`,
       s.gvwr && `GVWR ${Number(s.gvwr).toLocaleString()} lb`,
       s.lift ? 'Wheelchair lift' : null]).filter(Boolean).join(' · ')

  return (
    <div className={applied ? 'fill' : reviewing ? 'stack reviewpage' : 'stack'}>
      {/* Under review the title travels with the decision banner, as one block that holds still, so
          it is drawn by the review screen itself rather than here. */}
      {!reviewing && <div className="pagehead">
        <div>
          <h1 className="row">{title} {s.stub ? <Badge state="stub">Incomplete - seen only in trips</Badge> : null}</h1>
          {/* Nothing is said when there is nothing to say. */}
          {details && <div className="muted">{details}</div>}
          {/* Which license this one needs follows from what it is, not from the program it runs
              under - so it is read off the measurements on the line above, not out of a banner
              further down the page. */}
          {kind === 'vehicle' && s.license && (
            <div className={`licenseread ${s.license.known ? (s.license.cdl ? 'warn' : 'good') : 'info'}`}>
              <div>{s.license.summary}</div>
              {s.license.endorsement === 'P' && <div>Its driver must hold that endorsement.</div>}
            </div>
          )}
        </div>
        <div className="row headactions">
          <Link className="btn back" to={`/${path}`}>
            <ChevronLeft size={14} /> Back to {kind === 'driver' ? 'drivers' : 'vehicles'} list
          </Link>
        </div>
        {/* A vehicle's page is its own record and the file it owes - what its credentials cost in
            trips is the trips screen's question, asked there. */}
        {!applied && !reviewing && kind !== 'vehicle' && (
          <div className="row">
            <Link className="btn" to={`/trips?status=fail&${kind}id=${id}`}>{count(s.exposure.trips)} trips at risk from these credentials · {money(s.exposure.amount)}</Link>
            <button onClick={() => setEditing(true)}><Pencil size={14} /> Edit</button>
          </div>
        )}
      </div>}
      {reviewing && (
        <DriverReview id={id} driver={properName(s.firstname, s.lastname)} record={s} onDone={reload} />
      )}
      {applied && (
        <div className="applyreview">
          <ApplicationActions id={id} onDone={reload} />
          <DriverApplication id={id} />
        </div>
      )}
      {!applied && !reviewing && editing && (kind === 'driver'
        ? <DriverForm id={id} initial={s} onDone={() => { setEditing(false); reload() }} />
        : <VehicleForm id={id} initial={s} onDone={reload} />)}
      {!applied && !reviewing && kind === 'vehicle' && !s.modelyear && <div className="notice warn">Model year is missing, so the vehicle-age rule fails every trip for this unit.</div>}
      {/* What the measurements add up to. Shown rather than stored, with the reason attached, so
          a wrong answer is argued with rather than believed. */}
      {/* A hired driver's file does not stop mattering the day they are hired - the annual review,
          the Clearinghouse query and the medical certificate all fall due while they drive. */}
      {!applied && !reviewing && kind === 'driver' && <Requirements id={id} />}
      {/* A vehicle has a file of its own, and until now it did not: the inspection it owes, the
          reports its drivers made on it, and what has been done to it. 49 CFR Part 396. */}
      {!applied && !reviewing && kind === 'vehicle' && (
        <VehicleRequirements id={id} credentials={s.credentials || []} onChanged={reload} />
      )}
      
      
      {/* Not for a vehicle. Its requirements list is where a document is filed now, so a
          panel called Credentials at the foot of the page was the same job under a name
          nobody recognised, a screen away from the question it answers. */}
      {!applied && !reviewing && kind !== 'vehicle' && (
        <Credentials subject={kind} subjectid={id} credentials={s.credentials}
          onChange={reload} />
      )}
    </div>
  )
}

// What the vehicle's measurements add up to.
//
// Three conclusions, and they disagree with each other on purpose. A twelve-seat van carrying
// passengers for hire is a commercial motor vehicle under 49 CFR 390.5(2) and is not one under
// F.S. 316.003(14), because Florida has no compensation prong - so Part 391 reaches its driver on
// a run across the state line and does not reach them on a local one.
//
// Nothing here is stored or editable. It is worked out from the seating, the weight ratings and
// whether passengers are carried for compensation, and every answer carries the reason it came out
// that way, so a wrong one is argued with rather than believed. An unknown says so: not enough has
// been recorded is a different answer from no.
// A plain Yes or No, in one weight, with the reason beside it. No badge and no colour: whether a
// vehicle is a commercial motor vehicle is a fact about the vehicle, not good news or bad, and
// dressing it as a warning made three neutral facts look like three problems.


