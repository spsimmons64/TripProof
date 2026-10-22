import { Fragment, useState } from 'react'
import { ChevronRight, Loader2, Plus, Wrench } from 'lucide-react'
import { api } from '../lib/api.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import DocumentViewer from '../components/DocumentViewer.jsx'
import ReasonDialog from '../components/ReasonDialog.jsx'
import { CredentialForm } from '../components/Credentials.jsx'
import { date } from '../lib/format.js'

// A list of records with the one button that adds to it. The same table and the same forms
// whether it is read as a panel on the page or as the inside of the requirement that asks for it -
// only the frame differs, so there is one of each rather than two that drift.
function Shell({ bare, title, add, children }) {
  if (bare) {
    return (
      <div className="drawer">
        {add && <div className="row draweradd">{add}</div>}
        {children}
      </div>
    )
  }
  return (
    <div className="card qualcard">
      <div className="infotabs">
        <h3>{title}</h3>
        {add && <div className="row panelactions">{add}</div>}
      </div>
      {children}
    </div>
  )
}

// The same words the company and driver screens use, so the fleet reads as part of one
// application rather than a second one bolted on. Never the database's own word: nobody says
// "notapplicable" out loud, and a dispatcher should not have to work out what it meant.
const MARKS = {
  satisfied: ['st-active', 'Current'],
  expiring: ['st-ordered', 'Expiring'],
  expired: ['st-expired', 'Expired'],
  failed: ['st-expired', 'Failed'],
  overdue: ['st-expired', 'Overdue'],
  review: ['st-ordered', 'Waiting to be checked'],
  unknown: ['st-inactive', 'Cannot be decided'],
  pending: ['st-expired', 'Nothing on file'],
  notapplicable: ['st-inactive', 'Not required'],
}

