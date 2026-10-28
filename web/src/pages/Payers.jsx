import { useState } from 'react'
import { Loader2, Plus, Upload } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { date } from '../lib/format.js'
import { Modal } from '../admin/common.jsx'
import DocumentViewer from '../components/DocumentViewer.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import { US_STATES } from '../admin/CustomerProfile.jsx'
import { PhoneInput } from '../components/MaskedInput.jsx'

// Who this company bills.
//
// Its own list - the insurers, plans, carriers and facilities it has arrangements with. The
// shared rows are the brokers TripProof publishes compliance rules against: a trip carried
// for one of them is checked against that broker's requirements, which holds only while
// every company points at the same row. They are offered here and editable by nobody.
const BLANK = {
  name: '', category: 'commercial', payerid: '', website: '', notes: '', active: true,
  address1: '', address2: '', city: '', state: '', zip: '', phone: '', fax: '',
  contactname: '', contactemail: '',
}
const ADDRESS = ['address1', 'address2', 'city', 'state', 'zip', 'phone', 'contactname',
                 'contactemail']
// Private pay has no payer to bill, so it is a built-in row whose lines name none.
const PRIVATE = { recordid: 'privatepay', name: 'PRIVATE PAY', category: 'private', shared: true,
                  privatepay: true, active: true }
const BLANK_LINE = { state: '', program: '', status: 'active', scheduleid: '', effectivefrom: '', effectiveto: '',
  contractref: '', services: [], requiresapproval: false, reviewed: false, note: '' }
const BLANK_ASK = { qualificationcode: '', renewaldays: '', clause: '' }
const STATUS = { active: 'Active', planned: 'Planned', ended: 'Ended' }
// A line is in force while it is active and its dates have not run out.
const live = (l) => l.status === 'active' && !l.ended

export default function Payers() {
  const [data, error, reload] = useLoad(() => api.get('/company/payers'), [])
  const [editing, setEditing] = useState(null)
  const g = useGridParams({ defaultSort: 'name', defaultDir: 'asc' })

  if (!data) return <Loading error={error} page />
  // Each payer, and whether any of its state lines is in force.
  const linesof = (x) => data.lines.filter((l) => (x.privatepay ? !l.payerid : l.payerid === x.recordid))
  const all = [PRIVATE, ...data.payers].map((x) => {
    const held = linesof(x).filter(live)
    return { ...x, inuse: Boolean(x.active) && held.length > 0, setup: !x.shared || Boolean(x.decided) || linesof(x).length > 0 }
  })
  // Only the payers this company has set up: its own, and the shared ones it has a state line for.
  // The rest are offered when adding one.
  const offered = all.filter((x) => !x.setup && x.active)
  // Sorted and paged here, as the fee schedules are: a company has a handful of payers, and
  // a round trip to reorder them is one nobody should wait for.
  const flip = g.dir === 'desc' ? -1 : 1
  const shown = all.filter((x) => x.setup).sort((a, b) => {
    const x = a[g.sort] ?? '', y = b[g.sort] ?? ''
    if (x === y) return a.name.localeCompare(b.name)
    return (x > y ? 1 : -1) * flip
  })
  const page = shown.slice((g.page - 1) * g.pagesize, g.page * g.pagesize)

  return (
    <div className="fill payerspage">
      <div className="pagehead">
        <div>
          <h1>Payers</h1>
        </div>
        <button type="button" className="primary" onClick={() => setEditing({ ...BLANK })}>
          <Plus size={14} /> Add A Payer
        </button>
      </div>

      <DataGrid
        columns={[
          { id: 'name', label: 'Payer' },
          { id: 'category', label: 'Payer Type', width: '22%' },
          { id: 'inuse', label: 'Status', width: 120 },
        ]}
        rows={page}
        rowKey={(x) => x.recordid}
        sort={g.sort} dir={g.dir} onSort={g.onSort}
        pager={g.pager(shown.length, 'payer')}
        // Every row opens, shared ones included. Their details are not yours to change, but
        // your contract with them is yours - and refusing to open the row at all was what
        // stopped a contract being filed against ModivCare.
        onRowClick={(x) => setEditing(x)}
        empty="No payers yet."
        cells={(x) => [
          <><b>{x.name}</b>
            <span className="rowemail keepcase">{x.privatepay ? 'Billed To The Passenger'
              : [x.address1, x.address2, x.city, [x.state, x.zip].filter(Boolean).join(' ')]
                .filter(Boolean).join(', ')}</span></>,
          x.privatepay ? 'Private Pay' : data.categories[x.category] || x.category,
          <span className={x.inuse ? 'st-active' : 'st-inactive'}>
            {x.inuse ? 'Active' : 'Inactive'}
          </span>,
        ]} />

      {editing && (
        <PayerDialog key={editing.recordid || 'new'} held={editing} categories={data.categories}
          data={data} offered={offered}
          onPick={(x) => setEditing(x ? { ...x, adding: true } : { ...BLANK })}
          lines={editing.recordid ? linesof(editing) : []} reload={reload}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload() }} />
      )}
    </div>
  )
}

