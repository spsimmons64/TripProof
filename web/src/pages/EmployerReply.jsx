import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check, Plus, Send, X } from 'lucide-react'
import PublicShell from '../components/PublicShell.jsx'
import { FieldError, StateSelect, useFirstField } from '../components/LicenseDialog.jsx'

// A previous employer answering the safety performance history investigation - 49 CFR 391.23.
//
// The person at the other end has no account here, no stake in answering, and is doing the asking
// carrier a favour. Two things follow from that, and they shape the whole page.
//
// NOTHING IS TYPED THAT IS ALREADY KNOWN. Who the driver is, who is asking, and what the driver
// said about working there are all filled in. The employer confirms or corrects; they do not
// transcribe a form.
//
// AND EVERY ANSWER KEEPS ITS THIRD OPTION. "No" and "no records available" are different answers -
// one is evidence, the other is a gap the carrier still owns - so the page never reduces a question
// to a tick box that is either on or off.

const call = async (path, body) => {
  const res = await fetch(`/api/employer-reply${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await res.json().catch(() => null)
  if (!res.ok) throw new Error(typeof json?.detail === 'string' ? json.detail : 'That did not work')
  return json
}

const date = (v) => (v ? new Date(`${String(v).slice(0, 10)}T00:00:00`).toLocaleDateString('en-US') : '-')

const VERIFIED = [['yes', 'Yes'], ['no', 'No'], ['unable', 'Unable to verify']]
const FOURWAY = [['yes', 'Yes'], ['no', 'No'], ['unknown', 'Unknown'], ['na', 'Not applicable']]
const YESNO = [['yes', 'Yes'], ['no', 'No'], ['na', 'N/A - no records']]
const ACCIDENT = [['no', 'No'], ['yes', 'Yes'], ['norecords', 'No records available']]
const MODES = ['FMCSA', 'FTA', 'FRA', 'FAA', 'PHMSA', 'USCG', 'other']
const FONTS = [['modern', 'Modern'], ['signature', 'Inked'], ['quick', 'Quick'],
               ['hand', 'Handwritten'], ['cursive', 'Cursive'], ['fine', 'Fine'], ['bold', 'Bold']]

// The four §391.23(e) questions, in the form's own words.
const DA_QUESTIONS = [
  ['alcohol04', 'Alcohol test result of 0.04 or greater?'],
  ['positivetest', 'Verified positive controlled-substances test?'],
  ['refusedtest', 'Refusal to submit to a required DOT drug/alcohol test?'],
  ['otherviolation', 'Other applicable DOT drug/alcohol prohibition violation?'],
]

const SAP_QUESTIONS = [
  ['sapevaluated', 'SAP evaluation completed?'],
  ['saptreatment', 'SAP-prescribed education/treatment completed?'],
  ['rtdtest', 'Required return-to-duty test completed with acceptable result?'],
  ['followupplan', 'Driver subject to a follow-up testing plan?'],
]

// One question, one row, every option visible. A row of radios rather than a dropdown, because an
// unopened dropdown hides that there was ever a third answer.
function Ask({ label, name, options, value, onChange }) {
  return (
    <div className="askrow">
      <span className="askwhat">{label}</span>
      <span className="askpick">
        {options.map(([v, l]) => (
          <label key={v}>
            <input type="radio" name={name} checked={value === v} onChange={() => onChange(v)} /> {l}
          </label>
        ))}
      </span>
    </div>
  )
}

export default function EmployerReply() {
  const { token } = useParams()
  const [asked, setAsked] = useState(null)
  const [done, setDone] = useState(null)
  const [err, setErr] = useState(null)
  const [bad, setBad] = useState({})
  const [busy, setBusy] = useState(false)
  const [signing, setSigning] = useState(false)
  const box = useFirstField()
  const [v, setV] = useState({
    employmentverified: '', position: '', confirmedfrom: '', confirmedthrough: '',
    operatedcmv: '', dotmode: '', accidentanswer: '', accidentsattached: false,
    alcohol04: '', positivetest: '', refusedtest: '', otherviolation: '',
    sapevaluated: '', saptreatment: '', rtdtest: '', followupplan: '',
    respondedby: '', title: '', company: '', phone: '', email: '', signature: '',
    fontkey: 'modern', note: '',
  })
  const [accidents, setAccidents] = useState([])

  useEffect(() => {
    call(`/${token}`).then((r) => {
      setAsked(r)
      // Filled in from what the carrier already holds. The employer corrects what is wrong rather
      // than copying out what is right.
      setV((s) => ({ ...s,
        confirmedfrom: (r.employer.employedfrom || '').slice(0, 10),
        confirmedthrough: (r.employer.employedthrough || '').slice(0, 10),
        company: r.employer.company || '',
        phone: r.employer.phone || '',
        email: r.employer.email || '',
        respondedby: r.employer.contactname || '',
      }))
    }).catch((e) => setErr(e.message))
  }, [token])

  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setV({ ...v, [k]: e.target.value })
  }
  // Free text is typed and stored upper case. An email address is not free text and keeps its own.
  const upper = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setV({ ...v, [k]: e.target.value.toUpperCase() })
  }
  const pick = (k) => (value) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setV({ ...v, [k]: value })
  }

  const worked = v.employmentverified === 'yes'
  // §391.23(e) is not asked of an FMCSA employer: that history comes from the Clearinghouse
  // pre-employment query, and asking here as well duplicates it.
  const askDA = worked && v.dotmode && v.dotmode !== 'FMCSA'
  const anyViolation = DA_QUESTIONS.some(([k]) => v[k] === 'yes')

  const send = async () => {
    const problems = {}
    if (!v.employmentverified) problems.employmentverified = 'Please answer'
    if (!v.respondedby.trim()) problems.respondedby = 'Your name is required'
    if (!v.signature.trim()) problems.signature = 'Sign it before sending'
    if (worked && !v.accidentanswer) problems.accidentanswer = 'Please answer'
    setBad(problems)
    if (Object.keys(problems).length) return
    setBusy(true); setErr(null)
    try {
      setDone(await call(`/${token}`, {
        ...v,
        signature: v.signature,
        accidents: accidents.filter((a) => a.date || a.location),
      }))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (done) {
    return (
      <PublicShell company={done.accountname} what="Safety performance history" scroll>
        <div className="signsheet"><div className="card stack signdone">
          <span className="savedmark"><Check size={24} strokeWidth={3} /></span>
          <h1>Thank you</h1>
          <p>Your response has been sent to {done.accountname}. You can close this page.</p>
        </div></div>
      </PublicShell>
    )
  }

  const frame = (inner) => (
    <PublicShell company={asked?.requestor?.company} what="Safety performance history" scroll>
      <div className="signsheet">{inner}</div>
    </PublicShell>
  )
  if (err && !asked) return frame(<div className="card"><div className="notice bad">{err}</div></div>)
  if (!asked) return frame(<div className="card"><p className="muted">Opening…</p></div>)

  const { driver, requestor, employer } = asked

  return (
    <PublicShell company={requestor.company} what="Safety performance history" scroll>
      <div className="signsheet"><div className="card stack" ref={box}>
        <h1>Safety Performance History</h1>
        <p className="muted">
          {requestor.company} is considering {driver.name} for a driving position and is required to
          ask you about their safety performance history with you, under 49 CFR 391.23(d) and (e).
          The driver has given written consent for you to release it.
        </p>
        {err && <div className="notice bad">{err}</div>}

        {/* 1 and 2 - what the carrier already knows. Stated, never asked. */}
        <section>
          <h3 className="formsection">The Driver</h3>
          <dl className="askfacts">
            <div><dt>Name</dt><dd>{driver.name}</dd></div>
            <div><dt>Date of birth</dt><dd>{date(driver.dob)}</dd></div>
            <div><dt>License</dt>
              <dd>{[driver.licensestate, driver.licensenumber].filter(Boolean).join(' ') || '-'}</dd></div>
          </dl>
        </section>

        <section>
          <h3 className="formsection">Who Is Asking</h3>
          <dl className="askfacts">
            <div><dt>Company</dt><dd>{requestor.company}</dd></div>
            <div><dt>Address</dt>
              <dd>{[requestor.address1, requestor.city, requestor.state, requestor.zip]
                .filter(Boolean).join(', ') || '-'}</dd></div>
            <div><dt>Contact</dt>
              <dd>{[requestor.phone, requestor.email].filter(Boolean).join(' · ') || '-'}</dd></div>
            <div><dt>Requested</dt><dd>{date(requestor.sent)}</dd></div>
          </dl>
        </section>

        {/* 3 - what the driver told us, for the employer to confirm or correct. */}
        <section>
          <h3 className="formsection">Employment</h3>
          <div className="asklist">
            <Ask label={`Did ${driver.name} work for ${employer.company}?`} name="verified"
              options={VERIFIED} value={v.employmentverified} onChange={pick('employmentverified')} />
            {/* The bubble is positioned against its field, so it needs one to sit in - loose in a
                list it anchors to the page and lands in the corner of the window. */}
            <div className="fielderrline"><FieldError message={bad.employmentverified} /></div>
          </div>
          {worked && (
            <div className="profileform">
              <label className="field span-3">Position
                <input value={v.position} className="upper" onChange={upper('position')} /></label>
              <label className="field span-3">Dates - from
                <input type="date" value={v.confirmedfrom} onChange={set('confirmedfrom')} /></label>
              <label className="field span-3">Dates - to
                <input type="date" value={v.confirmedthrough} onChange={set('confirmedthrough')} /></label>
              <label className="field span-3">DOT mode
                <select value={v.dotmode} onChange={set('dotmode')}>
                  <option value="">Choose</option>
                  {MODES.map((m) => <option key={m} value={m}>{m === 'other' ? 'Other' : m}</option>)}
                </select>
              </label>
              <div className="span-6">
                <div className="asklist">
                  <Ask label="Did they operate a commercial motor vehicle?" name="cmv"
                    options={FOURWAY} value={v.operatedcmv} onChange={pick('operatedcmv')} />
                </div>
              </div>
              {/* Anything the questions above did not have a box for. */}
              <label className="field span-6">Anything else
                <textarea rows={3} value={v.note} className="upper"
                  onChange={upper('note')} /></label>
            </div>
          )}
        </section>

        {/* 4 - §391.23(d) */}
        {worked && (
          <section>
            <h3 className="formsection">Accidents - Preceding 3 Years</h3>
            <div className="asklist">
              <Ask label="Was the driver involved in any accidents required to be maintained under 49 CFR 390.15?"
                name="accidents" options={ACCIDENT} value={v.accidentanswer}
                onChange={pick('accidentanswer')} />
              <div className="fielderrline"><FieldError message={bad.accidentanswer} /></div>
            </div>
            {v.accidentanswer === 'yes' && (
              <div className="stack">
                {accidents.map((a, i) => (
                  <div key={i} className="profileform">
                    <label className="field span-2">Date
                      <input type="date" value={a.date || ''}
                        onChange={(e) => setAccidents(accidents.map((x, n) =>
                          n === i ? { ...x, date: e.target.value } : x))} /></label>
                    <label className="field span-2">Location
                      <input value={a.location || ''} className="upper"
                        onChange={(e) => setAccidents(accidents.map((x, n) =>
                          n === i ? { ...x, location: e.target.value.toUpperCase() } : x))} /></label>
                    <label className="field span-1">Fatalities
                      <input type="number" min="0" value={a.fatalities ?? ''}
                        onChange={(e) => setAccidents(accidents.map((x, n) =>
                          n === i ? { ...x, fatalities: e.target.value } : x))} /></label>
                    <label className="field span-1">Injuries
                      <input type="number" min="0" value={a.injuries ?? ''}
                        onChange={(e) => setAccidents(accidents.map((x, n) =>
                          n === i ? { ...x, injuries: e.target.value } : x))} /></label>
                    <label className="field check sharerow span-2">
                      <input type="checkbox" checked={Boolean(a.hazmat)}
                        onChange={(e) => setAccidents(accidents.map((x, n) =>
                          n === i ? { ...x, hazmat: e.target.checked } : x))} /> Hazmat
                    </label>
                    <label className="field span-4">Notes
                      <input value={a.note || ''} className="upper"
                        onChange={(e) => setAccidents(accidents.map((x, n) =>
                          n === i ? { ...x, note: e.target.value.toUpperCase() } : x))} /></label>
                    <div className="field span-2">
                      <button type="button" onClick={() => setAccidents(accidents.filter((_x, n) => n !== i))}>
                        <X size={13} /> Remove
                      </button>
                    </div>
                  </div>
                ))}
                <div>
                  <button type="button" onClick={() => setAccidents([...accidents, {}])}>
                    <Plus size={13} /> Add an accident
                  </button>
                </div>
                <label className="check">
                  <input type="checkbox" checked={v.accidentsattached}
                    onChange={(e) => setV({ ...v, accidentsattached: e.target.checked })} />
                  Additional accident information will be sent separately
                </label>
              </div>
            )}
          </section>
        )}

        {/* 5 - §391.23(e). Not asked of an FMCSA employer. */}
        {askDA && (
          <section>
            <h3 className="formsection">Drug And Alcohol History</h3>
            <div className="asklist">
              {DA_QUESTIONS.map(([k, label]) => (
                <Ask key={k} label={label} name={k} options={YESNO} value={v[k]} onChange={pick(k)} />
              ))}
            </div>
          </section>
        )}

        {/* 6 - only where something was answered yes. */}
        {askDA && anyViolation && (
          <section>
            <h3 className="formsection">SAP And Return To Duty</h3>
            <div className="asklist">
              {SAP_QUESTIONS.map(([k, label]) => (
                <Ask key={k} label={label} name={k} options={FOURWAY} value={v[k]} onChange={pick(k)} />
              ))}
            </div>
          </section>
        )}

        {/* 7 - the certification */}
        <section>
          <h3 className="formsection">Certification</h3>
          <p className="muted small">
            I certify that the information provided is based on records available to this company.
          </p>
          <div className="profileform">
            <label className={`field span-3${bad.respondedby ? ' bad' : ''}`}>Your Name *
              <input value={v.respondedby} className="upper" onChange={upper('respondedby')} />
              <FieldError message={bad.respondedby} />
            </label>
            <label className="field span-3">Title
              <input value={v.title} className="upper" onChange={upper('title')} /></label>
            <label className="field span-3">Company
              <input value={v.company} className="upper" onChange={upper('company')} /></label>
            <label className="field span-3">Phone
              <input value={v.phone} onChange={set('phone')} /></label>
            {/* Email keeps its own casing - an address is not free text - and takes the rest of
                the row rather than leaving half of one empty under it. */}
            <label className="field span-6">Email
              <input value={v.email} onChange={set('email')} /></label>
          </div>

          {/* The signature is the last thing on the page because it is the last thing that
              happens: everything above it is what is being certified. It is an act, not a field -
              the same act the driver performs on their own application - except that nobody proves
              who they are first. There is nothing to prove a previous employer against, so the
              name draws this one page and is kept nowhere else as a signature of record. */}
          <div className="signhereblock">
            <div className="signfields">
              <div className="signbox">
                <span className="signlabel">Signature Of Previous Employer</span>
                <div className="signline">
                  {v.signature
                    ? <span className={`sigink font-${v.fontkey}`}>{v.signature}</span>
                    : null}
                </div>
              </div>
              <div className="signbox datebox">
                <span className="signlabel">Signature Date</span>
                <div className="signline">
                  {v.signature ? new Date().toLocaleDateString('en-US') : null}
                </div>
              </div>
            </div>
            <div className="fielderrline"><FieldError message={bad.signature} /></div>
            {/* Sign, then send: the two things left to do, on one line in the order they happen. */}
            <div className="sendrow">
              {!v.signature && (
                <button type="button" className="primary" onClick={() => setSigning(true)}>
                  Sign
                </button>
              )}
              <button type="button" className="primary pushright"
                disabled={busy || !v.signature} onClick={send}>
                {busy ? 'Sending…' : <><Send size={15} /> Send response</>}
              </button>
            </div>
          </div>
        </section>
      </div></div>
      {signing && (
        <SignDialog name={v.respondedby} onClose={() => setSigning(false)}
          onSigned={(typedname, fontkey) => {
            setBad(({ signature: _gone, ...rest }) => rest)
            setV((s) => ({ ...s, signature: typedname, fontkey }))
            setSigning(false)
          }} />
      )}
    </PublicShell>
  )
}

// The signing itself: a name, a hand to write it in, and nothing else asked. A driver signing their
// application proves who they are first with a date of birth and a Social Security number; there is
// nothing to prove a previous employer against, and a password gate on a favour is a favour that
// does not get done.
function SignDialog({ name, onClose, onSigned }) {
  const [typedname, setTypedname] = useState(name || '')
  const [fontkey, setFontkey] = useState('modern')
  const [bad, setBad] = useState(null)
  const sign = (e) => {
    e.preventDefault()
    if (!typedname.trim()) { setBad('Type the name you want to sign with'); return }
    onSigned(typedname.trim().toUpperCase(), fontkey)
  }
  return (
    <div className="backdrop">
      <form className="modal" role="dialog" aria-modal="true" aria-label="Sign" onSubmit={sign}>
        <header><h2>Sign The Certification</h2>
          <button type="button" className="iconbtn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>
        <div className="body">
          <div className="stack">
            <p className="muted small">
              I certify that the information provided is based on records available to this company.
            </p>
            <div className="profileform">
              <label className={`field span-4${bad ? ' bad' : ''}`}>Sign As *
                <input value={typedname} className="upper" autoFocus
                  onChange={(e) => { setBad(null); setTypedname(e.target.value.toUpperCase()) }} />
                <FieldError message={bad} />
              </label>
              <label className="field span-2">Style
                <select value={fontkey} onChange={(e) => setFontkey(e.target.value)}>
                  {FONTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </label>
            </div>
            <div className="sigpreview">
              <span className={`sigink font-${fontkey}`}>{typedname || ' '}</span>
            </div>
          </div>
        </div>
        <footer>
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="primary">Sign</button>
        </footer>
      </form>
    </div>
  )
}
