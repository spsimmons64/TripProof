import { Fragment, useLayoutEffect, useRef, useState } from 'react'
import { Loader2, MoreHorizontal, Plus } from 'lucide-react'
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

// The answers, built from the payer types rather than written out - so a new type appears
// here the day it is added, at both scopes, with nothing else touched.
//
// Whole groups first, then the named subsets, with a rule between. Interleaving them put
// "All Commercial Payers" between the two broker lines, so choosing a scope meant reading
// every other line to find its pair.
function applyOptions(categories, plural) {
  const many = (c) => (plural && plural[c]) || `${categories[c]}s`
  return [
    [['private', 'Private Pay'],
     ...Object.keys(categories).map((c) => [`all:${c}`, `All ${many(c)}`])],
    Object.keys(categories).map((c) => [`select:${c}`, `Select ${many(c)}`]),
  ]
}

// Which of them a saved schedule already is.
function applyOf(held, payers) {
  // Read off the coverage, not off whether it has been saved - a copy carries the coverage
  // and no record id, and keying on the id made every copy come back as private pay.
  if (held.privatepay) return 'private'
  const kinds = String(held.payerkinds || '').split(',').filter(Boolean)
  if (kinds.length) return `all:${kinds[0]}`
  const ids = held.payerids || []
  if (!ids.length) return 'private'
  const payer = payers.find((p) => p.recordid === ids[0])
  return `select:${payer ? payer.category : 'broker'}`
}

// Choosing which payers a schedule covers. One list, the house grid, paged - a company
// with two hundred payers gets the same dialog as one with four.
//
// The paging is local state, NOT useGridParams: that keeps page and sort in the address bar,
// which is right for a page's own grid and wrong here - this dialog opens on top of the fee
// schedule grid, and the two would be reading and writing the same ?page.
function PayerChoice({ title, options, chosen, onClose, onDone }) {
  const [picked, setPicked] = useState(chosen)
  const [page, setPage] = useState(1)
  // The same number the pager's own control starts on - mine said 10 while the box said 25,
  // which is one setting with two values.
  const [pagesize, setPagesize] = useState(25)
  const [dir, setDir] = useState('asc')
  const toggle = (id) => setPicked(picked.includes(id)
    ? picked.filter((x) => x !== id) : [...picked, id])
  const sorted = [...options].sort(
    (a, b) => a[1].localeCompare(b[1]) * (dir === 'desc' ? -1 : 1))
  const slice = sorted.slice((page - 1) * pagesize, page * pagesize)
  const all = options.map(([id]) => id)
  // Not `tall`: a list of twelve in a dialog held at 90vh is mostly empty floor. It takes
  // the height it needs, and the grid is capped so a long list scrolls instead.
  return (
    <Modal title={title} onClose={onClose} width={760} flush
      footer={<>
        <div className="footactions">
          <button type="button"
            onClick={() => setPicked(picked.length === all.length ? [] : all)}>
            {picked.length === all.length ? 'Clear All' : 'Select All'}
          </button>
        </div>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" onClick={() => onDone(picked)}>Done</button>
      </>}>
      <DataGrid className="pickgrid"
        columns={[{ id: 'pick', label: '', width: 54, sortable: false },
                  { id: 'name', label: 'Payer' }]}
        rows={slice}
        rowKey={(r) => r[0]}
        sort="name" dir={dir}
        onSort={(_id, next) => { setDir(next); setPage(1) }}
        pager={{ total: options.length, page, pagesize, noun: 'payer',
                 onPage: setPage,
                 onPageSize: (n) => { setPagesize(n); setPage(1) } }}
        onRowClick={(r) => toggle(r[0])}
        empty="No payers of this type yet."
        cells={(r) => [
          // Read-only: the row is what toggles, so the box must not take the click twice.
          <input type="checkbox" checked={picked.includes(r[0])} readOnly tabIndex={-1} />,
          r[1],
        ]} />
    </Modal>
  )
}

