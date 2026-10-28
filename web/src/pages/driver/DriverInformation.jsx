// Driver page - DriverInformation. Moved out of
// pages/DriverReview.jsx, which had grown too large to work in safely.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../../lib/states.js'
import { api } from '../../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../../lib/live.js'
import { date } from '../../lib/format.js'
import { Bubble, Loading, useLoad } from '../../components/ui.jsx'
import { Modal } from '../../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../../components/Pager.jsx'
import { useUser } from '../../App.jsx'
import SignatureBlock from '../../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../../components/DocumentViewer.jsx'
import ApplicantForm from '../../components/ApplicantForm.jsx'
import SignedDocViewer from '../../components/SignedDocViewer.jsx'
import { PhoneInput } from '../../components/MaskedInput.jsx'
import LicenseDialog from '../../components/LicenseDialog.jsx'
import TestDialog from '../../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../../components/WithdrawDialog.jsx'
import { Email, Phone } from '../../components/Contact.jsx'

const LEVEL_OF = { none: 'noncmv', cmv: 'cmv', cdl: 'cdl', heavy: 'cdlheavy' }

const TICKED = {
  noncmv: { cmv: false, cdl: false, heavy: false },
  cmv: { cmv: true, cdl: false, heavy: false },
  cdl: { cmv: true, cdl: true, heavy: false },
  cdlheavy: { cmv: true, cdl: true, heavy: true },
}

const levelFrom = (o) => (o.heavy ? LEVEL_OF.heavy : o.cdl ? LEVEL_OF.cdl
  : o.cmv ? LEVEL_OF.cmv : LEVEL_OF.none)

// Something went in. It is a small thing to say, so it is said small: a mark, a word, and a way
// out - not a dialog dressed as a decision.
function SavedNote({ onClose }) {
  return (
    <div className="backdrop">
      <div className="modal savednote" role="dialog" aria-modal="true" aria-label="Saved">
        <span className="savedmark"><Check size={24} strokeWidth={3} /></span>
        <h2>Saved</h2>
        <p>This driver&rsquo;s information has been saved.</p>
        <button type="button" className="primary" onClick={onClose} autoFocus>Close</button>
      </div>
    </div>
  )
}

