import { useLayoutEffect, useRef, useState } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import { date, money } from '../lib/format.js'

// What this company charges, and what a payer contracts to pay it.
//
// Two different numbers held the same way. Private pay is what a passenger is billed direct;
// a broker schedule is what that broker has agreed to pay, which is frequently less. Keeping
// them apart is the only way to see where the shortfall is.
//
// Rates are LINES rather than columns, because a base fare, a mileage rate and a waiting
// charge are the same kind of thing with different units - and because the next contract
// will invent a charge nobody has a column for.
// A new price list starts today unless somebody says otherwise. Local date, not UTC:
// toISOString() in the evening dates a schedule tomorrow.
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// What a schedule's state actually is, from the two facts that decide it. Active is a
// switch meaning "count this at all"; the dates say which days it governs. Reading only the
// switch, a card that ended last February and one that starts next March both said "Active",
// which is true and tells nobody anything.
//
// A superseded schedule stays active on purpose: in_force requires it, so switching it off
// would stop it pricing the days it actually did price - and a trip carried in February has
// to stay explainable for ever.
function standing(x) {
  if (!x.active) return ['st-inactive', 'Retired']
  const from = String(x.effectivefrom || '').slice(0, 10)
  const to = String(x.effectiveto || '').slice(0, 10)
  if (to && to < today()) return ['st-inactive', 'Ended']
  if (from > today()) return ['st-inactive', `Starts ${date(x.effectivefrom)}`]
  return ['st-active', 'In force']
}

const BLANK = {
  name: '', payertype: '',
  effectivefrom: '',
  effectiveto: '', note: '', active: true,
}
const BLANKRATE = {
  ratetype: 'base', name: '', servicelevel: '', unit: 'trip', amount: '', includedunits: '',
  minimumunits: '', rounding: '', proceduracode: '', modifier: '', authrequired: false,
  loadedonly: true,
}


// Five included miles is "5", not "5.00". The column holds a count of miles or of quarter
// hours, and money's two decimal places on it read as a precision nobody meant. Nothing
// where there is nothing: an empty cell says "this charge has none" without putting a mark
// in every row of three mostly-empty columns.
const plain = (v) => (v === '' || v === null || v === undefined ? '' : String(Number(v)))

// What a line charges, in one phrase. "$3.50 per loaded mile", not 3.50 / mile / tick.
// Loaded belongs in the words rather than a column of its own: it qualifies the mile, and a
// ticked box three columns away leaves the reader to join them up.
function says(l, data) {
  const unit = data.units[l.unit] || l.unit
  const miles = l.ratetype === 'mileage' && l.loadedonly
  return `${money(l.amount || 0)} ${miles ? unit.replace('per ', 'per loaded ') : unit}`
}

// One grid, but not in whatever order the lines were typed: the per-service rates first in
// the order the services are listed, then the charges that apply to all of them. Shared last
// because they are the exceptions, and reading them first makes the per-service prices look
// like the exceptions instead.
//
// Applied when a line is FINISHED, never while it is being filled in. Sorting on every
// change meant choosing Wheelchair sent the row you were working on somewhere else before
// you had typed its amount, and you had to go and find it again.
function ordered(lines, services) {
  const rank = Object.keys(services)
  const at = (l) => {
    const i = rank.indexOf(l.servicelevel || '')
    return i === -1 ? rank.length : i
  }
  return [...lines].sort((a, b) => at(a) - at(b))
}

// Sorted here rather than on the server: a company has a handful of schedules, and a round
// trip to reorder six rows is a round trip nobody should wait for.
function sorted(list, sort, dir) {
  const flip = dir === 'desc' ? -1 : 1
  return [...list].sort((a, b) => {
    const x = a[sort] ?? '', y = b[sort] ?? ''
    if (x === y) return a.name.localeCompare(b.name)
    return (x > y ? 1 : -1) * flip
  })
}

