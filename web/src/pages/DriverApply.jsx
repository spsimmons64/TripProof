import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import LicenseScanner, { ScanResult } from '../components/LicenseScanner.jsx'
import { AlertCircle, Check, ChevronLeft, ChevronRight, Download, Eye, Loader2, Minus, PartyPopper, Plus, ScanLine, ShieldCheck, Upload, X } from 'lucide-react'
import { api } from '../lib/api.js'
import { STATE_NAMES } from '../lib/states.js'
import { EmailInput, PhoneInput, SsnInput, UpperArea, UpperInput, ZipInput } from '../components/MaskedInput.jsx'
import LicenseDialog, { FieldError, StateSelect, useFirstField } from '../components/LicenseDialog.jsx'
import PublicShell from '../components/PublicShell.jsx'
import { properName } from '../lib/names.js'
import { DEFAULT_FONT, SIGNATURE_FONTS } from '../lib/signatureFonts.js'

// The online driver application. No login: the applicant proves who they are with date of birth
// and SSN, and a token from that check carries the session. Eight steps - two that collect answers
// and files, six that are documents to read and sign, two of those only for a commercial driver -
// then submit.
//
// Form I-9 and Form W-4 are deliberately not here: the I-9's Section 1 may not be signed before a
// job offer has been accepted, and the W-4 belongs to payroll. Both are sent to the driver once
// they are hired; the I-9 step itself is kept below, ready for that.
const STEPS = [
  { n: 1, title: 'Application For Employment', blurb: 'Your details, residence history, employment history and license status' },
  { n: 2, title: "Driver's Licenses", blurb: "Driver's licenses held, upload driver's license, driver history" },
  { n: 3, title: 'Drug And Alcohol Policy', blurb: 'Testing, reporting and what a violation means', doc: 'DRUG_POLICY' },
  { n: 4, title: 'Workplace Policy', blurb: 'The rules you agree to work by', doc: 'WORKPLACE_POLICY' },
  { n: 5, title: 'Passenger Privacy', blurb: 'What you may do with what you learn about passengers',
    doc: 'PHI_ACK' },
  { n: 6, title: 'Clearinghouse Consent', blurb: 'Authorization to query the FMCSA Clearinghouse',
    doc: 'CLEARINGHOUSE_CONSENT', appliesif: (state) => willDriveCmv(state) },
  { n: 7, title: 'Safety Performance History', blurb: 'Release of your safety record from previous employers',
    doc: 'SAFETY_PERFORMANCE_CONSENT', appliesif: (state) => willDriveCmv(state) },
  { n: 8, title: 'Your FCRA Rights', blurb: 'A summary of your rights before any background report', doc: 'FCRA_SUMMARY' },
  { n: 9, title: 'FCRA Driver Consent', blurb: 'Permission to obtain consumer reports about you', doc: 'FCRA_AUTH' },
  // 49 CFR 40.25(j). Asked of the applicant rather than of a previous employer, because it is about
  // jobs they applied for and did NOT get - there is no employer record of those anywhere.
  { n: 10, title: 'Pre-Employment Drug And Alcohol Questionnaire',
    blurb: 'One question about tests taken for jobs you applied for in the last two years',
    appliesif: (state) => willDriveCmv(state) },
]

// The Clearinghouse is queried about commercial drivers, and a commercial driver is one holding a
// commercial license. The card decides it: nobody drives a vehicle that needs a CDL without one, and
// an applicant cannot know what the company runs, so asking them was never the better evidence.
function willDriveCmv(state) {
  const two = state.data?.steps?.['2'] || {}
  return (two.licenses || []).some((l) => COMMERCIAL.includes((l.classification || '').toUpperCase()))
}

const applies = (s, state) => !s.appliesif || s.appliesif(state)

// The license in force: the one issued most recently, which is what a commercial driver is judged on.
const COMMERCIAL = ['A', 'B', 'C']
const currentLicense = (licenses) => [...licenses].sort((a, b) => (b.issued || '').localeCompare(a.issued || ''))[0] || {}

// Where each step stands: done, still to do, or not applicable because the applicant said so. A
// step counts as done only when everything it demands is there - the same things Next checks, so
// the panel never says complete about a page that would refuse to be left.
function stepStatus(s, state) {
  if (!applies(s, state)) return 'na'
  if (s.doc) return state.signed?.[s.doc] ? 'done' : 'todo'
  const answers = state.data?.steps?.[String(s.n)]
  if (!answers) return 'todo'
  if (s.n === 1) return state.signed?.APPLICATION ? 'done' : 'todo'
  if (s.n === 2) {
    const licenses = answers.licenses || []
    return licenses.length && state.uploads?.license_front && state.uploads?.license_back
      ? 'done' : 'todo'
  }
  // The questionnaire is done when it is answered - and, where the answer is yes, when the detail
  // 40.25(j) asks for is filled in too.
  if (s.n === 10) {
    if (answers.priorviolation === 'no') return 'done'
    return answers.priorviolation === 'yes' && (answers.priortestdate || answers.prioremployer)
      ? 'done' : 'todo'
  }
  return 'done'
}

// Everything on step 1 is required except the secondary telephone.
const REQUIRED = {
  1: [
    ['firstname', 'The first name is required'],
    ['lastname', 'The last name is required'],
    ['address1', 'The street address is required'],
    ['city', 'The city is required'],
    ['state', 'The state is required'],
    ['zip', 'The ZIP code is required'],
    ['phone', 'The primary phone is required'],
    ['email', 'The email address is required'],
    ['emergencyname', 'The emergency contact is required'],
    ['emergencyphone', 'The emergency contact telephone is required'],

  ],
  2: [
    ['medexempt', 'An answer is required', (v) => cmvDriver(v)],
    ['medissued', 'The issue date is required', (v) => cmvDriver(v) && v.medexempt === 'no'],
    ['medexpires', 'The expiration date is required', (v) => cmvDriver(v) && v.medexempt === 'no'],
    ['licenseaction', 'An answer is required'],
    ['licenseactionwhy', 'An explanation is required', (v) => v.licenseaction === 'yes'],
  ],
  // Kept for the I-9 once it is sent out after hiring; no step in this wizard uses it.
  i9: [
    ['citizenship', 'Choose the one that applies to you'],
    ['anumber', 'The USCIS or A-Number is required', (v) => v.citizenship === 'permanent'],
    ['workuntil', 'The date is required', (v) => v.citizenship === 'authorized'],
    ['workproof', 'One of these is required', (v) => v.citizenship === 'authorized'
      && !((v.anumber || '').trim() || (v.i94 || '').trim() || (v.passport || '').trim())],
  ],
}

// A driver who holds the license and will actually drive a commercial vehicle: the medical card
// questions only apply to them.
const cmvDriver = (v) => (v.licenses || []).some((l) => COMMERCIAL.includes((l.classification || '').toUpperCase()))

// What a license can be issued as, and the endorsements that can sit on it.



// What each company policy is called when the applicant acknowledges it.
const POLICY_NAMES = {
  DRUG_POLICY: 'Drug And Alcohol Policy',
  WORKPLACE_POLICY: 'Workplace Policy',
  PHI_ACK: 'PHI Confidentiality And Privacy Acknowledgment',
  FCRA_AUTH: 'FCRA Driver Consent',
}

// A policy is acknowledged; a consent is given. The wording follows what is being signed.
const POLICY_ACK = {
  FCRA_AUTH: (name, company) => `I have read the ${name} of ${company}, I have had the chance to ask about `
    + 'anything in it, and I authorize consumer reports about me to be obtained as it describes.',
}
const acknowledgement = (doctype, name, company) => (POLICY_ACK[doctype]
  ? POLICY_ACK[doctype](name, company)
  : `I acknowledge that I have received, read and understand the ${name} of ${company}, that I have had `
    + 'the chance to ask about anything in it, and that I agree to follow it.')

// The hands a driver can sign in. All eight are self-hosted (SIL Open Font License): a page that
// handles Social Security numbers makes no third-party requests, and the CSP stays closed.
// The default is the first in the list; the rest are there for a driver who wants a different hand.
const FONTS = SIGNATURE_FONTS

export default function DriverApply() {
  const { accountnumber } = useParams()
  const [company, setCompany] = useState(null)
  const [error, setError] = useState(null)
  // The session lives in memory only. Opening the link - or reloading it - always starts at the
  // date of birth and SSN check: that is what finds an application to resume, and it keeps one
  // applicant's session from following the browser into another company's link.
  const [token, setToken] = useState('')
  const [state, setState] = useState(null)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    setToken(''); setState(null); setMessage(null); setError(null)
    api.get(`/driverapply/${accountnumber}`).then(setCompany).catch((e) => setError(e.message))
  }, [accountnumber])

  const onSession = (t, s) => { setToken(t); setState(s) }

  if (error) return <Shell><div className="notice bad">{error}</div></Shell>
  if (!company) return <Shell><Loader2 className="spin" /></Shell>
  if (!token || !state) {
    return (
      <Shell company={company}>
        <Identify accountnumber={accountnumber} message={message} onMessage={setMessage} onSession={onSession} />
      </Shell>
    )
  }
  return <Shell company={company}><Wizard token={token} state={state} setState={setState} /></Shell>
}

