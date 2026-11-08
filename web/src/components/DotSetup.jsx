import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from './ui.jsx'
import { Modal } from '../admin/common.jsx'
import { useUser } from '../App.jsx'

// DOT & CDL Setup. Everything about commercial motor vehicles and CDLs that is set rather than
// filed - what a driver will operate, a vehicle's FMCSA determination, the company's USDOT number
// and drug and alcohol program people - behind one button on the driver, the vehicle and the
// company. Shown only to an account with the DOT & CDL Compliance add-on; without it none of
// this applies, so neither the button nor the fields appear anywhere.

export function DotSetupButton({ kind, id, record, onSaved }) {
  const user = useUser()
  const [open, setOpen] = useState(false)
  if (!user?.dotmodule) return null
  const Dialog = { driver: DriverDot, vehicle: VehicleDot, company: CompanyDot }[kind]
  return (
    <>
      <button type="button" className="primary" onClick={() => setOpen(true)}>DOT &amp; CDL Setup</button>
      {open && <Dialog id={id} record={record} onClose={() => setOpen(false)}
        onSaved={() => { setOpen(false); onSaved?.() }} />}
    </>
  )
}

function Frame({ title, busy, err, onClose, onSave, children, loading, error }) {
  return (
    <Modal title={title} onClose={onClose} width={860}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        {!loading && (
          <button type="button" className="primary" disabled={busy} onClick={onSave}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
        )}
      </>}>
      {loading ? <Loading error={error} /> : (
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {children}
        </div>
      )}
    </Modal>
  )
}

const yesno = (v) => (v === true || v === 1 ? 'yes' : v === false || v === 0 ? 'no' : '')
const asBool = (v) => (v === 'yes' ? true : v === 'no' ? false : null)

// ------------------------------------------------------------------------------------------------
// Driver
// ------------------------------------------------------------------------------------------------

// One ordered answer rather than three boxes: a CDL vehicle is always a commercial motor vehicle,
// and 26,001 lb always needs a CDL, so the boxes cannot be ticked into a state that cannot exist.
const TICKED = {
  noncmv: { cmv: false, cdl: false, heavy: false },
  cmv: { cmv: true, cdl: false, heavy: false },
  cdl: { cmv: true, cdl: true, heavy: false },
  cdlheavy: { cmv: true, cdl: true, heavy: true },
}
const levelFrom = (o) => (o.heavy ? 'cdlheavy' : o.cdl ? 'cdl' : o.cmv ? 'cmv' : 'noncmv')