export default function FeeSchedules() {
  const [data, error, reload] = useLoad(() => api.get('/company/rates'), [])
  const [editing, setEditing] = useState(null)
  const [retiring, setRetiring] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const g = useGridParams({ defaultSort: 'name', defaultDir: 'asc' })

  // Copy and Supersede are the same act - a new schedule carrying this one's rates. They
  // differ in one thing: a supersede also ends the original, and only once the replacement
  // has been saved.
  const standingOf = async (x, active) => {
    setBusy(x.recordid); setErr(null)
    try { await api.post(`/company/rates/${x.recordid}/active`, { active }); reload() }
    catch (e) { setErr(e.message) }
    finally { setBusy(null); setRetiring(null) }
  }

  const start = async (x, how) => {
    const full = await api.get(`/company/rates/${x.recordid}`)
    const rates = (full.rates || []).map(({ recordid: _line, ...r }) => r)
    setEditing({
      ...full, rates, recordid: undefined,
      name: how === 'copy' ? `${full.name} (COPY)` : full.name,
      effectivefrom: '', effectiveto: '',
      ...(how === 'supersede'
        ? { supersedes: full.recordid, replacing: full.name } : {}),
    })
  }

  if (!data) return <Loading error={error} page />
  const held = data.schedules || []

  const shown = sorted(held, g.sort, g.dir)
  const page = shown.slice((g.page - 1) * g.pagesize, g.page * g.pagesize)

  return (
    // `fill` rather than `stack`: a list page gives its grid the height of the playground,
    // so the rows scroll under the headings and the pager sits on the bottom edge instead of
    // the whole page scrolling and the pager drifting off.
    <div className="fill">
      <div className="pagehead">
        <div><h1>Fee Schedules</h1></div>
        {/* No seeded rate line. It made sense when a line was edited in the grid; now the
            line is written in a dialog, the seed just put a nameless $0.00 row in a table
            whose own rule is that every line has a name. */}
        <button type="button" className="primary"
          onClick={() => setEditing({ ...BLANK, rates: [] })}>
          <Plus size={14} /> Add A Schedule
        </button>
      </div>

      {/* THE grid, like every other list in the product: teal header band, sortable
          headings, rows scrolling beneath them. Hand-rolling a table here gave this page a
          look of its own, which is the one thing a list in TripProof should not have. */}
      {err && <div className="notice bad">{err}</div>}
      <DataGrid
        columns={[
          { id: 'name', label: 'Schedule' },
          // Billed as stands where Payer stood: it answers the same question from the side
          // that matters day to day - how the money is asked for - and the broker's name is
          // read beside the schedule's own.
          { id: 'billingmethod', label: 'Billed as', width: '20%' },
          // One column, not two: the dates bound a single span, and sorting a list of
          // schedules by when they end is not a thing anybody does.
          { id: 'effectivefrom', label: 'In force', width: 210 },
          { id: 'active', label: 'State', width: 110 },
          // Three 96px buttons, two 8px gaps and the cell's own padding. Set short, the
          // cell clips them - these grids hide overflow so a long name ellipsises.
          { id: 'act', label: '', srLabel: 'Actions', width: 340, sortable: false },
        ]}
        rows={page}
        rowKey={(x) => x.recordid}
        sort={g.sort} dir={g.dir} onSort={g.onSort}
        pager={g.pager(shown.length, 'schedule')}
        onRowClick={async (x) => setEditing(await api.get(`/company/rates/${x.recordid}`))}
        empty="No fee schedule yet. Until one exists a booked trip carries no price."
        cells={(x) => [
          <b>{x.name}</b>,
          data.billing[x.billingmethod] || '',
          `${date(x.effectivefrom)} - ${x.effectiveto ? date(x.effectiveto) : 'open'}`,
          ((([cls, word]) => <span className={cls}>{word}</span>)(standing(x))),
          // The row still opens the schedule, so these stop the click reaching it.
          <span className="rowacts">
            <button type="button" className="linkbtn edit"
              onClick={(e) => { e.stopPropagation(); start(x, 'copy') }}>Copy</button>
            {/* Nothing to hand over from a schedule that governs nothing. Copy still
                works - its rates are worth reusing whether or not it is in use. */}
            <button type="button" className="linkbtn edit" disabled={!x.active}
              onClick={(e) => { e.stopPropagation(); start(x, 'supersede') }}>
              Supersede
            </button>
            <button type="button" className="linkbtn"
              onClick={(e) => { e.stopPropagation()
                if (x.active) setRetiring(x)
                else standingOf(x, true) }}>
              {x.active ? 'Retire' : 'Reinstate'}
            </button>
          </span>,
        ]} />

      {retiring && (
        <Modal title="Retire Fee Schedule" onClose={() => setRetiring(null)}
          footer={<>
            <button type="button" className="primary" disabled={busy === retiring.recordid}
              onClick={() => standingOf(retiring, false)}>Yes</button>
            <button type="button" onClick={() => setRetiring(null)}>No</button>
          </>}>
          <div className="stack">
            <div className="askorder">
              <span className="askmark">?</span>
              <p>Stop pricing anything from {retiring.name}?</p>
            </div>
          </div>
        </Modal>
      )}
      {editing && (
        <ScheduleEditor data={data} held={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload() }} />
      )}
    </div>
  )
}