// Who they are, and what they drive on. Everything is the office's to correct except the
// Social Security number, which is sealed - only its last four are shown.
export function DriverInformation({ record, onSaved }) {
  const access = useAppAccess(record, onSaved)
  const [f, setF] = useState(() => ({
    firstname: record?.firstname || '', lastname: record?.lastname || '', dob: record?.dob || '',
    phone: record?.phone || '', email: record?.email || '',
    address1: record?.address1 || '', address2: record?.address2 || '', city: record?.city || '',
    state: record?.state || '', zip: record?.zip || '',
    emergencyname: record?.emergencyname || '', emergencyphone: record?.emergencyphone || '',
    // Dispatch knows the driver by the driver ID unless somebody says otherwise.
    externalid: String(record?.externalid || record?.drivernumber || ''), hiredon: record?.hiredon || '',
    endorsementsneeded: record?.endorsementsneeded || '',
    terminatedon: record?.terminatedon || '',
    operation: record?.operation || 'noncmv',
    engagement: record?.engagement || '',
    licensenumber: record?.licensenumber || '', licensestate: record?.licensestate || '',
    licenseclass: record?.licenseclass || '', endorsements: record?.endorsements || '',
  }))
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState(null)
  if (!record) return <div className="card qualcard"><h3>Driver Information</h3></div>

  const set = (k) => (e) => { setSaved(false); setF({ ...f, [k]: e.target.value }) }

  const ticks = TICKED[f.operation] || TICKED.noncmv
  // Ticking a box turns on everything it implies; clearing one turns off everything that implies it.
  const operate = (which, on) => {
    const next = on
      ? { cmv: true, cdl: which !== 'cmv' , heavy: which === 'heavy' }
      : { cmv: which !== 'cmv' && ticks.cmv, cdl: which === 'heavy' && ticks.cdl, heavy: false }
    setSaved(false)
    setF({ ...f, operation: levelFrom(next) })
  }

  const field = (k, label, node, span) => (
    <label className={`field${span ? ` span-${span}` : ''}`}>{label}
      {node || <input value={f[k]} onChange={set(k)} />}
    </label>
  )
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const { hiredon, terminatedon, engagement, ...editable } = f
      // How the company engages the driver decides the employee paperwork, and is kept on its own.
      if ((engagement || '') !== (record.engagement || '')) {
        await api.put(`/drivers/${record.recordid}/engagement`, { engagement: engagement || null })
      }
      await api.put(`/drivers/${record.recordid}`, {
        ...Object.fromEntries(Object.entries(editable).map(([k, v]) => [k, v === '' ? null : v])),
        hiredon: record.hiredon || null, terminatedon: record.terminatedon || null,
      })
      setSaved(true)
      onSaved?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      {saved && <SavedNote onClose={() => setSaved(false)} />}
      <div className="card qualcard">
        <div className="infotabs">
          <h3>Driver Information</h3>
          <div className="row panelactions">{access.button}</div>
          <button type="button" className="primary" disabled={busy} onClick={save}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
        </div>
        {err && <div className="notice bad">{err}</div>}


        <div className="infoform profileform">
          {field('firstname', 'First Name', null, 2)}
          {field('lastname', 'Last Name', null, 2)}
          {field('dob', 'Date Of Birth', <input type="date" value={f.dob || ''} onChange={set('dob')} />, 1)}
          <label className="field span-1">Social Security Number
            <input value={record.ssnlast4 ? `•••-••-${record.ssnlast4}` : 'Not on file'} disabled />
          </label>
          {field('phone', 'Telephone', null, 2)}
          {field('email', 'Email', <input type="email" value={f.email} onChange={set('email')} />, 4)}
          {field('address1', 'Street Address', null, 3)}
          {field('address2', 'Apartment, Suite Or Unit', null, 3)}
          {field('city', 'City', null, 3)}
          {field('state', 'State', <input maxLength={2} value={f.state} onChange={set('state')} />, 1)}
          {field('zip', 'ZIP', null, 2)}
          {/* Who to call. It was given with the application and has lived in it ever since, which
              is a record of what was said that day rather than a number to ring this afternoon. */}
          {field('emergencyname', 'Emergency Contact', null, 3)}
          {field('emergencyphone', 'Emergency Contact Telephone',
            <PhoneInput value={f.emergencyphone || ''} onChange={set('emergencyphone')} />, 3)}
        </div>
        {access.body}
      </div>

      {/* What the company knows them as, and where they stand with it. Hiring and termination are
          decisions, recorded when they are taken - not fields to type into. */}
      <div className="card qualcard">
        <div className="infotabs">
          <h3>Company Information</h3>
          <button type="button" className="primary" disabled={busy} onClick={save}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
        </div>
        {/* Both panels save together, so a refusal shows here as well as at the top - otherwise
            somebody saving from this panel never sees it. */}
        {err && <div className="notice bad">{err}</div>}
        <div className="infoform profileform">
          <label className="field span-3">Engagement
            <select value={f.engagement}
              onChange={(e) => { setSaved(false); setF({ ...f, engagement: e.target.value }) }}>
              <option value="">Company default</option>
              <option value="employee">Employee (W-2)</option>
              <option value="contractor">Independent contractor (1099)</option>
              <option value="subcontracted">Supplied by a subcontracted provider</option>
            </select>
          </label>
          {/* Four to a row: six columns do not divide into four equal fields. */}
          <div className="span-6 fourup">
            <label className="field span-1">Driver ID<input value={record.drivernumber || ''} disabled /></label>
            {field('externalid', 'Dispatch ID', null, 1)}
            <label className="field span-1">Hired<input type="date" value={f.hiredon || ''} disabled /></label>
            <label className="field span-1">Terminated
              <input type="date" value={f.terminatedon || ''} disabled /></label>
          </div>
          <hr className="formrule span-6" />
          {/* What this driver is being qualified to operate - not what the yard holds today. A
              company buying a bus next quarter has to be able to qualify drivers for it now.

              One ordered answer rather than three boxes, because the thresholds are nested: a CDL
              vehicle is always a commercial motor vehicle, and 26,001 lb always needs a CDL. Boxes
              could be ticked into states that cannot exist. */}
          <label className="field check span-6">
            <input type="checkbox" checked={ticks.cmv}
              onChange={(e) => operate('cmv', e.target.checked)} />
            Driver will be operating Commercial Motor Vehicles in accordance with FMCSA 49 CFR §390.5
          </label>
          <label className="field check span-6">
            <input type="checkbox" checked={ticks.cdl}
              onChange={(e) => operate('cdl', e.target.checked)} />
            Driver will be operating a vehicle that requires a CDL (49 CFR 383.91)
          </label>
          <label className="field check span-6">
            <input type="checkbox" checked={ticks.heavy}
              onChange={(e) => operate('heavy', e.target.checked)} />
            Driver will be operating a vehicle rated 26,001 lb or more
          </label>
          {/* What the work requires, as against what the license carries. An endorsement nobody
              has stated is an endorsement nothing can check for, and the first anybody hears of a
              missing P is the day somebody puts the driver in a bus. */}
          <label className="field span-4">Endorsements This Driver Needs
            <input value={f.endorsementsneeded} placeholder="P, S"
              onChange={(e) => { setSaved(false)
                setF({ ...f, endorsementsneeded: e.target.value.toUpperCase() }) }} />
          </label>
          <hr className="formrule span-6" />
          <TransitAssignments id={record.recordid} onChanged={onSaved} />
        </div>
      </div>

      <ContractApprovals id={record.recordid} onChanged={onSaved} />
    </>
  )
}

