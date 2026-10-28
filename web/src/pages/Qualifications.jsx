import { useState } from 'react'
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'

// What this company asks of its drivers, as against what the law asks.
//
// Deliberately a separate page from the questions on Company settings, and the separation is the
// point. A question there is a FACT about the company - are you HIPAA covered, do you carry
// Medicaid trips - and answering it changes what the law requires. Everything here is a CHOICE,
// and it changes what this company requires. Run them through one list and somebody ends up saying
// something untrue about themselves in order to switch on a requirement they merely want.
// Who the company asks a requirement of. The first position is where the law leaves it; the other
// three are the company adding to that - and "every driver" was never the only honest answer, as a
// company may want a check only on the drivers the federal programme does not already cover.
const AUDIENCES = [
  ['regulation', 'Where the law requires it'],
  ['cdl', 'CDL drivers'],
  ['noncdl', 'Non-commercial drivers'],
  ['alldrivers', 'Every driver'],
]

// Nothing in a contract requirement is required by law, so its first position cannot say so. This
// is how a broker's term came to read on screen as though a statute imposed it.
const choicesFor = (r) => (r.bylaw
  ? AUDIENCES
  : AUDIENCES.map(([v, l]) => [v, v === 'regulation' ? 'Not asked' : l]))

// The same three groups the driver's own requirements list uses, so the two read as one subject.
const GROUPS = [
  ['consent', 'Driver Consents And Acknowledgements'],
  ['regulatory', 'Federal And State Requirements'],
  ['company', 'Company Requirements'],
]