function ScheduleEditor({ data, held, onClose, onSaved }) {
  const [f, setF] = useState({
    ...BLANK, ...held,
    // Its payer type: the passenger, or one kind of payer.
    payertype: held.privatepay ? 'private' : (held.payerkinds || '').split(',')[0] || '',
    effectivefrom: String(held.effectivefrom || '').slice(0, 10) || today(),
    effectiveto: String(held.effectiveto || '').slice(0, 10),
    note: held.note || '',
    active: held.active === undefined ? true : Boolean(held.active),
  })
  const [lines, setLines] = useState(
    ordered((held.rates || []), { ambulatory: 1, wheelchair: 1, stretcher: 1 }).map((r) => ({
      ...BLANKRATE, ...r,
      servicelevel: r.servicelevel || '', rounding: r.rounding || '',
      name: r.name || '',
      proceduracode: r.proceduracode || '', modifier: r.modifier || '',
      loadedonly: r.loadedonly === null || r.loadedonly === undefined
        ? true : Boolean(r.loadedonly),
      amount: r.amount ?? '', includedunits: r.includedunits ?? '',
      minimumunits: r.minimumunits ?? '',
      authrequired: Boolean(r.authrequired),
    })),
  )
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  // Which line is being written, if any. `at` is null for a new one. One at a time, because
  // the dialog is the gate: there is no half-finished row to leave lying in the grid, so
  // nothing has to be disabled to stop a stack of them building up.
  const [writing, setWriting] = useState(null)
  // The header's spacer has to be exactly as wide as the rows' scrollbar, or every heading
  // sits a few pixels left of its column. Measured from this table's own body rather than
  // guessed: it differs by browser, by zoom, and is 0 where scrollbars float over content.
  // The same mechanism, and the same reason, as the grids on the pages.
  const grid = useRef(null)
  useLayoutEffect(() => {
    const el = grid.current
    const body = el?.querySelector('tbody')
    if (!body) return undefined
    const measure = () => el.style.setProperty('--sbw', `${body.offsetWidth - body.clientWidth}px`)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(body)
    return () => ro.disconnect()
  })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  // Put away, then sorted into place. The old grid had to wait for focus to leave a row
  // before it dared reorder; a dialog says plainly when the line is finished.
  const keep = (line) => {
    setLines(ordered(writing.at === null ? [...lines, line]
      : lines.map((x, n) => (n === writing.at ? line : x)), data.services))
    setWriting(null)
  }

  const missing = [!f.name.trim() && 'a name', !f.payertype && 'the payer type',
                   !f.effectivefrom && 'the date it takes effect']
    .filter(Boolean)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = {
        // The dates are whatever the record already had, or today for a new one.
        name: f.name.trim(),
        // Set only by Supersede. The API ends that schedule the day before this one starts.
        supersedes: held.supersedes || null,
        payertype: f.payertype,
        effectivefrom: f.effectivefrom || null, effectiveto: f.effectiveto || null,
        active: f.active,
        rates: lines.filter((l) => l.amount !== '').map((l) => ({
          ratetype: l.ratetype, name: l.name.trim() || null,
          servicelevel: l.servicelevel || null, unit: l.unit,
          loadedonly: l.loadedonly,
          amount: Number(l.amount),
          includedunits: l.includedunits === '' ? null : Number(l.includedunits),
          minimumunits: l.minimumunits === '' ? null : Number(l.minimumunits),
          rounding: l.rounding || null,
          proceduracode: l.proceduracode.trim() || null,
          modifier: l.modifier.trim() || null, authrequired: l.authrequired,
        })),
      }
      if (held.recordid) await api.put(`/company/rates/${held.recordid}`, body)
      else await api.post('/company/rates', body)
      onSaved()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      {/* A fixed height, so a schedule of three rates and one of twenty are the same shape
          and nothing moves as lines are added. That only works because the rate list grows
          into whatever the form above it leaves - held at 90vh with the list capped, the
          space between the last rate and the footer was empty floor. */}
      <Modal title={held.replacing ? `Replace ${held.replacing}`
        : held.recordid ? 'Fee Schedule' : 'Add A Fee Schedule'} onClose={onClose}
      width={1140} tall
      footer={<>
        {/* Left, apart from the two that finish the dialog. Adding a line is work inside the
            schedule; Save and Close are what you do when the work is done, and a button that
            means something different does not belong in the same group as them. */}
        <div className="footactions">
          <button type="button"
            onClick={() => setWriting({ at: null, line: { ...BLANKRATE } })}>
            <Plus size={13} /> Add A Rate
          </button>
        </div>
        <button type="button" className="primary" disabled={busy || missing.length > 0}
          onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack schedulebody">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          {/* The name and whether it is in use, on one row. Active is the only thing about
              a schedule that changes without the rates changing, and it is read with the
              name rather than hunted for further down. */}
          {/* Active is not a field of a schedule - it is an act on one, and it lives on
              the grid row beside Copy and Supersede. Here it would be a toggle somebody can
              flip while editing rates. */}
          {/* A price list of one payer type. Which payer pays under it is set on the payer, and
              a payer is offered only the schedules of its own type. */}
          <label className="field span-3">Name *
            <input value={f.name} className="upper"
              onChange={(e) => setF({ ...f, name: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-3">Payer Type *
            <select value={f.payertype} onChange={set('payertype')}>
              <option value="">Choose</option>
              <option value="private">Private Pay</option>
              {Object.entries(data.categories).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          {/* How one price list replaces another: a schedule is not edited when prices change,
              the old one is given an end date and a new one starts the next day, so a trip
              carried in February keeps February's price for ever. */}
          <label className="field span-3">Takes Effect *
            <input type="date" value={f.effectivefrom} onChange={set('effectivefrom')} />
          </label>
          <label className="field span-3">Runs Until
            <input type="date" value={f.effectiveto} onChange={set('effectiveto')} />
          </label>
        </div>

        {/* One grid. Service is a column on the line, not a heading above a table of its
            own - the rows are the same shape whatever they price, and splitting them into
            separate tables repeated the header for every service and made a short schedule
            look like four. */}
        <section className="ratesection">
          <h3 className="formsection">Rates</h3>
          {!lines.length ? <div className="muted">No rate lines yet.</div> : (
            <div className="ratescroll" ref={grid}>
            {/* Read, not edited. A row of pickers and boxes for every line made a schedule of
                twenty charges a wall of controls, and the figures - the thing somebody opens
                this to check - were the hardest part of it to see. The line is written in a
                dialog and read here, the way a license is. */}
            <table className="residencetable recordtable ratetable">
              {/* Amount, unit and loaded are one column, because they are one sentence:
                  "$3.50 per loaded mile" is the rate, and split across three cells it has to
                  be reassembled by eye on every row. */}
              <thead><tr><th>Name</th><th>Type</th><th>Service</th><th>Rate</th>
                <th className="num">Included</th><th className="num">Minimum</th>
                <th>Code</th><th />
                {/* As wide as the rows' scrollbar, so the headings stay over their columns
                    and the scrollbar runs beside the rows rather than past the header. */}
                <th className="sbgutter" aria-hidden="true" /></tr></thead>
              <tbody>
                {lines.map((l, i) => (
                  /* The row opens the line. `click` is the same class the customer and driver
                     grids use, so a row that can be opened looks and behaves the same
                     wherever one is. */
                  <tr key={l.recordid || `new-${i}`} className="click"
                    onClick={() => setWriting({ at: i, line: l })}>
                    <td>{l.name}</td>
                    <td>{data.ratetypes[l.ratetype] || l.ratetype}</td>
                    <td>{data.services[l.servicelevel] || 'All'}</td>
                    <td className="ratesays">{says(l, data)}</td>
                    <td className="num">{plain(l.includedunits)}</td>
                    <td className="num">{plain(l.minimumunits)}</td>
                    <td>{l.proceduracode}</td>
                    <td className="actions">
                      {/* Stopped at the button: Remove sits inside a row that opens the line,
                          and without this it would delete the row and then open the dialog
                          on whatever took its place. */}
                      <button type="button" className="linkbtn"
                        onClick={(e) => { e.stopPropagation()
                          setLines(lines.filter((_, n) => n !== i)) }}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </section>

      </div>
      </Modal>
      {/* Beside the schedule dialog, not inside its body: a second backdrop that is a sibling
          of the first stacks above it by document order, with no z-index argument to have. */}
      {writing && (
        <RateDialog data={data} line={writing.line} isnew={writing.at === null}
          onClose={() => setWriting(null)} onKeep={keep} />
      )}
    </>
  )
}

// One rate line, written in a dialog. The same shape as the license dialog: the fields in a
// profileform, Cancel and the finishing action in the footer, and the cursor already in the
// first field because Modal puts it there.
function RateDialog({ data, line, isnew, onClose, onKeep }) {
  const [r, setR] = useState(line)
  const set = (k) => (e) => setR({ ...r, [k]: e.target.value })
  // A line needs a name and a figure. The name because the type alone does not identify a
  // charge - a schedule carries several surcharges, and "Surcharge $30" on an invoice tells
  // a passenger nothing. The figure because a rate with no amount is not a rate.
  const ok = r.name.trim() !== ''
    && String(r.amount).trim() !== '' && !Number.isNaN(Number(r.amount))
  return (
    <Modal title={isnew ? 'Add A Rate' : 'Edit This Rate'} onClose={onClose} width={720}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={!ok}
          onClick={() => onKeep(r)}>{isnew ? 'Add' : 'Save'}</button>
      </>}>
      <div className="profileform">
        {/* First, so it takes the cursor when the dialog opens: the name is what you came
            to write, and the type below it already has a sensible answer. */}
        <label className="field span-2">Name *
          <input value={r.name} className="upper"
            onChange={(e) => setR({ ...r, name: e.target.value.toUpperCase() })} />
        </label>
        <label className="field span-2">Type
          <select value={r.ratetype} onChange={set('ratetype')}>
            {Object.entries(data.ratetypes).map(([v, t]) => (
              <option key={v} value={v}>{t}</option>
            ))}
          </select>
        </label>
        <label className="field span-2">Service
          <select value={r.servicelevel} onChange={set('servicelevel')}>
            <option value="">All</option>
            {Object.entries(data.services).map(([v, t]) => (
              <option key={v} value={v}>{t}</option>
            ))}
          </select>
        </label>
        <label className="field span-2">Unit
          <select value={r.unit} onChange={set('unit')}>
            {Object.entries(data.units).map(([v, t]) => (
              <option key={v} value={v}>{t}</option>
            ))}
          </select>
        </label>
        <label className="field span-2">Amount *
          <input type="number" step="0.01" min="0" value={r.amount} onChange={set('amount')} />
        </label>
        <label className="field span-2">Included
          <input type="number" step="0.1" min="0" value={r.includedunits}
            onChange={set('includedunits')} />
        </label>
        <label className="field span-2">Minimum
          <input type="number" step="0.1" min="0" value={r.minimumunits}
            onChange={set('minimumunits')} />
        </label>
        <label className="field span-2">Code
          <input value={r.proceduracode} className="upper"
            onChange={(e) => setR({ ...r, proceduracode: e.target.value.toUpperCase() })} />
        </label>
        {/* Only mileage has an opinion about which miles. On any other charge the question
            does not arise, so it is not asked. */}
        {r.ratetype === 'mileage' && (
          <label className="field check sharerow beside">
            <input type="checkbox" checked={r.loadedonly}
              onChange={(e) => setR({ ...r, loadedonly: e.target.checked })} />
            Loaded miles only
          </label>
        )}
      </div>
    </Modal>
  )
}
