import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileUp, FlaskConical, Loader2, Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { date } from '../lib/format.js'
import { Loading, Tile, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import TestDialog from '../components/TestDialog.jsx'

// Random drug and alcohol testing - 49 CFR 382.305, on one page.
//
// It lived in a dialog behind a requirement, which is the wrong shape for it. Everything else in
// the catalog is a document somebody files; this is a programme somebody RUNS, all year, with a
// rate to hit and people to chase. That is work with a rhythm, and work with a rhythm wants a
// page: what the pool is, how far through the year's rate the company has got, whether the draws
// are spread out or bunched, and who still owes a test.
//
// The regulation asks three questions and the page answers them in that order:
//   382.305(b)  is the annual rate being met - the tiles
//   382.305(k)  are the selections spread reasonably through the year - the chart
//   382.305(l)  did the drivers who came out actually go and get tested - the table

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const BAD = ['positive', 'refusal', 'adulterated', 'substituted']

// Draws by month. One column per month of the year, split by what the draw was for.
//
// This is not decoration: 382.305(k) asks for selections "spread reasonably through the year",
// and that is a question about shape. Six draws in December and none before is a compliance
// finding that no table of six rows makes you see, and that one glance at this does.
//
// Built in the house chart grammar - recessive grid, thin columns on the baseline with a 4px
// rounded top, a 2px gap between stacked segments, hover for the figures, and the same numbers
// in a table underneath for anybody who cannot use the picture.
const W = 640, H = 200, PAD = { t: 10, r: 8, b: 26, l: 30 }
const GAP = 2

function column(x, top, w, bottom, rounded) {
  const h = bottom - top
  if (h <= 0) return ''
  const r = rounded ? Math.min(4, h, w / 2) : 0
  return `M${x},${bottom} V${top + r} Q${x},${top} ${x + r},${top} H${x + w - r} `
       + `Q${x + w},${top} ${x + w},${top + r} V${bottom} Z`
}

function DrawsChart({ year, selections, types }) {
  const [hover, setHover] = useState(null)
  const months = MONTHS.map((m, i) => {
    const mine = selections.filter((s) => {
      const d = new Date(`${s.drawnon}T00:00:00`)
      return d.getFullYear() === year && d.getMonth() === i
    })
    return {
      month: m,
      drug: mine.filter((s) => s.testtype === 'drug').reduce((n, s) => n + (s.selected || 0), 0),
      alcohol: mine.filter((s) => s.testtype === 'alcohol')
        .reduce((n, s) => n + (s.selected || 0), 0),
    }
  })
  const top = Math.max(1, ...months.map((m) => m.drug + m.alcohol))
  const max = top <= 4 ? 4 : Math.ceil(top / 4) * 4
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b
  const band = iw / 12
  const bw = Math.min(26, band * 0.55)
  const y = (v) => PAD.t + ih - (v / max) * ih
  const ticks = [0, 0.5, 1].map((f) => Math.round(f * max))
  const hd = hover !== null ? months[hover] : null

  return (
    <div className="chart">
      <div className="legend" aria-hidden="true">
        <span><span className="key" style={{ background: 'var(--teal-900)' }} />
          {types.drug}</span>
        <span><span className="key" style={{ background: 'var(--orange)' }} />
          {types.alcohol}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Drivers selected each month of ${year}, by what the draw was for`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="gridline" x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} />
            <text className="tick" x={PAD.l - 8} y={y(t) + 4} textAnchor="end">{t}</text>
          </g>
        ))}
        {months.map((m, i) => {
          const x = PAD.l + i * band + (band - bw) / 2
          const base = y(0)
          const drugTop = y(m.drug)
          const alcTop = y(m.drug + m.alcohol)
          return (
            <g key={m.month} className={hover === i ? 'hover' : undefined}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <path className="seg-risk"
                d={column(x, alcTop, bw, m.drug ? drugTop - GAP : base, true)} />
              <path className="seg-covered" d={column(x, drugTop, bw, base, !m.alcohol)} />
              <rect className="hit" x={PAD.l + i * band} y={PAD.t} width={band} height={ih} />
              <text className="tick" x={x + bw / 2} y={H - 8} textAnchor="middle">{m.month}</text>
            </g>
          )
        })}
      </svg>
      {hd && (
        <div className="tooltip"
          style={{ left: `${((PAD.l + band * hover + band / 2) / W) * 100}%`,
                   top: `${(y(hd.drug + hd.alcohol) / H) * 100}%` }}>
          <div className="muted">{hd.month} {year}</div>
          <div>{types.drug} <b>{hd.drug}</b></div>
          <div>{types.alcohol} <b>{hd.alcohol}</b></div>
        </div>
      )}
      <table className="sr-only">
        <caption>Drivers selected each month of {year}</caption>
        <thead><tr><th>Month</th><th>{types.drug}</th><th>{types.alcohol}</th></tr></thead>
        <tbody>
          {months.map((m) => (
            <tr key={m.month}><td>{m.month}</td><td>{m.drug}</td><td>{m.alcohol}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function RandomTesting() {
  const [data, error, reload] = useLoad(() => api.get('/company/random-selections'), [])
  const [pool, , reloadPool] = useLoad(() => api.get('/company/random-pool'), [])
  const [adding, setAdding] = useState(false)
  const [picked, setPicked] = useState([])
  const [f, setF] = useState(null)
  // Drivers whose names have just come out and whose test is being filed one after another,
  // which is what "record it on the spot" means: the office is on the phone to the clinic now,
  // not tomorrow, and sending them to four different driver pages to type four results is how
  // three of them never get typed.
  const [queue, setQueue] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const navigate = useNavigate()

  if (!data) {
    return (
      <div className="stack">
        <div className="pagehead"><h1>D&A Random Testing</h1></div>
        <div className="card"><Loading error={error} /></div>
      </div>
    )
  }
  const now = f ?? { drawnon: new Date().toISOString().slice(0, 10), testtype: 'drug',
    performedby: '', note: '', file: null }
  const owing = data.selections.flatMap((s) => (s.drivers || [])
    .filter((d) => !d.testid && !d.excusedon)
    .map((d) => ({ ...d, drawnon: s.drawnon, testtype: s.testtype })))

  const refresh = async () => { await reload(); await reloadPool() }

  const saveDraw = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('drawnon', now.drawnon)
      body.append('testtype', now.testtype)
      picked.forEach((id) => body.append('drivers', id))
      if (now.performedby.trim()) body.append('performedby', now.performedby.trim())
      if (now.note.trim()) body.append('note', now.note.trim())
      if (now.file) body.append('file', now.file)
      await api.post('/company/random-selections', body)
      const named = (pool?.drivers || []).filter((d) => picked.includes(d.recordid))
      setAdding(false); setF(null); setPicked([])
      await refresh()
      // Straight into recording what each of them came back with. Skippable, because the result
      // is usually days away - but offered, because sometimes it is not.
      setQueue(named)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const fileTest = (driverid) => async (form) => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('reason', 'random')
      body.append('collectedon', form.collectedon)
      body.append('result', form.result)
      if (form.testtype) body.append('testtype', form.testtype)
      if (form.substance?.trim()) body.append('substance', form.substance.trim())
      if (form.bac !== '' && form.bac != null) body.append('bac', form.bac)
      if (form.note.trim()) body.append('note', form.note.trim().toUpperCase())
      if (form.file) body.append('file', form.file)
      await api.post(`/drivers/${driverid}/testing/tests`, body)
      setQueue((q) => q.slice(1))
      await refresh()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const met = (k) => data.progress[k].selected >= data.progress[k].owed

  return (
    <div className="stack">
      <div className="pagehead">
        <h1>D&A Random Testing</h1>
        <div className="row headactions">
          <button type="button" onClick={() => setAdding(true)}>
            <Plus size={13} /> Record A Draw
          </button>
        </div>
      </div>

      {err && <div className="notice bad">{err}</div>}

      {/* 382.305(b): the rate is taken on the AVERAGE number of driver positions across the
          year, not on the headcount today, so both numbers are here and the one the rate is
          computed from is said out loud. */}
      <div className="grid cols-4">
        <Tile className="fill-teal" label="In the pool" value={data.pool}
          sub={data.averagedsince
            ? `averaging ${data.average} since ${date(data.averagedsince)}`
            : `averaging ${data.average} across ${data.year}`} />
        {Object.entries(data.rates).map(([k, rate]) => (
          <Tile key={k} className={met(k) ? 'fill-light' : 'fill-orange'}
            label={`${data.types[k]} · ${rate}%`}
            value={`${data.progress[k].selected} of ${data.progress[k].owed}`}
            sub={met(k) ? `the ${data.year} rate is met` : `still to draw in ${data.year}`} />
        ))}
        <Tile className={owing.length ? 'fill-orange' : ''} label="Tests owed now"
          value={owing.length}
          sub={owing.length ? 'drivers drawn and not yet tested' : 'everybody drawn has been tested'} />
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>Spread Through {data.year}</h3></div>
        <div className="panelbody">
        {/* 382.305(k). Six draws in December and none before is a finding, and it is a finding
            about shape - which a list of six rows will not show anybody. */}
        <DrawsChart year={data.year} selections={data.selections} types={data.types} />
        </div>
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>Drawn</h3>
          <span className="muted small">
            Every name that has come out, and what happened to them
          </span>
        </div>
        <div className="panelbody">
        {!data.selections.length ? (
          <div className="gridempty">No draws recorded yet</div>
        ) : (
          <table className="residencetable recordtable">
            <thead><tr><th>Drawn</th><th>For</th><th>Driver</th>
              <th className="growcol">Test</th><th /></tr></thead>
            <tbody>
              {data.selections.flatMap((x) => (
                (x.drivers || []).length ? x.drivers : [null]
              ).map((who, i) => (
                <tr key={who ? who.recordid : x.recordid}>
                  <td>{i === 0 ? date(x.drawnon) : ''}
                    {i === 0 && x.poolsize != null && (
                      <div className="muted small">pool of {x.poolsize}</div>
                    )}
                  </td>
                  <td>{data.types[x.testtype] || x.testtype}</td>
                  <td>{who ? who.driver : <span className="muted">No names recorded</span>}</td>
                  <td className={`growcol ${who && who.result
                    ? (BAD.includes(who.result) ? 'st-expired' : 'st-active')
                    : who && who.excusedon ? '' : 'st-expired'}`}>
                    {who && who.result
                      ? `${data.results?.[who.result] || who.result}`
                        + `${who.collectedon ? ` ${date(who.collectedon)}` : ''}`
                      : who && who.excusedon ? `Not tested - ${who.excused}`
                        : who ? 'Not tested' : '-'}
                  </td>
                  <td className="actions">
                    {who && !who.testid && !who.excusedon && (
                      <button type="button" className="linkbtn edit"
                        onClick={() => setQueue([{ recordid: who.driverid, name: who.driver }])}>
                        Record The Test
                      </button>
                    )}
                    {who && (
                      <button type="button" className="linkbtn edit"
                        onClick={() => navigate(`/drivers/${who.driverid}?section=testing`)}>
                        Open Driver
                      </button>
                    )}
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
        )}
        </div>
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>The Pool</h3>
          <span className="muted small">
            Drivers go in and out from their own Requirements - Random testing pool membership
          </span>
        </div>
        <div className="panelbody">
        {!(pool?.drivers || []).length ? (
          <div className="gridempty">Nobody is in the pool</div>
        ) : (
          <table className="residencetable recordtable">
            <thead><tr><th>Driver</th><th className="growcol">In the pool since</th><th /></tr></thead>
            <tbody>
              {pool.drivers.map((d) => (
                <tr key={d.recordid}>
                  <td>{d.name}</td>
                  <td className="growcol">{date(d.joinedon)}</td>
                  <td className="actions">
                    <button type="button" className="linkbtn edit"
                      onClick={() => navigate(`/drivers/${d.recordid}?section=testing`)}>Open</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        </div>
      </div>

      {adding && (
        <Modal title="Record A Draw" onClose={() => { setAdding(false); setF(null); setPicked([]) }}
          width={720}
          footer={<>
            <button type="button" className="primary"
              disabled={busy || !now.drawnon || !picked.length} onClick={saveDraw}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button"
              onClick={() => { setAdding(false); setF(null); setPicked([]) }}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-2">Drawn On
                <input type="date" value={now.drawnon} min="1900-01-01" max="2100-12-31"
                  onChange={(e) => setF({ ...now, drawnon: e.target.value })} />
              </label>
              <label className="field span-2">For
                <select value={now.testtype}
                  onChange={(e) => setF({ ...now, testtype: e.target.value })}>
                  {Object.entries(data.types).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </label>
              <label className="field span-2">Drawn By
                <input value={now.performedby} className="upper"
                  onChange={(e) => setF({ ...now, performedby: e.target.value.toUpperCase() })} />
              </label>
              <label className="field span-3">The List Of Names It Produced
                <input type="file"
                  onChange={(e) => setF({ ...now, file: e.target.files[0] || null })} />
              </label>
              <label className="field span-3">Note
                <textarea value={now.note} className="upper"
                  onChange={(e) => setF({ ...now, note: e.target.value.toUpperCase() })} />
              </label>
            </div>
            {/* Ticked from the pool rather than counted. Only pool members are offered: a name
                that was not in the hat cannot have come out of it, and the count on the draw is
                these ticks, so the two can never disagree. */}
            <section>
              <h3 className="formsection">Who came out</h3>
              {!(pool?.drivers || []).length ? (
                <div className="muted">
                  Nobody is in the pool yet. Put drivers in from their own Requirements -
                  Random testing pool membership.
                </div>
              ) : (
                <div className="endorsementgrid">
                  {pool.drivers.map((d) => (
                    <label key={d.recordid}>
                      <input type="checkbox" checked={picked.includes(d.recordid)}
                        onChange={(e) => setPicked(e.target.checked
                          ? [...picked, d.recordid]
                          : picked.filter((x) => x !== d.recordid))} />
                      {d.name}
                    </label>
                  ))}
                </div>
              )}
            </section>
          </div>
        </Modal>
      )}

      {/* One driver at a time, straight after the draw. Skip leaves the selection owing, which
          is the honest state when the result is not back yet. */}
      {queue.length > 0 && (
        <TestDialog title={`Random Test - ${queue[0].name}`} reason="random" locked
          reasons={data.reasons || { random: 'Random' }} results={data.results}
          busy={busy} err={err}
          onSave={fileTest(queue[0].recordid)}
          onClose={() => setQueue((q) => q.slice(1))} />
      )}
    </div>
  )
}
