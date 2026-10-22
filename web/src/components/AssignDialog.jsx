import { useState } from 'react'
import { Loader2, UserPlus } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, time } from '../lib/format.js'
import { Loading, useLoad } from './ui.jsx'
import { Modal } from '../admin/common.jsx'

// Who may take this leg, who may not, and why not.
//
// Everybody is listed. "Why is Tim not on this list" is the first question a dispatcher asks, and
// the answer has to be on the screen - so a driver who may not drive is shown, greyed, with the
// engine's own sentence against them. What is NOT shown is a way to choose them anyway.
export default function AssignDialog({ leg, onCancel, onClose, onDone }) {
  const [data, error, reload] = useLoad(
    () => api.get(`/legs/${leg.legid}/candidates`), [leg.legid])
  // The leg as the server knows it, not as whoever opened this dialog happened to describe it.
  // A caller that passes only an id - the issue strip does - would otherwise title the dialog
  // "Will-call · undefined", because a missing pickup time reads as a will-call and a missing
  // passenger prints as nothing at all.
  const on = data?.leg || leg
  const [driverid, setDriver] = useState(null)
  const [vehicleid, setVehicle] = useState(null)
  // The assignment in force is the starting point, and only the server reliably knows it.
  const [started, setStarted] = useState(false)
  if (data && !started) {
    setStarted(true)
    setDriver(data.leg.driverid || null)
    setVehicle(data.leg.vehicleid || null)
  }
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const chosen = (list, id, key) => (list || []).find((x) => x[key] === id)
  const d = chosen(data?.drivers, driverid, 'driverid')
  const v = chosen(data?.vehicles, vehicleid, 'vehicleid')
  const warnings = [...(d?.warnings || []), ...(v?.warnings || [])]
  const needswhy = warnings.length > 0
  // A restricted driving record is accepted by an owner or admin; any other warning by a supervisor.
  const holds = d?.holds || []
  const others = warnings.filter((w) => !holds.includes(w))
  const mayaccept = (!holds.length || data?.mayclear) && (!others.length || data?.mayoverride)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/legs/${leg.legid}/assign`, { driverid, vehicleid, overridereason: why })
      onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  const take = async () => {
    setBusy(true); setErr(null)
    try { await api.del(`/legs/${leg.legid}/assign`, { endreason: 'reassigned' }); onDone() }
    catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <Modal width={860} onClose={onClose}
      title={on.externalid
        ? `${on.externalid} · ${on.pickupat ? time(on.pickupat) : 'Will-call'} · ${on.passenger}`
        : 'Driver And Vehicle'}
      footer={<>
        <div className="footactions">
          {on.driverid && (
            <button type="button" disabled={busy} onClick={take}>Take Off This Driver</button>
          )}
          {onCancel && (
            <button type="button" className="danger" disabled={busy} onClick={onCancel}>
              Cancel This Trip
            </button>
          )}
        </div>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !driverid}
          onClick={save}>{busy ? <Loader2 size={15} className="spin" /> : 'Assign'}</button>
      </>}>
      {!data ? <Loading error={error} /> : (
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {!data.released && (
            <div className="notice">
              This is a will-call return with no pickup time yet. Who is free and who is nearest
              is worked out as of now, and will be different when it is released.
            </div>
          )}
          <div className="pickpair">
            <Candidates title="Driver" rows={data.drivers} idkey="driverid"
              chosen={driverid} onPick={setDriver} />
            <Candidates title="Vehicle" rows={data.vehicles} idkey="vehicleid"
              chosen={vehicleid} onPick={setVehicle} />
          </div>
          {needswhy && (
            <>
              <h3 className="formsection">Accepting A Warning</h3>
              {warnings.map((w) => <div key={w} className="notice warn">{w}</div>)}
              {mayaccept ? (
                <label className="field">Why this is being accepted *
                  <textarea value={why} onChange={(e) => setWhy(e.target.value)} /></label>
              ) : (
                <div className="notice bad">
                  {holds.length && !data.mayclear ? 'An owner or admin has to accept that.'
                    : 'A supervisor has to accept that.'}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Modal>
  )
}

function Candidates({ title, rows, idkey, chosen, onPick }) {
  return (
    <div>
      <h3 className="formsection">{title}</h3>
      <div className="picklist">
        {rows.map((r) => {
          const id = r[idkey]
          const blocked = !r.available
          return (
            <button key={id} type="button" disabled={blocked}
              className={`pickrow${chosen === id ? ' on' : ''}${blocked ? ' barred' : ''}`}
              onClick={() => onPick(id)}>
              <span className="pickname">{r.name}</span>
              {/* The reason, always. A greyed name with nothing against it sends somebody to
                  the telephone. */}
              <span className="pickwhy">
                {blocked ? r.blocked.join(' · ')
                  : [...(r.warnings || []), ...(r.drafts || []), ...(r.because || [])].join(' · ')}
              </span>
            </button>
          )
        })}
        {!rows.length && <div className="muted small">Nobody on file.</div>}
      </div>
    </div>
  )
}