function DriverDot({ id, record, onClose, onSaved }) {
  const [data, error] = useLoad(() => api.get(`/drivers/${id}/dot`), [id])
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const name = [record?.firstname, record?.lastname].filter(Boolean).join(' ')
  const title = `DOT & CDL Setup - ${name}`.replace(/ - $/, '')
  if (!data) return <Frame title={title} onClose={onClose} loading error={error} />

  const today = new Date().toISOString().slice(0, 10)
  const inpool = Boolean(data.pool.joinedon && !data.pool.leftpoolon)
  const lic = data.licenses[0]
  const v = f ?? {
    operation: data.operation, endorsementsneeded: data.endorsementsneeded || '',
    pool: inpool ? 'yes' : 'no', since: inpool ? data.pool.joinedon : '',
    commercial: lic ? yesno(lic.commercial) : '',
  }
  const set = (k, x) => setF({ ...v, [k]: x })
  const ticks = TICKED[v.operation] || TICKED.noncmv
  const operate = (which, on) => {
    const next = { ...ticks, [which]: on }
    if (on && which === 'heavy') { next.cdl = true; next.cmv = true }
    if (on && which === 'cdl') next.cmv = true
    if (!on && which === 'cmv') { next.cdl = false; next.heavy = false }
    if (!on && which === 'cdl') next.heavy = false
    set('operation', levelFrom(next))
  }

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.put(`/drivers/${id}/dot`, { operation: v.operation, endorsementsneeded: v.endorsementsneeded || null })
      if ((v.pool === 'yes') !== inpool || (v.pool === 'yes' && v.since && v.since !== data.pool.joinedon)) {
        if (inpool) await api.put(`/drivers/${id}/random-pool`, { on: null })
        if (v.pool === 'yes') await api.put(`/drivers/${id}/random-pool`, { on: v.since || today })
      }
      if (lic && v.commercial !== yesno(lic.commercial)) {
        await api.post(`/drivers/${id}/licenses/${lic.recordid}/commercial`, { commercial: asBool(v.commercial) })
      }
      onSaved()
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <Frame title={title} busy={busy} err={err} onClose={onClose} onSave={save}>
      <div>
        <h3 className="formsection">What This Driver Will Operate</h3>
        <div className="profileform">
          <label className="field check span-6">
            <input type="checkbox" checked={ticks.cmv} onChange={(e) => operate('cmv', e.target.checked)} />
            Driver will be operating Commercial Motor Vehicles in accordance with FMCSA 49 CFR §390.5
          </label>
          <label className="field check span-6">
            <input type="checkbox" checked={ticks.cdl} onChange={(e) => operate('cdl', e.target.checked)} />
            Driver will be operating a vehicle that requires a CDL (49 CFR 383.91)
          </label>
          <label className="field check span-6">
            <input type="checkbox" checked={ticks.heavy} onChange={(e) => operate('heavy', e.target.checked)} />
            Driver will be operating a vehicle rated 26,001 lb or more
          </label>
          <label className="field span-2">Endorsements This Driver Needs
            <input value={v.endorsementsneeded} placeholder="P, S"
              onChange={(e) => set('endorsementsneeded', e.target.value.toUpperCase())} />
          </label>
        </div>
      </div>
      <div>
        <h3 className="formsection">Random Testing</h3>
        <div className="profileform">
          <label className="field span-2">In The Random Pool
            <select value={v.pool} onChange={(e) => set('pool', e.target.value)}>
              <option value="no">No</option><option value="yes">Yes</option>
            </select>
          </label>
          {v.pool === 'yes' && (
            <label className="field span-2">In The Pool Since
              <input type="date" value={v.since || today} onChange={(e) => set('since', e.target.value)} />
            </label>
          )}
        </div>
      </div>
      <div>
        <h3 className="formsection">License On File</h3>
        {!lic ? <p className="muted">No license is on file for this driver.</p> : (
          <div className="profileform">
            <label className="field span-2">License
              <input value={`${lic.state || ''} ${lic.number || ''}`.trim()} disabled /></label>
            <label className="field span-2">Class<input value={lic.classification || ''} disabled /></label>
            <label className="field span-2">Commercial (CDL)
              <select value={v.commercial} onChange={(e) => set('commercial', e.target.value)}>
                <option value="">Not said</option><option value="yes">Yes</option><option value="no">No</option>
              </select>
            </label>
          </div>
        )}
      </div>
    </Frame>
  )
}

// ------------------------------------------------------------------------------------------------
// Vehicle
// ------------------------------------------------------------------------------------------------

const said = (x) => (x === true ? 'Yes' : x === false ? 'No' : 'Not known')

function VehicleDot({ id, record, onClose, onSaved }) {
  const [det, error] = useLoad(() => api.get(`/company/operating-profile/vehicles/${id}`), [id])
  const [fmcsa, setFmcsa] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const title = `DOT & CDL Setup - ${record?.externalid || 'Vehicle'}`
  if (!det) return <Frame title={title} onClose={onClose} loading error={error} />
  const facts = record?.facts || {}
  const why = facts.why || {}
  const value = fmcsa ?? (det.fmcsa || '')

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      if (value !== (det.fmcsa || '')) {
        await api.put(`/company/operating-profile/vehicles/${id}`, { fmcsa: value || null })
      }
      onSaved()
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <Frame title={title} busy={busy} err={err} onClose={onClose} onSave={save}>
      <div>
        <h3 className="formsection">Classification</h3>
        <div className="profileform">
          {/* Worked out from the seats and weight, with the reason - read here, never typed in. Two
              lines, so the whole reason shows. */}
          <label className="field span-6">Commercial Motor Vehicle
            <textarea rows={2} style={{ height: 'auto', minHeight: 0, resize: 'none' }} disabled
              value={`${said(facts.cmv_federal)}${why.cmv_federal ? ` - ${why.cmv_federal}` : ''}`} /></label>
          <label className="field span-6">CDL Required
            <textarea rows={2} style={{ height: 'auto', minHeight: 0, resize: 'none' }} disabled
              value={`${said(facts.cdl_required)}${why.cdl_required ? ` - ${why.cdl_required}` : ''}`} /></label>
          <label className="field span-2">FMCSA Determination
            <select value={value} onChange={(e) => setFmcsa(e.target.value)}>
              <option value="">Not determined</option>
              {Object.entries(det.choices).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
            </select>
          </label>
        </div>
      </div>
    </Frame>
  )
}

