import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check, ShieldCheck, Upload, X } from 'lucide-react'
import { SsnInput } from '../components/MaskedInput.jsx'
import { BLANK_LICENSE, FieldError, LicenseFields, licenseProblems, useFirstField }
  from '../components/LicenseDialog.jsx'
import PublicShell from '../components/PublicShell.jsx'
import SignHere from '../components/SignHere.jsx'

// One document, sent by one driver, from a link.
//
// The link says which document is wanted. It does not say who is holding it - so nothing of the
// driver's is shown until they have proved who they are with the same date of birth and Social
// Security number the application asks for, and nothing is filed until they send it.
//
// The page never says WHY the document is wanted. The reason is often the driver's own license
// history, and a page opened on a phone is read by whoever is standing behind them.

const FONTS = [['modern', 'Modern'], ['signature', 'Inked'], ['quick', 'Quick'],
               ['hand', 'Handwritten'], ['cursive', 'Cursive'], ['fine', 'Fine'], ['bold', 'Bold']]

// What the server said, in words. A rejected field comes back as a list of problems rather than a
// sentence, and answering that with "that did not work" tells somebody staring at a typo nothing
// at all about where the typo is.
const PLAIN = { issuedon: 'issue date', expireson: 'expiry date', dob: 'date of birth',
                ssn: 'Social Security number', file: 'document', front: 'front of the license',
                back: 'back of the license' }

const saidWhat = (json, fallback = 'That did not work') => {
  if (typeof json?.detail === 'string') return json.detail
  if (Array.isArray(json?.detail) && json.detail.length) {
    const said = json.detail.map((d) => {
      const field = PLAIN[(d.loc || []).slice(-1)[0]] || (d.loc || []).slice(-1)[0]
      return field ? `Check the ${field}.` : d.msg
    })
    return [...new Set(said)].join(' ')
  }
  return fallback
}

