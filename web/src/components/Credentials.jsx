import { useState } from 'react'
import DocumentViewer from './DocumentViewer.jsx'
import { FileText, Plus, RotateCcw } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, datetime, through } from '../lib/format.js'
import { Badge, useLoad } from './ui.jsx'

// Credential history for one holder: every card ever entered, newest first within each type.
// Renewing adds a new credential (the old one keeps covering the trips it covered); revoking ends
// coverage at a moment; deleting is only for entries made in error.
export default function Credentials({ subject, subjectid, credentials, onChange, addLabel,
                                      addSlot }) {
  const [adding, setAdding] = useState(null)       // null | {} | {renew: credential}
  const [revoking, setRevoking] = useState(null)
  const [viewing, setViewing] = useState(null)      // the credential whose file is being read
  const [types] = useLoad(() => api.get('/credentialtypes'))
  const mine = (types || []).filter((t) => t.subject === subject)

  const remove = async (c) => {
    if (!confirm(`Delete this ${c.typename}? Use this only for an entry made in error - a renewal should be added as a new credential.`)) return
    await api.del(`/credentials/${c.recordid}`)
    onChange()
  }

  // The Add button belongs where the page's action belongs - in the heading row - and a caller
  // that wants it there hands over a slot to put it in. Nothing is drawn here in that case: a
  // panel heading repeating the name of the page it is the whole of, with its own button beside
  // the page's own, is two of everything.
  const add = (
    <button className="primary" onClick={() => setAdding({})}>
      <Plus size={14} /> {addLabel || 'Add credential'}
    </button>
  )
  return (
    <div className="card stack">
      {addSlot ? addSlot(add) : (
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>Credentials</h2>
          {add}
        </div>
      )}
      {adding && <CredentialForm types={mine} subjectid={subjectid} renew={adding.renew}
        onDone={(changed) => { setAdding(null); if (changed) onChange() }} />}
      {revoking && <RevokeForm credential={revoking} onDone={(changed) => { setRevoking(null); if (changed) onChange() }} />}
      {credentials.length === 0 ? <div className="muted">Nothing on file. Every trip this {subject} ran is at risk until credentials are entered.</div> : (
        <div className="tablewrap"><table>
          <thead><tr><th>Credential</th><th>Number</th><th>Issued</th><th>Expires</th><th>Covers</th><th>Status</th><th>File</th><th /></tr></thead>
          <tbody>{credentials.map((c) => (
            <tr key={c.recordid}>
              <td>{c.typename}</td>
              <td>{c.number || '-'}{c.amount ? <div className="small muted">limit ${Number(c.amount).toLocaleString()}</div> : null}</td>
              <td>{date(c.issuedon)}</td>
              <td>{c.expireson ? date(c.expireson) : '-'}</td>
              <td className="small">{through(c.windowend)}{c.endcode === 'maxage' ? ` (${c.maxagedays}-day limit)` : ''}
                {c.revokedon && <div className="error">Revoked {datetime(c.revokedon)}{c.revokereason ? `: ${c.revokereason}` : ''}</div>}</td>
              <td><Badge state={c.state} /></td>
              <td>{c.documentid ? <a href="#" onClick={(e) => { e.preventDefault(); setViewing(c) }}><FileText size={14} /></a> : '-'}</td>
              <td><div className="row" style={{ flexWrap: 'nowrap' }}>
                <button title="Renew" onClick={() => setAdding({ renew: c })}><RotateCcw size={12} /> Renew</button>
                {!c.revokedon && <button className="danger" onClick={() => setRevoking(c)}>Revoke</button>}
                <button className="danger" onClick={() => remove(c)}>Delete</button>
              </div></td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
      {viewing && (
        <DocumentViewer id={viewing.documentid} name={viewing.filename || viewing.typename}
          onClose={() => setViewing(null)} />
      )}
    </div>
  )
}

// Exported so a requirement can open it directly: the row that asks for a document is the
// right place to file one, and a second form for the same job would drift from this one.
export function CredentialForm({ types, subjectid, renew, onDone, inset = false }) {
  const [f, setF] = useState({ credentialtypeid: renew?.credentialtypeid || types[0]?.recordid || '', issuedon: '', expireson: '', number: '', issuer: renew?.issuer || '', amount: '', notes: '' })
  const [file, setFile] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const type = types.find((t) => t.recordid === f.credentialtypeid)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    const fd = new FormData()
    fd.append('subjectid', subjectid)
    Object.entries(f).forEach(([k, v]) => v && fd.append(k, v))
    if (renew) fd.append('supersedes', renew.recordid)
    if (file) fd.append('file', file)
    try { await api.post('/credentials', fd); onDone(true) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    // `inset`: already inside a dialog that has named the thing being filed, so the rule and
    // the heading above the fields would be a second title under the first.
    <form className="stack" onSubmit={submit}
      style={inset ? undefined : { borderTop: '1px solid var(--border)', paddingTop: 12 }}>
      {!inset && <h3>{renew ? `Renew ${renew.typename}` : 'New credential'}</h3>}
      <div className="form">
        <label className="field">Type
          <select value={f.credentialtypeid} onChange={set('credentialtypeid')} disabled={!!renew}>
            {[...new Set(types.map((t) => t.category || 'other'))].map((cat) => (
              <optgroup key={cat} label={cat}>
                {types.filter((t) => (t.category || 'other') === cat).map((t) => <option key={t.recordid} value={t.recordid}>{t.name}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="field">Issued / Completed On *<input type="date" required value={f.issuedon} onChange={set('issuedon')} /></label>
        <label className="field">Expires On<input type="date" value={f.expireson} onChange={set('expireson')} /></label>
        <label className="field">Number<input value={f.number} onChange={set('number')} /></label>
        <label className="field">Issuer<input value={f.issuer} onChange={set('issuer')} /></label>
        {type?.hasamount ? <label className="field">Coverage Limit ($)<input type="number" min="0" step="1000" value={f.amount} onChange={set('amount')} /></label> : null}
        <label className="field">Scan Or Photo<input type="file" accept="image/*,application/pdf" onChange={(e) => setFile(e.target.files[0])} /></label>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="row"><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save and re-check trips'}</button><button type="button" onClick={() => onDone(false)}>Cancel</button></div>
    </form>
  )
}

function RevokeForm({ credential, onDone }) {
  const [at, setAt] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    try { await api.post(`/credentials/${credential.recordid}/revoke`, { revokedon: at, reason }); onDone(true) }
    catch (err) { setError(err.message) }
  }
  return (
    <form className="stack" onSubmit={submit} style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
      <h3>Revoke {credential.typename}</h3>
      <div className="small muted">Trips before this moment stay covered; trips at or after it will fail.</div>
      <div className="form">
        <label className="field">Revoked At *<input type="datetime-local" required value={at} onChange={(e) => setAt(e.target.value)} /></label>
        <label className="field">Reason *<input required value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="row"><button className="primary">Revoke</button><button type="button" onClick={() => onDone(false)}>Cancel</button></div>
    </form>
  )
}
