import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Mail, Pencil, Plus, Rocket } from 'lucide-react'
import { launchAccount } from '../lib/launch.js'
import { api } from '../lib/api.js'
import { Email } from '../components/Contact.jsx'
import { count, tzDate, tzDateTime, money0 } from '../lib/format.js'
import { formatEin, formatPhone } from '../lib/masks.js'
import TimeZoneSelect from '../components/TimeZoneSelect.jsx'
import { Badge, Loading, Tile, useLoad } from '../components/ui.jsx'
import { InvitationSent, Modal, clean, useCanEdit, useForm } from './common.jsx'
import CustomerProfileForm from './CustomerProfile.jsx'

export default function CustomerDetail() {
  const { id } = useParams()
  const [a, error, reload] = useLoad(() => api.get(`/admin/accounts/${id}`), [id])
  const [editing, setEditing] = useState(false)
  const [addingUser, setAddingUser] = useState(false)
  const [invitation, setInvitation] = useState(null)
  const editable = useCanEdit()
  if (!a) return <Loading error={error} />
  const s = a.stats

  const toggleStatus = async () => {
    const next = a.status === 'inactive' ? 'active' : 'inactive'
    if (next === 'inactive' && !confirm(`Deactivate ${a.name}? Every user is signed out and cannot sign in until it is made active again.`)) return
    await api.patch(`/admin/accounts/${id}`, { status: next })
    reload()
  }
  const invite = async (u) => {
    if (!confirm(`Send ${u.email} an email with a link to set a new password?`)) return
    setInvitation(await api.post(`/admin/users/${u.recordid}/invite`))
    reload()
  }
  const toggleUser = async (u) => { await api.patch(`/admin/users/${u.recordid}`, { disabled: !u.deleted }); reload() }
  const cityline = [a.city, [a.state, a.zip].filter(Boolean).join(' ')].filter(Boolean).join(', ')

  // The profile, in the order the customer record is read.
  const profile = [
    ['Account number', a.accountnumber],
    ['Company name', a.name],
    ['Address', [a.address1, a.address2, cityline].filter(Boolean).map((l) => <div key={l}>{l}</div>)],
    ['Telephone', a.phone && formatPhone(a.phone)],
    ['Fax', a.fax && formatPhone(a.fax)],
    ['EIN', a.ein && formatEin(a.ein)],
    ['Admin name', a.adminname],
    ['Admin email', a.adminemail && <a href={`mailto:${a.adminemail}`}>{a.adminemail}</a>],
    ['Medicaid ID', a.medicaidid],
    ['NPI', a.npi],
  ]

  return (
    <div className="stack">
      <div className="pagehead">
        <div>
          <div className="small"><Link to="/admin/customers">Customers</Link></div>
          <h1 className="row">{a.name} <Badge state={a.status} /></h1>
          <div className="muted">Account #{a.accountnumber} · customer since {tzDate(a.added)}</div>
        </div>
        <div className="row">
          <button className="launch" onClick={() => launchAccount(id)}><Rocket size={14} /> Launch</button>
        {editable && (
          <>
            <button onClick={() => setEditing(true)}><Pencil size={14} /> Edit profile</button>
            <button className={a.status === 'inactive' ? 'primary' : 'danger'} onClick={toggleStatus}>{a.status === 'inactive' ? 'Activate' : 'Deactivate'}</button>
          </>
        )}
        </div>
      </div>

      <div className="grid cols-4">
        <Tile className="hero fill-orange" label="At audit risk" value={money0(s.atrisk)} sub={`${count(s.risktrips)} of ${count(s.trips)} trips`} />
        <Tile className="fill-teal" label="Billed" value={money0(s.billed)} sub={s.lastimport ? `last import ${tzDateTime(s.lastimport)}` : 'no imports yet'} />
        <Tile className="fill-light" label="Drivers" value={count(s.drivers)} sub={`${s.stubdrivers} incomplete · ${count(s.vehicles)} vehicles`} />
        <Tile label="Credentials" value={count(s.credentials)} sub={`${s.packets} audit packets`} />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Profile</h2>
          <dl className="kv profile">
            {profile.map(([k, v]) => <ProfileRow key={k} label={k} value={v} />)}
          </dl>
        </div>

        <div className="card">
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
            <h2 style={{ margin: 0 }}>Users</h2>
            {editable && <button onClick={() => setAddingUser(true)}><Plus size={14} /> Add user</button>}
          </div>
          <div className="tablewrap"><table>
            <thead><tr><th>Name</th><th>Role</th><th>Status</th><th /></tr></thead>
            <tbody>{a.users.map((u) => (
              <tr key={u.recordid}>
                <td>{u.name}{u.recordid === a.primaryuserid && <> <Badge state="info">Admin</Badge></>}<div className="small muted"><Email address={u.email} /></div></td>
                <td>{u.role}</td>
                <td>
                  {u.deleted ? <Badge state="disabled" />
                    : u.lastlogin ? <><Badge state="active" /><div className="small muted">last sign-in {tzDateTime(u.lastlogin)}</div></>
                    : <><Badge state="pending">Invited</Badge>{u.lastinvited && <div className="small muted">{tzDateTime(u.lastinvited)}</div>}</>}
                </td>
                <td><div className="row" style={{ flexWrap: 'nowrap', justifyContent: 'flex-end' }}>
                  {editable && !u.deleted && (
                    <button onClick={() => invite(u)} title="Email a link to set a new password">
                      <Mail size={12} /> {u.lastlogin ? 'Send password reset' : 'Resend invitation'}
                    </button>
                  )}
                  {editable && u.recordid !== a.primaryuserid && (
                    <button className={u.deleted ? '' : 'danger'} onClick={() => toggleUser(u)}>{u.deleted ? 'Enable' : 'Disable'}</button>
                  )}
                </div></td>
              </tr>
            ))}</tbody>
          </table></div>
          {!a.emailconfigured && <div className="small muted" style={{ marginTop: 8 }}>Email isn’t set up on this server - invitation links are shown to you to pass on.</div>}
        </div>
      </div>

      <div className="card">
        <h2>Recent activity</h2>
        {a.activity.length === 0 ? <div className="muted">Nothing yet.</div> : (
          <div className="tablewrap"><table>
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Record</th></tr></thead>
            <tbody>{a.activity.map((x, i) => (
              <tr key={i}><td className="small">{tzDateTime(x.added)}</td><td>{x.username || '-'}</td>
                <td>{x.action}{x.phi ? <> <Badge state="phi" /></> : null}</td><td>{x.entitytype}</td></tr>
            ))}</tbody>
          </table></div>
        )}
      </div>

      {editing && <CustomerProfileForm account={a} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); reload() }} />}
      {addingUser && <AddUser accountid={id} onClose={() => setAddingUser(false)}
        onCreated={(r) => { setAddingUser(false); setInvitation(r.invitation); reload() }} />}
      {invitation && <InvitationSent invitation={invitation} onClose={() => setInvitation(null)} />}
    </div>
  )
}

