import { useState } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { tzDateTime } from '../lib/format.js'
import { Loading, useLoad } from './ui.jsx'
import { Modal } from '../admin/common.jsx'
import { EmailInput } from './MaskedInput.jsx'

// A Location's facility portal: whether the facility may request trips here, the contract its
// trips are billed to (none: private pay), and the facility's own logins.
export default function FacilityPortal({ place, onClose }) {
  const [data, error, reload] = useLoad(() => api.get(`/places/${place.recordid}/portal`), [place.recordid])
  const [v, setV] = useState(null)
  const [adding, setAdding] = useState(false)
  const [who, setWho] = useState({ name: '', email: '' })
  const [closing, setClosing] = useState(null)
  const [link, setLink] = useState(null)        // no mail set up: the link to pass on by hand
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const held = v || (data && { portal: data.portal, contractpayerid: data.contractpayerid || '' })
  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { const got = await fn(); setLink(got?.link || null); reload(); return true }
    catch (e) { setErr(e.message); return false } finally { setBusy(false) }
  }

  if (closing) {
    return (
      <Modal title="Close Login" onClose={() => setClosing(null)} width={520}
        footer={<>
          <button type="button" className="primary" disabled={busy}
            onClick={async () => { if (await act(() => api.post(`/facility-logins/${closing.recordid}/close`))) setClosing(null) }}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Yes'}
          </button>
          <button type="button" onClick={() => setClosing(null)}>No</button>
        </>}>
        <div className="stack">
          <div className="askorder"><span className="askmark">?</span><p>Close {closing.name}&rsquo;s login?</p></div>
        </div>
      </Modal>
    )
  }
  if (adding) {
    return (
      <Modal title="Add Login" onClose={() => setAdding(false)} width={560}
        footer={<>
          <button type="button" onClick={() => setAdding(false)}>Cancel</button>
          <button type="button" className="primary" disabled={busy || !who.name.trim() || !who.email.trim()}
            onClick={async () => { if (await act(() => api.post(`/places/${place.recordid}/logins`, who))) { setAdding(false); setWho({ name: '', email: '' }) } }}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Send Invitation'}
          </button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-6">Name *
              <input className="upper" value={who.name} onChange={(e) => setWho({ ...who, name: e.target.value.toUpperCase() })} />
            </label>
            <label className="field span-6">Email *
              <EmailInput value={who.email} onChange={(e) => setWho({ ...who, email: e.target.value })} />
            </label>
          </div>
        </div>
      </Modal>
    )
  }
  return (
    <Modal title="Facility Portal" onClose={onClose} width={940}
      footer={<>
        <div className="footactions">
          <button type="button" onClick={() => { setErr(null); setAdding(true) }}><Plus size={14} /> Add Login</button>
        </div>
        <button type="button" onClick={onClose}>Close</button>
        <button type="button" className="primary" disabled={busy || !held}
          onClick={() => act(() => api.put(`/places/${place.recordid}/portal`, { portal: held.portal, contractpayerid: held.contractpayerid || null }))}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      {!data ? <Loading error={error} box /> : (
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {link && <div className="notice good"><div>No email is set up. Pass this link on: <b style={{ wordBreak: 'break-all' }}>{link}</b></div></div>}
          <div className="kv"><dt>Location</dt><dd>{place.name}</dd></div>
          <div className="profileform">
            <label className="field check span-3">
              <input type="checkbox" checked={held.portal} onChange={(e) => setV({ ...held, portal: e.target.checked })} />
              Trip Requests From This Facility
            </label>
            <label className="field span-3">Contract
              <select value={held.contractpayerid} onChange={(e) => setV({ ...held, contractpayerid: e.target.value })}>
                <option value="">None - Private Pay</option>
                {data.payers.map((p) => <option key={p.recordid} value={p.recordid}>{p.name}</option>)}
              </select>
            </label>
          </div>
          <h3 className="formsection">Logins</h3>
          {!data.logins.length ? <div className="hireempty">No logins yet.</div> : (
            <table className="residencetable recordtable">
              <thead><tr><th>Name</th><th>Email</th><th>Status</th><th>Last Sign In</th><th /></tr></thead>
              <tbody>{data.logins.map((x) => (
                <tr key={x.recordid}>
                  <td>{x.name}</td>
                  <td>{x.email}</td>
                  <td className={x.status === 'Active' ? 'st-active' : x.status === 'Closed' ? 'st-expired' : undefined}>{x.status}</td>
                  <td>{x.lastloginon ? tzDateTime(x.lastloginon) : 'N/A'}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {x.status !== 'Closed' && <>
                      <button type="button" disabled={busy} onClick={() => act(() => api.post(`/facility-logins/${x.recordid}/invite`))}>
                        {x.status === 'Active' ? 'Reset Password' : 'Resend Invitation'}</button>{' '}
                      <button type="button" disabled={busy} onClick={() => setClosing(x)}>Close Login</button>
                    </>}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}
    </Modal>
  )
}
