import { useEffect, useState } from 'react'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { api } from '../lib/api.js'
import { money } from '../lib/format.js'
import { Modal } from '../admin/common.jsx'
import { useLoad } from './ui.jsx'

// Booking a trip by hand - the telephone and private pay case.
//
// The part worth having is not the form, it is the answer to "who should take it". TripProof
// already knows who may lawfully drive, where everybody last was, how close each is to their
// hours and which vehicles have a lift, so the office should not be holding that in its head
// at nine in the morning with a phone ringing.
//
// Every candidate carries its reasons and NOBODY is hidden - a driver who cannot go is shown
// with why, because "where is Tim on this list" is the first thing a dispatcher asks. The
// suggestion is pre-selected and can be overruled: the ranking does not know that this
// passenger always asks for Maria.


const EMPTY = {
  passenger: '', passengerphone: '', tripdate: '', servicelevel: 'ambulatory',
  payer: 'private', brokerid: '', note: '', pickupplace: '', dropoffplace: '', pickupat: '',
  minutes: 60, ret: false, returnat: '',
}

export default function BookTrip({ onClose, onBooked }) {
  const [f, setF] = useState(EMPTY)
  // Who is being billed, by name. "Broker" as a word was never enough: which broker decides
  // which rule set the trip is checked against, so a trip booked without one is a trip checked
  // against the federal baseline alone.
  const [payers] = useLoad(() => api.get('/company/payers'), [])
  // What this trip will be billed at, and what picking this payer does to who may drive it.
  // Asked as the form is filled rather than discovered afterwards: a dispatcher choosing
  // MODIVCARE is choosing a rule set as well as a rate card, and should be told so at the time.
  const [quote, setQuote] = useState(null)
  const [who, setWho] = useState(null)          // the ranked answer
  const [asking, setAsking] = useState(false)
  const [driverid, setDriverid] = useState(null)
  const [vehicleid, setVehicleid] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const ready = f.passenger.trim() && f.tripdate && f.pickupat
    && f.pickupplace.trim() && f.dropoffplace.trim()

  // Asked for explicitly rather than on every keystroke: it reads the whole roster against
  // the compliance engine, which is not something to do while somebody is still typing.
  const ask = async () => {
    setAsking(true); setErr(null)
    try {
      const when = `${f.tripdate}T${f.pickupat}:00`
      const qs = new URLSearchParams({ when, minutes: String(f.minutes),
        service: f.servicelevel, seats: '1', payer: f.payer,
        pickupplace: f.pickupplace.trim(), dropoffplace: f.dropoffplace.trim() })
      if (f.brokerid) qs.set('payerid', f.brokerid)
      const got = await api.get(`/trips/suggest?${qs}`)
      setWho(got)
      setDriverid(got.suggested.driverid)
      setVehicleid(got.suggested.vehicleid)
    } catch (e) { setErr(e.message) } finally { setAsking(false) }
  }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const legs = [{
        pickupat: `${f.tripdate}T${f.pickupat}:00`,
        pickupplace: f.pickupplace.trim(),
        dropoffplace: f.dropoffplace.trim(),
        driverid, vehicleid,
      }]
      if (f.ret && f.returnat) {
        legs.push({
          pickupat: `${f.tripdate}T${f.returnat}:00`,
          pickupplace: f.dropoffplace.trim(),
          dropoffplace: f.pickupplace.trim(),
          driverid, vehicleid,
        })
      }
      const got = await api.post('/trips', {
        passenger: f.passenger.trim(),
        passengerphone: f.passengerphone.trim() || null,
        tripdate: f.tripdate,
        servicelevel: f.servicelevel,
        payer: f.payer,
        brokerid: f.brokerid || null,
        note: f.note.trim() || null,
        legs,
      })
      onBooked?.(got)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // The pickup's state, read off its address the way the server reads it, so a state's own fee
  // schedule prices the quote. Only the state is watched, not every keystroke of the address.
  const pickupstate = (f.pickupplace.toUpperCase().match(/\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b/g) || [])
    .map((m) => m.slice(0, 2)).pop() || ''
  useEffect(() => {
    if (!f.tripdate || !f.servicelevel) { setQuote(null); return }
    let dropped = false
    const legs = f.ret ? 2 : 1
    api.get(`/dispatch/quote?servicelevel=${f.servicelevel}&on=${f.tripdate}&legs=${legs}`
            + (f.brokerid ? `&payerid=${f.brokerid}` : '')
            + (pickupstate ? `&state=${pickupstate}` : ''))
      .then((q) => { if (!dropped) setQuote(q) })
      .catch(() => { if (!dropped) setQuote(null) })
    return () => { dropped = true }
  }, [f.tripdate, f.servicelevel, f.brokerid, f.ret, pickupstate])

  const row = (c, chosen, pick, id, label) => (
    <label key={id} className={`pickrow${c.available ? '' : ' barred'}`}>
      <input type="radio" name={label} checked={chosen === id} disabled={!c.available}
        onChange={() => pick(id)} />
      <span className="pickwho">{c.name}</span>
      <span className="pickwhy">
        {(c.blocked.length ? c.blocked : c.because).join(' · ')}
        {c.warnings?.length ? <b> · {c.warnings.join(' · ')}</b> : null}
      </span>
    </label>
  )

  return (
    <Modal title="Book A Trip" onClose={onClose} width={860} tall
      footer={<>
        <div className="footactions">
          <button type="button" disabled={!ready || asking} onClick={ask}>
            {asking ? <Loader2 size={15} className="spin" /> : 'Who Should Take It'}
          </button>
        </div>
        <button type="button" className="primary" disabled={busy || !ready} onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Book It'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className="field span-3">Passenger *
            <input value={f.passenger} className="upper"
              onChange={(e) => setF({ ...f, passenger: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-3">Telephone
            <input value={f.passengerphone} onChange={set('passengerphone')} />
          </label>
          <label className="field span-2">Date *
            <input type="date" value={f.tripdate} onChange={set('tripdate')} />
          </label>
          <label className="field span-2">Pickup Time *
            <input type="time" value={f.pickupat} onChange={set('pickupat')} />
          </label>
          <label className="field span-2">Service
            <select value={f.servicelevel} onChange={set('servicelevel')}>
              {Object.entries(payers?.services || {}).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
          <label className="field span-6">Pick Up At *
            <input value={f.pickupplace} className="upper"
              onChange={(e) => setF({ ...f, pickupplace: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-6">Drop Off At *
            <input value={f.dropoffplace} className="upper"
              onChange={(e) => setF({ ...f, dropoffplace: e.target.value.toUpperCase() })} />
          </label>
          {/* The company's own payer list, not two words. `payer` stays the KIND - what sort of
              arrangement this is - and `brokerid` says which one, because the engine reads the
              second and the fee schedule reads the first. */}
          <label className="field span-2">Payer
            <select value={f.brokerid || 'private'} onChange={(e) => {
              const id = e.target.value === 'private' ? '' : e.target.value
              const chosen = (payers?.payers || []).find((x) => x.recordid === id)
              setF({ ...f, brokerid: id, payer: chosen ? chosen.category : 'private' })
            }}>
              <option value="private">Private pay</option>
              {(payers?.payers || []).filter((x) => x.active).map((x) => (
                <option key={x.recordid} value={x.recordid}>{x.name}</option>
              ))}
            </select>
          </label>
          {quote && (
            <div className="field span-2 quoted">
              <span className="quotelabel">Billed at</span>
              <span className="quoteamount">
                {quote.amount === null ? 'No price' : money(quote.amount)}
                {quote.amount !== null && !quote.complete ? '+' : ''}
              </span>
              <span className="quotewhy">
                {quote.schedulename ? `${quote.schedulename} · ${quote.why}` : quote.why}
                {quote.extrarequirements
                  ? ` This payer adds ${quote.extrarequirements} requirement${quote.extrarequirements === 1 ? '' : 's'}.`
                  : ''}
              </span>
            </div>
          )}
          <label className="field span-2">Allow
            <select value={f.minutes} onChange={set('minutes')}>
              {[30, 45, 60, 90, 120].map((m) => (
                <option key={m} value={m}>{m} minutes</option>
              ))}
            </select>
          </label>
          <label className="field span-2">Return
            <select value={f.ret ? 'yes' : 'no'}
              onChange={(e) => setF({ ...f, ret: e.target.value === 'yes' })}>
              <option value="no">One way</option>
              <option value="yes">Round trip</option>
            </select>
          </label>
          {f.ret && (
            <label className="field span-2">Return Time
              <input type="time" value={f.returnat} onChange={set('returnat')} />
            </label>
          )}
          <label className="field span-6">Note
            <textarea value={f.note} className="upper"
              onChange={(e) => setF({ ...f, note: e.target.value.toUpperCase() })} />
          </label>
        </div>

        {!who ? (
          <div className="notice">
            Fill the trip in, then ask who should take it - TripProof reads the roster against
            the requirements in force, where everybody last reported and what each vehicle can
            carry.
          </div>
        ) : (
          <>
            <section>
              <h3 className="formsection">Driver</h3>
              <div className="picklist">
                {who.drivers.map((d) => row(d, driverid, setDriverid, d.driverid, 'driver'))}
              </div>
            </section>
            <section>
              <h3 className="formsection">Vehicle</h3>
              <div className="picklist">
                {who.vehicles.map((v) => row(v, vehicleid, setVehicleid, v.vehicleid,
                  'vehicle'))}
              </div>
            </section>
          </>
        )}
      </div>
    </Modal>
  )
}