// What is asked of one vehicle, in the order the catalog puts it - and, under each one, the
// records that answer it. A requirement and its evidence were on opposite ends of the page: the
// ask at the top, the inspection reports and the maintenance records in panels of their own
// underneath, and nothing joining them. Opened here, a requirement IS its file - what is on
// record against it, newest first, and the button that adds to it.
//
// One at a time. Eight requirements each holding a list of records is a page nobody can read, and
// opening the one being worked on closes the one that was.
export function VehicleRequirements({ id, credentials = [], onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/vehicles/${id}/requirements`), [id])
  const [kinds] = useLoad(() => api.get('/credentialtypes'), [])
  const [open, setOpen] = useState(null)
  const [filing, setFiling] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [changing, setChanging] = useState(null)
  if (!data) return <Shell title="Requirements"><Loading error={error} /></Shell>

  const live = data.items.filter((r) => r.applies !== false)
  // Filing anything re-reads the requirement - its status is worked out from what is on file, so
  // the row has to be told, not left showing the answer it gave before the record existed.
  const changed = () => { reload(); onChanged?.() }

  return (
    <Shell title="Requirements">
      {/* The last column is a sentence, not buttons. */}
      <table className="residencetable recordtable lastisprose reqtable">
        <thead><tr><th><span className="sr-only">Open</span></th><th>Requirement</th><th>Status</th>
          <th>Where it stands</th></tr></thead>
        <tbody>
          {live.map((r) => {
            const [tone, says] = MARKS[r.status] || ['st-inactive', r.status]
            const typeid = (data.types || {})[(r.evidencesource || '').replace('credential:', '')]
            const shown = open === r.code
            return (
              <Fragment key={r.code}>
                <tr className="click" onClick={() => setOpen(shown ? null : r.code)}>
                  {/* Its own column, because it is the one thing on the row that says what will
                      happen if it is clicked. Beside the name it read as punctuation. */}
                  <td className="reqturn">
                    <ChevronRight size={22} strokeWidth={3} className={shown ? 'turned' : undefined} />
                  </td>
                  <td>
                    <b>{r.name}</b>
                    {/* Context under the name, not a column of its own. Somebody acting on the row
                        needs the sentence; the citation is there for the auditor who asks why. */}
                    <div className="muted small">
                      {[r.authority, r.citation].filter(Boolean).join(' · ')}
                    </div>
                  </td>
                  <td className={tone}>{says}</td>
                  <td>{r.why}</td>
                </tr>
                {shown && (
                  <tr className="drawerrow">
                    <td colSpan={4}>
                      {r.evidencesource === 'dvir'
                        ? <VehicleInspections bare id={id} onChanged={changed} />
                        : r.evidencesource === 'maintenance'
                          ? <VehicleMaintenance bare id={id} onChanged={changed} />
                          : <CredentialRecords
                              name={r.name} typeid={typeid}
                              credentials={credentials.filter((c) => c.credentialtypeid === typeid)}
                              onAdd={typeid ? () => setFiling({ typeid, name: r.name }) : null}
                              onView={setViewing}
                              onResult={r.reviewrequired ? async (c, result) => {
                                // A result already recorded is changed only with the reason.
                                if (c.result) { setChanging({ c, result }); return }
                                await api.put(`/credentials/${c.recordid}/result`, { result })
                                changed()
                              } : null} />}
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
          {!live.length && <tr><td colSpan={4}>Nothing is asked of this vehicle.</td></tr>}
        </tbody>
      </table>
      {filing && (
        <Modal title={filing.name} onClose={() => setFiling(null)} width={720}>
          <CredentialForm inset subjectid={id}
            types={(kinds || []).filter((t) => t.recordid === filing.typeid)}
            onDone={(saved) => { setFiling(null); if (saved) changed() }} />
        </Modal>
      )}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.name}
        onClose={() => setViewing(null)} />}
      {changing && (
        <ReasonDialog title="Change The Recorded Result" onClose={() => setChanging(null)}
          onSave={async (reason) => {
            await api.put(`/credentials/${changing.c.recordid}/result`, { result: changing.result, reason })
            changed()
          }} />
      )}
    </Shell>
  )
}

// What is on file for one requirement answered by a document: every one ever filed, newest first,
// because a renewal does not erase the card it replaced - the old one still covers the trips it
// covered, and an auditor asking about last March is asking about that one.
// `onResult`, where the rule asks for one: an inspection counts once it is recorded as passed.
function CredentialRecords({ name, typeid, credentials, onAdd, onView, onResult }) {
  const held = [...credentials].sort(
    (a, b) => String(b.issuedon || '').localeCompare(String(a.issuedon || '')))
  return (
    <Shell bare add={onAdd && (
      <button type="button" onClick={onAdd}><Plus size={13} /> Add record</button>)}>
      <table className="residencetable recordtable credtable">
        <thead><tr><th>Issued</th><th>Expires</th><th>Number</th>{onResult && <th>Result</th>}
          <th>Status</th><th /></tr></thead>
        <tbody>
          {held.map((c) => (
            <tr key={c.recordid}>
              <td>{date(c.issuedon)}</td>
              <td>{c.expireson ? date(c.expireson) : '-'}</td>
              <td>{c.number || '-'}</td>
              {onResult && (
                <td className={c.result === 'passed' ? 'st-active' : c.result === 'failed'
                  ? 'st-expired' : 'st-ordered'}>
                  <select value={c.result || ''} aria-label="Inspection result"
                    onChange={(e) => onResult(c, e.target.value)}>
                    <option value="" disabled>Not recorded</option>
                    <option value="passed">Passed</option>
                    <option value="failed">Failed</option>
                  </select>
                </td>
              )}
              <td><Badge state={c.state} /></td>
              <td className="actions">
                {c.documentid
                  ? <button type="button" className="linkbtn edit"
                      onClick={() => onView({ documentid: c.documentid, name })}>View</button>
                  : <span className="muted small">No scan filed</span>}
              </td>
            </tr>
          ))}
          {!held.length && <tr><td colSpan={onResult ? 6 : 5}>Nothing on file for this requirement.</td></tr>}
        </tbody>
      </table>
    </Shell>
  )
}

// 49 CFR 396.11. The reports themselves, and the one thing that stops the unit: a defect reported
// and not yet put right.
export function VehicleInspections({ id, bare, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/vehicles/${id}/dvirs`), [id])
  const [adding, setAdding] = useState(false)
  const [fixing, setFixing] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) return <Shell bare={bare} title="Inspection Reports"><Loading error={error} /></Shell>
  const now = f ?? { reportedon: '', kind: 'pretrip', defects: false, defectnote: '',
    driverid: '', note: '', file: null }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('reportedon', now.reportedon)
      body.append('kind', now.kind)
      body.append('defects', now.defects)
      if (now.defects) body.append('defectnote', now.defectnote.trim())
      if (now.driverid) body.append('driverid', now.driverid)
      if (now.note.trim()) body.append('note', now.note.trim())
      if (now.file) body.append('file', now.file)
      await api.post(`/vehicles/${id}/dvirs`, body)
      setF(null); setAdding(false); await reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Shell bare={bare} title="Inspection Reports" add={
      <button type="button" onClick={() => setAdding(true)}><Plus size={13} /> Add report</button>}>
      {err && <div className="notice bad">{err}</div>}
      {data.open.length > 0 && (
        <div className="notice bad">
          {data.open.length === 1 ? 'A defect is' : `${data.open.length} defects are`} outstanding
          on this vehicle. 49 CFR 396.11(a)(3): it must not be dispatched until the repair is
          certified.
        </div>
      )}
      <table className="residencetable recordtable">
        <thead><tr><th>Reported</th><th>Kind</th><th>By</th><th>Condition</th><th /></tr></thead>
        <tbody>
          {data.reports.map((r) => {
            const open = Boolean(r.defects) && !r.correctedon
            return (
              <tr key={r.recordid}>
                <td>{date(r.reportedon)}</td>
                <td>{data.kinds[r.kind] || r.kind}</td>
                <td>{(r.drivername || '').trim() || '-'}</td>
                <td className={open ? 'st-expired' : r.defects ? 'st-active' : undefined}>
                  {!r.defects ? 'No defects'
                    : open ? `Defect: ${r.defectnote}`
                      : `${r.correction === 'notneeded' ? 'No repair needed' : 'Corrected'} ${date(r.correctedon)}${r.certifiedbyname ? ` · certified by ${r.certifiedbyname}` : ''}`}
                </td>
                <td className="actions">
                  {open && (
                    <button type="button" className="linkbtn edit toread"
                      onClick={() => setFixing(r)}><Wrench size={13} /> Certify repair</button>
                  )}
                  {r.documentid && (
                    <button type="button" className="linkbtn edit"
                      onClick={() => setViewing({ documentid: r.documentid,
                        filename: 'Inspection report' })}>View</button>
                  )}
                  <button type="button" className="linkbtn" disabled={busy}
                    onClick={async () => {
                      setBusy(true)
                      try { await api.del(`/vehicles/${id}/dvirs/${r.recordid}`); await reload(); onChanged?.() }
                      catch (e) { setErr(e.message) } finally { setBusy(false) }
                    }}>Remove</button>
                </td>
              </tr>
            )
          })}
          {!data.reports.length && (
            <tr><td colSpan={5}>No inspection reports on file for this vehicle.</td></tr>
          )}
        </tbody>
      </table>

      {adding && (
        <Modal title="Add Inspection Report" onClose={() => { setAdding(false); setF(null) }}
          width={680}
          footer={<>
            <button type="button" className="primary" disabled={busy || !now.reportedon}
              onClick={save}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => { setAdding(false); setF(null) }}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-2">Reported
                <input type="date" value={now.reportedon} min="1900-01-01" max="2100-12-31"
                  onChange={(e) => setF({ ...now, reportedon: e.target.value })} />
              </label>
              <label className="field span-2">Kind
                <select value={now.kind} onChange={(e) => setF({ ...now, kind: e.target.value })}>
                  {Object.entries(data.kinds).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
              <label className="field span-2">Driver
                <select value={now.driverid}
                  onChange={(e) => setF({ ...now, driverid: e.target.value })}>
                  <option value="">Not recorded</option>
                  {data.drivers.map((d) => (
                    <option key={d.recordid} value={d.recordid}>
                      {d.firstname} {d.lastname}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field span-3">Condition
                <select value={String(now.defects)}
                  onChange={(e) => setF({ ...now, defects: e.target.value === 'true' })}>
                  <option value="false">No defects found</option>
                  <option value="true">Defect found</option>
                </select>
              </label>
              {now.defects && (
                <label className="field span-6">What Was Wrong
                  <input value={now.defectnote}
                    onChange={(e) => setF({ ...now, defectnote: e.target.value })} />
                </label>
              )}
              <label className="field span-3">The Report
                <input type="file"
                  onChange={(e) => setF({ ...now, file: e.target.files[0] || null })} />
              </label>
            </div>
          </div>
        </Modal>
      )}

      {fixing && (
        <CertifyRepair id={id} report={fixing} onClose={() => setFixing(null)}
          onDone={async () => { setFixing(null); await reload(); onChanged?.() }} />
      )}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)} />}
    </Shell>
  )
}