// ------------------------------------------------------------------------------------------------
// Company
// ------------------------------------------------------------------------------------------------

function CompanyDot({ onClose, onSaved }) {
  const [data, error] = useLoad(async () => {
    const [company, questions, der, supervisor] = await Promise.all([
      api.get('/company'), api.get('/company/questions'),
      api.get('/company/roles/der'), api.get('/company/roles/supervisor')])
    return { company, mis: questions.questions.find((q) => q.code === 'MIS_REQUESTED'), der, supervisor }
  }, [])
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const title = 'DOT & CDL Setup'
  if (!data) return <Frame title={title} onClose={onClose} loading error={error} />

  const derNow = data.der.held[0]
  const supNow = data.supervisor.held.map((h) => h.userid)
  const v = f ?? {
    usdot: data.company.usdot || '', mcnumber: data.company.mcnumber || '',
    mis: data.mis ? yesno(data.mis.answer) : '', der: derNow?.userid || '', supervisors: supNow,
  }
  const set = (k, x) => setF({ ...v, [k]: x })

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      if (v.usdot !== (data.company.usdot || '') || v.mcnumber !== (data.company.mcnumber || '')) {
        await api.put('/company', { usdot: v.usdot || null, mcnumber: v.mcnumber || null })
      }
      if (data.mis && v.mis !== yesno(data.mis.answer)) {
        await api.put('/company/questions/MIS_REQUESTED', { answer: asBool(v.mis) })
      }
      if (v.der !== (derNow?.userid || '')) {
        if (derNow) await api.del(`/company/roles/der/${derNow.recordid}`)
        if (v.der) await api.post('/company/roles/der', { userid: v.der })
      }
      for (const h of data.supervisor.held) {
        if (!v.supervisors.includes(h.userid)) await api.del(`/company/roles/supervisor/${h.recordid}`)
      }
      for (const u of v.supervisors) {
        if (!supNow.includes(u)) await api.post('/company/roles/supervisor', { userid: u })
      }
      onSaved()
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <Frame title={`${title} - ${data.company.name}`} busy={busy} err={err} onClose={onClose} onSave={save}>
      <div>
        <h3 className="formsection">Registration</h3>
        <div className="profileform">
          <label className="field span-2">USDOT #
            <input value={v.usdot} inputMode="numeric" onChange={(e) => set('usdot', e.target.value)} /></label>
          <label className="field span-2">MC #
            <input value={v.mcnumber} onChange={(e) => set('mcnumber', e.target.value.toUpperCase())} /></label>
          {data.mis && (
            <label className="field span-2">FMCSA Asked For An MIS Report
              <select value={v.mis} onChange={(e) => set('mis', e.target.value)}>
                <option value="">Not answered</option><option value="yes">Yes</option><option value="no">No</option>
              </select>
            </label>
          )}
        </div>
      </div>
      <div>
        <h3 className="formsection">Drug And Alcohol Program</h3>
        <div className="profileform">
          <label className="field span-3">Designated Employer Representative
            <select value={v.der} onChange={(e) => set('der', e.target.value)}>
              <option value="">Not appointed</option>
              {data.der.people.map((u) => <option key={u.recordid} value={u.recordid}>{u.name}</option>)}
            </select>
          </label>
          <div className="field span-3">Reasonable Suspicion Supervisors
            {data.supervisor.people.map((u) => (
              <label key={u.recordid} className="check">
                <input type="checkbox" checked={v.supervisors.includes(u.recordid)}
                  onChange={(e) => set('supervisors', e.target.checked
                    ? [...v.supervisors, u.recordid] : v.supervisors.filter((x) => x !== u.recordid))} />
                {u.name}
              </label>
            ))}
          </div>
        </div>
      </div>
    </Frame>
  )
}
