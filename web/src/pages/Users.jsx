import { useState } from 'react'
import { Plus, Send } from 'lucide-react'
import { api } from '../lib/api.js'
import { Email } from '../components/Contact.jsx'
import { date } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import SupervisorRecord from '../components/SupervisorRecord.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'

// Who at this company can sign in.
//
// A login is made here and is unusable until its invitation has been opened - nobody is ever handed
// a password, and nobody here can set one for somebody else. Closing a login keeps the person: the
// activity log has their name against everything they did, and that has to keep making sense.

const ROLES = [
  ['owner', 'Owner'],
  ['admin', 'Administrator'],
  ['staff', 'Staff'],
  ['auditor', 'Auditor'],
]
const ROLE_NAME = Object.fromEntries(ROLES.map(([k, l]) => [k, l]))

export default function Users() {
  const [data, error, reload] = useLoad(() => api.get('/account/users'), [])
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [link, setLink] = useState(null)
  const g = useGridParams({ defaultSort: 'name', defaultDir: 'asc' })

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

  if (!data) return <Loading error={error} page />
  const items = data.items || []
  const flip = g.dir === 'desc' ? -1 : 1
  const shown = [...items].sort((a, b) => {
    const x = a[g.sort] ?? '', y = b[g.sort] ?? ''
    if (x === y) return (a.name || '').localeCompare(b.name || '')
    return (x > y ? 1 : -1) * flip
  })
  const page = shown.slice((g.page - 1) * g.pagesize, g.page * g.pagesize)

  return (
    <div className="fill">
      <div className="pagehead">
        <div><h1>Users</h1></div>
        <button className="primary" onClick={() => setEditing({})}>
          <Plus size={14} /> Add A User
        </button>
      </div>

      {err && <div className="notice bad">{err}</div>}
      {link && (
        <div className="notice">
          <div>No mail is configured, so pass this on yourself:
            <input value={link} readOnly onFocus={(e) => e.target.select()} />
          </div>
        </div>
      )}

      <DataGrid
        columns={[
          { id: 'name', label: 'Name' },
          { id: 'email', label: 'Email', width: '22%' },
          // Read, not operated. A dropdown in every row offers to change somebody's access
          // with one stray click and says nothing about who they are.
          { id: 'role', label: 'Role', width: 150 },
          { id: 'lastlogin', label: 'Last signed in', width: 150 },
          { id: 'deleted', label: 'State', width: 110 },
          { id: 'act', label: '', srLabel: 'Actions', width: 300, sortable: false },
        ]}
        rows={page}
        rowKey={(u) => u.recordid}
        sort={g.sort} dir={g.dir} onSort={g.onSort}
        pager={g.pager(shown.length, 'user')}
        onRowClick={(u) => setEditing(u)}
        empty="Nobody yet."
        cells={(u) => [
          <b>{u.name}{u.recordid === data.me ? ' (you)' : ''}</b>,
          <Email address={u.email} />,
          ROLE_NAME[u.role] || u.role,
          u.lastlogin ? date(u.lastlogin) : u.passwordset ? 'Never' : 'Invited, not used',
          <span className={u.deleted ? 'st-inactive' : 'st-active'}>
            {u.deleted ? 'Closed' : 'Active'}
          </span>,
            <span className="rowacts">
              <button type="button" className="linkbtn edit"
                onClick={(e) => { e.stopPropagation(); setEditing(u) }}>Edit</button>
              {/* Nobody closes their own login: an account that locks out its last owner is
                  an account that has to ring us. The API refuses it too. */}
              {u.recordid !== data.me && (
                <button type="button" className="linkbtn" disabled={busy === u.recordid}
                  onClick={(e) => { e.stopPropagation(); change(u, { disabled: !u.deleted }) }}>
                  {u.deleted ? 'Reopen' : 'Deactivate'}
                </button>
              )}
            </span>,
        ]} />

      {editing && (
        <UserDialog held={editing} isme={editing.recordid === data.me}
          companyroles={data.companyroles || {}}
          onReset={() => invite(editing)}
          onClose={() => setEditing(null)}
          onDone={(r) => {
            setEditing(null)
            if (r && r.invitation && !r.invitation.emailed) setLink(r.invitation.link)
            reload()
          }} />
      )}
    </div>
  )
}

// "supervisor:abc123,safety:def456" - the role and the id of the appointment itself, which
// is what ending one needs.
const heldRoles = (s) => Object.fromEntries(
  String(s || '').split(',').filter(Boolean).map((p) => p.split(':')))