// The second half of 396.11(a)(3): the repair, and somebody certifying it. Without this the report is
// a complaint rather than a record.
function CertifyRepair({ id, report, onClose, onDone }) {
  const [f, setF] = useState({ correction: 'repaired', correctedon: '', correctedby: '', note: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  return (
    <Modal title="Certify The Repair" onClose={onClose} width={620}
      footer={<>
        <button type="button" className="primary" disabled={busy || !f.correctedon}
          onClick={async () => {
            setBusy(true); setErr(null)
            try {
              await api.put(`/vehicles/${id}/dvirs/${report.recordid}/corrected`, {
                correction: f.correction, correctedon: f.correctedon,
                correctedby: f.correctedby || null,
                note: f.note || null,
              })
              onDone()
            } catch (e) { setErr(e.message) } finally { setBusy(false) }
          }}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Certify'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="notice">
          Reported {date(report.reportedon)}: {report.defectnote}
        </div>
        <div className="profileform">
          {/* 396.11(a)(3)(ii): repaired, or certified as needing no repair to operate safely. */}
          <label className="field span-6">Certify That
            <select value={f.correction} onChange={(e) => setF({ ...f, correction: e.target.value })}>
              <option value="repaired">The Defect Was Repaired</option>
              <option value="notneeded">Repair Is Not Needed For Safe Operation</option>
            </select>
          </label>
          <label className="field span-3">Corrected On
            <input type="date" value={f.correctedon} min="1900-01-01" max="2100-12-31"
              onChange={(e) => setF({ ...f, correctedon: e.target.value })} />
          </label>
          <label className="field span-3">Corrected By
            <input value={f.correctedby}
              onChange={(e) => setF({ ...f, correctedby: e.target.value })} />
          </label>
          <label className="field span-6">Note
            <textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
          </label>
        </div>
      </div>
    </Modal>
  )
}

// 49 CFR 396.3(b): what was done, when, at what mileage and by whom.
export function VehicleMaintenance({ id, bare, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/vehicles/${id}/maintenance`), [id])
  const [adding, setAdding] = useState(false)
  const [viewing, setViewing] = useState(null)
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) return <Shell bare={bare} title="Maintenance"><Loading error={error} /></Shell>
  const now = f ?? { performedon: '', kind: 'scheduled', summary: '', odometer: '', vendor: '',
    note: '', file: null }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('performedon', now.performedon)
      body.append('kind', now.kind)
      body.append('summary', now.summary.trim())
      if (now.odometer) body.append('odometer', now.odometer)
      if (now.vendor.trim()) body.append('vendor', now.vendor.trim())
      if (now.note.trim()) body.append('note', now.note.trim())
      if (now.file) body.append('file', now.file)
      await api.post(`/vehicles/${id}/maintenance`, body)
      setF(null); setAdding(false); await reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Shell bare={bare} title="Maintenance" add={
      <button type="button" onClick={() => setAdding(true)}><Plus size={13} /> Add record</button>}>
      {err && <div className="notice bad">{err}</div>}
      <table className="residencetable recordtable">
        <thead><tr><th>Performed</th><th>Kind</th><th>Odometer</th><th>What was done</th>
          <th>By</th><th /></tr></thead>
        <tbody>
          {data.records.map((r) => (
            <tr key={r.recordid}>
              <td>{date(r.performedon)}</td>
              <td>{data.kinds[r.kind] || r.kind}</td>
              <td>{r.odometer == null ? '-' : r.odometer.toLocaleString()}</td>
              <td>{r.summary}</td>
              <td>{r.vendor || r.addedbyname || '-'}</td>
              <td className="actions">
                {r.documentid && (
                  <button type="button" className="linkbtn edit"
                    onClick={() => setViewing({ documentid: r.documentid,
                      filename: 'Maintenance record' })}>View</button>
                )}
                <button type="button" className="linkbtn" disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    try { await api.del(`/vehicles/${id}/maintenance/${r.recordid}`); await reload(); onChanged?.() }
                    catch (e) { setErr(e.message) } finally { setBusy(false) }
                  }}>Remove</button>
              </td>
            </tr>
          ))}
          {!data.records.length && (
            <tr><td colSpan={6}>No maintenance recorded for this vehicle.</td></tr>
          )}
        </tbody>
      </table>

      {adding && (
        <Modal title="Add Maintenance Record" onClose={() => { setAdding(false); setF(null) }}
          width={680}
          footer={<>
            <button type="button" className="primary"
              disabled={busy || !now.performedon || !now.summary.trim()} onClick={save}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => { setAdding(false); setF(null) }}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-2">Performed
                <input type="date" value={now.performedon} min="1900-01-01" max="2100-12-31"
                  onChange={(e) => setF({ ...now, performedon: e.target.value })} />
              </label>
              <label className="field span-2">Kind
                <select value={now.kind} onChange={(e) => setF({ ...now, kind: e.target.value })}>
                  {Object.entries(data.kinds).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
              <label className="field span-2">Odometer
                <input type="number" min="0" value={now.odometer}
                  onChange={(e) => setF({ ...now, odometer: e.target.value })} />
              </label>
              <label className="field span-6">What Was Done
                <input value={now.summary}
                  onChange={(e) => setF({ ...now, summary: e.target.value })} />
              </label>
              <label className="field span-3">Vendor
                <input value={now.vendor}
                  onChange={(e) => setF({ ...now, vendor: e.target.value })} />
              </label>
              <label className="field span-3">Invoice Or Work Order
                <input type="file"
                  onChange={(e) => setF({ ...now, file: e.target.files[0] || null })} />
              </label>
            </div>
          </div>
        </Modal>
      )}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)} />}
    </Shell>
  )
}

// The broker lines this vehicle is approved for, and the day it entered each service. A state's
// broker rules reach the vehicles that broker approved - Georgia's inspection, counted back from the
// service date for the first one (DCH 910.2) - so this is where that is said. The same panel as a
// driver's Broker Approvals.
export function VehicleBrokerApprovals({ id, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/vehicles/${id}/authorizations`), [id])
  const [from, setFrom] = useState({})
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  if (!data) return error ? <div className="notice bad">{error}</div> : null
  if (!data.contracts.length) return null
  const today = new Date().toISOString().slice(0, 10)
  const act = async (c, end) => {
    setBusy(c.recordid); setErr(null)
    try {
      if (end) await api.post(`/vehicles/${id}/authorizations/${c.recordid}/end`, {})
      else await api.post(`/vehicles/${id}/authorizations/${c.recordid}`,
        { servicefrom: from[c.recordid] || today })
      await reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  return (
    <div className="card qualcard">
      <div className="infotabs"><h3>Broker Approvals</h3></div>
      <div className="panelbody">
      {err && <div className="notice bad">{err}</div>}
      <table className="residencetable recordtable">
        <thead><tr><th>Line</th><th>In Service From</th><th>Approved</th><th>Status</th><th /></tr></thead>
        <tbody>
          {data.contracts.map((c) => (
            <tr key={c.recordid}>
              <td>{[c.broker, c.state, c.contractref].filter(Boolean).join(' ')}</td>
              <td>{c.approvalid ? date(c.servicefrom) : (
                <input type="date" value={from[c.recordid] || today} min="1900-01-01" max="2100-12-31"
                  aria-label="In service from"
                  onChange={(e) => setFrom({ ...from, [c.recordid]: e.target.value })} />
              )}</td>
              <td>{c.approvedon ? `${date(c.approvedon)}${c.approvedbyname ? ` · ${c.approvedbyname}` : ''}` : '-'}</td>
              <td className={c.approvalid ? 'st-active' : 'st-inactive'}>
                {c.approvalid ? 'Approved' : 'Not Approved'}
              </td>
              <td className="actions">
                <button type="button" className={c.approvalid ? 'linkbtn' : 'linkbtn edit'}
                  disabled={busy === c.recordid} onClick={() => act(c, Boolean(c.approvalid))}>
                  {c.approvalid ? 'End Approval' : 'Approve'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  )
}