// A copy of the api helper bound to the application token rather than a signed-in user.
function apiAuth(token) {
  const call = async (method, path, body, isForm) => {
    const r = await fetch(`/api${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(isForm ? {} : { 'Content-Type': 'application/json' }) },
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
    })
    const text = await r.text()
    const data = text ? JSON.parse(text) : null
    if (!r.ok) throw new Error(data?.detail || 'Something went wrong')
    return data
  }
  return {
    get: (p) => call('GET', p),
    post: (p, b) => call('POST', p, b),
    put: (p, b) => call('PUT', p, b),
    upload: (p, form) => call('POST', p, form, true),
  }
}

// The application's frame is the one every public page wears; it takes the whole company record
// here, so the wrapper keeps that shape and hands the shared shell what it needs.
function Shell({ company, children }) {
  return <PublicShell company={company?.accountname}>{children}</PublicShell>
}

// ------------------------------------------------------------------------------------------------
// Step 0 - who are you
// ------------------------------------------------------------------------------------------------

function Identify({ accountnumber, message, onMessage, onSession }) {
  const [v, setV] = useState({ dob: '', ssn: '', firstname: '', lastname: '' })
  const [needname, setNeedname] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [bad, setBad] = useState({})
  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    onMessage(null)
    setV({ ...v, [k]: e.target.value })
  }

  // Our own checks, in our own words: the browser's bubble can't be styled and says "this field".
  const check = () => {
    const problems = {}
    if (!v.dob) problems.dob = 'The birth date is required'
    if (!v.ssn) problems.ssn = 'The Social Security number is required'
    else if (v.ssn.replace(/\D/g, '').length !== 9) problems.ssn = 'Enter all nine digits'
    if (needname && !v.firstname.trim()) problems.firstname = 'The first name is required'
    if (needname && !v.lastname.trim()) problems.lastname = 'The last name is required'
    return problems
  }

  const submit = async (e) => {
    e.preventDefault()
    const problems = check()
    setBad(problems)
    if (Object.keys(problems).length) return
    setBusy(true); setErr(null); onMessage(null)
    try {
      const r = await api.post(`/driverapply/${accountnumber}/start`, v)
      if (r.state === 'new' && r.needname) { setNeedname(true); return }
      if (r.token) {
        const s = await apiAuth(r.token).get('/driverapply/session/state')
        onSession(r.token, s)
      } else onMessage(r.message)
    } catch (e2) { setErr(e2.message) } finally { setBusy(false) }
  }

  return (
    <form className="card applycard applysolo" onSubmit={submit} noValidate>
      <h1>Start or continue your application</h1>
      <div className="profileform">
        <label className={`field span-3${bad.dob ? ' bad' : ''}`}>Date Of Birth *
          <input type="date" value={v.dob} onChange={set('dob')} aria-invalid={!!bad.dob} />
          <FieldError message={bad.dob} />
        </label>
        <label className={`field span-3${bad.ssn ? ' bad' : ''}`}>Social Security Number *
          <SsnInput value={v.ssn} onChange={set('ssn')} aria-invalid={!!bad.ssn} />
          <FieldError message={bad.ssn} />
        </label>
        {needname && <>
          <label className={`field span-3${bad.firstname ? ' bad' : ''}`}>First Name *
            <UpperInput value={v.firstname} onChange={set('firstname')} aria-invalid={!!bad.firstname} />
            <FieldError message={bad.firstname} />
          </label>
          <label className={`field span-3${bad.lastname ? ' bad' : ''}`}>Last Name *
            <UpperInput value={v.lastname} onChange={set('lastname')} aria-invalid={!!bad.lastname} />
            <FieldError message={bad.lastname} />
          </label>
        </>}
      </div>
      {needname && <div className="notice">We don't have you yet - tell us your name and we'll begin.</div>}
      {message && <div className="notice warn">{message}</div>}
      {err && <div className="error">{err}</div>}
      <div className="assurance">
        <span className="shield" aria-hidden="true"><ShieldCheck size={40} strokeWidth={2.1} /></span>
        <div>
          <b>Your information is protected</b>
          <p>
            Your details are kept private and secure. Your Social Security number is never shown back to you
            or to staff - it is only used to find your application. Nobody but the company you are applying to
            can see what you enter, and we keep a record of every time it is opened.
          </p>
        </div>
      </div>

      <button className="primary big" disabled={busy}>{busy ? 'Checking…' : needname ? 'Begin application' : 'Continue'}</button>
    </form>
  )
}



// ------------------------------------------------------------------------------------------------
// The wizard
// ------------------------------------------------------------------------------------------------

function Wizard({ token, state, setState }) {
  const call = useMemo(() => apiAuth(token), [token])
  // Coming back opens the first page that is not finished - not the furthest page reached, which
  // may have been stepped into and left half done. A step that no longer applies is skipped.
  const resumeAt = () => (STEPS.find((s) => applies(s, state) && stepStatus(s, state) !== 'done')
    || [...STEPS].reverse().find((s) => applies(s, state))
    || STEPS[0]).n
  const [step, setStep] = useState(resumeAt())
  // Step 1 starts from the name given at the identity check, so what is shown is what is stored.
  const answersFor = (n) => {
    const saved = state.data?.steps?.[String(n)] || {}
    // 'No' is the answer for almost everyone, so it is the stored answer too - a default that only
    // showed on screen still counted as unanswered when Next checked.
    if (n === 2) return { licenseaction: 'no', medexempt: 'no', ...saved }
    if (n !== 1) return saved
    return { firstname: state.firstname || '', lastname: state.lastname || '', ...saved }
  }
  const [values, setValues] = useState(answersFor(step))
  // What the panel and the buttons judge by: the saved application with this step's unsaved answers
  // laid over it, so answering the commercial question moves those steps in or out at once.
  const live = useMemo(() => ({ ...state,
    data: { ...(state.data || {}), steps: { ...((state.data || {}).steps || {}), [String(step)]: values } } }),
  [state, step, values])
  const appliesNow = (s) => applies(s, live)
  // Retrieved once, the signature stays available for the rest of this visit - in memory only.
  const [unlocked, setUnlocked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const current = STEPS[step - 1]
  // Where Next and Back land: the nearest step that applies to this applicant.
  const nextStep = (from, by) => {
    let n = from
    while (n >= 1 && n <= STEPS.length && !appliesNow(STEPS[n - 1])) n += by
    return Math.min(Math.max(n, 1), STEPS.length)
  }
  const lastStep = STEPS.filter(appliesNow).slice(-1)[0]?.n || STEPS.length
  const done = state.status === 'submitted'
  const [saved, setSaved] = useState(false)
  const [bad, setBad] = useState({})
  useEffect(() => { setValues(answersFor(step)); setBad({}) }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // Moving between steps saves what is on screen: there is no separate save button.
  const goto = async (n) => {
    if (n === step) return
    setErr(null)
    // Whatever is on screen is saved before anything else, so an incomplete step never costs the
    // applicant what they had already typed into it.
    if (!current.doc) {
      setBusy(true)
      try {
        await call.put('/driverapply/session/step', { step, answers: values })
        setState(await call.get('/driverapply/session/state'))
      } catch (e) { setErr(e.message); setBusy(false); return }
      setBusy(false)
    }
    // Going forward, the step has to be complete; going back never blocks.
    if (n > step) {
      const problems = Object.fromEntries((REQUIRED[step] || [])
        .filter(([k, , when]) => (!when || when(values)) && !String(values[k] ?? '').trim())
        .map(([k, message]) => [k, message]))
      // Every break in the employment history needs a reason.
      for (const gap of employmentGaps(values.employers)) {
        if (!String((values.gaps || {})[gap.key] ?? '').trim()) problems[`gap:${gap.key}`] = 'A reason is required'
      }
      // And the application itself is signed before anything else is asked.
      if (step === 1 && !state.signed?.APPLICATION) problems.signature = 'The application must be signed'
      // The license itself, and a copy of both sides of it, before the license step is left behind.
      if (step === 2) {
        if (!state.uploads?.license_front) problems.license_front = 'A copy of the front is required'
        if (!state.uploads?.license_back) problems.license_back = 'A copy of the back is required'
        if (!(values.licenses || []).length) problems.licenses = 'Add the license you hold'
      }
      setBad(problems)
      if (Object.keys(problems).length) {
        // The signature sits at the foot of a long step; take them to it.
        if (problems.signature) {
          document.querySelector('.signblock')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        if (problems.license_front || problems.license_back) {
          document.querySelector('.filefield')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        } else if (problems.licenses) {
          document.querySelector('.licenses')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        return
      }
    }
    setStep(n)
    // Remember how far they have got, so coming back opens where they left off.
    call.put('/driverapply/session/progress', { step: n }).catch(() => {})
  }

  const refresh = async () => setState(await call.get('/driverapply/session/state'))

  // Save what is on screen and stop for now. The confirmation is a page of its own, with the way
  // back on it: returning asks for date of birth and SSN again, which is what finds the application.
  const saveForLater = async () => {
    setBusy(true); setErr(null)
    try {
      if (!current.doc) await call.put('/driverapply/session/step', { step, answers: values, advance: false })
      setSaved(true)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const submit = async () => {
    setBusy(true); setErr(null)
    try { await call.post('/driverapply/session/submit'); await refresh() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (saved) {
    return (
      <div className="card applycard applysolo">
        <h1>Your application is saved</h1>
        <p>
          Everything you have entered so far is kept. Come back whenever you like and carry on from
          where you stopped - you will be asked for your date of birth and Social Security number,
          which is how we find your application.
        </p>
        <button type="button" className="primary big" onClick={() => window.location.reload()}>
          Return to the application
        </button>
      </div>
    )
  }

  if (done) {
    return (
      <div className="card applycard applysolo celebrate">
        <Confetti />
        <div className="celebratebadge" aria-hidden="true"><PartyPopper size={44} strokeWidth={2.1} /></div>
        <h1>Thank You{state.firstname ? `, ${titleCase(state.firstname)}` : ''}!</h1>
        <p className="celebratelead">
          Your application is in the hands of {state.accountname}. Every page you filled in and every
          document you signed has been received and stored safely.
        </p>
        <ol className="nextsteps">
          <li><b>We review it.</b> {state.accountname} goes through your application and the documents you signed.</li>
          <li><b>We check your history.</b> Your driving record and background are looked at, as you authorized.</li>
          <li><b>We get in touch.</b> Someone from the office will contact you about the next step.</li>
        </ol>
        <p className="small muted celebratefoot">
          You can close this page. If you need to reach us about your application, contact
          {' '}{state.accountname} directly.
        </p>
      </div>
    )
  }

  const signedAll = STEPS.filter((s) => s.doc && appliesNow(s)).every((s) => state.signed?.[s.doc])

  return (
    <Signing.Provider value={{ unlocked, unlock: () => setUnlocked(true) }}>
    <div className="applylayout">
      <aside className="card applyprogress">
        <h2>Application Process</h2>
        <ol>
          {STEPS.map((s) => {
            const status = stepStatus(s, live)
            return (
              <li key={s.n} className={`${status}${s.n === step ? ' on' : ''}`}>
                <span className="bubble" aria-hidden="true">
                  {status === 'done' ? <Check size={16} /> : status === 'na' ? <Minus size={16} /> : '?'}
                </span>
                <span className="steptext">
                  <b>{s.title}</b>
                  <span>{s.blurb}</span>
                </span>
                <span className="sr-only">{status === 'done' ? 'Complete' : status === 'na' ? 'Not applicable' : 'Not complete'}</span>
              </li>
            )
          })}
        </ol>
      </aside>
      <div className="card applycard">
        <h1>{current.title}</h1>
        <hr className="cardrule" />
        {/* Only this middle band scrolls: the title above it and the buttons below stay put. */}
        <div className="cardscroll">
          {err && <div className="error">{err}</div>}
          {current.doc === 'I9'
            ? <I9Step call={call} state={state} refresh={refresh} token={token}
                values={values} setValues={setValues} bad={bad} />
            : current.doc
            ? <DocumentStep call={call} doctype={current.doc} state={state} refresh={refresh} token={token} />
            : <AnswerStep step={step} v={values} setV={setValues} bad={bad} setBad={setBad} call={call} state={state}
              refresh={refresh} token={token} />}
        </div>

        <div className="applynav">
          <button type="button" disabled={step === 1 || busy} onClick={() => goto(nextStep(step - 1, -1))}><ChevronLeft size={14} /> Back</button>
          <button type="button" disabled={busy} onClick={saveForLater}>Save And Complete Later</button>
          {step < lastStep
            ? <button type="button" className="primary" disabled={busy} onClick={() => goto(nextStep(step + 1, 1))}>
                {busy ? 'Saving…' : <>Next <ChevronRight size={14} /></>}
              </button>
            : <button type="button" className="primary" disabled={!signedAll || busy} onClick={submit}>Submit application</button>}
        </div>
        {step === lastStep && !signedAll && <p className="small muted">Sign every document before submitting.</p>}
      </div>

    </div>
    </Signing.Provider>
  )
}

// ------------------------------------------------------------------------------------------------
// Steps 1-3 - answers and files
// ------------------------------------------------------------------------------------------------

function AnswerStep({ step, v, setV, bad, setBad, call, state, refresh, token }) {
  const [adding, setAdding] = useState(false)
  const [addingEmployer, setAddingEmployer] = useState(false)
  const [addingLicense, setAddingLicense] = useState(false)
  // Reading the barcode on the back of the card, so nobody types what the card already says.
  const [scanning, setScanning] = useState(false)
  const [scanned, setScanned] = useState(null)
  // Which row of each table is being corrected, if any.
  const [editingLicense, setEditingLicense] = useState(null)
  const [editingResidence, setEditingResidence] = useState(null)
  const [editingEmployer, setEditingEmployer] = useState(null)
  const [editingAccidents, setEditingAccidents] = useState(null)
  const [editingViolations, setEditingViolations] = useState(null)
  // Replacing row `i` of one of the lists with what the dialog gives back.
  const replaceIn = (key, i, row) => setV({ ...v, [key]: v[key].map((old, n) => (n === i ? row : old)) })
  const [addingAccident, setAddingAccident] = useState(false)
  const [addingViolation, setAddingViolation] = useState(false)
  const gaps = employmentGaps(v.employers)
  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setV({ ...v, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  }
  // A field carries its own message, in the same bubble the identity check uses.
  const f = (k, label, span, node) => (
    <label className={`field span-${span}${bad[k] ? ' bad' : ''}`}>{label}
      {node}
      <FieldError message={bad[k]} />
    </label>
  )
  // A message stands until what it complains about changes. Tables and uploads are not fields, so
  // they say for themselves when they have been put right.
  const clearBad = (...keys) => setBad((was) => {
    const next = { ...was }
    for (const k of keys) delete next[k]
    return next
  })

  return (
    <>
      {step === 1 && (
        <>
          <div className="profileform">
            {/* Both were given at the identity check and are what found this application, so they
                head the form as a record of it rather than as something to edit. */}
            <label className="field span-3">Date Of Birth
              <input value={fullDate(state.dob)} readOnly disabled />
            </label>
            <label className="field span-3">Social Security Number
              <input value={state.ssnlast4 ? `\u2022\u2022\u2022-\u2022\u2022-${state.ssnlast4}` : ''} readOnly disabled />
            </label>
            {f('firstname', 'First Name *', 2,
              <UpperInput autoFocus value={v.firstname || ''} onChange={set('firstname')} />)}
            {f('middleinitial', 'Middle Initial', 1,
              <UpperInput maxLength={1} value={v.middleinitial || ''} onChange={set('middleinitial')} />)}
            {f('lastname', 'Last Name *', 3, <UpperInput value={v.lastname || ''} onChange={set('lastname')} />)}
            {f('address1', 'Street Address *', 4, <UpperInput value={v.address1 || ''} onChange={set('address1')} />)}
            {f('apt', 'Apartment / Suite Number', 2, <UpperInput value={v.apt || ''} onChange={set('apt')} />)}
            {f('city', 'City *', 2, <UpperInput value={v.city || ''} onChange={set('city')} />)}
            {f('state', 'State *', 1, <StateSelect value={v.state} onChange={set('state')} />)}
            {f('zip', 'ZIP *', 3, <ZipInput value={v.zip || ''} onChange={set('zip')} />)}
            {f('phone', 'Primary Phone *', 3, <PhoneInput value={v.phone || ''} onChange={set('phone')} />)}
            {f('phone2', 'Secondary Telephone', 3, <PhoneInput value={v.phone2 || ''} onChange={set('phone2')} />)}
            {f('email', 'Email Address *', 6, <EmailInput value={v.email || ''} onChange={set('email')} />)}
            {f('emergencyname', 'Emergency Contact *', 3, <UpperInput value={v.emergencyname || ''} onChange={set('emergencyname')} />)}
            {f('emergencyphone', 'Emergency Contact Telephone *', 3, <PhoneInput value={v.emergencyphone || ''} onChange={set('emergencyphone')} />)}
            <hr className="formrule" />

            <div className="span-6 residences">
              <p className="residenceask">
                List ANY different residences for the previous 3 years if you lived at the above address
                less than 3 years.
              </p>
              {(v.residences || []).length > 0 && (
                <table className="residencetable">
                  <thead><tr><th>Address</th><th>City</th><th>State</th><th>ZIP Code</th><th /></tr></thead>
                  <tbody>
                    {(v.residences || []).map((r, i) => (
                      <tr key={i}>
                        <td>{r.address1}</td><td>{r.city}</td><td>{r.state}</td><td>{r.zip}</td>
                        <td className="actions">
                          <button type="button" className="linkbtn edit" onClick={() => setEditingResidence(i)}>Edit</button>
                          <button type="button" className="linkbtn"
                            onClick={() => setV({ ...v, residences: v.residences.filter((_, n) => n !== i) })}>Remove</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <button type="button" onClick={() => setAdding(true)}><Plus size={14} /> Add</button>
            </div>

            <hr className="formrule" />

            <div className="span-6 residences">
              {/* A commercial driver owes ten years of history; anyone else, three. */}
              <p className="residenceask">List ALL employers in the last {v.operatescmv === 'yes' ? 10 : 3} years.</p>
              {(v.employers || []).length > 0 && (
                <table className="residencetable employertable">
                  <thead><tr><th>Employer</th><th>From</th><th>Through</th><th /></tr></thead>
                  <tbody>
                    {byNewestFirst(v.employers).map((r, i) => {
                      // A row can be preceded by two breaks: the one since today, and the one
                      // between this job's start and the previous job's end.
                      const above = gaps.filter((g) => (i === 0 && g.now) || (!g.now && g.end === r.from))
                      const row = (
                        <tr key={`job-${i}`} className={above.length ? 'hasgap' : undefined}>
                          <td>{r.employer}</td><td>{shortDate(r.from)}</td><td>{shortDate(r.through)}</td>
                          <td className="actions">
                            <button type="button" className="linkbtn edit"
                              onClick={() => setEditingEmployer(v.employers.indexOf(r))}>Edit</button>
                            <button type="button" className="linkbtn"
                              onClick={() => setV({ ...v, employers: v.employers.filter((e) => e !== r) })}>Remove</button>
                          </td>
                        </tr>
                      )
                      const gaprows = above.map((gap) => (
                        <tr key={`gap-${gap.key}`} className={`gaprow${bad[`gap:${gap.key}`] ? ' bad' : ''}`}>
                          <td colSpan={4}>
                            <span className="gapwhen">
                              Please Explain The Gap Of {gap.days} Days
                              {gap.now
                                ? ` Since ${gap.after || 'Your Last Employer'} And Today`
                                : ` Between ${gap.after || 'One Employer'} And ${gap.before || 'The Next'}`}
                            </span>
                            <UpperArea rows={3} value={(v.gaps || {})[gap.key] || ''} aria-label="Reason for the gap"
                              onChange={(e) => {
                                setBad(({ [`gap:${gap.key}`]: _gone, ...rest }) => rest)
                                setV({ ...v, gaps: { ...(v.gaps || {}), [gap.key]: e.target.value } })
                              }} />
                            <FieldError message={bad[`gap:${gap.key}`]} />
                          </td>
                        </tr>
                      ))
                      return gaprows.length ? [row, ...gaprows] : row
                    })}
                  </tbody>
                </table>
              )}
              <button type="button" onClick={() => setAddingEmployer(true)}><Plus size={14} /> Add</button>
            </div>
            <hr className="formrule" />
            <div className="span-6 closingtext">
              <ServerText call={call} doctype="APPLICATION" />
            </div>
            <hr className="formrule" />
            <ApplicationSignature call={call} state={state} refresh={refresh} error={bad.signature} answers={v} />
          </div>

        </>
      )}

      {adding && (
        <ResidenceDialog
          onClose={() => setAdding(false)}
          onAdd={(residence) => { setV({ ...v, residences: [...(v.residences || []), residence] }); setAdding(false) }} />
      )}

      {addingEmployer && (
        <EmployerDialog
          onClose={() => setAddingEmployer(false)}
          onAdd={(employer) => { setV({ ...v, employers: [...(v.employers || []), employer] }); setAddingEmployer(false) }} />
      )}

      {scanning && (
        <LicenseScanner token={token} onClose={() => setScanning(false)}
          onRead={(found) => { setScanning(false); setScanned(found) }} />
      )}

      {scanned && (
        <ScanResult found={scanned}
          onClose={() => { setScanned(null); setScanning(true) }}
          onUse={() => { setAddingLicense(scanned); setScanned(null) }} />
      )}

      {addingLicense && (
        <LicenseDialog initial={typeof addingLicense === 'object' ? addingLicense : undefined}
          onClose={() => setAddingLicense(false)}
          onAdd={(license) => {
            setV({ ...v, licenses: [...(v.licenses || []), license] })
            clearBad('licenses')
            setAddingLicense(false)
          }} />
      )}

      {editingResidence !== null && (
        <ResidenceDialog initial={v.residences[editingResidence]}
          onClose={() => setEditingResidence(null)}
          onAdd={(row) => { replaceIn('residences', editingResidence, row); setEditingResidence(null) }} />
      )}

      {editingEmployer !== null && (
        <EmployerDialog initial={v.employers[editingEmployer]}
          onClose={() => setEditingEmployer(null)}
          onAdd={(row) => { replaceIn('employers', editingEmployer, row); setEditingEmployer(null) }} />
      )}

      {editingAccidents !== null && (
        <AccidentDialog initial={v.accidents[editingAccidents]}
          onClose={() => setEditingAccidents(null)}
          onAdd={(row) => { replaceIn('accidents', editingAccidents, row); setEditingAccidents(null) }} />
      )}

      {editingViolations !== null && (
        <ViolationDialog initial={v.violations[editingViolations]}
          onClose={() => setEditingViolations(null)}
          onAdd={(row) => { replaceIn('violations', editingViolations, row); setEditingViolations(null) }} />
      )}

      {editingLicense !== null && (
        <LicenseDialog initial={v.licenses[editingLicense]}
          onClose={() => setEditingLicense(null)}
          onAdd={(license) => {
            setV({ ...v, licenses: v.licenses.map((l, n) => (n === editingLicense ? license : l)) })
            clearBad('licenses')
            setEditingLicense(null)
          }} />
      )}

      {addingAccident && (
        <AccidentDialog
          onClose={() => setAddingAccident(false)}
          onAdd={(a) => { setV({ ...v, accidents: [...(v.accidents || []), a] }); setAddingAccident(false) }} />
      )}

      {addingViolation && (
        <ViolationDialog
          onClose={() => setAddingViolation(false)}
          onAdd={(t) => { setV({ ...v, violations: [...(v.violations || []), t] }); setAddingViolation(false) }} />
      )}

      {/* 49 CFR 40.25(j). One question, and the detail the rule asks for where the answer is yes.
          It is asked of the applicant because it is about jobs they applied for and did not get:
          no previous employer holds a record of a test for a job somebody never started. */}
      {step === 10 && (
        <>
          <p className="residenceask">
            During the previous two years, have you tested positive, or refused to test, on any
            pre-employment drug or alcohol test administered by an employer to which you applied
            for, but did not obtain, safety-sensitive transportation work covered by DOT drug and
            alcohol testing rules?
          </p>
          <YesNo name="priorviolation" ask="Your Answer *" value={v.priorviolation}
            error={bad.priorviolation}
            onChange={(e) => {
              const answer = e.target.value
              setBad(({ priorviolation: _a, ...rest }) => rest)
              setV({ ...v, priorviolation: answer,
                ...(answer === 'no'
                  ? { prioremployer: '', priortestdate: '', priortesttype: '', priorrtd: '' }
                  : {}) })
            }} />
          <SlideDown open={v.priorviolation === 'yes'} className="span-6">
            <div className="profileform">
              {f('prioremployer', 'Employer You Applied To *', 3,
                <UpperInput value={v.prioremployer || ''} onChange={set('prioremployer')} />)}
              {f('priortestdate', 'Approximate Test Date *', 3,
                <input type="date" value={v.priortestdate || ''} onChange={set('priortestdate')} />)}
              {f('priortesttype', 'What Kind *', 3, (
                <select value={v.priortesttype || ''} onChange={set('priortesttype')}>
                  <option value="">Choose</option>
                  <option value="drug">Drug</option>
                  <option value="alcohol">Alcohol</option>
                  <option value="refusal">Refusal to test</option>
                </select>
              ))}
              {/* 40.25(j) does not end at the admission: Part 40 Subpart O decides whether the
                  person may perform safety-sensitive work again, so the answer that matters next
                  is whether that process is finished. */}
              {f('priorrtd', 'Have You Completed The DOT Return-To-Duty Requirements? *', 3, (
                <select value={v.priorrtd || ''} onChange={set('priorrtd')}>
                  <option value="">Choose</option>
                  <option value="yes">Yes</option>
                  <option value="inprogress">In progress</option>
                  <option value="no">No</option>
                </select>
              ))}
            </div>
            <p className="residenceask">
              If you have documentation from a substance abuse professional, send it with your
              application or give it to the company directly.
            </p>
          </SlideDown>
        </>
      )}

      {step === 2 && (
        <>
          <p className="residenceask">Upload A Copy Of Your Current Driver's License</p>
          <FileField call={call} state={state} refresh={refresh} token={token} kind="license_front"
            label="Front Of License:" error={bad.license_front} onUploaded={() => clearBad('license_front')} />
          <FileField call={call} state={state} refresh={refresh} token={token} kind="license_back"
            label="Back Of License:" error={bad.license_back} onUploaded={() => clearBad('license_back')} />
          <hr className="formrule" />
          <div className={`residences licenses${bad.licenses ? ' bad' : ''}`}>
            <p className="residenceask">List ALL driver licenses held within the last 3 years</p>
            {(v.licenses || []).length > 0 && (
              <table className="residencetable licensetable">
                <thead><tr><th>License Number</th><th>State</th><th>Class</th><th>Issued</th><th>Expires</th>
                  <th>Endorsements</th><th /></tr></thead>
                <tbody>
                  {(v.licenses || []).map((l, i) => {
                    const row = (
                      <tr key={i}>
                        <td>{l.number}</td>
                        <td>{l.state}</td><td>{l.classification}</td>
                        <td>{fullDate(l.issued)}</td><td>{fullDate(l.expires)}</td>
                        <td>{(l.endorsements || []).join(', ') || '-'}</td>
                        <td className="actions">
                          <button type="button" className="linkbtn edit" onClick={() => setEditingLicense(i)}>Edit</button>
                          <button type="button" className="linkbtn"
                            onClick={() => {
                              setV({ ...v, licenses: v.licenses.filter((_, n) => n !== i) })
                              clearBad('licenses')
                            }}>Remove</button>
                        </td>
                      </tr>
                    )
                    return row
                  })}
                </tbody>
              </table>
            )}
            <div className="fielderrline">
              <button type="button" onClick={() => setAddingLicense(true)}><Plus size={14} /> Add</button>
              <button type="button" onClick={() => setScanning(true)}><ScanLine size={14} /> Scan My License</button>
              <FieldError message={bad.licenses} />
            </div>
          </div>

          {/* The medical card is asked of a commercial driver, and the licenses above say whether
              this is one - so it appears as soon as a commercial class is listed. */}
          <SlideDown open={cmvDriver(v)} className="span-6">
            <hr className="formrule" />
            <YesNo name="medexempt" ask="Are You Exempt From Possessing A Medical Certificate? *"
              value={v.medexempt} error={bad.medexempt} onChange={set('medexempt')} />
            <SlideDown open={cmvDriver(v) && v.medexempt === 'no'}>
              <div className="profileform">
                {f('medissued', 'Medical Card Issue Date *', 3,
                  <input type="date" value={v.medissued || ''} onChange={set('medissued')} />)}
                {f('medexpires', 'Medical Card Expire Date *', 3,
                  <input type="date" value={v.medexpires || ''} onChange={set('medexpires')} />)}
              </div>
              <FileField call={call} state={state} refresh={refresh} token={token} kind="medical_certificate"
                label="Upload A Copy Of Your Medical Card:" />
            </SlideDown>
          </SlideDown>

          <hr className="formrule" />
          <div className="residences">
            <p className="residenceask">List ALL accidents or crashes you have been involved in the last 3 years</p>
            {(v.accidents || []).length > 0 && (
              <table className="residencetable accidenttable">
                <thead><tr><th>Date</th><th>Location</th><th>Injuries</th><th>Fatalities</th>
                  <th>Hazmat</th><th>At Fault</th><th /></tr></thead>
                <tbody>
                  {(v.accidents || []).map((a, i) => (
                    <tr key={i}>
                      <td>{fullDate(a.date)}</td><td>{a.location}</td>
                      <td>{a.injuries || 0}</td><td>{a.fatalities || 0}</td>
                      <td>{a.hazmat ? 'Yes' : 'No'}</td><td>{a.atfault ? 'Yes' : 'No'}</td>
                      <td className="actions">
                        <button type="button" className="linkbtn edit" onClick={() => setEditingAccidents(i)}>Edit</button>
                        <button type="button" className="linkbtn"
                          onClick={() => setV({ ...v, accidents: v.accidents.filter((_, n) => n !== i) })}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button type="button" onClick={() => setAddingAccident(true)}><Plus size={14} /> Add</button>
          </div>
          <hr className="formrule" />
          <div className="residences">
            <p className="residenceask">List ALL moving traffic violations in the last 3 years</p>
            {(v.violations || []).length > 0 && (
              <table className="residencetable violationtable">
                <thead><tr><th>Date</th><th>Location</th><th>Violation</th><th /></tr></thead>
                <tbody>
                  {(v.violations || []).map((t, i) => (
                    <tr key={i}>
                      <td>{fullDate(t.date)}</td><td>{t.location}</td><td>{t.violation}</td>
                      <td className="actions">
                        <button type="button" className="linkbtn edit" onClick={() => setEditingViolations(i)}>Edit</button>
                        <button type="button" className="linkbtn"
                          onClick={() => setV({ ...v, violations: v.violations.filter((_, n) => n !== i) })}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button type="button" onClick={() => setAddingViolation(true)}><Plus size={14} /> Add</button>
          </div>
          <hr className="formrule" />
          <div className="profileform">
            <YesNo name="licenseaction" ask="Has Your License Ever Been Revoked Or Have You Ever Been Denied A License In The Last 3 Years? *"
              value={v.licenseaction} error={bad.licenseaction}
              onChange={(e) => {
                const answer = e.target.value
                setBad(({ licenseaction: _a, licenseactionwhy: _b, ...rest }) => rest)
                setV({ ...v, licenseaction: answer, ...(answer === 'no' ? { licenseactionwhy: '' } : {}) })
              }} />
            <SlideDown open={v.licenseaction === 'yes'} className="span-6">
              <div className="profileform">
                {f('licenseactionwhy', 'Please Explain *', 6,
                  <UpperArea value={v.licenseactionwhy || ''} onChange={set('licenseactionwhy')} />)}
              </div>
              <FileField call={call} state={state} refresh={refresh} token={token} kind="license_action"
                label="Upload Any Documentation Regarding The Forfeiture:" />
            </SlideDown>
          </div>
        </>
      )}


    </>
  )
}

// Employment is listed newest first, and any break of more than a month between one job ending and
// the next beginning has to be explained - including the break between the latest job and today.
const GAP_DAYS = 30
const days = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000)

function byNewestFirst(employers) {
  return [...(employers || [])].sort((a, b) => String(b.from || '').localeCompare(String(a.from || '')))
}

function employmentGaps(employers) {
  const listed = byNewestFirst(employers).filter((e) => e.from && e.through)
  if (!listed.length) return []
  const today = new Date().toISOString().slice(0, 10)
  const gaps = []
  // `after` is the employer the gap follows, `before` the one it runs up to - so the question can
  // name them rather than leave the applicant counting dates.
  if (days(listed[0].through, today) > GAP_DAYS) {
    gaps.push({ start: listed[0].through, end: today, now: true, after: listed[0].employer })
  }
  listed.forEach((job, i) => {
    const older = listed[i + 1]
    if (older && days(older.through, job.from) > GAP_DAYS) {
      gaps.push({ start: older.through, end: job.from, after: older.employer, before: job.employer })
    }
  })
  return gaps.map((g) => ({ ...g, key: `${g.start}_${g.end}`, days: days(g.start, g.end) }))
}

// 03/2024 - dates in these tables only ever need the month and year.
const fullDate = (v) => (v ? `${String(v).slice(5, 7)}/${String(v).slice(8, 10)}/${String(v).slice(0, 4)}` : '')
const shortDate = (v) => (v ? `${String(v).slice(5, 7)}/${String(v).slice(0, 4)}` : '')
// 23 September 2026 - the date written out, as it is beside a signature.
const shortFullDate = (v) => (v ? new Date(String(v).replace(' ', 'T') + 'Z').toLocaleDateString('en-US',
  { year: 'numeric', month: 'long', day: 'numeric' }) : '')

// Opens and closes by animating its row from no height to its own, so the height never has to be
// guessed and the content inside stays laid out normally.
// Every dialog opens with the cursor already in its first field.


// Once the driver has proved who they are, their signature is theirs for the rest of the visit: the
// next document is signed by the button alone, with no second challenge. It lives in memory only, so
// closing the tab asks again.
const Signing = createContext({ unlocked: false, unlock: () => {} })

// A handful of paper pieces in the brand colours, falling once. Nothing moves for anyone who has
// asked their machine to keep still - the stylesheet handles that.
function Confetti() {
  const pieces = useMemo(() => Array.from({ length: 36 }, (_, i) => ({
    left: (i * 2.7 + (i % 5) * 3) % 100,
    delay: ((i % 9) * 0.18).toFixed(2),
    spin: i % 2 ? 1 : -1,
    tint: ['a', 'b', 'c', 'd'][i % 4],
  })), [])
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p, i) => (
        <span key={i} className={`bit tint-${p.tint}`}
          style={{ left: `${p.left}%`, animationDelay: `${p.delay}s`, '--spin': p.spin }} />
      ))}
    </div>
  )
}

const titleCase = (v) => String(v || '').toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase())

function SlideDown({ open, className = '', children }) {
  return (
    <div className={`slidedown ${className}${open ? ' open' : ''}`} aria-hidden={!open}>
      <div className="slideclip"><div className="slideinner">{children}</div></div>
    </div>
  )
}

function YesNo({ name, ask, value, onChange, error, disabled }) {
  return (
    <div className={`field span-6 radiofield${error ? ' bad' : ''}${disabled ? ' off' : ''}`}>
      <span className="radioask">{ask}</span>
      <div className="radios">
        {[['yes', 'Yes'], ['no', 'No']].map(([option, label]) => (
          <label key={option}>
            <input type="radio" name={name} value={option} checked={value === option}
              onChange={onChange} disabled={disabled} /> {label}
          </label>
        ))}
      </div>
      <FieldError message={error} />
    </div>
  )
}

function ResidenceDialog({ onAdd, onClose, initial }) {
  const [r, setR] = useState({ ...{ address1: '', city: '', state: '', zip: '' }, ...(initial || {}) })
  const [bad, setBad] = useState({})
  const box = useFirstField()
  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setR({ ...r, [k]: e.target.value })
  }
  const field = (k, label, span, node) => (
    <label className={`field span-${span}${bad[k] ? ' bad' : ''}`}>{label}{node}<FieldError message={bad[k]} /></label>
  )
  const save = (e) => {
    e.preventDefault()
    const problems = {}
    if (!r.address1.trim()) problems.address1 = 'The address is required'
    if (!r.city.trim()) problems.city = 'The city is required'
    if (!r.state) problems.state = 'The state is required'
    if (!r.zip.trim()) problems.zip = 'The ZIP code is required'
    setBad(problems)
    if (!Object.keys(problems).length) onAdd(r)
  }
  return (
    <div className="backdrop">
      <form ref={box} className="modal" role="dialog" aria-modal="true" aria-label="Add a residence" onSubmit={save}>
        <header><h2>Previous Residence</h2><button type="button" className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
        <div className="body">
          <div className="profileform">
            {field('address1', 'Address *', 6, <UpperInput value={r.address1} onChange={set('address1')} />)}
            {field('city', 'City *', 3, <UpperInput value={r.city} onChange={set('city')} />)}
            {field('state', 'State *', 1, <StateSelect value={r.state} onChange={set('state')} />)}
            {field('zip', 'ZIP Code *', 2, <ZipInput value={r.zip} onChange={set('zip')} />)}
          </div>
        </div>
        <footer><button type="button" onClick={onClose}>Cancel</button><button className="primary">{initial ? 'Save' : 'Add'}</button></footer>
      </form>
    </div>
  )
}

// The signature that closes the application: what was signed, when, and the way to sign it. Date of
// birth and SSN are asked again at the moment of signing; a driver who already has a signature signs
// with that one, and a driver who has none has it created here.
// The name a new signature is offered as: first, middle initial, last - from what is on screen if
// this is the step that holds it, otherwise from what has been saved.
const signerName = (state, answers) => {
  const one = { ...((state.data || {}).steps || {})['1'], ...(answers || {}) }
  const parts = [one.firstname || state.firstname, (one.middleinitial || '').trim(), one.lastname || state.lastname]
  return properName(...parts.filter(Boolean))
}

function ApplicationSignature({ call, state, refresh, error, doctype = 'APPLICATION', answers,
                               doctypes, label = 'Sign Application', signaturelabel = 'Signature' }) {
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const { unlocked, unlock } = useContext(Signing)
  const signature = state.signature
  const signed = state.signed?.[doctype]
  const list = doctypes || ['APPLICATION']

  // With the signature already retrieved this visit, the button is the whole of the signing.
  const signNow = async () => {
    setBusy(true); setErr(null)
    try {
      for (const d of list) await call.post('/driverapply/session/sign', { doctype: d })
      await refresh()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="span-6 signblock">
      <div className="signfields">
        <div className="signbox">
          <span className="signlabel">{signaturelabel}</span>
          <div className="signline">
            {signed && signature ? <span className={`sigink font-${signature.fontkey}`}>{signature.typedname}</span> : null}
            <SignatureStamp signed={signed} />
          </div>
        </div>
        <div className="signbox datebox">
          <span className="signlabel">Date</span>
          <div className="signline">{signed ? shortFullDate(signed.signedon) : null}</div>
        </div>
      </div>
      {!signed && (
        <div className={`field signaction${error ? ' bad' : ''}`}>
          <button type="button" className="primary" disabled={busy}
            onClick={() => (unlocked && signature ? signNow() : setAsking(true))}>
            {busy ? 'Signing…' : label}
          </button>
          <FieldError message={error} />
          {err && <div className="error">{err}</div>}
        </div>
      )}
      {asking && (
        <SignDialog call={call} refresh={refresh} signature={signature} title={label} onSigned={unlock}
          doctypes={list} name={signerName(state, answers)} onClose={() => setAsking(false)} />
      )}
    </div>
  )
}

function SignDialog({ call, refresh, onClose, signature, name, doctypes, onSigned, title = 'Sign Application' }) {
  // Two stages: prove who you are, then sign. The signature on file is not shown - and cannot be
  // used - until the date of birth and SSN have been checked against this driver by the server.
  const [v, setV] = useState({ dob: '', ssn: '', typedname: name || '', fontkey: DEFAULT_FONT })
  const [bad, setBad] = useState({})
  const box = useFirstField()
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [onfile, setOnfile] = useState(null)     // the base signature the lookup found, if any
  const [design, setDesign] = useState(false)    // designing one, because there is none or they asked
  const ready = !!onfile || design
  const set = (k) => (e) => { setBad(({ [k]: _gone, ...rest }) => rest); setV({ ...v, [k]: e.target.value }) }

  const lookup = async () => {
    const problems = {}
    if (!v.dob) problems.dob = 'The birth date is required'
    if (v.ssn.replace(/\D/g, '').length !== 9) problems.ssn = 'Enter all nine digits'
    setBad(problems)
    if (Object.keys(problems).length) return
    setBusy(true); setErr(null)
    try {
      const r = await call.post('/driverapply/session/verify', { dob: v.dob, ssn: v.ssn })
      if (r.signature) { setOnfile(r.signature); setDesign(false) }
      else { setOnfile(null); setDesign(true) }
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const sign = async () => {
    if (design && !v.typedname.trim()) { setBad({ typedname: 'Type the name you want to sign with' }); return }
    setBusy(true); setErr(null)
    try {
      // Designing one adopts it (and revokes any it replaces); otherwise the one on file is used.
      await call.post('/driverapply/session/signature',
        design ? v : { dob: v.dob, ssn: v.ssn, typedname: '', fontkey: onfile.fontkey })
      for (const doctype of doctypes) await call.post('/driverapply/session/sign', { doctype })
      await refresh()
      if (onSigned) onSigned()
      onClose()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const submit = (e) => { e.preventDefault(); if (ready) sign(); else lookup() }

  return (
    <div className="backdrop">
      <form ref={box} className="modal" role="dialog" aria-modal="true" aria-label={title} onSubmit={submit}>
        <header><h2>{title}</h2><button type="button" className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
        <div className="body">
          <div className="profileform">
            <label className={`field span-3${bad.dob ? ' bad' : ''}`}>Date Of Birth *
              <input type="date" value={v.dob} onChange={set('dob')} disabled={ready} /><FieldError message={bad.dob} />
            </label>
            <label className={`field span-3${bad.ssn ? ' bad' : ''}`}>Social Security Number *
              <SsnInput value={v.ssn} onChange={set('ssn')} disabled={ready} /><FieldError message={bad.ssn} />
            </label>
            {design && (
              <>
                <label className={`field span-4${bad.typedname ? ' bad' : ''}`}>Sign As *
                  <input value={v.typedname} onChange={set('typedname')} /><FieldError message={bad.typedname} />
                </label>
                <label className="field span-2">Style
                  <select value={v.fontkey} onChange={set('fontkey')}>
                    {FONTS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                  </select>
                </label>
              </>
            )}
          </div>

          {ready && (
            <>
              <div className="sigpreview">
                <span className={`sigink font-${design ? v.fontkey : onfile.fontkey}`}>
                  {(design ? v.typedname : onfile.typedname) || 'Your name'}
                </span>
              </div>
              <p className="small muted sighint">
                {design
                  ? 'This becomes your signature on file. It signs every document in this application '
                    + 'and cannot be changed afterwards, so check it before you sign.'
                  : 'Your signature on file. Every document in this application is signed with it.'}
              </p>
            </>
          )}
          {err && <div className="error">{err}</div>}
        </div>
        <footer>
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy}>
            {busy ? (ready ? 'Signing…' : 'Looking…') : ready ? 'Sign Document' : 'Lookup Signature'}
          </button>
        </footer>
      </form>
    </div>
  )
}
function SignatureStamp({ signed }) {
  if (!signed) return null
  const utc = String(signed.signedon).replace('T', ' ').slice(0, 19)
  return (
    <span className="sigstamp">
      <span>{signed.recordid}</span>
      <span>{utc.slice(0, 10)} · {utc.slice(11)} UTC</span>
      <span>IP {signed.ip || 'not recorded'}</span>
    </span>
  )
}

// A document's text, read from the server so the wording shown is the wording of record.
function ServerText({ call, doctype }) {
  const [doc, setDoc] = useState(null)
  useEffect(() => { call.get(`/driverapply/session/document/${doctype}`).then(setDoc).catch(() => setDoc(null)) },
    [doctype]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!doc) return null
  if (doc.format === 'html') return <div className="legaldoc" dangerouslySetInnerHTML={{ __html: doc.text }} />
  return <DocText text={doc.text} />
}



function AccidentDialog({ onAdd, onClose, initial }) {
  const [r, setR] = useState({ ...{ date: '', location: '', injuries: '', fatalities: '', hazmat: false, atfault: false }, ...(initial || {}) })
  const [bad, setBad] = useState({})
  const box = useFirstField()
  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setR({ ...r, [k]: e.target.value })
  }
  const check = (k) => () => setR({ ...r, [k]: !r[k] })
  const field = (k, label, span, node) => (
    <label className={`field span-${span}${bad[k] ? ' bad' : ''}`}>{label}{node}<FieldError message={bad[k]} /></label>
  )
  const save = (e) => {
    e.preventDefault()
    const problems = {}
    if (!r.date) problems.date = 'The date is required'
    if (!r.location.trim()) problems.location = 'The location is required'
    setBad(problems)
    if (!Object.keys(problems).length) onAdd(r)
  }
  return (
    <div className="backdrop">
      <form ref={box} className="modal" role="dialog" aria-modal="true" aria-label="Add an accident" onSubmit={save}>
        <header><h2>{initial ? 'Correct This Accident Or Crash' : 'Accident Or Crash'}</h2><button type="button" className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
        <div className="body">
          <div className="profileform">
            {field('date', 'Date *', 2, <input type="date" value={r.date} onChange={set('date')} />)}
            {field('location', 'Location *', 4, <UpperInput value={r.location} onChange={set('location')} />)}
            {field('injuries', 'Number Of Injuries', 3, <input type="number" min="0" value={r.injuries} onChange={set('injuries')} />)}
            {field('fatalities', 'Number Of Fatalities', 3, <input type="number" min="0" value={r.fatalities} onChange={set('fatalities')} />)}
            <div className="span-6 checkfield">
              <label><input type="checkbox" checked={r.hazmat} onChange={check('hazmat')} /> Hazardous Materials Were Spilled</label>
              <label><input type="checkbox" checked={r.atfault} onChange={check('atfault')} /> I Was At Fault</label>
            </div>
          </div>
        </div>
        <footer><button type="button" onClick={onClose}>Cancel</button><button className="primary">{initial ? 'Save' : 'Add'}</button></footer>
      </form>
    </div>
  )
}

function ViolationDialog({ onAdd, onClose, initial }) {
  const [r, setR] = useState({ ...{ date: '', location: '', violation: '' }, ...(initial || {}) })
  const [bad, setBad] = useState({})
  const box = useFirstField()
  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setR({ ...r, [k]: e.target.value })
  }
  const field = (k, label, span, node) => (
    <label className={`field span-${span}${bad[k] ? ' bad' : ''}`}>{label}{node}<FieldError message={bad[k]} /></label>
  )
  const save = (e) => {
    e.preventDefault()
    const problems = Object.fromEntries([['date', 'The date is required'], ['location', 'The location is required'],
                                         ['violation', 'The violation is required']]
      .filter(([k]) => !String(r[k] ?? '').trim()).map(([k, m]) => [k, m]))
    setBad(problems)
    if (!Object.keys(problems).length) onAdd(r)
  }
  return (
    <div className="backdrop">
      <form ref={box} className="modal" role="dialog" aria-modal="true" aria-label="Add a violation" onSubmit={save}>
        <header><h2>{initial ? 'Correct This Moving Traffic Violation' : 'Moving Traffic Violation'}</h2><button type="button" className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
        <div className="body">
          <div className="profileform">
            {field('date', 'Date *', 2, <input type="date" value={r.date} onChange={set('date')} />)}
            {field('location', 'Location *', 4, <UpperInput value={r.location} onChange={set('location')} />)}
            {field('violation', 'Violation *', 6, <UpperInput value={r.violation} onChange={set('violation')} />)}
          </div>
        </div>
        <footer><button type="button" onClick={onClose}>Cancel</button><button className="primary">{initial ? 'Save' : 'Add'}</button></footer>
      </form>
    </div>
  )
}

function EmployerDialog({ onAdd, onClose, initial }) {
  const [r, setR] = useState({ employer: '', supervisor: '', address1: '', city: '', state: '', zip: '',
                               phone: '', email: '', from: '', through: '', dotregulated: 'no', safetysensitive: 'no',
                               ...(initial || {}) })
  const [bad, setBad] = useState({})
  const box = useFirstField()
  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setR({ ...r, [k]: e.target.value })
  }
  const field = (k, label, span, node) => (
    <label className={`field span-${span}${bad[k] ? ' bad' : ''}`}>{label}{node}<FieldError message={bad[k]} /></label>
  )
  const save = (e) => {
    e.preventDefault()
    const required = [['employer', 'The employer name is required'], ['supervisor', 'The supervisor name is required'],
                      ['address1', 'The address is required'], ['city', 'The city is required'],
                      ['state', 'The state is required'], ['zip', 'The ZIP code is required'],
                      ['phone', 'The telephone is required'], ['email', 'The email address is required'],
                      ['from', 'The from date is required'], ['through', 'The through date is required']]
    const problems = Object.fromEntries(required.filter(([k]) => !String(r[k] ?? '').trim()).map(([k, m]) => [k, m]))
    if (!problems.through && r.from && r.through < r.from) problems.through = 'Through comes after from'
    setBad(problems)
    if (!Object.keys(problems).length) onAdd(r)
  }
  return (
    <div className="backdrop">
      <form ref={box} className="modal wide" role="dialog" aria-modal="true" aria-label="Add an employer" onSubmit={save}>
        <header><h2>{initial ? 'Correct This Previous Employer' : 'Previous Employer'}</h2><button type="button" className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
        <div className="body">
          <div className="profileform">
            {field('employer', 'Employer Name *', 3, <UpperInput value={r.employer} onChange={set('employer')} />)}
            {field('supervisor', 'Supervisor Name *', 3, <UpperInput value={r.supervisor} onChange={set('supervisor')} />)}
            {field('address1', 'Address *', 6, <UpperInput value={r.address1} onChange={set('address1')} />)}
            {field('city', 'City *', 3, <UpperInput value={r.city} onChange={set('city')} />)}
            {field('state', 'State *', 1, <StateSelect value={r.state} onChange={set('state')} />)}
            {field('zip', 'ZIP Code *', 2, <ZipInput value={r.zip} onChange={set('zip')} />)}
            {field('phone', 'Telephone *', 3, <PhoneInput value={r.phone} onChange={set('phone')} />)}
            {field('email', 'Email Address *', 3, <EmailInput value={r.email} onChange={set('email')} />)}
            {field('from', 'From *', 3, <input type="date" value={r.from} onChange={set('from')} />)}
            {field('through', 'Through *', 3, <input type="date" value={r.through} onChange={set('through')} />)}
            <hr className="formrule" />
            <YesNo name="dotregulated" value={r.dotregulated} onChange={set('dotregulated')}
              ask="Were You Subject To The DOT/FMCSA Regulations While Employed By This Carrier? If You Were A Driver, Select 'Yes'." />
            <YesNo name="safetysensitive" value={r.safetysensitive} onChange={set('safetysensitive')}
              ask="Was Your Job Designated As A Safety Sensitive Function, In Any DOT Regulated Mode, Subject To The Alcohol And Controlled Substances Testing Requirements Required By 49 CFR Part 40? If You Were A Driver, Select 'Yes'." />
          </div>
        </div>
        <footer><button type="button" onClick={onClose}>Cancel</button><button className="primary">{initial ? 'Save' : 'Add'}</button></footer>
      </form>
    </div>
  )
}



const ACCEPTS = 'image/*,application/pdf'

function FileField({ call, state, refresh, kind, label, token, error, onUploaded }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [preview, setPreview] = useState(null)      // { url, pdf } while the dialog is open
  const input = useRef(null)
  const have = state.uploads?.[kind]

  const pick = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setErr(null)
    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      setErr('Upload a photo or a PDF')
      return
    }
    setBusy(true)
    const form = new FormData()
    form.append('kind', kind)
    form.append('file', file)
    try {
      await call.upload('/driverapply/session/upload', form)
      await refresh()
      if (onUploaded) onUploaded()
    } catch (e2) { setErr(e2.message) } finally { setBusy(false) }
  }

  // The session is a bearer token rather than a cookie, so the file is fetched and shown from memory.
  // Fetched once per file: looking at it twice should not send it twice.
  const cached = useRef({ id: null, url: null, pdf: false })
  const view = async () => {
    if (cached.current.id === have?.documentid && cached.current.url) {
      setPreview({ url: cached.current.url, pdf: cached.current.pdf, kept: true })
      return
    }
    setBusy(true)
    const r = await fetch(`/api/driverapply/session/upload/${kind}`, { headers: { Authorization: `Bearer ${token}` } })
      .finally(() => setBusy(false))
    if (!r.ok) {
      const body = await r.json().catch(() => null)
      setErr(body?.detail || 'That file could not be opened')
      return
    }
    const blob = await r.blob()
    if (cached.current.url) URL.revokeObjectURL(cached.current.url)
    cached.current = { id: have?.documentid, url: URL.createObjectURL(blob),
                       pdf: blob.type === 'application/pdf' }
    setPreview({ ...cached.current, kept: true })
  }

  const close = () => setPreview(null)

  return (
    <div className={`filefield${error ? ' bad' : ''}`}>
      <span className="filelabel">{label}</span>
      <input ref={input} type="file" accept={ACCEPTS} onChange={pick} hidden />
      <div className="filebuttons">
        <button type="button" onClick={() => input.current?.click()} disabled={busy}>
          <Upload size={14} /> {busy ? 'Uploading…' : 'Upload'}
        </button>
        <button type="button" onClick={view} disabled={!have}><Eye size={14} /> View</button>
      </div>
      {have && <span className="filestate"><Check size={14} /> {have.filename}</span>}
      {err && <span className="filestate fileerr">{err}</span>}
      {error && <span className="filestate fileerr"><AlertCircle size={13} /> {error}</span>}

      {preview && (
        <div className="backdrop">
          <div className="modal filepreview" role="dialog" aria-modal="true" aria-label={have?.filename || 'File'}>
            <header><h2>{have?.filename}</h2><button className="iconbtn" onClick={close} aria-label="Close"><X size={18} /></button></header>
            <div className="body">
              {preview.pdf
                ? <iframe title={have?.filename || 'Document'} src={preview.url} />
                : <img src={preview.url} alt={have?.filename || 'Uploaded document'} />}
            </div>
            <footer><button onClick={close}>Close</button></footer>
          </div>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------------------------------------
// Steps 4-10 - read and sign
// ------------------------------------------------------------------------------------------------

const CITIZENSHIP = [
  ['citizen', 'A citizen of the United States'],
  ['national', 'A noncitizen national of the United States'],
  ['permanent', 'A lawful permanent resident'],
  ['authorized', 'A noncitizen authorized to work in the United States'],
]

// Form I-9. The official blank is filled on the server from this application, so what is shown is
// the form itself; these fields are the few things only the I-9 asks for.
function I9Step({ call, state, refresh, token, values, setValues, bad }) {
  const [file, setFile] = useState(null)
  const [err, setErr] = useState(null)
  const signed = state.signed?.I9
  const set = (k) => (e) => setValues({ ...values, [k]: e.target.value })

  // 8 CFR 274a.2(h)(1)(iii): a printed confirmation of what was signed, whenever they ask for it.
  const download = async () => {
    const r = await fetch('/api/driverapply/session/i9', { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) { setErr('That form could not be opened'); return }
    const url = URL.createObjectURL(await r.blob())
    const a = document.createElement('a')
    a.href = url; a.download = 'form-i-9.pdf'; a.click()
    URL.revokeObjectURL(url)
  }
  const answers = JSON.stringify(values)

  // Save what has been typed, then fetch the form filled with it. A short pause first, so the
  // form is not rebuilt on every keystroke.
  useEffect(() => {
    let url = null, dead = false
    const timer = setTimeout(async () => {
      try {
        await call.put('/driverapply/session/i9', { answers: JSON.parse(answers) })
        const r = await fetch('/api/driverapply/session/i9', { headers: { Authorization: `Bearer ${token}` } })
        if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || 'The form could not be built')
        const blob = await r.blob()
        if (dead) return
        url = URL.createObjectURL(blob)
        setFile(url)
      } catch (e) { if (!dead) setErr(e.message) }
    }, 600)
    return () => { dead = true; clearTimeout(timer); if (url) URL.revokeObjectURL(url) }
  }, [answers, token, signed]) // eslint-disable-line react-hooks/exhaustive-deps

  const f = (k, label, span, node) => (
    <label className={`field span-${span}${bad[k] ? ' bad' : ''}`}>{label}{node}<FieldError message={bad[k]} /></label>
  )
  return (
    <div className="policystep">
      <div className="profileform">
        {f('othernames', 'Other Last Names Used', 6,
          <UpperInput value={values.othernames || ''} onChange={set('othernames')} />)}
        <div className={`field span-6 radiofield column${bad.citizenship ? ' bad' : ''}`}>
          <span className="radioask">I Attest, Under Penalty Of Perjury, That I Am *</span>
          <div className="radios column">
            {CITIZENSHIP.map(([key, label]) => (
              <label key={key}>
                <input type="radio" name="citizenship" value={key} checked={values.citizenship === key}
                  onChange={set('citizenship')} /> {label}
              </label>
            ))}
          </div>
          <FieldError message={bad.citizenship} />
        </div>
        <SlideDown open={values.citizenship === 'permanent'} className="span-6">
          <div className="profileform">
            {f('anumber', 'USCIS Or A-Number *', 3,
              <UpperInput value={values.anumber || ''} onChange={set('anumber')} />)}
          </div>
        </SlideDown>
        <SlideDown open={values.citizenship === 'authorized'} className="span-6">
          <div className="profileform">
            {f('workuntil', 'Authorized To Work Until *', 3,
              <input type="date" value={values.workuntil || ''} onChange={set('workuntil')} />)}
            {f('anumber', 'USCIS Or A-Number', 3, <UpperInput value={values.anumber || ''} onChange={set('anumber')} />)}
            {f('i94', 'Form I-94 Admission Number', 3, <UpperInput value={values.i94 || ''} onChange={set('i94')} />)}
            {f('passport', 'Foreign Passport Number And Country', 3,
              <UpperInput value={values.passport || ''} onChange={set('passport')} />)}
            {bad.workproof && <div className="span-6 fielderrline"><FieldError message={bad.workproof} /></div>}
          </div>
        </SlideDown>
      </div>
      <hr className="formrule" />
      <div className="policyview">
        {file
          ? <iframe title="Form I-9" src={`${file}#toolbar=0&navpanes=0&statusbar=0&view=FitH`} />
          : !err && <div className="muted">Building your form…</div>}
      </div>
      {err && <div className="error">{err}</div>}
      <div className="profileform signfoot">
        <hr className="formrule" />
        {!signed && (
          <label className="span-6 check attest">
            <input type="checkbox" checked={!!values.acknowledged}
              onChange={() => setValues({ ...values, acknowledged: !values.acknowledged })} />
            I have read the attestation above and I am signing Section 1 of Form I-9.
          </label>
        )}
        {(values.acknowledged || signed) && (
          <ApplicationSignature call={call} state={state} refresh={refresh} signaturelabel="Signature Of Driver"
            doctype="I9" doctypes={['I9']} label="Sign This Document" />
        )}
        {signed && (
          <div className="span-6 downloadrow">
            <button type="button" onClick={download}><Download size={14} /> Download Your Signed Form</button>
          </div>
        )}
      </div>
    </div>
  )
}

