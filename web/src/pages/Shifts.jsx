import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2, Pencil, Plus, Sparkles, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import { Candidates } from '../components/AssignDialog.jsx'

// The day's shifts: which vehicle each working driver takes, and over what hours.
//
// Laid out the way a day is read - one column per driver, the day running down the side in
// quarter hours - so who has what, and when, is seen at a glance rather than looked up. Each
// assignment is a block in its driver's column. No trips here: scheduling is Dispatch's.
//
// Every pairing is the compliance rules' to allow, and the server is what refuses one: the vehicle
// list here only shows the answer in advance, so nobody chooses a van and is told no afterwards.

const SLOT = 28                      // pixels per quarter hour
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const shift = (day, n) => { const [y, m, d] = day.split('-').map(Number); return ymd(new Date(y, m - 1, d + n)) }
const minutes = (hhmm) => { const [h, m] = String(hhmm).slice(0, 5).split(':').map(Number); return h * 60 + m }
const clock = (mins) => {
  const m = ((mins % 1440) + 1440) % 1440
  const h = Math.floor(m / 60)
  return `${h % 12 || 12}:${String(m % 60).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}
// A shift whose end is at or before its start runs past midnight.
// A new assignment runs over the company's hours that day (Company page, Hours Of Operation);
// eight to five where none are set.
const opens = (data) => data.hours?.open || '08:00'
const closes = (data) => data.hours?.close || '17:00'
const ends = (s) => { const a = minutes(s.startsat); const b = minutes(s.endsat); return b > a ? b : b + 1440 }

export default function Shifts() {
  const [day, setDay] = useState(() => ymd(new Date()))
  const [data, error, reload] = useLoad(() => api.get(`/shifts?day=${day}`), [day])
  const [editing, setEditing] = useState(null)     // {} new, or a shift
  const [removing, setRemoving] = useState(null)
  const [generating, setGenerating] = useState(false)

  // The page fills the window and only the board scrolls - the way Dispatch is laid out - so the
  // driver and vehicle headers stay pinned above the day however far down it is read.
  return (
    <div className="fill wide">
      <div className="pagehead daypagehead">
        <h1>Vehicle Assignments</h1>
        <div className="segs daypick">
          <button type="button" className="chip" title="The day before" aria-label="The day before"
            onClick={() => setDay(shift(day, -1))}><ChevronLeft size={16} /></button>
          <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
          <button type="button" className="chip" title="The day after" aria-label="The day after"
            onClick={() => setDay(shift(day, 1))}><ChevronRight size={16} /></button>
        </div>
        <div className="row pushright">
          <Link className="btn back" to="/dispatch"><ChevronLeft size={14} /> Back To Dispatch</Link>
          <button type="button" onClick={() => setEditing({})}><Plus size={14} /> Add Assignment</button>
          <button type="button" onClick={() => setGenerating(true)}>
            <Sparkles size={14} /> Auto Generate
          </button>
        </div>
      </div>

      {!data ? <Loading error={error} page /> : (
        <Board data={data} onEdit={setEditing} />
      )}

      {editing && data && (
        <ShiftDialog day={day} data={data} start={editing}
          onRemove={() => { setRemoving(editing); setEditing(null) }}
          onClose={() => setEditing(null)} onDone={() => { setEditing(null); reload() }} />
      )}
      {removing && (
        <Modal title="Remove Assignment" onClose={() => setRemoving(null)} width={520}
          footer={<RemoveButtons shift={removing} onClose={() => setRemoving(null)}
            onDone={() => { setRemoving(null); reload() }} />}>
          <div className="stack">
            <div className="askorder"><span className="askmark">?</span>
              <p>Remove {removing.drivername}&rsquo;s assignment to {removing.vehiclename}?</p></div>
          </div>
        </Modal>
      )}
      {generating && data && (
        <GenerateDialog day={day} data={data} onClose={() => setGenerating(false)}
          onDone={() => { setGenerating(false); reload() }} />
      )}
    </div>
  )
}

function RemoveButtons({ shift: s, onClose, onDone }) {
  const [busy, setBusy] = useState(false)
  return <>
    <button type="button" className="primary" disabled={busy}
      onClick={async () => { setBusy(true); await api.del(`/shifts/${s.recordid}`); onDone() }}>
      {busy ? <Loader2 size={15} className="spin" /> : 'Yes'}
    </button>
    <button type="button" onClick={onClose}>No</button>
  </>
}

// One column per active driver. A driver who changes vehicles during the day has a block for each,
// in order.
function Board({ data, onEdit }) {
  const columns = useMemo(() => {
    // Every active driver has a column, so who has nothing that day is as plain as who does.
    const byDriver = new Map(data.drivers.map((d) => [d.driverid, { driverid: d.driverid, name: d.name, shifts: [] }]))
    data.shifts.forEach((s) => {
      if (!byDriver.has(s.driverid)) byDriver.set(s.driverid, { driverid: s.driverid, name: s.drivername, shifts: [] })
      byDriver.get(s.driverid).shifts.push(s)
    })
    byDriver.forEach((c) => c.shifts.sort((a, b) => minutes(a.startsat) - minutes(b.startsat)))
    return [...byDriver.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [data])

  // The hours shown: the company's that day (Company page), or six to eight where none are set -
  // stretched to whatever is on the board, the stretch shaded as out of hours.
  const open = data.hours?.open ? [minutes(data.hours.open), ends({ startsat: data.hours.open, endsat: data.hours.close })] : null
  const [from, to] = useMemo(() => {
    let lo = open ? open[0] : 6 * 60
    let hi = open ? open[1] : 20 * 60
    columns.forEach((c) => {
      c.shifts.forEach((s) => { lo = Math.min(lo, minutes(s.startsat)); hi = Math.max(hi, ends(s)) })
    })
    return [Math.floor(lo / 60) * 60, Math.ceil(hi / 60) * 60]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columns, data.hours])
  const slots = []
  for (let m = from; m < to; m += 15) slots.push(m)
  const top = (m) => ((m - from) / 15) * SLOT

  return (
    <div className="card shiftboard">
      <div className="shiftscroll">
        <div className="shiftgutter">
          <div className="shifthead" />
          {slots.map((m) => <div key={m} className="shiftslot">{clock(m)}</div>)}
        </div>
        {columns.map((c) => (
          <div key={c.driverid} className="shiftcol">
            <div className={`shifthead${c.shifts.length ? '' : ' unassigned'}`}>
              <b>{c.name.toUpperCase()}</b>
              <span>{!c.shifts.length ? 'No Vehicles Assigned To Driver For This Day'
                : c.shifts.length === 1
                  ? `${c.shifts[0].vehiclename}${c.shifts[0].vehicledescr ? ` · ${c.shifts[0].vehicledescr}` : ''}`
                  : c.shifts.map((s) => s.vehiclename).join(' → ')}</span>
            </div>
            <div className="shiftbody" style={{ height: slots.length * SLOT }}>
              {open && open[0] > from && <div className="offhours" style={{ top: 0, height: top(open[0]) }} />}
              {open && open[1] < to && <div className="offhours" style={{ top: top(open[1]), height: top(to) - top(open[1]) }} />}
              {slots.map((m) => <div key={m} className="shiftline" style={{ top: top(m) }} />)}
              {c.shifts.map((s) => (
                <button key={s.recordid} type="button" className="shiftblock" title="Change this assignment"
                  onClick={() => onEdit(s)}
                  style={{ top: top(minutes(s.startsat)) + 1,
                           height: ((ends(s) - minutes(s.startsat)) / 15) * SLOT - 2 }}>
                  <Pencil size={12} /> {s.vehiclename} · {clock(minutes(s.startsat))} - {clock(ends(s))}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Adding or changing one shift. The driver and the hours first; then every vehicle, with whether
// this driver may take it - the same list the dispatch board shows for a trip.
function ShiftDialog({ day, data, start, onRemove, onClose, onDone }) {
  const known = Boolean(start.recordid)
  const [f, setF] = useState({
    driverid: start.driverid || '', vehicleid: start.vehicleid || null,
    startsat: start.startsat || opens(data), endsat: start.endsat || closes(data),
  })
  const [fits, setFits] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const lookup = async (driverid, startsat) => {
    setFits(null)
    if (!driverid) return
    try { setFits((await api.post('/shifts/fit', { day, driverid, startsat })).vehicles) }
    catch (e) { setErr(e.message) }
  }
  // A shift being changed opens with its driver's vehicles already listed.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (start.driverid) lookup(start.driverid, start.startsat) }, [])
  const pickDriver = (driverid) => {
    const next = { ...f, driverid, vehicleid: null }
    setF(next)
    lookup(driverid, next.startsat)
  }
  // Adding a shift that starts while the driver is on another one is changing vehicles at that time:
  // said before it is saved, and the earlier shift ends there when it is.
  const running = !known && f.driverid && data.shifts.find((s) => {
    if (s.driverid !== f.driverid) return false
    const t = minutes(f.startsat)
    return minutes(s.startsat) < t && t < ends(s)
  })
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = { day, driverid: f.driverid, vehicleid: f.vehicleid, startsat: f.startsat,
                     endsat: f.endsat, switch: Boolean(running) }
      if (known) await api.put(`/shifts/${start.recordid}`, body)
      else await api.post('/shifts', body)
      onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal title={known ? 'Change Assignment' : 'Add An Assignment'} onClose={onClose} width={860}
      footer={<>
        {known && (
          <div className="footactions">
            <button type="button" className="danger" onClick={onRemove}><X size={14} /> Remove Assignment</button>
          </div>
        )}
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !f.driverid || !f.vehicleid}
          onClick={save}>{busy ? <Loader2 size={15} className="spin" /> : 'Save'}</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {running && (
          <div className="notice warn">
            {running.drivername} is in {running.vehiclename} {clock(minutes(running.startsat))} - {clock(ends(running))}.
            Saving switches them at {clock(minutes(f.startsat))}: that assignment ends then.
          </div>
        )}
        <div className="profileform">
          <label className="field span-3">Driver *
            <select value={f.driverid} onChange={(e) => pickDriver(e.target.value)}>
              <option value="" disabled>Choose a driver</option>
              {data.drivers.map((d) => <option key={d.driverid} value={d.driverid}>{d.name}</option>)}
            </select>
          </label>
          <label className="field span-1">Starts *
            <input type="time" value={f.startsat} onChange={(e) => setF({ ...f, startsat: e.target.value })} />
          </label>
          <label className="field span-1">Ends *
            <input type="time" value={f.endsat} onChange={(e) => setF({ ...f, endsat: e.target.value })} />
          </label>
        </div>
        {f.driverid && (fits ? (
          <Candidates title="Vehicle" rows={fits} idkey="vehicleid" chosen={f.vehicleid}
            onPick={(vehicleid) => setF({ ...f, vehicleid })} />
        ) : <Loading />)}
      </div>
    </Modal>
  )
}

// Auto generation: which drivers are working - ticked where they already have a vehicle that day - and their
// hours; then the proposal, with why each vehicle was chosen. Nothing is saved until Save.
function GenerateDialog({ day, data, onClose, onDone }) {
  // A driver who switches vehicles has several shifts that day: their day runs from the first start
  // to the last end.
  const planned = new Map()
  for (const s of data.shifts) {
    const was = planned.get(s.driverid)
    planned.set(s.driverid, was ? { startsat: s.startsat < was.startsat ? s.startsat : was.startsat,
                                    endsat: s.endsat > was.endsat ? s.endsat : was.endsat } : s)
  }
  // Only the drivers some vehicle is lawful for - asked for when the dialog opens.
  const [who, setWho] = useState(null)
  const [proposal, setProposal] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  useEffect(() => {
    api.post('/shifts/eligible', { day }).then((got) => {
      const ok = new Set(got.drivers)
      setWho(data.drivers.filter((d) => ok.has(d.driverid)).map((d) => {
        const s = planned.get(d.driverid)
        return { driverid: d.driverid, name: d.name, on: Boolean(s),
                 startsat: s?.startsat || opens(data),
                 endsat: s?.endsat || closes(data) }
      }))
    }).catch((e) => setErr(e.message))
  }, [day])
  const setRow = (i, k, v) => setWho(who.map((w, n) => (n === i ? { ...w, [k]: v } : w)))
  const generate = async () => {
    setBusy(true); setErr(null)
    try {
      const got = await api.post('/shifts/generate', {
        day, drivers: who.filter((w) => w.on).map(({ driverid, startsat, endsat }) => ({ driverid, startsat, endsat })),
      })
      setProposal(got.proposal)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/shifts/plan', {
        day, shifts: proposal.filter((p) => p.vehicleid).map((p) => ({
          day, driverid: p.driverid, vehicleid: p.vehicleid, startsat: p.startsat,
          endsat: p.endsat, reasons: p.reasons, source: 'auto',
        })),
      })
      onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal title="Auto Generate Vehicle Assignments" onClose={onClose} width={900} tall
      footer={proposal ? <>
        <button type="button" onClick={() => setProposal(null)}>Back</button>
        <button type="button" className="primary" disabled={busy || !proposal.some((p) => p.vehicleid)}
          onClick={save}>{busy ? <Loader2 size={15} className="spin" /> : 'Save'}</button>
      </> : <>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !who?.some((w) => w.on)}
          onClick={generate}>{busy ? <Loader2 size={15} className="spin" /> : 'Generate'}</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {!who ? (!err && <Loading />) : !proposal ? (
          <table className="residencetable recordtable shiftpick">
            <thead><tr><th /><th>Driver</th><th>Starts</th><th>Ends</th></tr></thead>
            <tbody>
              {who.map((w, i) => (
                <tr key={w.driverid}>
                  <td><input type="checkbox" checked={w.on} onChange={(e) => setRow(i, 'on', e.target.checked)} /></td>
                  <td>{w.name}</td>
                  <td><input type="time" value={w.startsat} disabled={!w.on}
                    onChange={(e) => setRow(i, 'startsat', e.target.value)} /></td>
                  <td><input type="time" value={w.endsat} disabled={!w.on}
                    onChange={(e) => setRow(i, 'endsat', e.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="residencetable recordtable shiftproposal">
            <thead><tr><th>Driver</th><th>Vehicle</th><th>Hours</th><th>Why</th></tr></thead>
            <tbody>
              {proposal.map((p) => (
                <tr key={p.driverid}>
                  <td>{p.drivername}</td>
                  <td className={p.vehicleid ? undefined : 'st-expired'}>{p.vehiclename || 'None'}</td>
                  <td>{clock(minutes(p.startsat))} - {clock(minutes(p.endsat))}</td>
                  <td className={p.vehicleid ? undefined : 'st-expired'}>
                    {p.vehicleid ? [...p.reasons, p.hours && `${p.hours} on duty this week`].filter(Boolean).join(' · ')
                      : p.blocked.join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Modal>
  )
}
