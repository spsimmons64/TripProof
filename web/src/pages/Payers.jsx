import { useState } from 'react'
import { Loader2, Plus, Upload } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { date } from '../lib/format.js'
import { Modal } from '../admin/common.jsx'
import DocumentViewer from '../components/DocumentViewer.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'

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

export default function Payers() {
  const [data, error, reload] = useLoad(() => api.get('/company/payers'), [])
  const [editing, setEditing] = useState(null)
  const g = useGridParams({ defaultSort: 'name', defaultDir: 'asc' })

  if (!data) return <div className="card"><Loading error={error} /></div>
  // Sorted and paged here, as the fee schedules are: a company has a handful of payers, and
  // a round trip to reorder them is one nobody should wait for.
  const flip = g.dir === 'desc' ? -1 : 1
  const shown = [...data.payers].sort((a, b) => {
    const x = a[g.sort] ?? '', y = b[g.sort] ?? ''
    if (x === y) return a.name.localeCompare(b.name)
    return (x > y ? 1 : -1) * flip
  })
  const page = shown.slice((g.page - 1) * g.pagesize, g.page * g.pagesize)

  return (
    <div className="fill">
      <div className="pagehead">
        <div>
          <h1>Payers</h1>
          <div className="muted">Who this company bills for a trip.</div>
        </div>
        <button type="button" className="primary" onClick={() => setEditing({ ...BLANK })}>
          <Plus size={14} /> Add A Payer
        </button>
      </div>

      <DataGrid
        columns={[
          { id: 'name', label: 'Payer' },
          { id: 'category', label: 'Payer Type', width: '20%' },
          { id: 'city', label: 'Where', width: '22%', sortable: false },
          { id: 'active', label: 'State', width: 120 },
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
          <b>{x.name}{x.shared
            ? <span className="muted"> · shared</span> : null}</b>,
          data.categories[x.category] || x.category,
          [x.city, x.state].filter(Boolean).join(', '),
          <span className={x.active ? 'st-active' : 'st-inactive'}>
            {x.active ? 'Active' : 'Inactive'}
          </span>,
        ]} />

      {editing && (
        <PayerDialog held={editing} categories={data.categories}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload() }} />
      )}
    </div>
  )
}

function PayerDialog({ held, categories, onClose, onSaved }) {
  const [f, setF] = useState({
    ...BLANK, ...held,
    payerid: held.payerid || '', website: held.website || '', notes: held.notes || '',
    ...Object.fromEntries(ADDRESS.map((k) => [k, held[k] || ''])),
    active: held.active === undefined ? true : Boolean(held.active),
  })
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const missing = !f.name.trim()

  const act = async (fn, key) => {
    setBusy(key); setErr(null)
    try { await fn(); onSaved() } catch (e) { setErr(e.message); setBusy(null) }
  }

  return (
    <Modal title={held.recordid ? 'Payer' : 'Add A Payer'} onClose={onClose} width={720}
      footer={<>
        {held.recordid && !held.shared && (
          <div className="footactions">
            <button type="button" disabled={busy !== null}
              onClick={() => act(() => api.del(`/company/payers/${held.recordid}`), 'remove')}>
              Remove
            </button>
          </div>
        )}
        <button type="button" onClick={onClose}>{held.shared ? 'Close' : 'Cancel'}</button>
        {!held.shared && (
          <button type="button" className="primary" disabled={busy !== null || missing}
            onClick={() => act(() => (held.recordid
              ? api.put(`/company/payers/${held.recordid}`, f)
              : api.post('/company/payers', f)), 'save')}>
            {busy === 'save' ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
        )}
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <fieldset className="plain" disabled={Boolean(held.shared)}>
        <div className="profileform">
          <label className="field span-4">Name *
            <input value={f.name} className="upper"
              onChange={(e) => setF({ ...f, name: e.target.value.toUpperCase() })} />
          </label>
          <label className="field switch span-2 beside">
            <input type="checkbox" checked={f.active}
              onChange={(e) => setF({ ...f, active: e.target.checked })} />
            <span className="lever" aria-hidden="true" />
            Active
          </label>
          {/* What kind of payer this is, which decides how it can be billed - an insurer
              takes a claim, a broker its own submission, a facility an invoice. */}
          <label className="field span-3">Payer Type *
            <select value={f.category} onChange={set('category')}>
              {Object.entries(categories).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
          {/* Claim.MD's own id for this payer. A claim sent with the wrong one is turned away
              at the front door, and there is no id at all for anyone not billed
              electronically. */}
          <label className="field span-3">Payer ID
            <input value={f.payerid} onChange={set('payerid')} />
          </label>
          <label className="field span-6">Contact
            <input value={f.contactname} className="upper"
              onChange={(e) => setF({ ...f, contactname: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-6">Website
            <input value={f.website} onChange={set('website')} />
          </label>

          <hr className="brandrule span-6" />
          {/* Where to write, because a denial is argued on paper and the paper has to go
              somewhere. The same fields, in the same order, as the company's own address. */}
          <label className="field span-4">Address
            <input value={f.address1} className="upper"
              onChange={(e) => setF({ ...f, address1: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-2">Suite
            <input value={f.address2} className="upper"
              onChange={(e) => setF({ ...f, address2: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-3">City
            <input value={f.city} className="upper"
              onChange={(e) => setF({ ...f, city: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-1">State
            <input value={f.state} className="upper" maxLength={2}
              onChange={(e) => setF({ ...f, state: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-2">ZIP
            <input value={f.zip} onChange={set('zip')} />
          </label>
          <label className="field span-2">Phone
            <input value={f.phone} onChange={set('phone')} />
          </label>
          {/* Still how a prior authorisation, an appeal and a records request reach plenty
              of payers. */}
          <label className="field span-2">Fax
            <input value={f.fax} onChange={set('fax')} />
          </label>
          <label className="field span-6">Contact email
            <input value={f.contactemail}
              onChange={(e) => setF({ ...f, contactemail: e.target.value.toLowerCase() })} />
          </label>

          <label className="field span-6">Notes
            <textarea value={f.notes} onChange={set('notes')} rows={3} />
          </label>
        </div>
        </fieldset>

        {/* Against every payer the company bills, shared ones included. These are this
            company's papers, shared with nobody, and they are the whole reason a shared
            payer has to be openable. */}
        {held.recordid && <Documents payer={held} />}
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
function Documents({ payer }) {
  const [list, error, reload] = useLoad(
    () => api.get(`/company/payers/${payer.recordid}/documents`), [payer.recordid])
  const [adding, setAdding] = useState(false)
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
      <hr className="brandrule" />
      <h3 className="formsection">Documents</h3>
      {err && <div className="notice bad">{err}</div>}
      {!list ? <Loading error={error} /> : (
        <>
          {list.length > 0 && (
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
          )}
          <div className="formactions">
            <button type="button" onClick={() => setAdding(true)}>
              <Upload size={13} /> Add A Document
            </button>
          </div>
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
          <label className="field span-6">What this is *
            <input value={f.title} className="upper"
              onChange={(e) => setF({ ...f, title: e.target.value.toUpperCase() })} />
          </label>
          <label className="field span-3">In force from
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
