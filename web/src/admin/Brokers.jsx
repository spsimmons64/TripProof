import { useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { count } from '../lib/format.js'
import { Badge, useLoad } from '../components/ui.jsx'
import DataGrid from '../components/DataGrid.jsx'
import { Modal, clean, useCanEdit, useForm } from './common.jsx'

const COLUMNS = [
  { id: 'name', label: 'Broker' },
  { id: 'category', label: 'Payer Type', width: 200 },
  // How the clearinghouse names it. Blank for anyone not billed electronically - a broker
  // takes its own submission and a facility takes an invoice.
  { id: 'city', label: 'Where', width: '18%', sortable: false },
  { id: 'phone', label: 'Phone', width: 140 },
  { id: 'trips', label: 'Trips', width: 90, numeric: true },
  { id: 'status', label: 'Status', width: 110 },
]

export default function Brokers() {
  const [data, error, reload] = useLoad(() => api.get('/admin/brokers'))
  const [editing, setEditing] = useState(null)
  const editable = useCanEdit()
  return (
    <div className="fill">
      <div className="pagehead">
        <h1>Brokers</h1>
        {editable && <button className="primary" onClick={() => setEditing({})}><Plus size={14} /> New broker</button>}
      </div>
      <DataGrid columns={COLUMNS} rows={data?.payers} rowKey={(b) => b.recordid} error={error} onRowClick={setEditing} empty="No brokers yet."
        cells={(b) => [
          <><span className="cellname">{b.name}</span><span className="rowemail plandesc">{b.code}</span></>,
          data.categories[b.category] || b.category,
          [b.city, b.state].filter(Boolean).join(', '),
          b.phone || '',
          count(b.trips),
          <Badge state={b.active ? 'active' : 'disabled'} />,
        ]} />
      {editing && <PayerDialog payer={editing.recordid ? editing : null}
        categories={data.categories} editable={editable}
        onClose={() => { setEditing(null); reload() }} onSaved={() => { setEditing(null); reload() }} />}
    </div>
  )
}

function PayerDialog({ payer, categories, editable, onClose, onSaved }) {
  const b = payer || {}
  const f = useForm({ code: b.code || '', name: b.name || '', category: b.category || 'broker',
     payerid: b.payerid || '', website: b.website || '', notes: b.notes || '',
     address1: b.address1 || '', address2: b.address2 || '', city: b.city || '',
     state: b.state || '', zip: b.zip || '', phone: b.phone || '', fax: b.fax || '',
     contactname: b.contactname || '', contactemail: b.contactemail || '',
     active: b.active ?? true },
    async (v) => {
      if (payer) await api.put(`/admin/brokers/${payer.recordid}`, clean(v))
      else await api.post('/admin/brokers', clean(v))
      onSaved()
    })
  return (
    <Modal width={820} title={payer ? payer.name : 'New Broker'} onClose={onClose}
      footer={<><button onClick={onClose}>Cancel</button>{editable && <button className="primary" onClick={f.onSubmit} disabled={f.busy}>Save</button>}</>}>
      {(
        <fieldset className="plain" disabled={!editable}>
          <form className="profileform" onSubmit={f.onSubmit}>
            <label className="field span-2">Code *<input required disabled={!!payer} value={f.values.code} onChange={f.set('code')} /></label>
            <label className="field span-4">Name *<input required value={f.values.name} onChange={f.set('name')} /></label>
            {/* What kind of payer this is, which is what decides how a company can bill it -
                a broker takes its own submission, a facility takes an invoice, an insurer
                takes a claim. */}
            <label className="field span-3">Payer Type *
              <select value={f.values.category} onChange={f.set('category')}>
                {Object.entries(categories).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </label>
            {/* Claim.MD's own id for this payer. A claim sent with the wrong one is turned
                away at the front door, and there is no id at all for anyone not billed
                electronically. */}
            <label className="field span-3">Payer ID
              <input value={f.values.payerid} onChange={f.set('payerid')} />
            </label>
            <label className="field span-6">Contact<input value={f.values.contactname} onChange={f.set('contactname')} /></label>
            <label className="field span-6">Website<input value={f.values.website} onChange={f.set('website')} /></label>
            {/* Where to write and who to ring. The same fields the company's own payer
                screen carries, written by the same code, so one cannot gain a field the
                other quietly drops. */}
            <label className="field span-4">Address<input value={f.values.address1} onChange={f.set('address1')} /></label>
            <label className="field span-2">Suite<input value={f.values.address2} onChange={f.set('address2')} /></label>
            <label className="field span-3">City<input value={f.values.city} onChange={f.set('city')} /></label>
            <label className="field span-1">State<input value={f.values.state} maxLength={2} onChange={f.set('state')} /></label>
            <label className="field span-2">ZIP<input value={f.values.zip} onChange={f.set('zip')} /></label>
            <label className="field span-2">Phone<input value={f.values.phone} onChange={f.set('phone')} /></label>
            <label className="field span-2">Fax<input value={f.values.fax} onChange={f.set('fax')} /></label>
            <label className="field span-6">Contact Email<input value={f.values.contactemail} onChange={f.set('contactemail')} /></label>
            <label className="field span-6">Notes<textarea value={f.values.notes} onChange={f.set('notes')} rows={3} /></label>
            <label className="check span-6"><input type="checkbox" checked={f.values.active} onChange={f.set('active')} /> Active</label>
          </form>
          {f.error && <div className="error">{f.error}</div>}
        </fieldset>
      )}
    </Modal>
  )
}
