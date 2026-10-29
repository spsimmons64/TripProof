import { useState } from 'react'
import DocumentViewer from '../components/DocumentViewer.jsx'
import IssueDialog from '../components/IssueDialog.jsx'
import OutDialog from '../components/OutDialog.jsx'
import AssignDialog from '../components/AssignDialog.jsx'
import EditTrip from '../components/EditTrip.jsx'
import LegRoute from '../components/LegRoute.jsx'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, ChevronLeft, FileText, PauseCircle, Pencil } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, datetime, money, through, tzDateTime } from '../lib/format.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'

// Everything that happened on one leg, in the order it happened.
//
// Assembled rather than stored: the assignment history, the execution times, every wait and every
// issue are separate records written by different people at different moments, and an audit asks
// one question of all of them - what happened, when, and who says so. A single list is the only
// honest answer, because a reader must be able to see that nothing has been left out between two
// rows.
//
// Every line carries its own time. Nothing here is computed from "now", so this page reads the
// same in a year as it does this afternoon.
function WhatHappened({ leg, issues, changes, words }) {
  const events = []
  // Two kinds of time land in this one list and they are not read the same way. A pickup is a
  // BUSINESS time - stored as the wall clock the company works to, shown exactly as recorded. A
  // moment something happened is a TIMESTAMP, stored in UTC, and has to be turned into the
  // reader's zone. Formatting the second kind like the first put every line on this page four
  // hours into the future, which on a page whose whole purpose is an audit is not a small thing.
  const add = (at, what, detail, tone, zoned = true) =>
    { if (at) events.push({ at, what, detail, tone, zoned }) }

  for (const a of leg.assignments || []) {
    add(a.assignedon, 'Assigned',
        [a.drivername || 'no driver', a.unit, a.byname && `by ${a.byname}`]
          .filter(Boolean).join(' · '))
    if (a.override) {
      add(a.assignedon, 'Warning accepted', a.overridereason, 'warn')
    }
    add(a.acknowledgedon, 'Driver acknowledged', a.drivername)
    add(a.declinedon, 'Driver declined', a.drivername, 'warn')
    add(a.endedon, 'Taken off',
        [(words.endreasons || {})[a.endreason] || a.endreason, a.drivername]
          .filter(Boolean).join(' · '), 'warn')
  }
  add(leg.pickupat, 'Pickup time', 'Scheduled', undefined, false)
  // Every step the driver reported, with the moment it happened and who said so. A step reported
  // from a phone and one typed in by the office are different kinds of evidence, so the line says
  // which - and where the two times differ, the delay in reaching us is stated rather than hidden.
  const SAID = { enroute: 'On the way', arrived: 'Arrived at the pickup',
                 onboard: 'Passenger aboard', completed: 'Arrived at the destination' }
  for (const e of leg.events || []) {
    const late = e.recordedon && e.happenedon && e.recordedon !== e.happenedon
    add(e.happenedon, SAID[e.state] || e.state,
        [e.drivername ? `reported by ${e.drivername}` : e.byname ? `entered by ${e.byname}` : null,
         e.latitude != null ? `${Number(e.latitude).toFixed(5)}, ${Number(e.longitude).toFixed(5)}` : null,
         late ? `reached us ${tzDateTime(e.recordedon)}` : null].filter(Boolean).join(' · '))
  }
  for (const w of leg.waits || []) {
    add(w.startedon, 'Waiting started',
        [(words.waitreasons || {})[w.reason] || w.reason, w.note].filter(Boolean).join(' · '))
    add(w.endedon, 'Waiting ended', `${w.minutes} minute${w.minutes === 1 ? '' : 's'}`)
  }
  for (const i of issues) {
    add(i.raisedon, 'Problem reported',
        [(words.issuekinds || {})[i.kind] || i.kind, i.note, i.drivername && `- ${i.drivername}`]
          .filter(Boolean).join(' · '), 'bad')
    add(i.acknowledgedon, 'Problem seen by the office', i.byname)
    add(i.resolvedon, 'Problem resolved', i.resolution)
  }
  // Every edit, field by field from old to new, with who made it and why - and, where a driver was
  // on the leg, the moment they said they had read it.
  for (const c of changes) {
    add(c.changedon, 'Trip changed',
        [c.changes.map((x) => `${x.field}: ${x.old} → ${x.new}`).join('; '),
         c.byname && `by ${c.byname}`, c.reason].filter(Boolean).join(' · '), 'warn')
    if (c.driverid) {
      add(c.seenon, 'Driver read the change', c.drivername)
    }
  }
  // What the finished leg is worth, rather than a second "completed" line beside the event.
  if (leg.dropoffat) {
    add(leg.dropoffat, 'Leg closed',
        [leg.miles != null && `${leg.miles} miles`, leg.signature && 'signature captured',
         leg.gps && 'GPS recorded'].filter(Boolean).join(' · ') || 'No mileage or signature recorded',
        undefined, false)
  }

  events.sort((x, y) => String(x.at).localeCompare(String(y.at)))
  if (!events.length) return <div className="muted small">Nothing has happened on this leg yet.</div>

  return (
    <table className="residencetable recordtable happened">
      <thead><tr><th>When</th><th>What</th><th>Detail</th></tr></thead>
      <tbody>
        {events.map((e, n) => (
          <tr key={`${e.at}-${e.what}-${n}`}>
            <td className="mono">{e.zoned ? tzDateTime(e.at) : datetime(e.at)}</td>
            <td className={e.tone === 'bad' ? 'st-expired' : e.tone === 'warn' ? 'st-ordered' : undefined}>
              {e.what}
            </td>
            <td>{e.detail || ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// Whether a text to a driver went, in a word or two.
const TEXTSTATUS = { sent: 'Sent', queued: 'Sending', failed: 'Not sent', off: 'Not sent (texting not set up)',
                     nophone: 'Not sent (no mobile number)' }

export default function TripDetail() {
  const { id } = useParams()
  const [trip, error, reload] = useLoad(() => api.get(`/trips/${id}`), [id])
  // Each leg as it was driven, for its map.
  const [routes] = useLoad(() => api.get(`/trips/${id}/routes`), [id])
  const navigate = useNavigate()
  // Back to wherever this was opened from: Dispatch opens it from a trip's dialog, and Back puts
  // that dialog up again on the same day.
  const came = useLocation().state?.back
  const back = () => (came ? navigate('/dispatch', { state: { open: came.legid, day: came.day } }) : navigate(-1))
  const [issue, setIssue] = useState(null)
  const [out, setOut] = useState(false)
  const [assigning, setAssigning] = useState(null)
  const legOf = (i) => (trip.legs || []).find((l) => l.recordid === i.legid)
  const [viewing, setViewing] = useState(null)      // the credential whose file is being read
  const [editing, setEditing] = useState(false)
  if (!trip) return <Loading error={error} page />
  const atRisk = trip.checks.some((c) => c.outcome !== 'pass')

  // An OPEN problem is not history, so it does not belong in the timeline below - that table is
  // a record and nothing in it is computed from now. It belongs at the top, where somebody who
  // opened this trip because they were told there was a problem can act on it.
  const open = (trip.issues || []).filter((i) => !i.resolvedon)
  const setBilling = async (billingstatus) => { await api.patch(`/trips/${id}`, { billingstatus }); reload() }

  return (
    <div className="stack">
      <div className="pagehead">
        <div>
          <div className="small"><Link to="/trips">Trips</Link></div>
          <h1 className="row">Trip <span className="mono" style={{ fontSize: 20 }}>{trip.externalid}</span>
            {atRisk ? <Badge state="atrisk" /> : <Badge state="clean" />}</h1>
          <div className="muted">{date(trip.tripdate)} · {trip.brokername || 'Unknown broker'} · {trip.servicelevel || 'level not given'} · {money(trip.billedamount)} · {trip.billingstatus}</div>
        </div>
        <div className="row">
          <button type="button" className="back" onClick={back}><ChevronLeft size={14} /> Back</button>
          {trip.billingstatus === 'unbilled' && atRisk && <button onClick={() => setBilling('held')}><PauseCircle size={14} /> Hold from billing</button>}
          {trip.billingstatus === 'held' && <button onClick={() => setBilling('unbilled')}>Release hold</button>}
          {!trip.edit?.locked && (
            <button type="button" onClick={() => setEditing(true)}><Pencil size={14} /> Edit Trip</button>
          )}
        </div>
      </div>


      {/* The same moves the dispatch board offers. Sending somebody to another screen to do the
          thing this screen has just told them about is the dead end all over again. */}
      {issue && (
        <IssueDialog issue={issue} kinds={trip.issuekinds || {}}
          title={`A Problem On ${trip.externalid}`}
          onOut={() => { setOut({ kind: 'vehicle', who: legOf(issue)?.vehicleid }); setIssue(null) }}
          onReassign={() => { setAssigning({ legid: issue.legid, tripid: trip.recordid,
                                             externalid: trip.externalid }); setIssue(null) }}
          onClose={() => setIssue(null)}
          onDone={() => { setIssue(null); reload() }} />
      )}
      {out && <OutDialog start={out} onClose={() => setOut(false)}
        onDone={() => { setOut(false); reload() }} />}
      {assigning && (
        <AssignDialog leg={assigning} onClose={() => setAssigning(null)}
          onCancel={() => setAssigning(null)}
          onDone={() => { setAssigning(null); reload() }} />
      )}

      {trip.legs.map((leg) => {
        const checks = trip.checks.filter((c) => c.legid === leg.recordid)
        return (
          <div className="card" key={leg.recordid}>
            <h2>Leg {leg.legnumber} · pickup {datetime(leg.pickupat)}</h2>
            <div className="row muted" style={{ marginBottom: 12 }}>
              <span>Driver: {leg.driverid ? <Link to={`/drivers/${leg.driverid}`}>{leg.drivername}</Link> : (leg.driverexternal || 'none')}</span>
              <span>· Vehicle: {leg.vehicleid ? <Link to={`/vehicles/${leg.vehicleid}`}>{leg.unit || 'vehicle'}{leg.modelyear ? ` (${leg.modelyear})` : ''}</Link> : (leg.vehicleexternal || 'none')}</span>
              <span>· Signature {leg.signature ? 'yes' : 'no'} · GPS {leg.gps ? 'yes' : 'no'}</span>
            </div>
            {/* A problem the driver reported on this leg, not yet resolved: said here, on its leg,
                with the way to deal with it - not as a strip across the top of the page. */}
            {open.filter((i) => i.legid === leg.recordid || (!i.legid && leg === trip.legs[0])).map((i) => (
              <div key={i.recordid} className="legproblem">
                <AlertTriangle size={16} />
                <span><b>{(trip.issuekinds || {})[i.kind] || i.kind}</b>{i.note ? ` - ${i.note}` : ''}
                  <span className="muted"> · {i.drivername}, {tzDateTime(i.raisedon)}
                    {i.acknowledgedon ? ` · seen ${tzDateTime(i.acknowledgedon)}` : ' · not seen yet'}</span></span>
                <button type="button" onClick={() => setIssue(i)}><AlertTriangle size={14} /> Deal With It</button>
              </div>
            ))}
            {routes?.legs?.[leg.recordid] && <LegRoute route={routes.legs[leg.recordid]} style={routes.style} />}
            <WhatHappened leg={leg} issues={trip.issues.filter((i) => i.legid === leg.recordid)}
              changes={(trip.changes || []).filter((c) => c.legid === leg.recordid
                || (!c.legid && leg.legnumber === trip.legs[0].legnumber))}
              words={trip} />
            <div className="tablewrap"><table>
              <thead><tr><th>Requirement</th><th>Version</th><th>Result</th><th>Evidence</th><th>Covered</th></tr></thead>
              <tbody>{checks.map((c) => (
                <tr key={c.code}>
                  <td>{c.description}<div className="small muted">{c.code}</div></td>
                  {/* The rule as it stood when this leg was judged; unapproved means no reviewer had
                      signed it off yet. */}
                  <td className="small">{c.version ? `v${c.version}` : '-'} {!c.verified && <Badge state="unverified" />}</td>
                  <td><Badge state={c.outcome} /></td>
                  <td className="small">
                    {c.outcome === 'pass' && c.credentialid ? (
                      <>#{c.number || '-'} · issued {date(c.issuedon)} · expires {c.expireson ? date(c.expireson) : 'none printed'}
                        {c.documentid && <> · <a href="#" onClick={(e) => { e.preventDefault(); setViewing(c) }}><FileText size={12} /> file</a></>}</>
                    ) : c.outcome === 'pass' ? 'Meets rule' : <span className="error">{c.reason}</span>}
                  </td>
                  <td className="small">{c.windowstart ? `${date(c.windowstart)} ${through(c.windowend)}` : '-'}</td>
                </tr>
              ))}</tbody>
            </table></div>
          </div>
        )
      })}
      {(trip.texts || []).length > 0 && (
        <div className="card qualcard">
          <div className="infotabs"><h3>Texts To Drivers</h3></div>
          <div className="panelbody">
            <table className="residencetable recordtable textstable">
              <thead><tr><th>Sent</th><th>Driver</th><th>Message</th><th>Status</th></tr></thead>
              <tbody>{trip.texts.map((x) => (
                <tr key={x.recordid}>
                  <td>{tzDateTime(x.added)}</td>
                  <td>{x.drivername || '-'}</td>
                  <td>{x.body}</td>
                  <td className={x.status === 'sent' ? 'st-active' : x.status === 'queued' ? undefined : 'st-expired'}>
                    {TEXTSTATUS[x.status] || x.status}{x.status === 'failed' && x.error ? `: ${x.error}` : ''}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
      {trip.run && <div className="small muted">Checked {tzDateTime(trip.run.finished)} by engine {trip.run.engineversion} ({trip.run.reason}). Run {trip.run.recordid}.</div>}
      {editing && (
        <EditTrip tripid={trip.recordid} onClose={() => setEditing(false)}
          onDone={() => { setEditing(false); reload() }} />
      )}
      {viewing && (
        <DocumentViewer id={viewing.documentid} name={viewing.filename || viewing.typename}
          onClose={() => setViewing(null)} />
      )}
    </div>
  )
}