// What this person has put their own name to. Read on the person, where somebody looking
// for "has she signed it" actually looks - the supervisor training record was only reachable
// through a compliance requirement dialog, which is a strange place to go for that.
function SignedDocuments({ who }) {
  const [data, error] = useLoad(
    () => api.get(`/account/users/${who.recordid}/documents`), [who.recordid])
  const [reading, setReading] = useState(null)
  if (!data) return <Loading error={error} />
  if (!data.items.length) return <p className="muted small">Nothing signed yet.</p>
  return (
    <>
      <table className="residencetable recordtable coverstable">
        <tbody>
          {data.items.map((d) => (
            <tr key={d.recordid}>
              <td className="growcol">{data.labels[d.doctype] || d.doctype}</td>
              <td>{date(d.signedon)}</td>
              <td className="actions">
                {/* Only the training record renders back; it is the one a user signs on
                    their own account. Anything else is listed and said to be on file. */}
                {d.doctype === 'SUPERVISOR_TRAINING_RECORD' && (
                  <button type="button" className="linkbtn edit"
                    onClick={() => setReading(true)}>View</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {reading && <SupervisorRecord who={who} onClose={() => setReading(null)} />}
    </>
  )
}

// One login, added or corrected. The same dialog either way: what a user IS - their name and
// what they may do - is the same question whether it is being asked for the first time or
// put right afterwards.
function UserDialog({ held, isme, companyroles, onReset, onClose, onDone }) {
  const made = Boolean(held.recordid)
  const was = heldRoles(held.heldroles)
  const [v, setV] = useState({
    name: held.name || '', email: held.email || '', role: held.role || 'staff',
  })
  // The appointments this person holds. Ticked here and written through the same endpoints
  // the Company Requirements screen appoints from - one store, two doors, so a supervisor
  // appointed here still gets the email and still owes the signed training record.
  const [roles, setRoles] = useState(Object.keys(was))
  const toggle = (r) => () => setRoles(roles.includes(r)
    ? roles.filter((x) => x !== r) : [...roles, r])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setV({ ...v, [k]: e.target.value })
  const missing = !v.name.trim() || (!made && !v.email.trim())

  // Only what changed, and by the appointment's own id where one is being ended.
  const saveRoles = async (userid) => {
    for (const r of Object.keys(companyroles)) {
      if (roles.includes(r) && !was[r]) {
        await api.post(`/company/roles/${r}`, { userid })
      } else if (!roles.includes(r) && was[r]) {
        await api.del(`/company/roles/${r}/${was[r]}`)
      }
    }
  }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      if (made) {
        // Role is left out when it is their own login - the API refuses it, and sending it
        // only to be refused turns a rename into an error.
        await api.patch(`/account/users/${held.recordid}`,
          isme ? { name: v.name.trim() } : { name: v.name.trim(), role: v.role })
        await saveRoles(held.recordid)
        onDone(null)
      } else {
        const made2 = await api.post('/account/users', { ...v, name: v.name.trim() })
        await saveRoles(made2.recordid)
        onDone(made2)
      }
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <Modal title={made ? 'User' : 'Add A User'} onClose={onClose} width={620} footer={<>
      {/* Left, away from the two that finish the dialog: emailing somebody a link is work
          on this record, not a way of leaving it. Offered on a saved login only - a user
          being added gets their invitation from Save. */}
      {made && !held.deleted && (
        <div className="footactions">
          <button type="button" disabled={busy}
            onClick={async () => { setBusy(true); try { await onReset() } finally { setBusy(false) } }}>
            <Send size={13} /> {held.passwordset ? 'Send Password Reset' : 'Send Invitation'}
          </button>
        </div>
      )}
      <button type="button" onClick={onClose}>Cancel</button>
      <button type="button" className="primary" disabled={busy || missing} onClick={save}>
        {made ? 'Save' : 'Send The Invitation'}
      </button>
    </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className="field span-3">Name *
            <input value={v.name} onChange={set('name')} autoFocus />
          </label>
          <label className="field span-3">Role
            <select value={v.role} onChange={set('role')} disabled={isme}>
              {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          {/* Its own row: an address is long, and it is the one field here that has to be
              read back character by character before the invitation goes out.
              Not editable on an existing login - changing it would hand the account to a
              different mailbox, which is a reset, not an edit. */}
          <label className="field span-6">Email {made ? '' : '*'}
            <input type="email" value={v.email} onChange={set('email')} disabled={made} />
          </label>
        </div>

        {Object.keys(companyroles).length > 0 && (
          <section>
            {/* What this person is appointed to, as against what they may do in the
                software. A role here is a named responsibility a regulation asks for; the
                Role above is a login's permissions. */}
            <h3 className="formsection">Appointments</h3>
            <div className="appointlist">
              {Object.entries(companyroles).map(([k, label]) => (
                <label className="field check" key={k}>
                  <input type="checkbox" checked={roles.includes(k)} onChange={toggle(k)} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </section>
        )}

        {made && (
          <section>
            <h3 className="formsection">Signed Documents</h3>
            <SignedDocuments who={held} />
          </section>
        )}
      </div>
    </Modal>
  )
}
