import { useState } from 'react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { EinInput, EmailInput, PhoneInput, ZipInput } from '../components/MaskedInput.jsx'
import { US_STATES } from '../admin/CustomerProfile.jsx'
import { useForm } from '../admin/common.jsx'
import { useLocation, useNavigate } from 'react-router-dom'
import { useUser } from '../App.jsx'
import Qualifications from './Qualifications.jsx'
import CompanyRequirements from './CompanyRequirements.jsx'
import MerchantConnect from './MerchantConnect.jsx'
import BackgroundChecks from './BackgroundChecks.jsx'
import Billing from './Billing.jsx'
import OperatingProfile from './OperatingProfile.jsx'

const FIELDS = ['name', 'address1', 'address2', 'city', 'county', 'state', 'zip', 'phone', 'fax',
  'email', 'supportemail', 'billingemail', 'ein', 'usdot', 'mcnumber', 'medicaidid', 'npi',
  'dba']

// Three answers, not two. Until a question is answered, every rule that needs it reports itself as
// undecidable rather than guessing - so an unanswered question costs a visible gap on the driver's
// requirements, which is the right price. Defaulting these to "no" would quietly switch off whole
// bodies of law.
//
// Wheelchair work is deliberately not asked: the fleet already records which vehicles have a lift,
// and asking the office to restate a fact the system holds is how two answers to one question drift
// apart.
const CHOICES = [['', 'Not answered'], ['yes', 'Yes'], ['no', 'No']]

const asChoice = (answer) => (answer === null || answer === undefined ? '' : (answer ? 'yes' : 'no'))

// Three screens about one subject, so one page with three tabs rather than three entries in a
// sidebar. What the company IS, what it asks of its drivers, and what is asked of it.
// Billing is listed only where the person can see it. A tab that opens on "you may not look at
// this" is worse than no tab.
const tabsFor = (role) => [
  ['profile', 'Company'],
  ['operations', 'Operations'],
  ['operating-profile', 'Operating Profile'],
  ['qualifications', 'Driver Qualifications'],
  ['requirements', 'Company Requirements'],
  // Merchant Connect holds the company's own merchant keys, so it is shown to the same
  // people Billing is - and for the same reason. A tab that opens on "you may not look at
  // this" is worse than no tab.
  // Background Checks sits with these for the same reason: it holds the key to an account that
  // can spend the company's money, and shows that account's invoices.
  ...(['owner', 'admin'].includes(role)
    ? [['screening', 'Background Checks'], ['merchant', 'Merchant Connect'],
       ['billing', 'Billing']] : []),
]

