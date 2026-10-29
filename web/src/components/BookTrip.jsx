import { useEffect, useState } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, money } from '../lib/format.js'
import { Modal } from '../admin/common.jsx'
import { useLoad } from './ui.jsx'
import SearchSelect from './SearchSelect.jsx'
import { PhoneInput, ZipInput } from './MaskedInput.jsx'
import { US_STATES } from '../admin/CustomerProfile.jsx'

// Booking a trip by hand - the telephone and private pay case. Who drives it is decided on
// Dispatch, where every trip of the day is assigned: booking only writes the trip down.


const EMPTY = {
  passenger: '', passengerphone: '', tripdate: '', servicelevel: 'ambulatory',
  payer: 'private', brokerid: '', note: '', pickupplace: '', dropoffplace: '', pickupat: '',
  ret: 'no', returnat: '', appointmentat: '',
}

export default function BookTrip({ onClose, onBooked }) {
  // Most trips are booked for today, so the date starts there.
  const [f, setF] = useState(() => {
    const d = new Date()
    const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return { ...EMPTY, tripdate: today }
  })
  // The drive from the pickup to the drop-off, worked out once the appointment, the pickup and the
  // drop-off are all known; the pickup time is set from it - the drive and ten minutes before the
  // appointment - and can still be changed.
  const [route, setRoute] = useState(null)
  // A pickup time typed in by hand stands: the route is still said, but it no longer moves the time.
  // A new appointment time is a new question, and sets it again.
  const [byHand, setByHand] = useState(false)
  useEffect(() => {
    setRoute(null)
    if (!f.tripdate || !f.appointmentat || !f.pickupplace.trim() || !f.dropoffplace.trim()) return undefined
    let dropped = false
    const wait = setTimeout(() => {
      const qs = new URLSearchParams({ pickup: f.pickupplace.trim(), dropoff: f.dropoffplace.trim(),
                                       arrive: `${f.tripdate}T${f.appointmentat}:00` })
      api.get(`/route-estimate?${qs}`)
        .then((got) => {
          if (dropped) return
          setRoute(got)
          if (!byHand) setF((was) => ({ ...was, pickupat: got.pickupat }))
        })
        .catch((e) => { if (!dropped) setRoute({ error: e.message }) })
    }, 500)
    return () => { dropped = true; clearTimeout(wait) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.tripdate, f.appointmentat, f.pickupplace, f.dropoffplace])
  // Who is being billed, by name. "Broker" as a word was never enough: which broker decides
  // which rule set the trip is checked against, so a trip booked without one is a trip checked
  // against the federal baseline alone.
  const [payers] = useLoad(() => api.get('/company/payers'), [])
  // The passengers and places already on file, chosen from rather than typed again.
  const [riders, , reloadRiders] = useLoad(() => api.get('/passengers'), [])
  const [places, , reloadPlaces] = useLoad(() => api.get('/places'), [])
  const [passengerid, setPassengerid] = useState('')
  const [placeid, setPlaceid] = useState('')
  const [adding, setAdding] = useState(null)       // 'passengers' | 'places'
  const pickRider = (id, list = riders?.items) => {
    const r = (list || []).find((x) => x.recordid === id)
    setPassengerid(id)
    // Their own telephone, and their home as the pickup - which can still be changed.
    setF((was) => ({ ...was, passenger: r?.name || '', passengerphone: r?.phone || '',
                     pickupplace: r?.full || r?.address || '' }))
  }
  const pickPlace = (id, list = places?.items) => {
    const p = (list || []).find((x) => x.recordid === id)
    setPlaceid(id)
    setF((was) => ({ ...was, dropoffplace: p?.full || p?.address || '' }))
  }
  // What this trip will be billed at, and what picking this payer does to who may drive it.
  // Asked as the form is filled rather than discovered afterwards: a dispatcher choosing
  // MODIVCARE is choosing a rule set as well as a rate card, and should be told so at the time.
  const [quote, setQuote] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  // A round trip needs its return time; a will-call return is the one that does not.
  const ready = f.passenger.trim() && f.tripdate && f.pickupat
    && f.pickupplace.trim() && f.dropoffplace.trim() && (f.ret !== 'yes' || f.returnat)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const legs = [{
        pickupat: `${f.tripdate}T${f.pickupat}:00`,
        pickupplace: f.pickupplace.trim(),
        dropoffplace: f.dropoffplace.trim(),
        appointmentat: f.appointmentat ? `${f.tripdate}T${f.appointmentat}:00` : null,
      }]
      if (f.ret === 'yes') {
        legs.push({
          pickupat: `${f.tripdate}T${f.returnat}:00`,
          pickupplace: f.dropoffplace.trim(),
          dropoffplace: f.pickupplace.trim(),
        })
      } else if (f.ret === 'willcall') {
        // No time and nobody on it yet: who is free and nearest is a question for when the
        // passenger rings, not for now.
        legs.push({
          pickupat: null,
          pickupplace: f.dropoffplace.trim(),
          dropoffplace: f.pickupplace.trim(),
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
    const legs = f.ret === 'no' ? 1 : 2
    api.get(`/dispatch/quote?servicelevel=${f.servicelevel}&on=${f.tripdate}&legs=${legs}`
            + (f.brokerid ? `&payerid=${f.brokerid}` : '')
            + (pickupstate ? `&state=${pickupstate}` : ''))
      .then((q) => { if (!dropped) setQuote(q) })
      .catch(() => { if (!dropped) setQuote(null) })
    return () => { dropped = true }
  }, [f.tripdate, f.servicelevel, f.brokerid, f.ret, pickupstate])

  return (<>
    <Modal title="Book A Trip" onClose={onClose} width={860}
      footer={<>
        <button type="button" className="primary" disabled={busy || !ready} onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Book It'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <div className="field span-6">Passenger *
            <div className="pickadd">
              <SearchSelect items={riders?.items || []} value={passengerid} onChange={pickRider}
                label={(r) => `${r.name}${r.dob ? ` - DOB ${date(r.dob)}` : ''} - ${r.full || r.address}`} />
              <button type="button" onClick={() => setAdding('passengers')}><Plus size={13} /> New Passenger</button>
            </div>
          </div>
          <div className="field span-6">Drop Off At *
            <div className="pickadd">
              <SearchSelect items={places?.items || []} value={placeid} onChange={pickPlace}
                label={(p) => `${p.name} - ${p.full || p.address}`} />
              <button type="button" onClick={() => setAdding('places')}><Plus size={13} /> New Location</button>
            </div>
          </div>
          <div className="fourup span-6">
            <label className="field">Date *
              <input type="date" value={f.tripdate} onChange={set('tripdate')} />
            </label>
            <label className="field">Appointment Time
              <input type="time" value={f.appointmentat}
                onChange={(e) => { setByHand(false); setF({ ...f, appointmentat: e.target.value }) }} />
            </label>
            <label className="field">Pickup Time *
              <input type="time" value={f.pickupat}
                onChange={(e) => { setByHand(true); setF({ ...f, pickupat: e.target.value }) }} />
            </label>
            <label className="field">Service
              <select value={f.servicelevel} onChange={set('servicelevel')}>
                {Object.entries(payers?.services || {}).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="field span-2">Telephone
            <PhoneInput value={f.passengerphone} onChange={set('passengerphone')} />
          </label>
          <label className="field span-4">Pick Up At *
            <input value={f.pickupplace} className="upper"
              onChange={(e) => setF({ ...f, pickupplace: e.target.value.toUpperCase() })} />
          </label>
          {route && (
            <div className={`span-6 routeline${route.error ? ' st-expired' : ''}`}>
              {route.error ? route.error
                : `${route.routed ? 'Drive' : 'Straight-line estimate'}: ${route.minutes} min, ${route.miles} mi, plus 10 min. `
                  + (byHand && f.pickupat !== route.pickupat ? `Worked out ${clock(route.pickupat)}; pickup kept as entered.`
                    : `Pickup set to ${clock(route.pickupat)}.`)}
            </div>
          )}
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
          <label className="field span-2">Return
            <select value={f.ret} onChange={(e) => setF({ ...f, ret: e.target.value })}>
              <option value="no">One way</option>
              <option value="yes">Round trip</option>
              <option value="willcall">Round trip, will-call</option>
            </select>
          </label>
          {f.ret === 'yes' && (
            <label className="field span-2">Return Time *
              <input type="time" value={f.returnat} onChange={set('returnat')} />
            </label>
          )}
          <label className="field span-6">Note
            <textarea value={f.note} className="upper"
              onChange={(e) => setF({ ...f, note: e.target.value.toUpperCase() })} />
          </label>
          {/* What it will be billed at, for a payer: one line, under the rest. Private pay has none. */}
          {f.brokerid && quote && (
            <div className="span-6 billedline">
              <b>Billed at {quote.amount === null ? 'no price' : money(quote.amount)}{quote.amount !== null && !quote.complete ? '+' : ''}</b>
              {' · '}{quote.schedulename ? `${quote.schedulename} · ${quote.why}` : quote.why}
              {quote.extrarequirements
                ? ` This payer adds ${quote.extrarequirements} requirement${quote.extrarequirements === 1 ? '' : 's'}.`
                : ''}
            </div>
          )}
        </div>

      </div>
    </Modal>
    {adding && (
      <EntryDialog kind={adding} onClose={() => setAdding(null)}
        // The new one is chosen at once; the list is read again so it is there to choose next time.
        onAdded={(got) => {
          setAdding(null)
          if (adding === 'passengers') { reloadRiders(); pickRider(got.recordid, [got]) }
          else { reloadPlaces(); pickPlace(got.recordid, [got]) }
        }} />
    )}
  </>)
}

// A new passenger or place, not on the list yet: a name, an address and a telephone.
// `entry`: one already on the list, being put right (or, with `onRemoved`, taken off it).
export function EntryDialog({ kind, entry = null, onClose, onAdded, onRemoved }) {
  const [v, setV] = useState(() => ({ name: '', address: '', city: '', state: '', zip: '', phone: '', dob: '',
    ...(entry ? Object.fromEntries(Object.entries(entry).map(([k, x]) => [k, x ?? ''])) : {}),
    ...(entry?.dob ? { dob: String(entry.dob).slice(0, 10) } : {}) }))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [asking, setAsking] = useState(false)
  const passenger = kind === 'passengers'
  const save = async () => {
    setBusy(true); setErr(null)
    const body = { name: v.name, address: v.address, city: v.city, state: v.state, zip: v.zip, phone: v.phone,
                   dob: passenger ? v.dob : null }
    try { onAdded(await (entry ? api.put(`/${kind}/${entry.recordid}`, body) : api.post(`/${kind}`, body))) }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  const noun = passenger ? 'Passenger' : 'Location'
  if (asking) {
    return (
      <Modal title={`Remove ${noun}`} onClose={() => setAsking(false)} width={520}
        footer={<>
          <button type="button" className="primary" disabled={busy}
            onClick={async () => { setBusy(true); await api.del(`/${kind}/${entry.recordid}`); onRemoved() }}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Yes'}
          </button>
          <button type="button" onClick={() => setAsking(false)}>No</button>
        </>}>
        <div className="stack">
          <div className="askorder"><span className="askmark">?</span>
            <p>Remove {entry.name} from the {passenger ? 'passengers' : 'locations'}?</p></div>
        </div>
      </Modal>
    )
  }
  return (
    <Modal title={entry ? `Change ${noun}` : `New ${noun}`} onClose={onClose} width={620}
      footer={<>
        {entry && onRemoved && (
          <div className="footactions">
            <button type="button" className="danger" onClick={() => setAsking(true)}>Remove {noun}</button>
          </div>
        )}
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !v.name.trim() || !v.address.trim() || !v.city.trim() || !v.state || !v.zip
                  || (passenger && !v.dob)} onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className={`field ${passenger ? 'span-2' : 'span-4'}`}>Name *
            <input value={v.name} className="upper" onChange={(e) => setV({ ...v, name: e.target.value.toUpperCase() })} />
          </label>
          {/* Asked of a caller to be sure which passenger they are. */}
          {passenger && (
            <label className="field span-2">Date Of Birth *
              <input type="date" value={v.dob} onChange={(e) => setV({ ...v, dob: e.target.value })} />
            </label>
          )}
          <label className="field span-2">Telephone
            <PhoneInput value={v.phone} onChange={(e) => setV({ ...v, phone: e.target.value })} />
          </label>
          <label className="field span-6">Address *
            <input value={v.address} className="upper" autoComplete="address-line1"
              onChange={(e) => setV({ ...v, address: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-3">City *
            <input value={v.city} className="upper" autoComplete="address-level2"
              onChange={(e) => setV({ ...v, city: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-1">State *
            <select value={v.state} onChange={(e) => setV({ ...v, state: e.target.value })}>
              <option value="">Choose</option>
              {US_STATES.map((st) => <option key={st}>{st}</option>)}
            </select>
          </label>
          <label className="field span-2">ZIP *
            <ZipInput value={v.zip} onChange={(e) => setV({ ...v, zip: e.target.value })} />
          </label>
        </div>
      </div>
    </Modal>
  )
}

// "14:05" as the office reads it: 2:05 PM.
function clock(hhmm) {
  const [h, m] = String(hhmm).split(':').map(Number)
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}
