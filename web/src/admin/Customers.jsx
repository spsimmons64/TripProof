import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Rocket, Search, SlidersHorizontal, X } from 'lucide-react'
import { launchAccount } from '../lib/launch.js'
import { api } from '../lib/api.js'
import { count, money0 } from '../lib/format.js'
import { Badge, useLoad } from '../components/ui.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import { InvitationSent, useCanEdit } from './common.jsx'
import CustomerProfileForm from './CustomerProfile.jsx'

const COLUMNS = [
  { id: 'accountnumber', label: 'Account #', width: 110, firstDir: 'asc' },
  { id: 'name', label: 'Customer', firstDir: 'asc' },
  { id: 'status', label: 'Status', width: 110, firstDir: 'asc' },
  { id: 'plan', label: 'Plan', width: 150, firstDir: 'asc' },
  { id: 'users', label: 'Users', width: 90, numeric: true },
  { id: 'drivers', label: 'Drivers', width: 95, numeric: true },
  { id: 'vehicles', label: 'Vehicles', width: 100, numeric: true },
  { id: 'trips', label: 'Trips', width: 85, numeric: true },
  { id: 'atrisk', label: 'At risk', width: 100, numeric: true },
  { id: 'launch', srLabel: 'Launch', width: 120, className: 'actions', sortable: false },
]

// Search, filters, sort and page live in the URL (useGridParams) so a view can be linked or reloaded.
export default function Customers() {
  const g = useGridParams({ filters: ['status', 'risk'] })
  const [data, error, reload] = useLoad(() => api.get(`/admin/accounts?${g.query}`), [g.query])
  const [adding, setAdding] = useState(false)
  const [invitation, setInvitation] = useState(null)
  const [opened, setOpened] = useState(null)      // the customer whose profile dialog is open
  const navigate = useNavigate()
  const editable = useCanEdit()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])

  // Clicking a customer opens its profile in a dialog over the grid (full record fetched on open).
  const openProfile = async (id) => {
    try { setOpened(await api.get(`/admin/accounts/${id}`)) } catch (e) { alert(e.message) }
  }
  const { status, risk } = g.filters

  return (
    <div className="fill">
      <div className="pagehead">
        <h1>Customers</h1>
        <div className="row">
          <div className="searchbox"><Search size={14} /><input placeholder="Search Customers" value={g.search} onChange={(e) => g.setSearch(e.target.value)} /></div>
          {editable && <button className="primary" onClick={() => setAdding(true)}><Plus size={14} /> New customer</button>}
        </div>
      </div>

      <div className="filterbar">
        <span className="filtertitle"><SlidersHorizontal size={15} /> Filters</span>
        <label className="filter">Status
          <select value={status} onChange={(e) => g.setFilter('status', e.target.value)}>
            <option value="">All</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="setup">Setup</option>
          </select>
        </label>
        <label className="filter">Exposure
          <select value={risk} onChange={(e) => g.setFilter('risk', e.target.value)}>
            <option value="">All</option><option value="yes">Trips at risk</option><option value="no">Nothing at risk</option>
          </select>
        </label>
        {g.filtered && (
          <button className="linkbtn" onClick={g.clear}>
            <X size={14} /> Clear filters
          </button>
        )}
      </div>

      <DataGrid columns={COLUMNS} rows={data?.items} rowKey={(a) => a.recordid} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort} onRowClick={(a) => openProfile(a.recordid)}
        empty={g.filtered ? 'No customers match these filters.' : 'No customers yet.'}
        pager={g.pager(data?.total, 'customers')}
        cells={(a) => [
          a.accountnumber,
          <>
            <button className="linkbtn cell" onClick={(e) => { e.stopPropagation(); openProfile(a.recordid) }}>{a.name}</button>
            {a.adminemail && <a className="rowemail" href={`mailto:${a.adminemail}`} onClick={(e) => e.stopPropagation()}>{a.adminemail}</a>}
          </>,
          <Badge state={a.status} />,
          a.planname ? <>{a.planname}{['past_due', 'unpaid'].includes(a.substatus) || a.holdreason === 'billing'
            ? <span className="rowemail billwarn">{a.holdreason === 'billing' ? 'billing hold' : 'past due'}</span>
            : <span className="rowemail">{a.fleetsize} vehicles</span>}</> : <span className="muted">-</span>,
          a.users, count(a.drivers), count(a.vehicles), count(a.trips), money0(a.atrisk),
          <button className="launch sm" onClick={(e) => { e.stopPropagation(); launchAccount(a.recordid) }}
            title={`Open ${a.name}’s portal in a new tab`}><Rocket size={13} /> Launch</button>,
        ]} />

      {adding && <CustomerProfileForm onClose={() => setAdding(false)}
        onSaved={(r) => { setAdding(false); reload(); setInvitation({ ...r.invitation, accountid: r.recordid }) }} />}
      {opened && <CustomerProfileForm account={opened} detailsLink readOnly={!editable}
        onClose={() => setOpened(null)} onSaved={() => { setOpened(null); reload() }} />}
      {invitation && <InvitationSent invitation={invitation}
        onClose={() => { const id = invitation.accountid; setInvitation(null); navigate(`/admin/customers/${id}`) }} />}
    </div>
  )
}