export default function Company({ tab = 'profile' }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const TABS = tabsFor(useUser()?.role)
  // The tab is in the address, so a link to one lands on it and the back button works - including
  // the paths these screens had of their own before they became tabs.
  const here = pathname.replace(/^\/company\//, '').replace(/^\//, '')
  const on = TABS.some(([k]) => k === here) ? here : tab
  return (
    <div className="stack companypage">
      {/* The tabs pin to the top; each tab prints its own heading underneath, the way every other
          page in this application does. */}
      <header className="companyhead">
        <nav className="tabs companytabs" aria-label="Company settings">
          {TABS.map(([key, label]) => (
            <button key={key} type="button" className={on === key ? 'on' : undefined}
              onClick={() => navigate(key === 'profile' ? '/company' : `/company/${key}`)}>
              {label}
            </button>
          ))}
        </nav>
      </header>
      {on === 'profile' && <CompanyProfile />}
      {on === 'operations' && <Operations />}
      {on === 'operating-profile' && <OperatingProfile />}
      {on === 'qualifications' && <Qualifications />}
      {on === 'requirements' && <CompanyRequirements />}
      {on === 'screening' && <BackgroundChecks />}
      {on === 'merchant' && <MerchantConnect />}
      {on === 'billing' && <Billing />}
    </div>
  )
}

// What decides which rules reach this company's drivers. Each answer switches a body of law on or
// off, so the help under it says which, and an unanswered one is counted in the heading rather than
// left to be noticed. Its own tab because it is its own subject: the page beside it is an address
// and a telephone number, and this is the thing the whole engine turns on.
function Operations() {
  const canEdit = ['owner', 'admin'].includes(useUser()?.role)
  const [data, error, reload] = useLoad(() => api.get('/company/questions'))
  const [answers, setAnswers] = useState(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) return <Loading error={error} />
  const questions = data.questions
  const now = answers ?? Object.fromEntries(questions.map((q) => [q.code, asChoice(q.answer)]))
  const open = questions.filter((q) => now[q.code] === '').length

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      // Only what actually moved, so saving one answer does not rewrite the others and their dates.
      for (const q of questions) {
        if (now[q.code] !== asChoice(q.answer)) {
          await api.put(`/company/questions/${q.code}`,
            { answer: now[q.code] === '' ? null : now[q.code] === 'yes' })
        }
      }
      setSaved(true); setAnswers(null); await reload()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="stack stickypage">
      <div className="pagehead">
        <h1>Operations</h1>
        {canEdit && <button className="primary" onClick={save} disabled={busy}>Save</button>}
      </div>
      {err && <div className="notice bad">{err}</div>}
      {saved && <div className="notice good">Saved.</div>}
      <div className="card qualcard">
        <div className="infotabs"><h3>
          Operations
          {open > 0 && <span className="sectionnote">{open} unanswered</span>}
        </h3></div>
        <div className="panelbody">
        <fieldset className="plain" disabled={!canEdit}>
          <section>
            <div className="asklist">
              {questions.map((q) => (
                <label key={q.code} className="askrow">
                  <span className="askwhat">
                    {q.question}
                    <span className="askhelp">{q.help}</span>
                  </span>
                  <select value={now[q.code]}
                    onChange={(e) => { setSaved(false)
                      setAnswers({ ...now, [q.code]: e.target.value }) }}>
                    {CHOICES.map(([value, label]) =>
                      <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
              ))}
            </div>
          </section>
        </fieldset>
        </div>
      </div>
    </div>
  )
}

function CompanyProfile() {
  const [company, error, reload] = useLoad(() => api.get('/company'))
  if (!company) return <Loading error={error} />
  return (
    <CompanyForm company={company} onSaved={reload} />
  )
}

function CompanyForm({ company, onSaved }) {
  const canEdit = ['owner', 'admin'].includes(useUser()?.role)
  const [saved, setSaved] = useState(false)

  const f = useForm(Object.fromEntries(FIELDS.map((k) => [k, company[k] || ''])), async (v) => {
    setSaved(false)
    await api.put('/company', v)
    setSaved(true)
    onSaved()
  })
  const v = f.values
  const set = (k) => (e) => { setSaved(false); f.set(k)(e) }

  return (
    <div className="stack stickypage">
      <div className="pagehead">
        <h1>Company</h1>
        {canEdit && <button className="primary" onClick={f.onSubmit} disabled={f.busy}>Save</button>}
      </div>
      {f.error && <div className="notice bad">{f.error}</div>}
      {saved && <div className="notice good">Saved.</div>}
      <fieldset className="plain" disabled={!canEdit}>
        <form className="stack" onSubmit={f.onSubmit}>
            <div className="card qualcard">
              <div className="infotabs"><h3>Demographics</h3></div>
              <div className="panelbody">
              <div className="profileform">
                <label className="field span-4">Company Name *<input required value={v.name} onChange={set('name')} /></label>
                <label className="field span-1">DBA<input value={v.dba} onChange={set('dba')} /></label>
                <label className="field span-1">Account #<input value={company.accountnumber || ''} disabled /></label>
                <label className="field span-6">Address Line 1<input value={v.address1} onChange={set('address1')} autoComplete="address-line1" /></label>
                <label className="field span-6">Address Line 2<input value={v.address2} onChange={set('address2')} autoComplete="address-line2" /></label>
                <label className="field span-2">City<input value={v.city} onChange={set('city')} autoComplete="address-level2" /></label>
                <label className="field span-1">County<input value={v.county} onChange={set('county')} /></label>
                <label className="field span-1">State
                  <select value={v.state} onChange={set('state')}>{US_STATES.map((s) => <option key={s}>{s}</option>)}</select>
                </label>
                <label className="field span-2">ZIP<ZipInput value={v.zip} onChange={set('zip')} /></label>
                <label className="field span-3">Telephone<PhoneInput value={v.phone} onChange={set('phone')} /></label>
                <label className="field span-3">Fax<PhoneInput value={v.fax} onChange={set('fax')} autoComplete="off" /></label>
              </div>
              </div>
            </div>
            <div className="card qualcard">
              <div className="infotabs"><h3>Email Addresses</h3></div>
              <div className="panelbody">
              <div className="profileform">
                <label className="field span-2">General<EmailInput value={v.email} onChange={set('email')} /></label>
                <label className="field span-2">Support<EmailInput value={v.supportemail} onChange={set('supportemail')} /></label>
                <label className="field span-2">Billing<EmailInput value={v.billingemail} onChange={set('billingemail')} /></label>
              </div>
              </div>
            </div>
            <div className="card qualcard">
              <div className="infotabs"><h3>Identifiers</h3></div>
              <div className="panelbody">
              <div className="profileform fiveup">
                <label className="field">EIN<EinInput value={v.ein} onChange={set('ein')} /></label>
                {/* The biennial update's month comes off the last digit of this number and its
                    year off the digit before it, so it is not a reference field. */}
                <label className="field">USDOT #<input value={v.usdot} onChange={set('usdot')} inputMode="numeric" /></label>
                <label className="field">MC #<input value={v.mcnumber} onChange={set('mcnumber')} /></label>
                <label className="field">Medicaid ID<input value={v.medicaidid} onChange={set('medicaidid')} /></label>
                <label className="field">NPI<input value={v.npi} onChange={set('npi')} inputMode="numeric" /></label>
              </div>
              </div>
            </div>
        </form>
      </fieldset>
    </div>
  )
}