function DocumentStep({ call, doctype, state, refresh, token }) {
  const [doc, setDoc] = useState(null)
  const [file, setFile] = useState(null)        // { url, pdf } for a policy the company filed
  const [err, setErr] = useState(null)

  useEffect(() => {
    setDoc(null); setFile(null); setErr(null)
    call.get(`/driverapply/session/document/${doctype}`).then(setDoc).catch((e) => setErr(e.message))
  }, [doctype]) // eslint-disable-line react-hooks/exhaustive-deps

  // A company policy is a file, so it is fetched with the session token and shown from memory.
  useEffect(() => {
    // Guard on the doctype too: moving between steps changes it before the new document arrives.
    if (doc?.source !== 'company' || doc.doctype !== doctype) return undefined
    let url = null
    fetch(`/api/driverapply/session/policy/${doctype}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || 'That policy could not be opened')
        const blob = await r.blob()
        url = URL.createObjectURL(blob)
        setFile({ url, pdf: blob.type === 'application/pdf' })
      })
      .catch((e) => setErr(e.message))
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [doc, doctype, token])

  if (!doc) return <div className="muted">Loading…</div>
  // Whatever is being signed - the company's own policy or the wording we ship - fills the card,
  // with the signature at its foot, just above the rule over the buttons.
  return (
    <div className="policystep">
      {doc.source === 'company' ? (
        <div className="policyview">
          {file
            // #toolbar=0 keeps the viewer's own bar out of it: the page shows the document, nothing else.
            ? file.pdf
              ? <iframe title={doc.title} src={`${file.url}#toolbar=0&navpanes=0&statusbar=0&view=FitH`} />
              : <img src={file.url} alt={doc.filename || doc.title} />
            : !err && <div className="muted">Loading…</div>}
        </div>
      ) : doc.format === 'html' ? (
        // Our own copy of a published document, served from our own origin and never user content.
        <div className="doctext legaldoc" dangerouslySetInnerHTML={{ __html: doc.text }} />
      ) : (
        <div className="doctext"><DocText text={doc.text} /></div>
      )}
      {doc.source === 'company' && (
        <p className="acknowledge">
          {acknowledgement(doctype, POLICY_NAMES[doctype] || doc.title, doc.accountname)}
        </p>
      )}
      {err && <div className="error">{err}</div>}
      <div className="profileform signfoot">
        <hr className="formrule" />
        <ApplicationSignature call={call} state={state} refresh={refresh} signaturelabel="Signature Of Driver"
          doctype={doctype} doctypes={[doctype]} label="Sign This Document" />
      </div>
    </div>
  )
}

// The documents are written as Markdown; only headings, bullets and bold appear in them.
function DocText({ text }) {
  const bold = (line) => line.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <b key={i}>{part}</b> : part))
  const blocks = []
  for (const raw of text.split('\n\n')) {
    const block = raw.trim()
    if (!block) continue
    if (block.startsWith('#')) blocks.push(<h2 key={blocks.length}>{block.replace(/^#+\s*/, '')}</h2>)
    else if (block.startsWith('- ')) {
      blocks.push(
        <ul key={blocks.length}>
          {block.split(/\n(?=- )/).map((item, i) => <li key={i}>{bold(item.replace(/^- /, '').replace(/\n\s*/g, ' '))}</li>)}
        </ul>)
    } else blocks.push(<p key={blocks.length}>{bold(block.replace(/\n\s*/g, ' '))}</p>)
  }
  return <>{blocks}</>
}

