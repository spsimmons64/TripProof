import { useEffect, useState } from 'react'
import { Activity, Mail, Plus, Search, SlidersHorizontal, X } from 'lucide-react'
import { api } from '../lib/api.js'
import { Email } from '../components/Contact.jsx'
import { tzDateTime } from '../lib/format.js'
import { Badge, useLoad } from '../components/ui.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import { InvitationSent, Modal, useCanEdit, useForm } from './common.jsx'
import { AddUser } from './CustomerDetail.jsx'
import { useUser } from '../App.jsx'
import TimeZoneSelect, { zoneLabel } from '../components/TimeZoneSelect.jsx'

const ROLES = { superadmin: 'Super admin', support: 'Support (read-only)' }
const userStatus = (u) => (u.deleted ? 'disabled' : u.passwordset ? 'active' : 'invited')

const COLUMNS = [
  { id: 'name', label: 'Name' },
  { id: 'role', label: 'Admin role', width: 190 },
  { id: 'status', label: 'Status', width: 120 },
  { id: 'timezone', label: 'Time zone', width: 150, sortable: false },
  { id: 'lastlogin', label: 'Last sign-in', width: 190, firstDir: 'desc' },
  { id: 'activity', srLabel: 'Activity', width: 130, className: 'actions', sortable: false },
]

// TripProof staff - the people who use this admin portal. Customers set up their own users; those
// show (read-only) on the customer's page, not here.
export default function Users() {
  const g = useGridParams({ filters: ['role', 'status'] })
  const [data, error, reload] = useLoad(() => api.get(`/admin/users?${g.query}`), [g.query])
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(null)
  const [invitation, setInvitation] = useState(null)
  const [watching, setWatching] = useState(null)      // whose activity is open
  const editable = useCanEdit()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])

  return (
    <div className="fill">
      <div className="pagehead">
        <h1>Users</h1>
        <div className="row">
          <div className="searchbox"><Search size={14} /><input placeholder="Search Users" value={g.search} onChange={(e) => g.setSearch(e.target.value)} /></div>
          {editable && data?.staffaccountid && <button className="primary" onClick={() => setAdding(true)}><Plus size={14} /> New user</button>}
        </div>
      </div>

      <div className="filterbar">
        <span className="filtertitle"><SlidersHorizontal size={15} /> Filters</span>
        <label className="filter">Role
          <select value={g.filters.role} onChange={(e) => g.setFilter('role', e.target.value)}>
            <option value="">All</option><option value="superadmin">Super admin</option><option value="support">Support</option>
            <option value="none">No admin access</option>
          </select>
        </label>
        <label className="filter">Status
          <select value={g.filters.status} onChange={(e) => g.setFilter('status', e.target.value)}>
            <option value="">All</option><option value="active">Active</option><option value="invited">Invited</option><option value="disabled">Disabled</option>
          </select>
        </label>
        {g.filtered && <button className="linkbtn" onClick={g.clear}><X size={14} /> Clear filters</button>}
      </div>

      <DataGrid columns={COLUMNS} rows={data?.items} rowKey={(u) => u.recordid} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort} onRowClick={editable ? setEditing : undefined}
        empty={g.filtered ? 'No users match these filters.' : 'No staff users yet.'}
        pager={g.pager(data?.total, 'users')}
        cells={(u) => [
          <>
            <span className="cellname">{u.name}</span>
            <Email address={u.email} />
          </>,
          u.platformrole ? ROLES[u.platformrole] : <span className="muted">No admin access</span>,
          <Badge state={userStatus(u)} />,
          <span title={u.timezone || ''}>{zoneLabel(u.timezone) || <span className="muted">-</span>}</span>,
          u.lastlogin ? tzDateTime(u.lastlogin) : <span className="muted">never</span>,
          <button className="sm" onClick={(e) => { e.stopPropagation(); setWatching(u) }} title={`What ${u.name} has done`}>
            <Activity size={13} /> Activity</button>,
        ]} />

      {adding && <AddUser accountid={data.staffaccountid} platform onClose={() => setAdding(false)}
        onCreated={(r) => { setAdding(false); setInvitation(r.invitation); reload() }} />}
      {editing && <StaffForm staff={editing} onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); reload() }} onInvited={(inv) => { setEditing(null); setInvitation(inv); reload() }} />}
      {invitation && <InvitationSent invitation={invitation} onClose={() => setInvitation(null)} />}
      {watching && <UserActivity staff={watching} onClose={() => setWatching(null)} />}
    </div>
  )
}