export default function Qualifications() {
  const [data, error, reload] = useLoad(() => api.get('/company/qualifications'), [])
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [adding, setAdding] = useState(false)
  const [retiring, setRetiring] = useState(null)

  if (!data) return <Loading error={error} page />

  const save = async (code, applyto) => {
    setBusy(code); setErr(null)
    try {
      await api.put(`/company/qualifications/${code}`, { applyto })
      await reload()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  const rows = (group) => data.rules.filter((r) => (r.grouping || 'regulatory') === group)

  return (
    <div className="stack">
      <div className="pagehead">
        <h1>Driver Qualifications</h1>
        <button className="primary" onClick={() => setAdding(true)}>
          <Plus size={14} /> Add requirement
        </button>
      </div>
      {err && <div className="notice bad">{err}</div>}

      <div className="card qualintro">
        <p>
          TripProof determines which requirements apply by law. You can add requirements based on
          company policy, contracts, brokers, or other business needs.
        </p>
        <p className="qualnever">Requirements mandated by law cannot be turned off.</p>
      </div>

      {GROUPS.map(([key, title]) => {
        const list = rows(key)
        if (!list.length) return null
        return (
          <div key={key} className="card factpanel">
            <h3 className="reqhead">{title}</h3>
            {list.map((r) => {
              // Adopted at all - whichever audience the company chose.
              const adopted = ['alldrivers', 'cdl', 'noncdl'].includes(r.applyto)
              return (
                <div key={r.code} className="factrow qualrow">
                  <div className="factwhat">
                    {r.name}
                    <span className="factcite">
                      {[r.authority, r.citation].filter(Boolean).join(' · ')}
                    </span>
                    {/* Why it cannot be adopted, or what changes about it if it is. Shown on the
                        row rather than behind the control, because it is the thing somebody needs
                        BEFORE they choose rather than after. */}
                    {r.extendnote && (
                      <span className={r.extendable ? 'factnote' : 'factcannot'}>
                        {r.extendnote}
                      </span>
                    )}
                  </div>
                  {/* Its own column, so the buttons line up down the page whether or not the
                      row beside them has any. */}
                  <div className="qualown">
                    {r.own && (
                      <>
                        <button type="button" disabled={busy === r.code}
                          onClick={() => setAdding(r)}>
                          <Pencil size={13} /> Edit
                        </button>
                        <button type="button" className="danger" disabled={busy === r.code}
                          onClick={() => setRetiring(r)}>
                          <Trash2 size={13} /> Remove
                        </button>
                      </>
                    )}
                  </div>
                  <div className="qualwho">
                    {r.universal ? (
                      <span className="muted small">Asked of every driver</span>
                    ) : !r.extendable ? (
                      <span className="muted small">Where the law requires it</span>
                    ) : (
                      <select value={r.applyto === 'off' ? 'regulation' : r.applyto}
                        disabled={busy === r.code}
                        onChange={(e) => save(r.code, e.target.value)}>
                        {choicesFor(r).map(([v, l]) =>
                          <option key={v} value={v}>{l}</option>)}
                      </select>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )
      })}
      {adding && (
        <AddRequirement data={data} rule={adding === true ? null : adding}
          onClose={() => setAdding(false)}
          onDone={() => { setAdding(false); reload() }} />
      )}

      {retiring && (
        <Modal title="Remove Requirement" onClose={() => setRetiring(null)}
          footer={<>
            <button type="button" className="primary" disabled={busy === retiring.code}
              onClick={async () => {
                setBusy(retiring.code)
                try { await api.del(`/company/qualifications/${retiring.code}`); await reload() }
                catch (e) { setErr(e.message) }
                finally { setBusy(null); setRetiring(null) }
              }}>Yes</button>
            <button type="button" onClick={() => setRetiring(null)}>No</button>
          </>}>
          <div className="stack">
            <div className="askorder">
              <span className="askmark">?</span>
              <p>Stop asking for {retiring.name}?</p>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// A requirement this company asks for and nobody else has heard of. The fields are the ones that
// change what the engine does with it - who it reaches, when it is due, whether it stops the
// driver, whether it goes out of date - said in words rather than in the catalog's own terms.
function AddRequirement({ data, rule, onClose, onDone }) {
  // Opened on what is already there when editing, so changing one field does not mean retyping
  // the other seven.
  const [f, setF] = useState(() => ({
    name: rule?.name || '', description: rule?.description || '',
    audience: rule?.audience || 'all', duestage: rule?.duestage || 'prehire',
    duedays: rule?.duedays ?? '', expiresafterdays: rule?.expiresafterdays ?? '',
    blocking: rule?.blocking || false,
  }))
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('body', JSON.stringify({
        ...f,
        duedays: f.duestage === 'athire' && f.duedays ? Number(f.duedays) : null,
        expiresafterdays: f.expiresafterdays ? Number(f.expiresafterdays) : null,
      }))
      if (file) body.append('template', file)
      if (rule) await api.put(`/company/qualifications/${rule.code}/rule`, body)
      else await api.post('/company/qualifications', body)
      onDone()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal title={rule ? 'Edit Requirement' : 'Add A Requirement'} onClose={onClose} width={720}
      footer={<>
        <button type="button" className="primary" disabled={busy || !f.name.trim()} onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className="field span-6">Name *
            <input value={f.name} onChange={set('name')}
              placeholder="Defensive driving course" />
          </label>
          <label className="field span-6">What It Is
            <input value={f.description} onChange={set('description')}
              placeholder="Shown at the top of the requirement when somebody opens it" />
          </label>
          <label className="field span-3">Who It Applies To
            <select value={f.audience} onChange={set('audience')}>
              {Object.entries(data.audiences || {}).map(([v, l]) =>
                <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field span-3">When It Is Due
            <select value={f.duestage} onChange={set('duestage')}>
              {Object.entries(data.stages || {}).map(([v, l]) =>
                <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          {f.duestage === 'athire' && (
            <label className="field span-3">Days After Hire
              <input type="number" min="1" max="3650" value={f.duedays}
                onChange={set('duedays')} placeholder="30" />
            </label>
          )}
          <label className="field span-3">Expires After (Days)
            <input type="number" min="1" max="3650" value={f.expiresafterdays}
              onChange={set('expiresafterdays')} placeholder="Leave empty if it never expires" />
          </label>
          <label className="field span-6">
            Blank form to hand out{rule?.templatedocumentid ? ' - replace the one on file' : ''}
            <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} />
          </label>
          <label className="field check span-6">
            <input type="checkbox" checked={f.blocking}
              onChange={(e) => setF({ ...f, blocking: e.target.checked })} />
            This requirement stops the driver until it is met
          </label>
        </div>
      </div>
    </Modal>
  )
}
