import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search } from 'lucide-react'
import { api } from '../lib/api.js'
import { Badge, useLoad } from '../components/ui.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import { PhoneInput } from '../components/MaskedInput.jsx'
import { Email, Phone } from '../components/Contact.jsx'
import { properName } from '../lib/names.js'

export function CredentialSummary({ r }) {
  if (r.expired) return <Badge state="expired">{r.expired} expired</Badge>
  if (r.expiring) return <Badge state="expiring">{r.expiring} expiring</Badge>
  if (!r.credentials) return <Badge state="stub">None on file</Badge>
  return <Badge state="current">{r.credentials} current</Badge>
}

// Where a driver stands with the company, in the order they pass through it.
const FILTERS = [
  ['', 'All'],
  ['application', 'Application'],
  ['appcor', 'Corrections'],
  ['new', 'New'],
  ['pending', 'Pending'],
  ['hired', 'Active Driver'],
  ['inactive', 'Inactive'],
]

const COLUMNS = [
  { id: 'drivernumber', label: 'Driver ID', width: 110 },
  { id: 'name', label: 'Name', width: 260 },
  { id: 'status', label: 'Status', width: 140 },
  { id: 'licenseclass', label: 'Driver type', width: 150 },
  { id: 'phone', label: 'Telephone', width: 160 },
  // No width: the email takes whatever is left, so nothing stretches into a gap.
  { id: 'email', label: 'Email' },
]

export const driverState = (d) => ({ application: 'applicant', appcor: 'corrections', new: 'newdriver',
  pending: 'awaiting' }[d.status] || d.status || 'hired')

// Commercial or not follows the licence they hold: nobody drives a vehicle that needs a CDL without
// one. A driver whose licence class is not on file yet is neither, and says so.
const driverType = (d) => (!d.licenseclass ? '-'
  : ['A', 'B', 'C'].includes(String(d.licenseclass).toUpperCase()) ? 'Commercial' : 'Non-commercial')

// A driver whose record is their application: the office decides on it, and only the driver edits it.
export const APPLYING = ['application', 'appcor', 'new']

export default function Drivers() {
  const g = useGridParams({ filters: ['status'] })
  const [data, error, reload] = useLoad(() => api.get(`/drivers?${g.query}`), [g.query])
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])

  return (
    <div className="fill">
      <div className="pagehead">
        <h1>Drivers</h1>
        <div className="row">
          <div className="searchbox"><Search size={14} /><input placeholder="Search Drivers" value={g.search}
            onChange={(e) => g.setSearch(e.target.value)} /></div>
          <button className="primary" onClick={() => setAdding(true)}><Plus size={14} /> Add driver</button>
        </div>
      </div>

      <div className="filterrow">
        {FILTERS.map(([value, label]) => (
          <button key={value || 'all'} type="button" className={`chip${g.filters.status === value ? ' on' : ''}`}
            onClick={() => g.setFilter('status', value)}>{label}</button>
        ))}
      </div>

      {adding && <DriverForm onDone={(id) => { setAdding(false); if (id) navigate(`/drivers/${id}`); else reload() }} />}

      <DataGrid columns={COLUMNS} rows={data?.items} rowKey={(d) => d.recordid} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort} onRowClick={(d) => navigate(`/drivers/${d.recordid}`)}
        /* An application still being filled in is the driver's, not the office's: there is nothing
           to review and nothing to decide until they submit it. */
        rowClickable={(d) => d.status !== 'application'}
        empty={g.filtered ? 'No drivers match this filter.' : 'No drivers yet.'}
        pager={data && g.pager(data.total, 'driver')}
        cells={(d) => [
          d.drivernumber || '-',
          <span className={d.disqualified ? 'stoppedname' : undefined}>
            {properName(d.firstname, d.lastname)} {d.stub ? <Badge state="stub" /> : null}
          </span>,
          d.disqualified
            ? <Badge state="disqualified">Disqualified</Badge>
            : <Badge state={driverState(d)} />,
          driverType(d),
          <Phone number={d.phone} />,
          <Email address={d.email} />,
        ]} />
    </div>
  )
}

export function DriverForm({ initial = {}, id, onDone }) {
  const [f, setF] = useState({ firstname: '', lastname: '', externalid: '', dob: '', licensenumber: '', licensestate: 'FL', licensesince: '', email: '', phone: '', hiredon: '', terminatedon: '', ...initial })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    const keys = ['firstname', 'lastname', 'externalid', 'dob', 'licensenumber', 'licensestate', 'licensesince', 'email', 'phone', 'hiredon', 'terminatedon']
    const body = Object.fromEntries(keys.map((k) => [k, f[k] === '' || f[k] === undefined ? null : f[k]]))
    try {
      if (id) { await api.put(`/drivers/${id}`, body); onDone() }
      else onDone((await api.post('/drivers', body)).recordid)
    } catch (err) { setError(err.message) }
  }
  return (
    <form className="card stack" onSubmit={submit}>
      <div className="form">
        <label className="field">First name<input required value={f.firstname} onChange={set('firstname')} /></label>
        <label className="field">Last name<input required value={f.lastname} onChange={set('lastname')} /></label>
        <label className="field">Dispatch ID<input value={f.externalid || ''} onChange={set('externalid')} /></label>
        <label className="field">License number<input value={f.licensenumber || ''} onChange={set('licensenumber')} /></label>
        <label className="field">License state<input maxLength={2} value={f.licensestate || ''} onChange={set('licensestate')} /></label>
        <label className="field">First licensed<input type="date" value={f.licensesince || ''} onChange={set('licensesince')} /></label>
        <label className="field">Date of birth<input type="date" value={f.dob || ''} onChange={set('dob')} /></label>
        <label className="field">Email<input type="email" value={f.email || ''} onChange={set('email')} /></label>
        <label className="field">Phone<PhoneInput value={f.phone || ''} onChange={set('phone')} /></label>
        <label className="field">Hired<input type="date" value={f.hiredon || ''} onChange={set('hiredon')} /></label>
        <label className="field">Terminated<input type="date" value={f.terminatedon || ''} onChange={set('terminatedon')} /></label>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="row"><button className="primary">Save</button><button type="button" onClick={() => onDone()}>Cancel</button></div>
    </form>
  )
}