const BLANK = {
  name: '', applyto: 'private', payerids: [],
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

  if (!data) return <div className="card"><Loading error={error} /></div>
  const held = data.schedules || []

  const shown = sorted(held, g.sort, g.dir)
  const page = shown.slice((g.page - 1) * g.pagesize, g.page * g.pagesize)

  return (
    // `fill` rather than `stack`: a list page gives its grid the height of the playground,
    // so the rows scroll under the headings and the pager sits on the bottom edge instead of
    // the whole page scrolling and the pager drifting off.
    <div className="fill">
      <div className="pagehead">
        <div>
          <h1>Fee Schedules</h1>
          <div className="muted">
            What this company charges, and what each payer contracts to pay it.
          </div>
        </div>
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
          <b>{x.name}<span className="muted"> · {x.privatepay ? 'Private Pay'
            : x.payerkinds
              ? `All ${(data.categoryplural || {})[x.payerkinds] || x.payerkinds}`
              : x.payernames || 'nobody yet'}</span></b>,
          data.billing[x.billingmethod] || '',
          `${date(x.effectivefrom)} - ${x.effectiveto ? date(x.effectiveto) : 'open'}`,
          ((([cls, word]) => <span className={cls}>{word}</span>)(standing(x))),
          // The row still opens the schedule, so these stop the click reaching it.
          <span className="rowacts">
            <button type="button" className="linkbtn edit"
              onClick={(e) => { e.stopPropagation(); start(x, 'copy') }}>Copy</button>
            <button type="button" className="linkbtn edit"
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
    // Which of the three this schedule already is, read off the record.
    // Which of the seven this schedule already is. "All Transportation Brokers" and
    // "Select Transportation Brokers" are one payer type at two scopes, which is why they
    // are one choice rather than two questions.
    applyto: applyOf(held, data.payers || []),
    payerids: held.payerids || [],
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
  const [choosing, setChoosing] = useState(false)
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

  const missing = [!f.name.trim() && 'a name',
                   !f.effectivefrom && 'the date it takes effect',
                   f.applyto.startsWith('select:') && !f.payerids.length
                     && 'at least one payer']
    .filter(Boolean)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = {
        // The dates are whatever the record already had, or today for a new one.
        name: f.name.trim(),
        // Set only by Supersede. The API ends that schedule the day before this one starts.
        supersedes: held.supersedes || null,
        privatepay: f.applyto === 'private',
        payerkinds: f.applyto.startsWith('all:') ? [f.applyto.slice(4)] : [],
        payerids: f.applyto.startsWith('select:') ? f.payerids : [],
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
          <label className="field span-6">Name *
            <input value={f.name} className="upper"
              onChange={(e) => setF({ ...f, name: e.target.value.toUpperCase() })} />
          </label>
          {/* Who this applies to. A rule, not a list: "all brokers" is one choice that
              covers seventy-five of them and covers the seventy-sixth the day it is added.
              Naming payers is the exception, and it wins over the kind. */}
          <label className="field span-2">Applies To
            <div className="withpick">
            <select value={f.applyto} onChange={(e) => {
              const applyto = e.target.value
              setF({ ...f, applyto,
                // Switching type drops payers of the old one - they are not offered any
                // more, and a saved schedule should not hold names its own dropdown cannot
                // show.
                payerids: f.payerids.filter((id) => (data.payers || []).some(
                  (p) => p.recordid === id && `select:${p.category}` === applyto)),
              })
            }}>
              {applyOptions(data.categories, data.categoryplural)
                .map((group, n) => (
                  <Fragment key={n}>
                    {n > 0 && <hr />}
                    {group.map(([v, label]) => (
                      <option key={v} value={v}>{label}</option>
                    ))}
                  </Fragment>
                ))}
            </select>
            {/* Always there, off where there is nothing to choose - "All Transportation
                Brokers" has already answered it. A control that appears and disappears
                moves the fields beside it; one that greys out does not. */}
            <button type="button" className="pickbtn" title="Choose payers"
              disabled={!f.applyto.startsWith('select:')}
              onClick={() => setChoosing(true)}>
              <MoreHorizontal size={16} />
            </button>
            </div>
          </label>
          {/* On the same row as who it applies to, and the same width whatever is chosen -
              they shrank to make room for Billed as, which no longer exists.
              They are how one price list replaces another: a schedule is not edited when
              prices change, the old one is given an end date and a new one starts the next
              day, so a trip carried in February keeps February's price for ever. */}
          <label className="field span-2">Takes effect *
            <input type="date" value={f.effectivefrom} onChange={set('effectivefrom')} />
          </label>
          <label className="field span-2">Runs until
            <input type="date" value={f.effectiveto} onChange={set('effectiveto')} />
          </label>
        </div>

        {/* Always, once a "Select ..." is chosen. A section that appears only after the
            first payer is added leaves the dialog saying nothing about a choice that has
            not been made yet. */}
        {f.applyto.startsWith('select:') && (
          <section>
            {/* Headed like Rates below it, because it is the same kind of thing: a short
                list the schedule carries. The choosing happens in the dialog behind the
                ellipsis; this is only what came back. */}
            <h3 className="formsection">Payers</h3>
            {f.payerids.length === 0 && (
              <p className="needpayers">Please Select The Connected Payers</p>
            )}
            {f.payerids.length > 0 && (
            <table className="residencetable recordtable coverstable">
              <tbody>
                {f.payerids.map((id) => {
                  const payer = (data.payers || []).find((p) => p.recordid === id)
                  return (
                    <tr key={id}>
                      <td className="growcol">{payer ? payer.name : id}</td>
                      <td className="actions">
                        <button type="button" className="linkbtn"
                          onClick={() => setF({ ...f,
                            payerids: f.payerids.filter((x) => x !== id) })}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            )}
          </section>
        )}

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
                dialog and read here, the way a licence is. */}
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
      {choosing && (
        <PayerChoice title="Choose Payers" chosen={f.payerids}
          options={(data.payers || [])
            .filter((p) => `select:${p.category}` === f.applyto)
            .map((p) => [p.recordid, p.name])}
          onClose={() => setChoosing(false)}
          onDone={(payerids) => { setF({ ...f, payerids }); setChoosing(false) }} />
      )}
      {writing && (
        <RateDialog data={data} line={writing.line} isnew={writing.at === null}
          onClose={() => setWriting(null)} onKeep={keep} />
      )}
    </>
  )
}

// One rate line, written in a dialog. The same shape as the licence dialog: the fields in a
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
