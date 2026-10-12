import { useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { money } from '../lib/format.js'
import { Badge, useLoad } from '../components/ui.jsx'
import DataGrid from '../components/DataGrid.jsx'
import { Modal, useCanEdit, useForm } from './common.jsx'

const COLUMNS = [
  { id: 'name', label: 'Plan' },
  { id: 'range', label: 'Vehicles', width: 120, numeric: true },
  { id: 'price', label: 'Price / month', width: 150, numeric: true },
  { id: 'trial', label: 'Free trial', width: 120, numeric: true },
  { id: 'subscribers', label: 'Subscribers', width: 130, numeric: true },
  { id: 'applying', label: 'Applying', width: 110, numeric: true },
  { id: 'status', label: 'Status', width: 120 },
]

const range = (p) => (p.maxvehicles ? `${p.minvehicles}-${p.maxvehicles}` : `${p.minvehicles}+`)

// Subscription plans: one tier per fleet-size range. The online application picks the active tier
// whose range contains the applicant's vehicle count, so active ranges may not overlap.
export default function Plans() {
  const [data, error, reload] = useLoad(() => api.get('/admin/plans'))
  const [editing, setEditing] = useState(null)
  const editable = useCanEdit()
  return (
    <div className="fill">
      <div className="pagehead">
        <h1>Subscription plans</h1>
        {editable && <button className="primary" onClick={() => setEditing({})}><Plus size={14} /> New plan</button>}
      </div>
      <div className="notice info" style={{ marginBottom: 16 }}>Pricing is by fleet size: an applicant’s vehicle count picks the active plan whose range contains it. A plan with no price is shown as “Contact us” and can’t be bought online. Changing a price affects new subscriptions only - existing subscribers keep the price they signed up at.</div>
      <DataGrid columns={COLUMNS} rows={data} rowKey={(p) => p.recordid} error={error} onRowClick={editable ? setEditing : undefined}
        empty="No plans yet."
        cells={(p) => [
          <><span className="cellname">{p.name}</span>{p.description && <span className="rowemail plandesc">{p.description}</span>}</>,
          range(p),
          p.monthlyprice == null ? <span className="muted">Contact us</span> : money(p.monthlyprice),
          p.trialdays ? `${p.trialdays} days` : '-',
          p.subscribers, p.applying,
          <Badge state={p.active ? 'active' : 'disabled'}>{p.active ? 'Active' : 'Retired'}</Badge>,
        ]} />
      {editing && <PlanForm plan={editing.recordid ? editing : null} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}
    </div>
  )
}

function PlanForm({ plan, onClose, onSaved }) {
  const p = plan || {}
  const f = useForm({
    code: p.code || '', name: p.name || '', description: p.description || '', minvehicles: p.minvehicles ?? '', maxvehicles: p.maxvehicles ?? '',
    monthlyprice: p.monthlyprice ?? '', contact: plan ? p.monthlyprice == null : false, trialdays: p.trialdays ?? 14,
    features: (p.features || []).join('\n'), active: p.active ?? true, sortorder: p.sortorder ?? 0,
  }, async (v) => {
    const body = {
      code: v.code, name: v.name, description: v.description || null, minvehicles: Number(v.minvehicles),
      maxvehicles: v.maxvehicles === '' ? null : Number(v.maxvehicles),
      monthlyprice: v.contact || v.monthlyprice === '' ? null : Number(v.monthlyprice), trialdays: Number(v.trialdays) || 0,
      features: v.features.split('\n').map((s) => s.trim()).filter(Boolean), active: !!v.active, sortorder: Number(v.sortorder) || 0,
    }
    if (plan) await api.put(`/admin/plans/${plan.recordid}`, body)
    else await api.post('/admin/plans', body)
    onSaved()
  })
  const v = f.values
  return (
    <Modal width={680} title={plan ? `Edit ${plan.name}` : 'New plan'} onClose={onClose}
      footer={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={f.onSubmit} disabled={f.busy}>Save</button></>}>
      <form className="profileform" onSubmit={f.onSubmit}>
        <label className="field span-2">Code *<input required disabled={!!plan} value={v.code} onChange={f.set('code')} /></label>
        <label className="field span-4">Name *<input required value={v.name} onChange={f.set('name')} /></label>
        <label className="field span-6">Short description<input value={v.description} onChange={f.set('description')} /></label>
        <label className="field span-2">From vehicles *<input type="number" min="1" required value={v.minvehicles} onChange={f.set('minvehicles')} /></label>
        <label className="field span-2">To vehicles<input type="number" min="1" value={v.maxvehicles} onChange={f.set('maxvehicles')} /></label>
        <label className="field span-2">Sort order<input type="number" value={v.sortorder} onChange={f.set('sortorder')} /></label>
        <label className="field span-2">Price per month ($)<input type="number" min="0" step="0.01" value={v.contact ? '' : v.monthlyprice} disabled={v.contact} onChange={f.set('monthlyprice')} /></label>
        <label className="field span-2">Free trial (days)<input type="number" min="0" max="90" value={v.trialdays} onChange={f.set('trialdays')} /></label>
        <label className="check span-2" style={{ alignSelf: 'end', height: 36 }}><input type="checkbox" checked={v.contact} onChange={f.set('contact')} /> Contact us (no online price)</label>
        <label className="field span-6">Features (one per line, shown on the plan card)<textarea value={v.features} onChange={f.set('features')} rows={4} /></label>
        <label className="check span-6"><input type="checkbox" checked={v.active} onChange={f.set('active')} /> Active (offered to new applicants)</label>
      </form>
      {f.error && <div className="error">{f.error}</div>}
    </Modal>
  )
}