const ACTIVITY_COLUMNS = [
  { id: 'when', label: 'When', width: 170 },
  { id: 'action', label: 'Action', width: 210 },
  { id: 'record', label: 'Record' },
  { id: 'account', label: 'Account', width: 180 },
  { id: 'ip', label: 'IP', width: 190 },
]
const PAGE = 50

// Everything one staff member has done, newest first - including what they did inside a customer's
// portal after a Launch (the Account column says whose). Read-only: the activity log can't be changed.
function UserActivity({ staff, onClose }) {
  const [page, setPage] = useState(1)
  const [data, error] = useLoad(() => api.get(`/admin/activity?userid=${staff.recordid}&page=${page}&pagesize=${PAGE}`), [page])
  return (
    <Modal width={1000} title={`Activity · ${staff.name}`} onClose={onClose} flush>
      <div className="activitypanel">
        <DataGrid className="bare" columns={ACTIVITY_COLUMNS} rows={data?.items} rowKey={(l) => l.recordid} error={error}
          empty="No activity recorded yet."
          pager={{ total: data?.total, page, pagesize: PAGE, noun: 'events', onPage: setPage }}
          cells={(l) => [
            <span className="nowrap">{tzDateTime(l.added)}</span>,
            <>{l.action.replace(/-/g, ' ')}{l.phi ? <> <Badge state="phi" /></> : null}</>,
            l.entitytype ? <span className="small">{l.entitytype}{l.entityid ? <span className="muted"> · {l.entityid.slice(0, 8)}</span> : null}</span> : '-',
            l.accountname || '-',
            <span className="small muted ellipsis" title={l.ip || ''}>{l.ip || '-'}</span>,
          ]} />
      </div>
    </Modal>
  )
}

function StaffForm({ staff, onClose, onSaved, onInvited }) {
  const me = useUser()
  const self = staff.recordid === me.recordid
  const f = useForm({ name: staff.name, platformrole: staff.platformrole || '', disabled: !!staff.deleted,
    timezone: staff.timezone || 'America/New_York' }, async (v) => {
    await api.patch(`/admin/users/${staff.recordid}`, { name: v.name.trim(), platformrole: v.platformrole, disabled: v.disabled,
      timezone: v.timezone })
    onSaved()
  })
  const [sending, setSending] = useState(false)
  const invite = async () => {
    setSending(true)
    try { onInvited(await api.post(`/admin/users/${staff.recordid}/invite`)) } catch (e) { alert(e.message); setSending(false) }
  }
  const v = f.values
  return (
    <Modal width={560} title={staff.name} onClose={onClose}
      footer={<>
        {!staff.deleted && <button type="button" onClick={invite} disabled={sending} style={{ marginRight: 'auto' }}>
          <Mail size={14} /> {staff.passwordset ? 'Send password reset' : 'Resend invitation'}</button>}
        <button onClick={onClose}>Cancel</button>
        <button className="primary" onClick={f.onSubmit} disabled={f.busy}>Save</button>
      </>}>
      <form className="profileform" onSubmit={f.onSubmit}>
        <label className="field span-6">Name *<input required value={v.name} onChange={f.set('name')} /></label>
        <label className="field span-6">Email<input value={staff.email} disabled /></label>
        <label className="field span-6">Time zone<TimeZoneSelect value={v.timezone} onChange={f.set('timezone')} /></label>
        <label className="field span-3">Admin Role
          <select value={v.platformrole} onChange={f.set('platformrole')} disabled={self}>
            <option value="superadmin">Super admin</option><option value="support">Support (read-only)</option><option value="">No admin access</option>
          </select>
        </label>
        <label className="field span-3">Status
          <select value={v.disabled ? 'disabled' : 'active'} onChange={(e) => f.set('disabled')(e.target.value === 'disabled')} disabled={self}>
            <option value="active">{staff.passwordset || staff.deleted ? 'Active' : 'Active (invited)'}</option><option value="disabled">Disabled</option>
          </select>
        </label>
      </form>
      {f.error && <div className="error">{f.error}</div>}
    </Modal>
  )
}
