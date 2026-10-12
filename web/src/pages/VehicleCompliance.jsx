import { useState } from 'react'
import { Loader2, Plus, Wrench } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import DocumentViewer from '../components/DocumentViewer.jsx'
import { date } from '../lib/format.js'

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

// What is asked of one vehicle, in the order the catalog puts it.
export function VehicleRequirements({ id }) {
  const [data, error] = useLoad(() => api.get(`/vehicles/${id}/requirements`), [id])
  if (!data) {
    return <div className="card qualcard"><h3>Requirements</h3><Loading error={error} /></div>
  }
  const live = data.items.filter((r) => r.applies !== false)
  return (
    <div className="card qualcard">
      <div className="infotabs"><h3>Requirements</h3></div>
      <table className="residencetable recordtable">
        <thead><tr><th>Requirement</th><th>Status</th><th>Where it stands</th></tr></thead>
        <tbody>
          {live.map((r) => {
            const [tone, says] = MARKS[r.status] || ['st-inactive', r.status]
            return (
              <tr key={r.code}>
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
            )
          })}
          {!live.length && <tr><td colSpan={3}>Nothing is asked of this vehicle.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

// 49 CFR 396.11. The reports themselves, and the one thing that stops the unit: a defect reported
// and not yet put right.
export function VehicleInspections({ id, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/vehicles/${id}/dvirs`), [id])
  const [adding, setAdding] = useState(false)
  const [fixing, setFixing] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return <div className="card qualcard"><h3>Inspection Reports</h3><Loading error={error} /></div>
  }
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
    <div className="card qualcard">
      <div className="infotabs">
        <h3>Inspection Reports</h3>
        <div className="row panelactions">
          <button type="button" onClick={() => setAdding(true)}><Plus size={13} /> Add report</button>
        </div>
      </div>
      {err && <div className="notice bad">{err}</div>}
      {data.open.length > 0 && (
        <div className="notice bad">
          {data.open.length === 1 ? 'A defect is' : `${data.open.length} defects are`} outstanding
          on this vehicle. 49 CFR 396.11(c): it must not be dispatched until the repair is
          certified.
        </div>
      )}
      <table className="residencetable recordtable">
        <thead><tr><th>Reported</th><th>Kind</th><th>By</th><th>Condition</th><th /></tr></thead>
        <tbody>
          {data.reports.map((r) => {
            const open = r.defects && !r.correctedon
            return (
              <tr key={r.recordid}>
                <td>{date(r.reportedon)}</td>
                <td>{data.kinds[r.kind] || r.kind}</td>
                <td>{(r.drivername || '').trim() || '-'}</td>
                <td className={open ? 'st-expired' : r.defects ? 'st-active' : undefined}>
                  {!r.defects ? 'No defects'
                    : open ? `Defect: ${r.defectnote}`
                      : `Corrected ${date(r.correctedon)}`}
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
                <label className="field span-6">What was wrong
                  <input value={now.defectnote}
                    onChange={(e) => setF({ ...now, defectnote: e.target.value })} />
                </label>
              )}
              <label className="field span-3">The report
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
    </div>
  )
}

// The second half of 396.11(c): the repair, and somebody certifying it. Without this the report is
// a complaint rather than a record.
function CertifyRepair({ id, report, onClose, onDone }) {
  const [f, setF] = useState({ correctedon: '', correctedby: '', note: '' })
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
                correctedon: f.correctedon, correctedby: f.correctedby || null,
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
          <label className="field span-3">Corrected on
            <input type="date" value={f.correctedon} min="1900-01-01" max="2100-12-31"
              onChange={(e) => setF({ ...f, correctedon: e.target.value })} />
          </label>
          <label className="field span-3">Corrected by
            <input value={f.correctedby}
              onChange={(e) => setF({ ...f, correctedby: e.target.value })} />
          </label>
          <label className="field span-6">Note
            <input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
          </label>
        </div>
      </div>
    </Modal>
  )
}

// 49 CFR 396.3(b): what was done, when, at what mileage and by whom.
export function VehicleMaintenance({ id, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/vehicles/${id}/maintenance`), [id])
  const [adding, setAdding] = useState(false)
  const [viewing, setViewing] = useState(null)
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return <div className="card qualcard"><h3>Maintenance</h3><Loading error={error} /></div>
  }
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
    <div className="card qualcard">
      <div className="infotabs">
        <h3>Maintenance</h3>
        <div className="row panelactions">
          <button type="button" onClick={() => setAdding(true)}><Plus size={13} /> Add record</button>
        </div>
      </div>
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
              <label className="field span-6">What was done
                <input value={now.summary}
                  onChange={(e) => setF({ ...now, summary: e.target.value })} />
              </label>
              <label className="field span-3">Vendor
                <input value={now.vendor}
                  onChange={(e) => setF({ ...now, vendor: e.target.value })} />
              </label>
              <label className="field span-3">Invoice or work order
                <input type="file"
                  onChange={(e) => setF({ ...now, file: e.target.files[0] || null })} />
              </label>
            </div>
          </div>
        </Modal>
      )}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)} />}
    </div>
  )
}
