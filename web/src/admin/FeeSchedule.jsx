import { useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { money } from '../lib/format.js'
import { Badge, useLoad } from '../components/ui.jsx'
import DataGrid from '../components/DataGrid.jsx'
import { Modal, useCanEdit, useForm } from './common.jsx'

const COLUMNS = [
  { id: 'name', label: 'Service' },
  { id: 'code', label: 'Code', width: 170 },
  { id: 'price', label: 'Price', width: 140, numeric: true },
  { id: 'status', label: 'Status', width: 120 },
]

// What TripProof charges for each screening service it orders for a customer.
export default function FeeSchedule() {
  const [data, error, reload] = useLoad(() => api.get('/admin/fees'))
  const [editing, setEditing] = useState(null)
  const editable = useCanEdit()
  return (
    <div className="fill">
      <div className="pagehead">
        <h1>Fee Schedule</h1>
        {editable && <button className="primary" onClick={() => setEditing({})}><Plus size={14} /> New fee</button>}
      </div>
      <DataGrid columns={COLUMNS} rows={data} rowKey={(f) => f.recordid} error={error}
        onRowClick={editable ? setEditing : undefined} empty="No fees yet."
        cells={(f) => [
          <span className="cellname">{f.name}</span>,
          f.code,
          f.price == null ? <span className="muted">Not set</span> : money(f.price),
          <Badge state={f.active ? 'active' : 'disabled'}>{f.active ? 'Active' : 'Inactive'}</Badge>,
        ]} />
      {editing && <FeeForm fee={editing.recordid ? editing : null} onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); reload() }} />}
    </div>
  )
}

function FeeForm({ fee, onClose, onSaved }) {
  const f = useForm({ code: fee?.code || '', name: fee?.name || '', price: fee?.price ?? '', sortorder: fee?.sortorder ?? 0,
    active: fee ? !!fee.active : true }, async (v) => {
    const body = { code: v.code, name: v.name, price: v.price === '' ? null : Number(v.price), sortorder: Number(v.sortorder) || 0,
      active: !!v.active }
    if (fee) await api.put(`/admin/fees/${fee.recordid}`, body)
    else await api.post('/admin/fees', body)
    onSaved()
  })
  const v = f.values
  return (
    <Modal width={560} title={fee ? fee.name : 'New fee'} onClose={onClose}
      footer={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={f.onSubmit} disabled={f.busy}>Save</button></>}>
      <form className="profileform" onSubmit={f.onSubmit}>
        <label className="field span-6">Service *<input required value={v.name} onChange={f.set('name')} /></label>
        <label className="field span-2">Code *<input required disabled={!!fee} value={v.code} onChange={f.set('code')} /></label>
        <label className="field span-2">Price ($)<input type="number" min="0" step="0.01" value={v.price} onChange={f.set('price')} /></label>
        <label className="field span-2">Sort order<input type="number" value={v.sortorder} onChange={f.set('sortorder')} /></label>
        <label className="check span-6"><input type="checkbox" checked={v.active} onChange={f.set('active')} /> Active</label>
      </form>
      {f.error && <div className="error">{f.error}</div>}
    </Modal>
  )
}
