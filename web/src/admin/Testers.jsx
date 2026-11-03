import { api } from '../lib/api.js'
import { date } from '../lib/format.js'
import { useLoad } from '../components/ui.jsx'
import DataGrid from '../components/DataGrid.jsx'
import { Email } from '../components/Contact.jsx'
import { formatPhone } from '../lib/masks.js'

// Transport companies that asked, from the public site, to test TripProof. Newest first.
const COLUMNS = [
  { id: 'added', label: 'Signed Up', width: 120, sortable: false },
  { id: 'company', label: 'Company', sortable: false },
  { id: 'name', label: 'Name', width: '16%', sortable: false },
  { id: 'email', label: 'Email', width: '20%', sortable: false },
  { id: 'phone', label: 'Phone', width: 140, sortable: false },
  { id: 'state', label: 'State', width: 80, sortable: false },
  { id: 'fleet', label: 'Vehicles', width: 100, sortable: false },
  { id: 'brokers', label: 'Brokers', width: '16%', sortable: false },
]

export default function Testers() {
  const [data, error] = useLoad(() => api.get('/admin/testers'))
  return (
    <div className="fill">
      <div className="pagehead"><h1>Testers</h1></div>
      <DataGrid columns={COLUMNS} rows={data?.items} rowKey={(t) => t.recordid} error={error} empty="Nobody has signed up yet."
        cells={(t) => [date(t.added), <span className="cellname" title={t.note || undefined}>{t.company}</span>, t.name,
          <Email address={t.email} />, t.phone ? formatPhone(t.phone) : '', t.state || '', t.fleet || '', t.brokers || '']} />
    </div>
  )
}
