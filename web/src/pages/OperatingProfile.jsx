import { useState } from 'react'
import { MoreHorizontal } from 'lucide-react'
import { api } from '../lib/api.js'
import { date } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import { STATE_NAMES } from '../lib/states.js'
import { useUser } from '../App.jsx'
import DataGrid from '../components/DataGrid.jsx'

// What the company does, as records: where it operates, how it engages drivers, and what has been
// determined about each vehicle. Who it carries for, and so its programs, is kept on Payers. The
// rules read these to decide what each driver owes. Anything undecided is listed at the top - an
// unanswered question leaves the rules that depend on it under review, never quietly exempt.
const DECISION = { notqualified: 'Would Refuse', needsreview: 'Needs Review' }

export default function OperatingProfile() {
  const canEdit = ['owner', 'admin'].includes(useUser()?.role)
  const [data, error, reload] = useLoad(() => api.get('/company/operating-profile'))
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [transitFor, setTransitFor] = useState(null)   // the vehicle whose programs are open
  const [histPage, setHistPage] = useState(1)
  const [histSize, setHistSize] = useState(25)
  const [err, setErr] = useState(null)
  const [saved, setSaved] = useState(false)

  if (!data) return <Loading error={error} page />
  const { choices } = data
  const p = draft ?? {
    operatingstates: (data.profile.operatingstates || '').split(',').filter(Boolean),
    employmentmodel: data.profile.employmentmodel || '',
    compliancecontact: data.profile.compliancecontact || '',
    enforcetripcheck: Boolean(data.profile.enforcetripcheck),
  }
  const set = (k, v) => { setSaved(false); setDraft({ ...p, [k]: v }) }

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); await reload(); return true } catch (e) { setErr(e.message); return false }
    finally { setBusy(false) }
  }
  const saveProfile = () => act(async () => {
    await api.put('/company/operating-profile', p)
    setDraft(null); setSaved(true)
  })
  const assess = (v, value) => act(async () => {
    await api.put(`/company/operating-profile/vehicles/${v.recordid}`,
      { fmcsa: value || null, note: v.note })
  })
  // Every program whose answer changed in the vehicle's dialog, saved one at a time.
  const saveTransit = (v, picked) => act(async () => {
    for (const t of data.vehicleprograms) {
      if ((picked[t.code] || '') !== (v.transit[t.code] || '')) {
        await api.put(`/company/operating-profile/vehicles/${v.recordid}/transit/${t.code}`,
          { determination: picked[t.code] || null })
      }
    }
    setTransitFor(null)
  })
  // "FL Covered · GA Not determined" - one line however many programs touch the company.
  const transitSummary = (v) => data.vehicleprograms
    .map((t) => `${t.state} ${determination(v.transit[t.code])}`).join(' · ')
  // One determination select, the same for FMCSA and every transit program.
  const decide = (value, onPick) => (canEdit ? (
    <select value={value || ''} disabled={busy} onChange={(e) => onPick(e.target.value)}>
      <option value="">Not determined</option>
      {Object.entries(choices.determination).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
    </select>
  ) : determination(value))
  const determination = (value) => choices.determination[value] || 'Not determined'
  const tone = (value) => (value === 'covered' ? 'st-active' : value === 'notcovered' ? 'st-inactive'
    : 'st-ordered')

  return (
    <div className="stack stickypage">
      <div className="pagehead">
        <h1>Operating Profile</h1>
        {canEdit && <button className="primary" onClick={saveProfile} disabled={busy}>Save</button>}
      </div>
      {err && <div className="notice bad">{err}</div>}
      {saved && <div className="notice good">Saved.</div>}

      <div className="card qualcard">
        <div className="infotabs"><h3>Profile</h3></div>
        <div className="panelbody">
        <fieldset className="plain" disabled={!canEdit}>
          <div className="profilegrid">
            <div className="profileform">
              <label className="field span-6">Employment Model
                <select value={p.employmentmodel} onChange={(e) => set('employmentmodel', e.target.value)}>
                  <option value="">Not recorded</option>
                  {Object.entries(choices.employment).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </label>
              <label className="field span-6">Compliance Contact
                <select value={p.compliancecontact} onChange={(e) => set('compliancecontact', e.target.value)}>
                  <option value="">Not named</option>
                  {data.users.map((u) => <option key={u.recordid} value={u.recordid}>{u.name}</option>)}
                </select>
              </label>
              <label className="field check span-6">
                <input type="checkbox" checked={p.enforcetripcheck}
                  onChange={(e) => set('enforcetripcheck', e.target.checked)} />
                Refuse trip assignments that fail an approved requirement
              </label>
            </div>
            {/* Every state and DC by name, ticked where the company operates. As tall as the
                fields beside it, and scrolls within that. */}
            <div className="field statepick">Operating States
              <div className="statechecks">
                {Object.entries(STATE_NAMES).sort((x, y) => x[1].localeCompare(y[1])).map(([code, name]) => (
                  <label key={code} className="check">
                    <input type="checkbox" checked={p.operatingstates.includes(code)}
                      onChange={(e) => set('operatingstates', e.target.checked
                        ? [...p.operatingstates, code] : p.operatingstates.filter((x) => x !== code))} />
                    {name}
                  </label>
                ))}
              </div>
            </div>
          </div>
        </fieldset>
        </div>
      </div>

      {/* One determination per transit safety program touching the company: federal ones, and
          those of its home and operating states. */}
      <div className="card qualcard">
        <div className="infotabs"><h3>Transit Safety Programs</h3></div>
        <div className="panelbody">
        <table className="residencetable recordtable">
          <thead><tr><th>Program</th><th>State</th><th>Citation</th><th>Determined</th>
            <th>Determination</th></tr></thead>
          <tbody>
            {data.transit.map((t) => (
              <tr key={t.code}>
                <td>{t.name}</td>
                <td>{t.state}</td>
                <td>{`${t.authority} ${t.citation}`}</td>
                <td>{t.determination ? determination(t.determination) : 'No'}</td>
                <td className={tone(t.determination)}>
                  {canEdit ? (
                    <select value={t.determination || ''} disabled={busy}
                      onChange={(e) => act(() => api.put(`/company/operating-profile/transit/${t.code}`,
                        { determination: e.target.value || null }))}>
                      <option value="">Not determined</option>
                      {Object.entries(choices.determination).map(([c, l]) =>
                        <option key={c} value={c}>{l}</option>)}
                    </select>
                  ) : determination(t.determination)}
                </td>
              </tr>
            ))}
            {!data.transit.length && <tr><td colSpan={5}>No transit safety program touches this company's states.</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>Vehicle Determinations</h3></div>
        <div className="panelbody">
        <table className="residencetable recordtable vehicletable">
          <thead><tr><th>Vehicle</th><th className="center">Seats</th><th className="center">GVWR</th>
            <th className="center">Lift</th><th>FMCSA</th>
            {/* One column for every transit safety program that governs vehicles and touches the
                company's states, however many there are - set in the vehicle's own dialog. */}
            {data.vehicleprograms.length > 0 && <th>Transit Programs</th>}</tr></thead>
          <tbody>
            {data.vehicles.map((v) => (
              <tr key={v.recordid}>
                <td>{[v.externalid, v.make, v.model].filter(Boolean).join(' ') || '-'}</td>
                <td className="center">{v.seats ?? '-'}</td>
                <td className="center">{v.gvwr ? `${Number(v.gvwr).toLocaleString()} lb` : '-'}</td>
                <td className="center">{v.lift ? 'Yes' : 'No'}</td>
                <td className={tone(v.fmcsa)}>{decide(v.fmcsa, (x) => assess(v, x))}</td>
                {data.vehicleprograms.length > 0 && (
                  <td>
                    <div className="withpick">
                      <input readOnly value={transitSummary(v)} title={transitSummary(v)} />
                      {canEdit && (
                        <button type="button" className="pickbtn" title="Transit programs"
                          onClick={() => setTransitFor(v)}><MoreHorizontal size={16} /></button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {!data.vehicles.length && <tr><td colSpan={data.vehicleprograms.length ? 6 : 5}>No vehicles on file.</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>Trip Checks In Shadow</h3></div>
        <div className="panelbody">
        <table className="residencetable recordtable">
          <thead><tr><th>Checked</th><th>Trip Date</th><th>Driver</th><th>Program</th><th>Why</th>
            <th>Decision</th></tr></thead>
          <tbody>
            {data.shadow.map((e) => {
              const why = e.blockers[0] || e.warnings[0] || {}
              return (
                <tr key={e.recordid}>
                  <td>{date(e.evaluatedon)}</td>
                  <td>{date(e.evaluatedfor)}</td>
                  <td>{`${e.firstname || ''} ${e.lastname || ''}`.trim() || '-'}</td>
                  <td>{choices.programs[e.program] || e.program || '-'}</td>
                  <td>{[why.name, why.reason].filter(Boolean).join(' - ') || '-'}</td>
                  <td className={e.decision === 'notqualified' ? 'st-expired' : 'st-ordered'}>
                    {DECISION[e.decision] || e.decision}
                  </td>
                </tr>
              )
            })}
            {!data.shadow.length && <tr><td colSpan={6}>Nothing in the last 30 days would have been refused.</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>Change History</h3></div>
        {/* The house grid, paged here rather than in the address bar - it is one panel on a page,
            and its rows scroll under the headings within a fixed height. */}
        <div className="historypanel">
          <DataGrid className="bare"
            columns={[{ id: 'savedon', label: 'Saved', width: 140, sortable: false },
                      { id: 'by', label: 'By', width: 240, sortable: false },
                      { id: 'what', label: 'What Was Saved', sortable: false }]}
            rows={data.history.slice((histPage - 1) * histSize, histPage * histSize)}
            rowKey={(h) => `${h.savedon}-${h.savedbyname}`}
            empty="The profile has not been saved yet."
            pager={{ total: data.history.length, page: histPage, pagesize: histSize, noun: 'change',
                     onPage: setHistPage, onPageSize: (n) => { setHistSize(n); setHistPage(1) } }}
            cells={(h) => [
              date(h.savedon),
              h.savedbyname || '-',
              h.snapshot.transit
                ? Object.entries(h.snapshot.transit).map(([c, d]) =>
                  `${(data.transit.find((t) => t.code === c) || {}).name || c}: ${choices.determination[d] || 'Not determined'}`).join('; ')
                : [`Employment: ${choices.employment[h.snapshot.employmentmodel] || 'Not recorded'}`,
                  `States: ${h.snapshot.operatingstates || 'none'}`,
                  h.snapshot.enforcetripcheck ? 'Refusing failed trips' : null].filter(Boolean).join('; '),
            ]} />
        </div>
      </div>

      {transitFor && (
        <VehicleTransit vehicle={transitFor} programs={data.vehicleprograms}
          choices={choices.determination} busy={busy} onClose={() => setTransitFor(null)}
          onSave={(picked) => saveTransit(transitFor, picked)} />
      )}
    </div>
  )
}

// One vehicle's determination under each transit safety program that touches the company.
function VehicleTransit({ vehicle, programs, choices, busy, onClose, onSave }) {
  const [picked, setPicked] = useState({ ...vehicle.transit })
  const name = [vehicle.externalid, vehicle.make, vehicle.model].filter(Boolean).join(' ')
  return (
    <Modal title={`${name} Transit Programs`} onClose={onClose} width={720}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy} onClick={() => onSave(picked)}>Save</button>
      </>}>
      <table className="residencetable recordtable transittable">
        <thead><tr><th>Program</th><th className="center">State</th><th>Determination</th></tr></thead>
        <tbody>
          {programs.map((t) => (
            <tr key={t.code}>
              <td title={`${t.authority} ${t.citation}`}>{t.name}</td>
              <td className="center">{t.state}</td>
              <td>
                <select value={picked[t.code] || ''}
                  onChange={(e) => setPicked({ ...picked, [t.code]: e.target.value })}>
                  <option value="">Not determined</option>
                  {Object.entries(choices).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  )
}
