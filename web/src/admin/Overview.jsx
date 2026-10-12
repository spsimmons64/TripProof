import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import { count, tzDateTime, money0 } from '../lib/format.js'
import { Badge, Loading, Tile, useLoad } from '../components/ui.jsx'

export default function Overview() {
  const [data, error] = useLoad(() => api.get('/admin/overview'))
  const navigate = useNavigate()
  if (!data) return <Loading error={error} />
  const { counts: c, accounts, activity } = data

  return (
    <div className="stack">
      <div className="pagehead"><div>
        <h1>Overview</h1>
      </div></div>


      <div className="grid cols-4">
        <Tile className="hero fill-orange" label="At audit risk, all customers" value={money0(c.atrisk)} sub={`of ${money0(c.billed)} billed`} />
        <Tile className="fill-teal" label="Customers" value={count(c.customers)} sub={`${c.setup} in setup · ${c.inactive} inactive · ${count(c.users)} users`} />
        <Tile className="fill-light" label="Trips checked" value={count(c.trips)} sub={`${count(c.drivers)} drivers · ${count(c.vehicles)} vehicles`} />
        <Tile label="Credential types" value={count(c.credentialtypes)} />
      </div>

      <div className="grid">
        <div className="card">
          <h2>Customers by exposure</h2>
          {accounts.length === 0 ? <div className="muted">No customers yet. <Link to="/admin/customers">Add one</Link></div> : (
            <div className="tablewrap"><table>
              <thead><tr><th>Customer</th><th>Status</th><th className="num">Trips</th><th className="num">At risk</th></tr></thead>
              <tbody>{accounts.map((a) => (
                <tr key={a.recordid} className="click" onClick={() => navigate(`/admin/customers/${a.recordid}`)}>
                  <td>{a.name}</td><td><Badge state={a.status} /></td>
                  <td className="num">{count(a.trips)}</td><td className="num">{money0(a.atrisk)}</td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </div>
      </div>

      <div className="card">
        <h2>Recent activity</h2>
        <div className="tablewrap"><table>
          <thead><tr><th>When</th><th>Who</th><th>Account</th><th>Action</th><th>Record</th></tr></thead>
          <tbody>{activity.map((a, i) => (
            <tr key={i}><td className="small">{tzDateTime(a.added)}</td><td>{a.username || '-'}</td><td>{a.accountname || '-'}</td>
              <td>{a.action}{a.phi ? <> <Badge state="phi" /></> : null}</td><td>{a.entitytype || ''}</td></tr>
          ))}</tbody>
        </table></div>
      </div>
    </div>
  )
}