// The transit safety programs this driver works under - Florida's Chapter 14-90, the FTA's safety
// plan, and any other state's program touching the company. Saved as it is ticked.
function TransitAssignments({ id, onChanged }) {
  const [data, , reload] = useLoad(() => api.get(`/drivers/${id}/transit-programs`), [id])
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState([])
  const [busy, setBusy] = useState(false)
  if (!data || !data.programs.length) return null
  // One line however many programs touch the company: the ones this driver works under.
  const summary = data.programs.filter((t) => t.assigned)
    .map((t) => `${t.state} ${t.citation}`).join(' · ') || 'None'
  const save = async () => {
    setBusy(true)
    try {
      await api.put(`/drivers/${id}/transit-programs`, { codes: picked })
      await reload(); onChanged?.(); setOpen(false)
    } finally { setBusy(false) }
  }
  return (
    <>
      <label className="field span-6">Transit Programs
        <div className="withpick">
          <input readOnly value={summary} title={summary} />
          <button type="button" className="pickbtn" title="Transit programs"
            onClick={() => { setPicked(data.programs.filter((t) => t.assigned).map((t) => t.code)); setOpen(true) }}>
            <MoreHorizontal size={16} />
          </button>
        </div>
      </label>
      {open && (
        <Modal title="Transit Programs" onClose={() => setOpen(false)} width={720}
          footer={<>
            <button type="button" onClick={() => setOpen(false)}>Cancel</button>
            <button type="button" className="primary" disabled={busy} onClick={save}>Save</button>
          </>}>
          <table className="residencetable recordtable transittable">
            <thead><tr><th>Program</th><th className="center">State</th>
              <th className="center">Works Under</th></tr></thead>
            <tbody>
              {data.programs.map((t) => (
                <tr key={t.code}>
                  <td title={`${t.authority} ${t.citation}`}>{t.name}</td>
                  <td className="center">{t.state}</td>
                  <td className="center">
                    <input type="checkbox" checked={picked.includes(t.code)}
                      onChange={(e) => setPicked(e.target.checked ? [...picked, t.code]
                        : picked.filter((c) => c !== t.code))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Modal>
      )}
    </>
  )
}

// The broker contracts that require their drivers to be approved, and whether this one is. A
// driver without the approval cannot take that contract's trips.
function ContractApprovals({ id, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/authorizations`), [id])
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  if (!data) return error ? <div className="notice bad">{error}</div> : null
  if (!data.contracts.length) return null
  const act = async (c, end) => {
    setBusy(c.recordid); setErr(null)
    try {
      await api.post(`/drivers/${id}/authorizations/${c.recordid}${end ? '/end' : ''}`, {})
      await reload(); onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  return (
    <div className="card qualcard">
      <div className="infotabs"><h3>Broker Approvals</h3></div>
      <div className="panelbody">
      {err && <div className="notice bad">{err}</div>}
      <table className="residencetable recordtable">
        <thead><tr><th>Contract</th><th>Approved</th><th>Status</th><th /></tr></thead>
        <tbody>
          {data.contracts.map((c) => (
            <tr key={c.recordid}>
              <td>{[c.broker, c.state, c.contractref].filter(Boolean).join(' ')}</td>
              <td>{c.approvedon ? `${date(c.approvedon)}${c.approvedbyname ? ` · ${c.approvedbyname}` : ''}` : '-'}</td>
              <td className={c.approvalid ? 'st-active' : 'st-inactive'}>
                {c.approvalid ? 'Approved' : 'Not Approved'}
              </td>
              <td className="actions">
                <button type="button" className={c.approvalid ? 'linkbtn' : 'linkbtn edit'}
                  disabled={busy === c.recordid} onClick={() => act(c, Boolean(c.approvalid))}>
                  {c.approvalid ? 'End Approval' : 'Approve'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  )
}

// The driver's own app: whether they can sign in, and the one button that lets them.
//
// An invitation the first time and a reset after that - the same distinction the office logins
// make, because the mail has to say the right thing. Sits on the driver's record rather than in a
// settings screen somewhere: it is a fact about this person, like their licence.
function useAppAccess(record, onChanged) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [link, setLink] = useState(null)
  const [sent, setSent] = useState(false)
  const send = async () => {
    setBusy(true); setErr(null); setLink(null)
    try {
      const got = await api.post(`/drivers/${record.recordid}/appaccess`, {})
      setSent(true)
      if (!got.emailed && got.link) setLink(got.link)
      onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  // The button goes in the Driver Information header beside Save; only what sending it reports -
  // a failure, a link to pass on, or that it went - shows below, and only when there is one.
  return {
    button: (
      <button type="button" className="pill" disabled={busy || !record.email} onClick={send}>
        <Send size={13} /> {record.hasapppassword ? 'Send Password Reset' : 'Send App Invitation'}
      </button>
    ),
    body: (err || link || sent) && (
      <div className="appaccess">
        {err && <div className="notice bad">{err}</div>}
        {link && (
          <div className="notice">
            No mail is configured, so pass this on yourself:
            <input value={link} readOnly onFocus={(e) => e.target.select()} />
          </div>
        )}
        {sent && !link && <div className="notice good">Sent to {record.email}.</div>}
      </div>
    ),
  }
}