function PayerDialog({ held, categories, data, offered, onPick, lines, reload, onClose, onSaved }) {
  const [f, setF] = useState({
    ...BLANK, ...held,
    payerid: held.payerid || '', website: held.website || '', notes: held.notes || '',
    ...Object.fromEntries(ADDRESS.map((k) => [k, held[k] || ''])),
    active: held.active === undefined ? true : Boolean(held.active),
    scheduleid: (held.privatepay ? data.privatepayschedule : held.scheduleid) || '',
  })
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [line, setLine] = useState(null)   // the state line being added or edited
  const [filing, setFiling] = useState(false)   // a document being added
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const missing = !f.name.trim()
    // Every payer is paid under a fee schedule of its own type.
    || !data.schedules.some((x) => x.recordid === f.scheduleid
      && x.kind === (held.privatepay ? 'private' : f.category))
  // A shared payer's details are everybody's; only whether this company works with it is its own.
  const locked = Boolean(held.shared)
  // A broker on the master list is located by the master: its address and contact are read there.
  const placed = locked || Boolean(held.mastered)

  const act = async (fn, key) => {
    setBusy(key); setErr(null)
    try { await fn(); onSaved() } catch (e) { setErr(e.message); setBusy(null) }
  }
  // The fee schedules this payer can be paid under: active, and of its own payer type.
  const kind = held.privatepay ? 'private' : f.category
  const schedules = data.schedules.filter((x) => x.kind === kind)
  const scheduleField = (
    <label className="field span-6">Fee Schedule *
      <select value={f.scheduleid} onChange={set('scheduleid')}>
        <option value="">Choose</option>
        {schedules.map((x) => <option key={x.recordid} value={x.recordid}>{x.name}</option>)}
      </select>
    </label>
  )
  // Saved as the company's own for every payer, a shared one and private pay included.
  const keepSchedule = (id) => api.put(`/company/payers/${id}/schedule`, { scheduleid: f.scheduleid })
  const save = () => act(async () => {
    if (held.privatepay) return keepSchedule('privatepay')
    if (held.shared) {
      await api.put(`/company/payers/${held.recordid}/status`,
        { active: f.active, contactname: f.contactname, contactemail: f.contactemail })
      return keepSchedule(held.recordid)
    }
    const id = held.recordid
      ? (await api.put(`/company/payers/${held.recordid}`, f), held.recordid)
      : (await api.post('/company/payers', f)).recordid
    return keepSchedule(id)
  }, 'save')

  return (
    <Modal title={!held.recordid || held.adding ? 'Add A Payer'
      : held.privatepay ? 'Private Pay' : 'Payer'}
      onClose={onClose} width={720}
      footer={<>
        {held.recordid && !held.shared && (
          <div className="footactions">
            <button type="button" disabled={busy !== null}
              onClick={() => act(() => api.del(`/company/payers/${held.recordid}`), 'remove')}>
              Remove
            </button>
          </div>
        )}
        {held.recordid && !held.privatepay && (
          <button type="button" onClick={() => setFiling(true)}>
            <Upload size={13} /> Add A Document
          </button>
        )}
        {held.recordid && (
          <button type="button" onClick={() => setLine({
            ...BLANK_LINE, program: held.privatepay ? 'privatepay'
              : (data.categoryprograms[held.category] || [])[0] || '' })}>
            <Plus size={13} /> Add A State
          </button>
        )}
        <button type="button" onClick={onClose}>Cancel</button>
        {/* For a shared payer, Save keeps only what is this company's own - whether it works with
            it and who it deals with there. Its details are everybody's, and its states and
            documents save in their own dialogs. */}
        <button type="button" className="primary" disabled={busy !== null || missing}
          onClick={save}>
          {busy === 'save' ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {/* Adding one starts from the shared list - a broker, or private pay - or a payer of the
            company's own. Choosing a shared one opens it, ready for its first state. */}
        {(!held.recordid || held.adding) && offered.length > 0 && (
          <div className="profileform">
            <label className="field span-6">Payer
              <select value={held.adding ? held.recordid : ''} onChange={(e) =>
                onPick(offered.find((o) => o.recordid === e.target.value))}>
                <option value="">New Payer</option>
                {offered.map((o) => <option key={o.recordid} value={o.recordid}>{o.name}</option>)}
              </select>
            </label>
          </div>
        )}
        {!held.privatepay && <>
        <fieldset className="plain">
        <div className="profileform">
          <label className="field span-4">Name *
            <input disabled={locked} value={f.name} className="upper"
              onChange={(e) => setF({ ...f, name: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-2">Status
            <select value={f.active ? 'active' : 'inactive'}
              onChange={(e) => setF({ ...f, active: e.target.value === 'active' })}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
          {/* What kind of payer this is, which decides how it can be billed - an insurer
              takes a claim, a broker its own submission, a facility an invoice. */}
          <label className="field span-3">Payer Type *
            <select disabled={locked} value={f.category} onChange={set('category')}>
              {Object.entries(categories).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
          {/* Claim.MD's own id for this payer. A claim sent with the wrong one is turned away
              at the front door, and there is no id at all for anyone not billed
              electronically. */}
          <label className="field span-3">Payer ID
            <input disabled={locked} value={f.payerid} onChange={set('payerid')} />
          </label>
          {scheduleField}

          <hr className="brandrule span-6" />
          {/* Where to write, because a denial is argued on paper and the paper has to go
              somewhere. The same fields, in the same order, as the company's own address. */}
          {/* Who the company deals with there is its own, so open even at a shared payer. */}
          <label className="field span-6">Contact
            <input value={f.contactname} className="upper"
              onChange={(e) => setF({ ...f, contactname: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-4">Address
            <input disabled={placed} value={f.address1} className="upper"
              onChange={(e) => setF({ ...f, address1: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-2">Suite
            <input disabled={placed} value={f.address2} className="upper"
              onChange={(e) => setF({ ...f, address2: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-3">City
            <input disabled={placed} value={f.city} className="upper"
              onChange={(e) => setF({ ...f, city: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-1">State
            <input disabled={placed} value={f.state} className="upper" maxLength={2}
              onChange={(e) => setF({ ...f, state: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-2">ZIP
            <input disabled={placed} value={f.zip} onChange={set('zip')} />
          </label>
          <label className="field span-2">Phone
            <PhoneInput disabled={placed} value={f.phone} onChange={set('phone')} />
          </label>
          {/* Still how a prior authorisation, an appeal and a records request reach plenty
              of payers. */}
          <label className="field span-2">Fax
            <PhoneInput disabled={placed} value={f.fax} onChange={set('fax')} autoComplete="off" />
          </label>
          <label className="field span-6">Contact Email
            <input value={f.contactemail}
              onChange={(e) => setF({ ...f, contactemail: e.target.value.toLowerCase() })} />
          </label>
          <label className="field span-6">Website
            <input disabled={locked} value={f.website} onChange={set('website')} />
          </label>

          <label className="field span-6">Notes
            <textarea disabled={locked} value={f.notes} onChange={set('notes')} rows={3} />
          </label>
        </div>
        </fieldset>
        </>}

        {/* Where the company carries for this payer. These lines are what decide its programs,
            so they are kept for shared payers as much as its own. */}
        {held.privatepay && <div className="profileform">{scheduleField}</div>}
        {held.recordid && <States payer={held} lines={lines} data={data} reload={reload}
          editing={line} setEditing={setLine} />}

        {/* Against every payer the company bills, shared ones included. These are this
            company's papers, shared with nobody, and they are the whole reason a shared
            payer has to be openable. */}
        {held.recordid && !held.privatepay && <Documents payer={held} adding={filing}
          setAdding={setFiling} />}
      </div>
    </Modal>
  )
}

// The states the company carries for this payer in, one line each, with the program the line
// falls under, its dates and whether it is in force.
function States({ payer, lines, data, reload, editing, setEditing }) {
  return (
    <>
      {/* Private pay has nothing above its lines to set them apart from. */}
      {!payer.privatepay && <>
        <hr className="brandrule" />
        <h3 className="formsection">States</h3>
      </>}
      {lines.length > 0 && (
        <table className="residencetable recordtable">
          <thead><tr><th>State</th><th className="growcol">Program</th><th className="center">Effective</th>
            <th>Status</th><th /></tr></thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.recordid}>
                <td>{l.state || '-'}</td>
                <td className="growcol">{data.programs[l.program] || l.program || '-'}</td>
                <td className="center">{[l.effectivefrom && date(l.effectivefrom),
                  l.effectiveto && date(l.effectiveto)].filter(Boolean).join(' - ') || 'N/A'}</td>
                <td className={live(l) ? 'st-active' : l.status === 'planned' ? 'st-ordered'
                  : 'st-inactive'}>{l.ended ? 'Ended' : STATUS[l.status] || l.status}</td>
                <td className="actions">
                  <button type="button" className="linkbtn edit" onClick={() => setEditing({
                    ...BLANK_LINE, ...l, effectivefrom: l.effectivefrom || '',
                    effectiveto: l.effectiveto || '', contractref: l.contractref || '',
                    note: l.note || '', requiresapproval: Boolean(l.requiresapproval),
                    reviewed: Boolean(l.reviewed),
                    services: (l.services || '').split(',').filter(Boolean) })}>Edit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing && (
        <LineDialog payer={payer} line={editing} data={data}
          current={editing.recordid ? lines.find((l) => l.recordid === editing.recordid) : null}
          reload={reload} onClose={() => setEditing(null)} />
      )}
    </>
  )
}

// One line: the state, its program, dates and status, and - for a payer with a contract - the
// contract's terms and what it asks of the drivers who work it.
function LineDialog({ payer, line, data, current, reload, onClose }) {
  const [f, setF] = useState(line)
  const [ask, setAsk] = useState(BLANK_ASK)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const act = async (fn, close) => {
    setBusy(true); setErr(null)
    try { await fn(); reload(); if (close) onClose() } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }
  const base = '/company/operating-profile/contracts'
  // Only the programs this kind of payer can carry; a line already on another keeps it listed.
  const kinds = payer.privatepay ? ['privatepay'] : data.categoryprograms[payer.category]
    || Object.keys(data.programs).filter((k) => k !== 'privatepay')
  const choices = f.program && !kinds.includes(f.program) ? [...kinds, f.program] : kinds
  const save = () => act(() => {
    const body = { ...f, payerid: payer.privatepay ? null : payer.recordid,
      scheduleid: f.scheduleid || null,
      effectivefrom: f.effectivefrom || null, effectiveto: f.effectiveto || null }
    return f.recordid ? api.put(`${base}/${f.recordid}`, body) : api.post(base, body)
  }, true)

  return (
    <Modal title={f.recordid ? 'Edit State' : 'Add A State'} onClose={onClose} width={720}
      footer={<>
        {f.recordid && (
          <div className="footactions">
            <button type="button" disabled={busy}
              onClick={() => act(() => api.del(`${base}/${f.recordid}`), true)}>Remove</button>
          </div>
        )}
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !f.state} onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className="field span-1">State *
            <select value={f.state} onChange={set('state')}>
              <option value="">-</option>
              {US_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="field span-3">Program
            <select value={f.program} disabled={choices.length < 2} onChange={set('program')}>
              {choices.map((k) => <option key={k} value={k}>{data.programs[k] || k}</option>)}
            </select>
          </label>
          <label className="field span-2">Status
            <select value={f.status} onChange={set('status')}>
              {Object.entries(STATUS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <label className="field span-3">Effective From
            <input type="date" value={f.effectivefrom} onChange={set('effectivefrom')} />
          </label>
          <label className="field span-3">Effective To
            <input type="date" value={f.effectiveto} onChange={set('effectiveto')} />
          </label>
          {/* Only where this state is paid differently from the payer's own schedule. */}
          <label className="field span-6">Fee Schedule
            <select value={f.scheduleid || ''} onChange={set('scheduleid')}>
              <option value="">Same As Payer</option>
              {data.schedules.filter((x) => x.kind === (payer.privatepay ? 'private' : payer.category))
                .map((x) => <option key={x.recordid} value={x.recordid}>{x.name}</option>)}
            </select>
          </label>
          {!payer.privatepay && <>
            <label className="field span-6">Contract ID
              <input value={f.contractref} className="upper"
                onChange={(e) => setF({ ...f, contractref: e.target.value.toUpperCase() })} />
            </label>
            <div className="field span-6">Covered Services
              <div className="row">
                {data.contractservices.map((s) => (
                  <label key={s} className="check">
                    <input type="checkbox" checked={f.services.includes(s)}
                      onChange={(e) => setF({ ...f, services: e.target.checked
                        ? [...f.services, s] : f.services.filter((x) => x !== s) })} />
                    {s[0].toUpperCase() + s.slice(1)}
                  </label>
                ))}
              </div>
            </div>
            <label className="check span-6">
              <input type="checkbox" checked={f.requiresapproval}
                onChange={(e) => setF({ ...f, requiresapproval: e.target.checked })} />
              Drivers must be approved before they work this contract
            </label>
            <label className="check span-6">
              <input type="checkbox" checked={f.reviewed}
                onChange={(e) => setF({ ...f, reviewed: e.target.checked })} />
              The contract has been reviewed for its driver requirements
            </label>
          </>}
          <label className="field span-6">Note
            <textarea value={f.note} className="upper"
              onChange={(e) => setF({ ...f, note: e.target.value.toUpperCase() })} />
          </label>
        </div>
        {/* What the contract asks of its drivers. Each points at a qualification the file
            already tracks, so it adds a source to that row rather than a second copy of it. */}
        {current && !payer.privatepay && (
          <>
            <h3 className="formsection">Driver Requirements In This Contract</h3>
            <table className="residencetable recordtable">
              <thead><tr><th>Qualification</th><th>Renewal</th><th>Clause</th><th /></tr></thead>
              <tbody>
                {current.requirements.map((r) => (
                  <tr key={r.recordid}>
                    <td>{r.qualification || r.qualificationcode}</td>
                    <td>{r.renewaldays ? `Every ${r.renewaldays} days` : 'Once'}</td>
                    <td>{r.clause || '-'}</td>
                    <td className="actions">
                      <button type="button" className="linkbtn" disabled={busy}
                        onClick={() => act(() => api.post(
                          `${base}/${f.recordid}/requirements/${r.recordid}/end`, {}))}>Remove</button>
                    </td>
                  </tr>
                ))}
                {!current.requirements.length && <tr><td colSpan={4}>None recorded.</td></tr>}
              </tbody>
            </table>
            <div className="profileform">
              <label className="field span-3">Qualification
                <select value={ask.qualificationcode}
                  onChange={(e) => setAsk({ ...ask, qualificationcode: e.target.value })}>
                  <option value="">Choose</option>
                  {data.catalog.map((q) => <option key={q.code} value={q.code}>{q.name}</option>)}
                </select>
              </label>
              <label className="field span-1">Renewal Days
                <input type="number" min="1" value={ask.renewaldays}
                  onChange={(e) => setAsk({ ...ask, renewaldays: e.target.value })} />
              </label>
              <label className="field span-2">Clause
                <input value={ask.clause} className="upper"
                  onChange={(e) => setAsk({ ...ask, clause: e.target.value.toUpperCase() })} />
              </label>
            </div>
            <div className="row">
              <button type="button" disabled={busy || !ask.qualificationcode}
                onClick={() => act(async () => {
                  await api.post(`${base}/${f.recordid}/requirements`, {
                    qualificationcode: ask.qualificationcode, clause: ask.clause || null,
                    renewaldays: ask.renewaldays ? Number(ask.renewaldays) : null })
                  setAsk(BLANK_ASK)
                })}>
                <Plus size={13} /> Add Requirement
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}

// What this company holds on file for this payer - the contract, its amendments, a rate
// sheet, a provider manual. The rates on a schedule are a copy of what the contract says, so
// when a payer underpays the paper should be one click from the payer rather than in
// somebody's mailbox.
//
// Shared payers hold documents too: the payer is everybody's, the paperwork is this
// company's. What a company may not do is rename a shared payer, which is a different thing.
function Documents({ payer, adding, setAdding }) {
  const [list, error, reload] = useLoad(
    () => api.get(`/company/payers/${payer.recordid}/documents`), [payer.recordid])
  const [viewing, setViewing] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const drop = async (id) => {
    setBusy(id); setErr(null)
    try {
      await api.del(`/company/payers/${payer.recordid}/documents/${id}`)
      reload()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  return (
    <>
      {err && <div className="notice bad">{err}</div>}
      {!list ? <Loading error={error} /> : (
        <>
          {list.length > 0 && <>
            <hr className="brandrule" />
            <h3 className="formsection">Documents</h3>
            <table className="residencetable recordtable">
              <thead><tr><th className="growcol">Document</th><th>In force</th>
                <th>Filed</th><th /></tr></thead>
              <tbody>
                {list.map((d) => (
                  <tr key={d.recordid}>
                    <td className="growcol">{d.title}</td>
                    <td>
                      {d.effectivefrom || d.effectiveto
                        ? `${d.effectivefrom ? date(d.effectivefrom) : '?'} - ${d.effectiveto ? date(d.effectiveto) : 'open'}`
                        : ''}
                    </td>
                    <td>{date(d.added)}</td>
                    <td className="actions">
                      {/* The house viewer. A plain link to the file would not carry the
                          session - the token is a header here, not a cookie - and the
                          download endpoint is also the one that logs who looked. */}
                      <button type="button" className="linkbtn edit"
                        onClick={() => setViewing(d)}>View</button>
                      <button type="button" className="linkbtn" disabled={busy === d.recordid}
                        onClick={() => drop(d.recordid)}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>}
        </>
      )}
      {adding && (
        <DocumentDialog payer={payer} onClose={() => setAdding(false)}
          onSaved={() => { setAdding(false); reload() }} />
      )}
      {viewing && (
        <DocumentViewer id={viewing.documentid} name={viewing.title}
          onClose={() => setViewing(null)} />
      )}
    </>
  )
}

function DocumentDialog({ payer, onClose, onSaved }) {
  const [f, setF] = useState({ title: '', effectivefrom: '', effectiveto: '', note: '' })
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const missing = !f.title.trim() || !file

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('title', f.title.trim())
      if (f.effectivefrom) body.append('effectivefrom', f.effectivefrom)
      if (f.effectiveto) body.append('effectiveto', f.effectiveto)
      if (f.note.trim()) body.append('note', f.note.trim())
      body.append('file', file)
      await api.post(`/company/payers/${payer.recordid}/documents`, body)
      onSaved()
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <Modal title="Add A Document" onClose={onClose} width={620}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || missing} onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Add'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className="field span-6">What This Is *
            <input value={f.title} className="upper"
              onChange={(e) => setF({ ...f, title: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-3">In Force From
            <input type="date" value={f.effectivefrom} onChange={set('effectivefrom')} />
          </label>
          <label className="field span-3">Until
            <input type="date" value={f.effectiveto} onChange={set('effectiveto')} />
          </label>
          <label className="field span-6">File *
            <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
          <label className="field span-6">Note
            <textarea value={f.note} onChange={set('note')} rows={2} />
          </label>
        </div>
      </div>
    </Modal>
  )
}
