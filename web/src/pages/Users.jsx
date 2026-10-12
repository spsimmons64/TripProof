import { useState } from 'react'
import { Plus, Send } from 'lucide-react'
import { api } from '../lib/api.js'
import { Email } from '../components/Contact.jsx'
import SupervisorRecord from '../components/SupervisorRecord.jsx'
import { date } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { useUser } from '../App.jsx'
import { Modal } from '../admin/common.jsx'

// Who at this company can sign in.
//
// A login is made here and is unusable until its invitation has been opened - nobody is ever handed
// a password, and nobody here can set one for somebody else. Closing a login keeps the person: the
// activity log has their name against everything they did, and that has to keep making sense.

const ROLES = [
  ['owner', 'Owner', 'Everything, including billing and who else can sign in'],
  ['admin', 'Administrator', 'Everything except billing'],
  ['staff', 'Staff', 'Day-to-day work: drivers, vehicles, trips, documents'],
  ['auditor', 'Auditor', 'Read-only'],
]
const ROLE_NAME = Object.fromEntries(ROLES.map(([k, l]) => [k, l]))

export default function Users() {
  const me = useUser()
  // TripProof staff read this page and change nothing on it - the server refuses either way, so the
  // page does not offer buttons that cannot work.
  const staff = Boolean(me?.platformrole)
  const [data, error, reload] = useLoad(() => api.get('/account/users'), [])
  const [adding, setAdding] = useState(false)
  const [record, setRecord] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [link, setLink] = useState(null)

  const act = async (key, fn) => {
    setBusy(key); setErr(null)
    try { await fn(); reload() } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  const invite = (u) => act(u.recordid, async () => {
    const r = await api.post(`/account/users/${u.recordid}/invite`, {})
    // With no mail configured the link comes back instead, to be passed on by hand.
    if (!r.emailed && r.link) setLink(r.link)
  })
  const change = (u, patch) => act(u.recordid, () => api.patch(`/account/users/${u.recordid}`, patch))

  if (!data) return <Loading error={error} />
  const items = data.items || []

  return (
    <div className="stack">
      <div className="pagehead">
        <h1>Users</h1>
        {!staff && (
          <button className="primary" onClick={() => setAdding(true)}><Plus size={14} /> Add a user</button>
        )}
      </div>

      {err && <div className="notice bad">{err}</div>}
      {staff && (
        <div className="notice">Signed in as TripProof staff: this company manages its own users.</div>
      )}
      {link && (
        <div className="notice">
          <div>No mail is configured, so pass this on yourself:
            <input value={link} readOnly onFocus={(e) => e.target.select()} />
          </div>
        </div>
      )}

      <div className="card qualcard">
        <table className="residencetable credentiallist">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Last signed in</th>
            <th>Supervisor training</th><th /></tr></thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.recordid}>
                <td>{u.name}{u.recordid === data.me ? ' (you)' : ''}</td>
                <td><Email address={u.email} /></td>
                <td>
                  <select value={u.role} disabled={staff || u.recordid === data.me || Boolean(u.deleted)}
                    onChange={(e) => change(u, { role: e.target.value })}>
                    {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </td>
                <td>{u.deleted ? 'Closed' : u.lastlogin ? date(u.lastlogin)
                  : u.passwordset ? 'Never' : 'Invited, not used'}</td>
                {/* 49 CFR 382.603. Only for the people it reaches - a role nobody holds is not
                    a gap in everybody's row. */}
                <td className={u.supervisor && !u.trainingsignedon ? 'st-expired' : undefined}>
                  {!u.supervisor ? '-'
                    : u.trainingsignedon
                      ? <button type="button" className="linkbtn edit"
                          onClick={() => setRecord(u)}>Signed {date(u.trainingsignedon)}</button>
                      : 'Not signed'}
                </td>
                <td className="actions">
                  {!staff && !u.deleted && !u.lastlogin && (
                    <button type="button" className="sm" disabled={busy === u.recordid}
                      onClick={() => invite(u)}><Send size={13} /> Invite again</button>
                  )}
                  {!staff && u.recordid !== data.me && (
                    <button type="button" className="sm" disabled={busy === u.recordid}
                      onClick={() => change(u, { disabled: !u.deleted })}>
                      {u.deleted ? 'Reopen' : 'Close'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!items.length && <tr><td colSpan={6}>Nobody yet.</td></tr>}
          </tbody>
        </table>
      </div>

      {record && <SupervisorRecord who={record} onClose={() => setRecord(null)} />}
      {adding && <AddUser onClose={() => setAdding(false)}
        onAdded={(r) => { setAdding(false); if (!r.invitation?.emailed) setLink(r.invitation?.link); reload() }} />}
    </div>
  )
}

function AddUser({ onClose, onAdded }) {
  const [v, setV] = useState({ name: '', email: '', role: 'staff' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setV({ ...v, [k]: e.target.value })

  const save = async () => {
    setBusy(true); setErr(null)
    try { onAdded(await api.post('/account/users', v)) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal title="Add A User" onClose={onClose} width={560} footer={<>
      <button type="button" onClick={onClose}>Cancel</button>
      <button type="button" className="primary" disabled={busy || !v.name.trim() || !v.email.trim()}
        onClick={save}>Send the invitation</button>
    </>}>
      <div className="reviewform bare">
        <div className="form">
          {err && <div className="notice bad span-12">{err}</div>}
          <label className="field span-6">Name *<input value={v.name} onChange={set('name')} autoFocus /></label>
          <label className="field span-6">Email *
            <input type="email" value={v.email} onChange={set('email')} /></label>
          <label className="field span-12">Role
            <select value={v.role} onChange={set('role')}>
              {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select></label>
          <p className="span-12 formprose">{ROLES.find(([k]) => k === v.role)?.[2]}</p>
        </div>
      </div>
    </Modal>
  )
}