const call = async (path, body) => {
  const res = await fetch(`/api/upload-request${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await res.json().catch(() => null)
  if (!res.ok) throw new Error(saidWhat(json))
  return json
}

// One question, one row, every option visible - the same shape the employer's reply form uses.
function Ask({ label, name, options, value, onChange }) {
  return (
    <div className="askrow">
      <span className="askwhat">{label}</span>
      <span className="askpick">
        {options.map(([val, l]) => (
          <label key={val}>
            <input type="radio" name={name} checked={value === val}
              onChange={() => onChange(val)} /> {l}
          </label>
        ))}
      </span>
    </div>
  )
}

export default function UploadDocument() {
  const { token } = useParams()
  const [asked, setAsked] = useState(null)      // what the link is for
  const [open, setOpen] = useState(false)       // proved who they are
  const [done, setDone] = useState(null)
  const [v, setV] = useState({ dob: '', ssn: '', issuedon: '', expireson: '', exempt: false, file: null })
  // 49 CFR 40.25(j): the one question nobody but the applicant can answer.
  const [q, setQ] = useState({ priorviolation: '', prioremployer: '', priortestdate: '',
                               priortesttype: '', priorrtd: '' })
  const [signed, setSigned] = useState(null)      // what they signed with, once they have
  // A license is a card with a number, a state, a class and two sides, so it is filled in
  // rather than photographed - the same fields the office fills in, from the same component.
  const [lic, setLic] = useState(BLANK_LICENSE)
  const [front, setFront] = useState(null)
  const [back, setBack] = useState(null)
  const [bad, setBad] = useState({})
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const box = useFirstField()
  const picker = useRef(null)

  useEffect(() => { call(`/${token}`).then(setAsked).catch((e) => setErr(e.message)) }, [token])

  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setV({ ...v, [k]: e.target.value })
  }

  const identify = () => {
    const problems = {}
    if (!v.dob) problems.dob = 'The birth date is required'
    if (v.ssn.replace(/\D/g, '').length !== 9) problems.ssn = 'Enter all nine digits'
    setBad(problems)
    return Object.keys(problems).length === 0
  }

  const proceed = async () => {
    if (!identify()) return
    setBusy(true); setErr(null)
    try {
      await call(`/${token}/open`, { dob: v.dob, ssn: v.ssn })
      setOpen(true)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // The proof goes up with the file rather than buying a session: a link that has been opened is
  // not a link that may then be used by whoever picks the phone up next.
  const send = async (how = signed) => {
    const body = new FormData()
    if (asked.questionnaire) {
      if (!q.priorviolation) { setBad({ priorviolation: 'Please answer' }); return }
      if (q.priorviolation === 'yes' && !q.prioremployer.trim()) {
        setBad({ prioremployer: 'Say which employer you applied to' })
        return
      }
      if (!how) { setBad({ signature: 'Sign it before sending' }); return }
      Object.entries(q).forEach(([k, val]) => { if (val) body.append(k, val) })
      // Only a signature being adopted here travels with the answer. Where they already had one,
      // the server signs with that and never reads what the page sent.
      if (how.design) {
        body.append('signature', how.typedname)
        body.append('fontkey', how.fontkey)
      }
      if (q.priorviolation === 'yes' && v.file) body.append('file', v.file)
    } else if (asked.license) {
      const problems = licenseProblems(lic)
      if (!front && !back) problems.front = 'Send at least one side'
      setBad(problems)
      if (Object.keys(problems).length) return
      body.append('number', lic.number)
      body.append('state', lic.state)
      body.append('classification', lic.classification)
      body.append('commercial', lic.commercial)
      body.append('endorsements', (lic.endorsements || []).join(''))
      body.append('issuedon', lic.issued)
      body.append('expireson', lic.expires)
      if (front) body.append('front', front)
      if (back) body.append('back', back)
    } else if (!v.exempt && !v.file) {
      setBad({ file: 'Choose the document first' })
      return
    } else if (!v.exempt) {
      const silly = (d) => d && (d < '1900-01-01' || d > '2100-12-31')
      const problems = {}
      if (silly(v.issuedon)) problems.issuedon = 'Check the year'
      if (silly(v.expireson)) problems.expireson = 'Check the year'
      if (Object.keys(problems).length) { setBad(problems); return }
    }
    setBusy(true); setErr(null)
    try {
      body.append('dob', v.dob)
      body.append('ssn', v.ssn)
      if (!asked.license && !asked.questionnaire) {
        if (v.exempt) {
          body.append('exempt', 'true')
        } else {
          if (v.issuedon) body.append('issuedon', v.issuedon)
          if (v.expireson) body.append('expireson', v.expireson)
          body.append('file', v.file)
        }
      }
      const res = await fetch(`/api/upload-request/${token}`, { method: 'POST', body })
      const json = await res.json().catch(() => null)
      if (!res.ok) throw new Error(saidWhat(json))
      setDone(json)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const questionnaireForm = (
    <>
      <p>
        During the previous two years, have you tested positive, or refused to test, on any
        pre-employment drug or alcohol test administered by an employer to which you applied for,
        but did not obtain, safety-sensitive transportation work covered by DOT drug and alcohol
        testing rules?
      </p>
      <div className="asklist">
        <Ask label="Your answer" name="priorviolation"
          options={[['no', 'No'], ['yes', 'Yes']]} value={q.priorviolation}
          onChange={(value) => {
            setBad(({ priorviolation: _g, ...rest }) => rest)
            setQ(value === 'no'
              ? { ...q, priorviolation: value, prioremployer: '', priortestdate: '',
                  priortesttype: '', priorrtd: '' }
              : { ...q, priorviolation: value })
          }} />
        <div className="fielderrline"><FieldError message={bad.priorviolation} /></div>
      </div>
      {q.priorviolation === 'yes' && (
        <div className="profileform">
          <label className={`field span-3${bad.prioremployer ? ' bad' : ''}`}>
            Employer You Applied To *
            <input value={q.prioremployer} className="upper"
              onChange={(e) => {
                setBad(({ prioremployer: _g, ...rest }) => rest)
                setQ({ ...q, prioremployer: e.target.value.toUpperCase() })
              }} />
            <FieldError message={bad.prioremployer} />
          </label>
          <label className="field span-3">Approximate Test Date
            <input type="date" value={q.priortestdate}
              onChange={(e) => setQ({ ...q, priortestdate: e.target.value })} /></label>
          <label className="field span-3">What Kind
            <select value={q.priortesttype}
              onChange={(e) => setQ({ ...q, priortesttype: e.target.value })}>
              <option value="">Choose</option>
              <option value="drug">Drug</option>
              <option value="alcohol">Alcohol</option>
              <option value="refusal">Refusal to test</option>
            </select>
          </label>
          {/* What happens next turns on this: Part 40 Subpart O decides whether they may perform
              safety-sensitive work again, not whether they may be employed. */}
          <label className="field span-3">Have you completed the DOT return-to-duty requirements?
            <select value={q.priorrtd}
              onChange={(e) => setQ({ ...q, priorrtd: e.target.value })}>
              <option value="">Choose</option>
              <option value="yes">Yes</option>
              <option value="inprogress">In progress</option>
              <option value="no">No</option>
            </select>
          </label>
          {/* Whatever they hold showing the process was done - the SAP's determination, the
              follow-up plan, a return-to-duty result. Never required: a driver may have disclosed
              a violation and have nothing in their hand. */}
          <label className="field span-6">Return-To-Duty Or SAP Paperwork
            <input type="file" accept="application/pdf,image/*"
              onChange={(e) => setV({ ...v, file: e.target.files[0] || null })} />
          </label>
        </div>
      )}
      {/* An attestation, not a form: what makes it one is the driver putting their name to it. */}
      <div className="signhereblock flush">
        <p className="muted small">
          I certify that the answer above is true and complete to the best of my knowledge.
        </p>
        <SignHere busy={busy}
          action="Sign The Questionnaire" submit="Send It"
          lookup={async ({ dob, ssn }) => (await call(`/${token}/open`, { dob, ssn })).signature}
          onSubmit={(how) => { setSigned(how); send(how) }} />
      </div>

    </>
  )

  const licenseForm = (
    <>
      <div className="profileform">
        <LicenseFields r={lic} setR={setLic} bad={bad} setBad={setBad} copies
          front={front} setFront={setFront} back={back} setBack={setBack} />
      </div>
      <FieldError message={bad.front} />
      <p className="muted small">A clear photograph of each side is fine, up to 20 MB each.</p>
    </>
  )

  if (done) {
    return (
      <PublicShell company={asked?.accountname || done?.accountname} what="Document to send" scroll>
        <div className="signsheet"><div className="card stack signdone">
          <span className="savedmark"><Check size={24} strokeWidth={3} /></span>
          <h1>Sent</h1>
          <p>{done.document} is filed with {done.accountname}. You can close this page.</p>
        </div></div>
      </PublicShell>
    )
  }

  const frame = (inner) => (
    <PublicShell company={asked?.accountname} what="Document to send" scroll>
      <div className="signsheet">{inner}</div>
    </PublicShell>
  )
  if (err && !asked) return frame(<div className="card"><div className="notice bad">{err}</div></div>)
  if (!asked) return frame(<div className="card"><p className="muted">Opening…</p></div>)

  return (
    <PublicShell company={asked.accountname} what="Document to send" scroll>
      <div className="signsheet"><div className="card stack" ref={box}>
        <h1>{asked.document}</h1>
        <p className="muted">{asked.accountname} has asked you for a copy of this.</p>
        {err && <div className="notice bad">{err}</div>}

        {!open ? (
          <div className="stack">
            <p><ShieldCheck size={15} /> So that only you can use this link, confirm who you are.</p>
            <div className="profileform">
              <label className={`field span-3${bad.dob ? ' bad' : ''}`}>Date Of Birth *
                <input type="date" value={v.dob} onChange={set('dob')} />
                <FieldError message={bad.dob} />
              </label>
              <label className={`field span-3${bad.ssn ? ' bad' : ''}`}>Social Security Number *
                <SsnInput value={v.ssn} onChange={set('ssn')} />
                <FieldError message={bad.ssn} />
              </label>
            </div>
            <div><button type="button" className="primary" disabled={busy} onClick={proceed}>
              {busy ? 'Checking…' : 'Continue'}</button></div>
          </div>
        ) : (
          <div className="stack">
            {asked.questionnaire ? questionnaireForm : asked.license ? licenseForm : (
            <div className="profileform">
              {/* A driver who is exempt has nothing to send, and saying so is the answer rather
                  than a gap. It comes first because it decides whether any of the rest is asked.
                  Not offered where there is no exemption to claim - a driver either holds a license
                  or does not drive. */}
              {asked.exemptable && (
                <label className="field check span-6">
                  <input type="checkbox" checked={v.exempt}
                    onChange={(e) => {
                      setBad(({ file: _gone, ...rest }) => rest)
                      setV({ ...v, exempt: e.target.checked })
                    }} />
                  I am exempt and have no document to send
                </label>
              )}
              {/* Bounded, because a date field will happily take a five-digit year from a
                  fumbled keystroke and the first anybody hears of it is a rejection. */}
              <label className={`field span-3${bad.issuedon ? ' bad' : ''}`}>Issue Date
                <input type="date" value={v.issuedon} disabled={v.exempt}
                  min="1900-01-01" max="2100-12-31" onChange={set('issuedon')} />
                <FieldError message={bad.issuedon} />
              </label>
              <label className={`field span-3${bad.expireson ? ' bad' : ''}`}>Expire Date
                <input type="date" value={v.expireson} disabled={v.exempt}
                  min="1900-01-01" max="2100-12-31" onChange={set('expireson')} />
                <FieldError message={bad.expireson} />
              </label>
              <label className={`field span-6${bad.file ? ' bad' : ''}`}>The Document *
                <input ref={picker} type="file" accept="application/pdf,image/*"
                  disabled={v.exempt}
                  onChange={(e) => {
                    setBad(({ file: _gone, ...rest }) => rest)
                    setV({ ...v, file: e.target.files[0] || null })
                  }} />
                <FieldError message={bad.file} />
              </label>
            </div>
            )}
            {!asked.license && !asked.questionnaire && !v.exempt && (
              <p className="muted small">A clear photograph is fine. PDF or a photo, up to 20 MB.</p>
            )}
            {/* The questionnaire carries its own action row, with signing beside sending. */}
            {!asked.questionnaire && (
              <div className="formactions">
                <button type="button" className="primary right" disabled={busy} onClick={send}>
                  {busy ? 'Sending…' : <><Upload size={15} /> Send it</>}
                </button>
              </div>
            )}
          </div>
        )}
      </div></div>
    </PublicShell>
  )
}
