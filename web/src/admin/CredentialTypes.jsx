import { useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'
import { Modal, SUBJECT_LABEL, clean, useCanEdit, useForm } from './common.jsx'

export default function CredentialTypes() {
  const [data, error, reload] = useLoad(() => api.get('/admin/credentialtypes'))
  const [editing, setEditing] = useState(null)
  const editable = useCanEdit()
  if (!data) return <Loading error={error} />

  return (
    <div className="stack">
      <div className="pagehead">
        <div><h1>Credential types</h1></div>
        {editable && <button className="primary" onClick={() => setEditing({})}><Plus size={14} /> New type</button>}
      </div>
      {['driver', 'vehicle', 'company'].map((s) => (
        <div className="card" key={s}>
          <h2>{SUBJECT_LABEL[s]}</h2>
          <div className="tablewrap"><table>
            <thead><tr><th>Type</th><th>Category</th><th>Age limit</th><th>If no expiry printed</th>
              <th className="num">In use</th><th>Status</th></tr></thead>
            <tbody>{data.filter((t) => t.subject === s).map((t) => (
              <tr key={t.recordid} className={editable ? 'click' : ''} onClick={() => editable && setEditing(t)}>
                <td>{t.name}{t.hasamount ? <> <Badge state="neutral">$ limit</Badge></> : null}<div className="small muted">{t.code}</div></td>
                <td className="small">{t.category || '-'}</td>
                <td className="small">{t.maxagedays ? `${t.maxagedays} days` : '-'}</td>
                <td className="small">{t.defaultvaliddays ? `good ${t.defaultvaliddays} days` : '-'}</td>
                <td className="num small">{t.credentials} on file</td>
                <td><Badge state={t.active ? 'active' : 'disabled'} /></td>
              </tr>
            ))}</tbody>
          </table></div>
        </div>
      ))}
      {editing && <TypeForm type={editing.recordid ? editing : null} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}
    </div>
  )
}

function TypeForm({ type, onClose, onSaved }) {
  const t = type || {}
  const f = useForm({ code: t.code || '', name: t.name || '', subject: t.subject || 'driver', category: t.category || '',
    maxagedays: t.maxagedays ?? '', defaultvaliddays: t.defaultvaliddays ?? '', hasamount: !!t.hasamount,
    description: t.description || '', active: t.active ?? true },
  async (v) => {
    const body = clean({ ...v, maxagedays: v.maxagedays === '' ? null : Number(v.maxagedays),
      defaultvaliddays: v.defaultvaliddays === '' ? null : Number(v.defaultvaliddays) })
    if (type) await api.put(`/admin/credentialtypes/${type.recordid}`, body)
    else await api.post('/admin/credentialtypes', body)
    onSaved()
  })
  return (
    <Modal title={type ? `Edit ${type.name}` : 'New Credential Type'} onClose={onClose}
      footer={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={f.onSubmit} disabled={f.busy}>Save</button></>}>
      <form className="form" onSubmit={f.onSubmit}>
        <label className="field">Code *<input required disabled={!!type} value={f.values.code} onChange={f.set('code')} /></label>
        <label className="field">Name *<input required value={f.values.name} onChange={f.set('name')} /></label>
        <label className="field">Held by
          <select disabled={!!type} value={f.values.subject} onChange={f.set('subject')}>
            <option value="driver">Driver</option><option value="vehicle">Vehicle</option><option value="company">Company</option>
          </select>
        </label>
        <label className="field">Category<input value={f.values.category} onChange={f.set('category')} /></label>
        <label className="field">Age limit (days)<input type="number" min="1" value={f.values.maxagedays} onChange={f.set('maxagedays')} /></label>
        <label className="field">Good for (days) when no expiry printed<input type="number" min="1" value={f.values.defaultvaliddays} onChange={f.set('defaultvaliddays')} /></label>
      </form>
      <label className="field">Description (shown when entering a credential)<input value={f.values.description} onChange={f.set('description')} /></label>
      <div className="row">
        <label className="check"><input type="checkbox" checked={f.values.hasamount} onChange={f.set('hasamount')} /> Carries a dollar limit (insurance)</label>
        <label className="check"><input type="checkbox" checked={f.values.active} onChange={f.set('active')} /> Active</label>
      </div>
      <div className="small muted">
        <b>Age limit</b>: a check older than this never counts, whatever is printed (monthly exclusion checks: 31).{' '}
        <b>Good for</b>: assumed validity for certificates without a printed expiry (CPR: 730).
        Code and holder can’t change after creation.
      </div>
      {f.error && <div className="error">{f.error}</div>}
    </Modal>
  )
}
