import { useState } from 'react'
import { api } from '../lib/api.js'
import { count } from '../lib/format.js'
import { Badge, useLoad } from '../components/ui.jsx'
import DataGrid from '../components/DataGrid.jsx'
import { Modal, useCanEdit } from './common.jsx'

// Which payment processors TripProof offers its customers.
//
// The platform decides what is on the menu. It does not hold anybody's keys and there is no
// screen here that could show one - a customer's merchant credentials are theirs, and staff
// standing in their office is not staff being them.
const COLUMNS = [
  { id: 'name', label: 'Gateway' },
  { id: 'fields', label: 'Needs', width: '26%', sortable: false },
  { id: 'configured', label: 'Set up by', width: 120, numeric: true },
  { id: 'inuse', label: 'In use by', width: 120, numeric: true },
  { id: 'active', label: 'State', width: 120 },
]

export default function Gateways() {
  const [data, error, reload] = useLoad(() => api.get('/admin/gateways'))
  const [opened, setOpened] = useState(null)
  const editable = useCanEdit()
  return (
    <div className="fill">
      <div className="pagehead">
        <div>
          <h1>Payment Gateways</h1>
        </div>
      </div>
      <DataGrid columns={COLUMNS} rows={data?.gateways} rowKey={(g) => g.code} error={error}
        onRowClick={setOpened} empty="No payment gateways."
        cells={(g) => [
          <><span className="cellname">{g.name}</span>
            <span className="rowemail plandesc">{g.code}</span></>,
          // What a company will be asked for. The count of secrets is the useful half: it is
          // what support will be told "I have pasted" when something does not work.
          `${g.fields.length} field${g.fields.length === 1 ? '' : 's'}, ${g.secrets} secret`,
          count(g.configured),
          count(g.inuse),
          <Badge state={g.active ? 'active' : 'disabled'} />,
        ]} />
      {opened && (
        <GatewayDialog gateway={opened} editable={editable}
          onClose={() => setOpened(null)}
          onSaved={() => { setOpened(null); reload() }} />
      )}
    </div>
  )
}

function GatewayDialog({ gateway, editable, onClose, onSaved }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const act = async (active) => {
    setBusy(true); setErr(null)
    try {
      await api.put(`/admin/gateways/${gateway.code}`, { active })
      onSaved()
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal title={gateway.name} onClose={onClose} width={620}
      footer={<>
        <button type="button" onClick={onClose}>Close</button>
        {editable && (
          <button type="button" className={gateway.active ? '' : 'primary'} disabled={busy}
            onClick={() => act(!gateway.active)}>
            {gateway.active ? 'Withdraw' : 'Offer To Customers'}
          </button>
        )}
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {gateway.note && <p className="dialogbrief">{gateway.note}</p>}
        {/* What the customer will be asked for. Shown here so support can walk somebody
            through it without opening the customer's own screen. */}
        <table className="residencetable recordtable">
          <thead><tr><th>Field</th><th>Kept</th><th>Required</th></tr></thead>
          <tbody>
            {gateway.fields.map((f) => (
              <tr key={f.name}>
                <td>{f.label}</td>
                <td>{f.secret ? 'Sealed, never shown again' : 'In the clear'}</td>
                <td>{f.optional ? 'Optional' : 'Yes'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">
          Set up by {count(gateway.configured)}, taking payments at {count(gateway.inuse)}.
        </p>
      </div>
    </Modal>
  )
}