function ProfileRow({ label, value }) {
  const empty = value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)
  return <><dt>{label}</dt><dd>{empty ? <span className="muted">-</span> : value}</dd></>
}

export function AddUser({ accountid, platform, onClose, onCreated }) {
  const f = useForm({ email: '', name: '', role: platform ? 'admin' : 'staff', platformrole: platform ? 'support' : '',
    timezone: platform ? 'America/New_York' : '' },
    async (v) => onCreated(await api.post('/admin/users', { ...clean(v), accountid })))
  return (
    <Modal title={platform ? 'Add TripProof Staff' : 'Add User'} onClose={onClose}
      footer={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={f.onSubmit} disabled={f.busy}>Create and send invitation</button></>}>
      <form className="form" onSubmit={f.onSubmit}>
        <label className="field">Email *<input type="email" required value={f.values.email} onChange={f.set('email')} /></label>
        <label className="field">Name *<input required value={f.values.name} onChange={f.set('name')} /></label>
        {platform ? (
          <label className="field">Admin Role<select value={f.values.platformrole} onChange={f.set('platformrole')}>
            <option value="support">Support (read-only)</option><option value="superadmin">Super admin</option></select></label>
        ) : (
          <label className="field">Role<select value={f.values.role} onChange={f.set('role')}>
            <option value="owner">Owner</option><option value="admin">Admin</option><option value="staff">Staff</option>
            <option value="auditor">Auditor (read-only)</option></select></label>
        )}
        <label className="field">Time zone
          <TimeZoneSelect value={f.values.timezone} onChange={f.set('timezone')} inheritLabel={platform ? undefined : 'Same as the account'} />
        </label>
      </form>
      <div className="small muted">They’ll get an email invitation to set their password.</div>
      {f.error && <div className="error">{f.error}</div>}
    </Modal>
  )
}
