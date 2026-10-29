import { useState } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { date } from '../lib/format.js'
import { Modal } from '../admin/common.jsx'
import { Loading, useLoad } from './ui.jsx'
import { PhoneInput } from './MaskedInput.jsx'
import SearchSelect from './SearchSelect.jsx'
import { EntryDialog } from './BookTrip.jsx'

// Putting right a booked trip, within what its stage allows.
//
// The server decides what may change - the same answer it gives the endpoint that takes the edit -
// and this shows it: a field that can no longer be changed is shown, filled in and shut, so the
// dispatcher sees what the trip says and why that part is fixed. On the road only where the
// passenger is going; a finished leg, billed, cancelled or returned, nothing. A broker's trip, or any change to a leg under way or done, needs a reason.

const STAGE = {
  open: null,
  moving: 'Under way - only the drop-off can be changed.',
  done: 'Finished - a completed leg cannot be changed.',
  closed: 'Closed - nothing on this leg can be changed.',
}
const clock = (v) => (v ? String(v).slice(0, 16) : '')

export default function EditTrip({ tripid, onClose, onDone }) {
  const [trip, error] = useLoad(() => api.get(`/trips/${tripid}`), [tripid])
  const [payers] = useLoad(() => api.get('/company/payers'), [])
  // The same lists Book A Trip chooses from, and the same way to add to them.
  const [riders, , reloadRiders] = useLoad(() => api.get('/passengers'), [])
  const [places, , reloadPlaces] = useLoad(() => api.get('/places'), [])
  const [adding, setAdding] = useState(null)       // { kind, leg? }
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (trip && !f) {
    setF({
      passenger: trip.passenger || '', passengerphone: trip.passengerphone || '',
      servicelevel: trip.servicelevel || 'ambulatory', brokerid: trip.brokerid || '',
      payer: trip.payer || 'private', note: trip.note || '', reason: '',
      legs: trip.legs.map((l) => ({
        legid: l.recordid, legnumber: l.legnumber, pickupat: clock(l.pickupat),
        dropoffat: clock(l.dropoffat), appointmentat: clock(l.appointmentat), route: null,
        byhand: false, placeid: '', pickupplace: l.pickupplace || '',
        dropoffplace: l.dropoffplace || '', miles: l.miles ?? '',
      })),
    })
  }
  if (!trip || !f) {
    return <Modal title="Edit Trip" onClose={onClose}><Loading error={error} /></Modal>
  }

  const rules = trip.edit
  const set = (k, upper) => (e) => setF({ ...f, [k]: upper ? e.target.value.toUpperCase() : e.target.value })
  const setLeg = (n, k, upper) => (e) => setF({
    ...f, legs: f.legs.map((l, i) => (i === n ? { ...l, [k]: upper ? e.target.value.toUpperCase() : e.target.value } : l)),
  })
  const shut = !rules.tripfields
  const may = (leg, field) => ({
    open: ['pickupat', 'pickupplace', 'dropoffplace'],
    moving: ['dropoffplace'],
    done: [],
    closed: [],
  }[rules.legs[leg.legid]] || []).includes(field)
  const ready = f.passenger.trim() && (!rules.reasonrequired || f.reason.trim())
  const putLeg = (n, patch) => setF((was) => ({ ...was, legs: was.legs.map((l, i) => (i === n ? { ...l, ...patch } : l)) }))
  const pickRider = (id, list = riders?.items) => {
    const r = (list || []).find((x) => x.recordid === id)
    if (r) setF((was) => ({ ...was, passengerid: id, passenger: r.name, passengerphone: r.phone || was.passengerphone }))
  }
  const pickPlace = (n, id, list = places?.items) => {
    const p = (list || []).find((x) => x.recordid === id)
    if (p) { putLeg(n, { placeid: id, dropoffplace: p.full || p.address }); routeFor(n, { dropoffplace: p.full || p.address }) }
  }
  // An appointment works the pickup back from the drive, the same as Book A Trip: the drive and ten
  // minutes before it. A pickup changed by hand stands.
  const routeFor = (n, patch = {}) => {
    const l = { ...f.legs[n], ...patch }
    if (!l.appointmentat || !l.pickupplace.trim() || !l.dropoffplace.trim()) return
    const qs = new URLSearchParams({ pickup: l.pickupplace.trim(), dropoff: l.dropoffplace.trim(), arrive: `${l.appointmentat}:00` })
    api.get(`/route-estimate?${qs}`)
      .then((got) => putLeg(n, { route: got, ...(l.byhand ? {} : { pickupat: `${l.appointmentat.slice(0, 10)}T${got.pickupat}` }) }))
      .catch((e) => putLeg(n, { route: { error: e.message } }))
  }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.put(`/trips/${tripid}`, {
        passenger: f.passenger, passengerphone: f.passengerphone.trim() || null,
        servicelevel: f.servicelevel, brokerid: f.brokerid || null, payer: f.payer,
        note: f.note.trim() || null, reason: f.reason.trim() || null,
        legs: f.legs.map((l) => ({
          legid: l.legid,
          pickupat: l.pickupat ? `${l.pickupat}:00` : null,
          dropoffat: l.dropoffat ? `${l.dropoffat}:00` : null,
          appointmentat: l.appointmentat ? `${l.appointmentat}:00` : null,
          pickupplace: l.pickupplace, dropoffplace: l.dropoffplace,
          miles: l.miles === '' ? null : Number(l.miles),
        })),
      })
      onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (<>
    <Modal title={`Edit Trip - ${trip.externalid}`} onClose={onClose} width={860} tall
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        {!rules.locked && (
          <button type="button" className="primary" disabled={busy || !ready} onClick={save}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save Changes'}
          </button>
        )}
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {rules.locked && <div className="notice bad">{rules.locked}</div>}
        <fieldset disabled={Boolean(rules.locked)} className="plain stack">
          <div className="card qualcard">
          <div className="infotabs"><h3>The Trip</h3></div>
          <div className="panelbody stack">
          {shut && !rules.locked && (
            <div className="notice warn">The trip has started. The passenger, service and payer can no longer be changed.</div>
          )}
          <div className="profileform">
            <div className="field span-6">Passenger *
              <div className="pickadd">
                <SearchSelect items={riders?.items || []} value={f.passengerid || ''} onChange={pickRider} disabled={shut}
                  placeholder={f.passenger || 'Choose'}
                  label={(r) => `${r.name}${r.dob ? ` - DOB ${date(r.dob)}` : ''} - ${r.full || r.address}`} />
                <button type="button" disabled={shut} onClick={() => setAdding({ kind: 'passengers' })}>
                  <Plus size={13} /> New Passenger</button>
              </div>
            </div>
            <label className="field span-3">Telephone
              <PhoneInput value={f.passengerphone} onChange={set('passengerphone')} />
            </label>
            <label className="field span-3">Service
              <select value={f.servicelevel} disabled={shut} onChange={set('servicelevel')}>
                {Object.entries(payers?.services || {}).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </label>
            <label className="field span-3">Payer
              <select value={f.brokerid || 'private'} disabled={shut} onChange={(e) => {
                const id = e.target.value === 'private' ? '' : e.target.value
                const chosen = (payers?.payers || []).find((x) => x.recordid === id)
                setF({ ...f, brokerid: id, payer: chosen ? chosen.category : 'private' })
              }}>
                <option value="private">Private pay</option>
                {(payers?.payers || []).filter((x) => x.active || x.recordid === f.brokerid).map((x) => (
                  <option key={x.recordid} value={x.recordid}>{x.name}</option>
                ))}
              </select>
            </label>
          </div>
          </div>
          </div>

          {f.legs.map((l, n) => {
            const stage = rules.legs[l.legid]
            return (
              <div key={l.legid} className="card qualcard">
                <div className="infotabs"><h3>{f.legs.length > 1 ? `Leg ${l.legnumber}` : 'Pickup And Drop-Off'}</h3></div>
                <div className="panelbody stack">
                {STAGE[stage] && <div className="notice warn">{STAGE[stage]}</div>}
                <div className="profileform">
                  <label className="field span-3">Appointment Time
                    <input type="datetime-local" value={l.appointmentat} disabled={!may(l, 'pickupat')}
                      onChange={(e) => { const v = e.target.value; putLeg(n, { appointmentat: v, byhand: false }); routeFor(n, { appointmentat: v, byhand: false }) }} />
                  </label>
                  <label className="field span-3">Pickup Time
                    <input type="datetime-local" value={l.pickupat} disabled={!may(l, 'pickupat')}
                      onChange={(e) => putLeg(n, { pickupat: e.target.value, byhand: true })} />
                  </label>
                  <label className="field span-6">Pick Up At
                    <input value={l.pickupplace} className="upper" disabled={!may(l, 'pickupplace')}
                      onChange={setLeg(n, 'pickupplace', true)} />
                  </label>
                  <div className="field span-6">Drop Off At
                    <div className="pickadd">
                      <SearchSelect items={places?.items || []} value={l.placeid} disabled={!may(l, 'dropoffplace')}
                        placeholder={l.dropoffplace || 'Choose'} onChange={(id) => pickPlace(n, id)}
                        label={(p) => `${p.name} - ${p.full || p.address}`} />
                      <button type="button" disabled={!may(l, 'dropoffplace')}
                        onClick={() => setAdding({ kind: 'places', leg: n })}><Plus size={13} /> New Location</button>
                    </div>
                  </div>
                  {l.route && (
                    <div className={`span-6 routeline${l.route.error ? ' st-expired' : ''}`}>
                      {l.route.error ? l.route.error
                        : `${l.route.routed ? 'Drive' : 'Straight-line estimate'}: ${l.route.minutes} min, ${l.route.miles} mi, plus 10 min. `
                          + (l.byhand ? 'Pickup kept as entered.' : 'Pickup set from it.')}
                    </div>
                  )}
                </div>
                </div>
              </div>
            )
          })}

          <div className="card qualcard">
          <div className="infotabs"><h3>Note And Reason</h3></div>
          <div className="panelbody">
          <div className="profileform">
            <label className="field span-6">Note
              <textarea value={f.note} className="upper" onChange={set('note', true)} />
            </label>
            <label className="field span-6">Why Is It Being Changed{rules.reasonrequired ? ' *' : ''}
              <textarea value={f.reason} className="upper" onChange={set('reason', true)} />
            </label>
          </div>
          </div>
          </div>
        </fieldset>
      </div>
    </Modal>
    {adding && (
      <EntryDialog kind={adding.kind} onClose={() => setAdding(null)}
        onAdded={(got) => {
          const was = adding
          setAdding(null)
          if (was.kind === 'passengers') { reloadRiders(); pickRider(got.recordid, [got]) }
          else { reloadPlaces(); pickPlace(was.leg, got.recordid, [got]) }
        }} />
    )}
  </>)
}
