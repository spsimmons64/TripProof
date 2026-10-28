import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check, PartyPopper, ShieldCheck } from 'lucide-react'
import { SsnInput } from '../components/MaskedInput.jsx'
import { FieldError, useFirstField } from '../components/LicenseDialog.jsx'
import PublicShell from '../components/PublicShell.jsx'
import SignHere from '../components/SignHere.jsx'
import { DEFAULT_FONT, SIGNATURE_FONTS } from '../lib/signatureFonts.js'

// One document, signed by one driver, from a link.
//
// The link says which document is on the table. It does not say who is sitting at it - so nothing
// of the driver's is shown until they have proved who they are with the same date of birth and
// Social Security number the application asks for, and nothing is signed until they say so.

const FONTS = SIGNATURE_FONTS

const call = async (path, body) => {
  const res = await fetch(`/api/sign${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await res.json().catch(() => null)
  if (!res.ok) throw new Error(typeof json?.detail === 'string' ? json.detail : 'That did not work')
  return json
}

// What a form asks for that nothing on file can answer. Three kinds, because a W-4 needs a choice,
// some text and some figures, and nothing beyond that.
function FormAsks({ asks, answers, onChange }) {
  const set = (id, value) => onChange({ ...answers, [id]: value })
  return (
    <div className="profileform">
      {asks.map((a) => {
        if (a.kind === 'choice') {
          return (
            <label key={a.id} className="field span-6">{a.label}{a.required ? ' *' : ''}
              <select value={answers[a.id] || ''} onChange={(e) => set(a.id, e.target.value)}>
                <option value="">Choose</option>
                {a.choices.map(([val, text]) => <option key={val} value={val}>{text}</option>)}
              </select>
            </label>
          )
        }
        if (a.kind === 'tick') {
          return (
            <label key={a.id} className="field check span-6">
              <input type="checkbox" checked={!!answers[a.id]}
                onChange={(e) => set(a.id, e.target.checked)} />
              <span>{a.label}</span>
            </label>
          )
        }
        return (
          <label key={a.id} className={`field span-${a.kind === 'money' ? '2' : '3'}`}>
            {a.label}{a.required ? ' *' : ''}
            <input inputMode={a.kind === 'money' ? 'decimal' : undefined}
              value={answers[a.id] || ''} onChange={(e) => set(a.id, e.target.value)} />
          </label>
        )
      })}
    </div>
  )
}

// The form itself, redrawn whenever an answer changes. Fetched rather than linked because the
// page carries a date of birth and a Social Security number: a plain URL to it would be readable
// by anybody holding a forwarded link.
// 49 CFR 395.8(j)(2) - the hours the driver had already worked before they got here.
//
// Not a document to read: a form to fill in, which they then sign. The seven days are named for
// them rather than left as blank rows, because "last Tuesday" is a question people get wrong and
// a statement is worthless if the days it covers are not the days it says.
//
// ON DUTY, not driving - loading, waiting, inspecting, anything they were required to be doing -
// and for EVERY employer, because the limits follow the person rather than this carrier's share
// of them. Said in the form rather than left for somebody to know.
const DAYNAME = (iso) => {
  const [y, m, d] = iso.split('-')
  return new Date(Number(y), Number(m) - 1, Number(d))
    .toLocaleDateString('en-US', { weekday: 'long' })
}
function Prev7({ days, onChange, relieved, onRelieved }) {
  const set = (i, val) => onChange(days.map((d, n) => (n === i ? { ...d, hours: val } : d)))
  const total = days.reduce((t, d) => t + (Number(d.hours) || 0), 0)
  return (
    <div className="stack">
      <p className="muted small">
        For each of the last seven days, how many hours in total were you ON DUTY? That is not
        just driving - it includes loading, waiting, inspections and anything else you were
        required to be doing. Include work for every employer, not only for us. Enter 0 for a
        day you did not work.
      </p>
      <table className="residencetable recordtable">
        <thead><tr><th>Day</th><th className="growcol">Date</th><th>Hours on duty</th></tr></thead>
        <tbody>
          {days.map((d, i) => (
            <tr key={d.on}>
              <td>{DAYNAME(d.on)}</td>
              <td className="growcol">{d.on.slice(5, 7)}/{d.on.slice(8, 10)}/{d.on.slice(0, 4)}</td>
              <td>
                <input type="number" min="0" max="24" step="0.25" value={d.hours ?? ''}
                  onChange={(e) => set(i, e.target.value)} style={{ width: 90 }} />
              </td>
            </tr>
          ))}
          <tr><td /><td className="growcol"><b>Total</b></td><td><b>{total} h</b></td></tr>
        </tbody>
      </table>
      <div className="profileform">
        <label className="field span-3">When were you last relieved from duty? *
          <input type="datetime-local" value={relieved}
            onChange={(e) => onRelieved(e.target.value)} />
        </label>
      </div>
    </div>
  )
}

function FormView({ url, who, answers, title }) {
  const [src, setSrc] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    let dead = false
    let made = null
    // A short wait, so typing a ZIP code does not redraw the page five times.
    const timer = setTimeout(async () => {
      try {
        const r = await fetch(url, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...who, answers }),
        })
        if (!r.ok) throw new Error('The form could not be drawn just now.')
        const blob = await r.blob()
        if (dead) return
        made = URL.createObjectURL(blob)
        setSrc(made); setErr(null)
      } catch (e) { if (!dead) setErr(e.message) }
    }, 350)
    // The URL is released on the next draw rather than on every render, so the viewer is never
    // pointed at something that has just been taken away from it.
    return () => { dead = true; clearTimeout(timer); if (made) setTimeout(() => URL.revokeObjectURL(made), 60000) }
  }, [url, JSON.stringify(answers), JSON.stringify(who)])

  if (err) return <div className="notice bad">{err}</div>
  if (!src) return <div className="formview formloading">Drawing the form…</div>
  // KEYED ON THE SOURCE. An <object> very often keeps showing the PDF it already has when its
  // `data` changes, so moving from one form to the next left the previous document on screen
  // under the next one's heading - which read as the new form arriving already signed. The key
  // forces a new element, and a new element has nothing to keep.
  return <object key={src} className="formview" data={`${src}#view=FitH`}
    type="application/pdf" aria-label={title} />
}

export default function SignDocument() {
  const { token: opened } = useParams()
  // The link in the email is for a packet, not a page. Signing one form moves this on to the next
  // without the address changing, so coming back to the same link always lands on what is still
  // owed rather than on a document already signed.
  const [token, setToken] = useState(opened)
  const [asked, setAsked] = useState(null)      // what the link is for
  const [doc, setDoc] = useState(null)          // the text, once they have proved who they are
  const [done, setDone] = useState(null)
  const [v, setV] = useState({ dob: '', ssn: '', typedname: '', fontkey: DEFAULT_FONT })
  // What a government form asks for that we do not already hold - the W-4's filing status and
  // address. Kept apart from the identity fields because these go ON the form.
  const [answers, setAnswers] = useState({})
  // The driver's own figures, where the thing being signed is a form they fill in.
  const [days, setDays] = useState([])
  const [relieved, setRelieved] = useState('')
  // What was signed a moment ago, said once at the top of the next form so somebody knows the
  // first one landed.
  const [justSigned, setJustSigned] = useState(null)
  // The same gate the driver application uses. It is opened by SIGNING once in this visit, not by
  // typing a date of birth to read a document: proving who you are to open a form is not the act
  // of putting your name on it. Until it is open, every signature asks for the pair.
  const [unlocked, setUnlocked] = useState(false)
  // Everything put a name to in this visit, so the last page can say what was actually done
  // rather than only naming the one that happened to be last.
  const [finished, setFinished] = useState([])
  const [bad, setBad] = useState({})
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const box = useFirstField()

  useEffect(() => {
    call(`/${token}`)
      .then((r) => {
        // Already signed, and something else is still owed: go there instead of refusing.
        if (r.insteadof) { setToken(r.insteadof); return }
        setAsked(r)
      })
      .catch((e) => setErr(e.message))
  }, [token])

  const set = (k) => (e) => { setBad(({ [k]: _gone, ...rest }) => rest); setV({ ...v, [k]: e.target.value }) }

  const read = async () => {
    const problems = {}
    if (!v.dob) problems.dob = 'The birth date is required'
    if (v.ssn.replace(/\D/g, '').length !== 9) problems.ssn = 'Enter all nine digits'
    setBad(problems)
    if (Object.keys(problems).length) return
    setBusy(true); setErr(null)
    try {
      const r = await call(`/${token}/read`, { dob: v.dob, ssn: v.ssn })
      setDoc(r)
      // A form the driver fills in arrives with its rows already named, so the seven days are
      // the seven days the statement is about rather than whichever ones they remember.
      setDays(r.days || [])
      setV((s) => ({ ...s, typedname: r.signature?.typedname || '', fontkey: r.signature?.fontkey || DEFAULT_FONT }))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const submit = async (signed) => {
    setBusy(true); setErr(null)
    try {
      const r = await call(`/${token}/sign`, { ...signed, answers, relieved: relieved || null,
        days: days.map((d) => ({ on: d.on, hours: d.hours })) })
      // Straight on to the next form. They proved who they were a moment ago to sign the last
      // one; asking for a date of birth and a Social Security number again to carry on with the
      // same packet is a wall where there should be a page turn.
      setFinished((was) => [...was, r.title])
      if (r.next) {
        const nextDoc = await call(`/${r.next.token}/read`, { dob: v.dob, ssn: v.ssn })
        setDays(nextDoc.days || [])
        setRelieved('')
        setToken(r.next.token)
        setAsked({ accountname: r.accountname, title: r.next.title })
        setAnswers({})
        setDoc(nextDoc)
        setJustSigned(r.title)
        return
      }
      setDone(r)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (done) {
    return (
      <PublicShell company={asked?.accountname || done?.accountname} what="Document to sign" scroll>
        {/* The end of the packet, and it should feel like one. Somebody has just read and
            signed federal forms on a phone; the page that follows that should say it is done,
            say what was done, and let them put it down. */}
        <div className="signsheet"><div className="card stack signdone alldone">
          <span className="savedmark big"><PartyPopper size={34} strokeWidth={2.25} /></span>
          <h1>All done</h1>
          <p className="donelead">
            Thank you - everything {done.accountname} needed from you is signed and filed.
          </p>
          <ul className="donelist">
            {(finished.length ? finished : [done.title]).map((t) => (
              <li key={t}><Check size={16} strokeWidth={3} /> {t}</li>
            ))}
          </ul>
          <p className="muted">
            Nothing else is needed from you here. You can close this tab.
          </p>
          <p className="muted small">
            Keep an eye on your email - {done.accountname} will be in touch about your start.
          </p>
        </div></div>
      </PublicShell>
    )
  }

  const frame = (inner) => (
    <PublicShell company={asked?.accountname} what="Document to sign" scroll>
      <div className="signsheet">{inner}</div>
    </PublicShell>
  )
  if (err && !asked) return frame(<div className="card"><div className="notice bad">{err}</div></div>)
  if (!asked) return frame(<div className="card"><p className="muted">Opening…</p></div>)

  return (
    <>
    <PublicShell company={asked?.accountname || done?.accountname} what="Document to sign" scroll>
      <div className="signsheet"><div className="card stack" ref={box}>
        <h1>{asked.title}</h1>
        <p className="muted">{asked.accountname} has asked you to read and sign this.</p>
        {justSigned && (
          <div className="notice good">
            <Check size={15} /> {justSigned} is signed. One more below.
          </div>
        )}
        {err && <div className="notice bad">{err}</div>}

        {!doc ? (
          <div className="stack">
            {/* The one moment on this page where somebody has to be told why they are being
                asked for a Social Security number. It gets the weight that deserves. */}
            <p className="proveit">
              <ShieldCheck size={30} strokeWidth={2.25} />
              <span>So that only you can sign it, confirm who you are.</span>
            </p>
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
            <div><button type="button" className="primary" disabled={busy} onClick={read}>
              {busy ? 'Checking…' : 'Continue'}</button></div>
          </div>
        ) : (
          <div className="stack">
            {/* A government form is shown AS the form. What is read is the page that will be
                signed, filled in with what the office already holds - not a description of it in
                our words. The questions sit above it because answering one changes what the page
                below says. */}
            {doc.format === 'pdf' ? (
              <>
                {(doc.asks || []).length > 0 && (
                  <FormAsks asks={doc.asks} answers={answers} onChange={setAnswers} />
                )}
                <FormView url={doc.pdf} who={{ dob: v.dob, ssn: v.ssn }} answers={answers}
                  title={doc.title} />
                <p className="muted small">
                  This is the form itself, filled in with your answers as you type them. Your
                  signature goes on it when you sign below, and the signed copy is what is filed.
                </p>
              </>
            ) : doc.format === 'prev7' ? (
              <Prev7 days={days} onChange={setDays}
                relieved={relieved} onRelieved={setRelieved} />
            ) : doc.format === 'html'
              ? <div className="doc" dangerouslySetInnerHTML={{ __html: doc.text }} />
              : <div className="doc plaintext">{doc.text}</div>}
            <div className="profileform">
              {!doc.signature && (
                <>
                  <label className={`field span-4${bad.typedname ? ' bad' : ''}`}>Sign As *
                    <input value={v.typedname} onChange={set('typedname')} />
                    <FieldError message={bad.typedname} />
                  </label>
                  <label className="field span-2">Style
                    <select value={v.fontkey} onChange={set('fontkey')}>
                      {FONTS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                    </select>
                  </label>
                </>
              )}
              {/* A preview belongs to a signature being DESIGNED - it is the only way to see what
                  you are about to adopt. A signature already on file is never previewed on an
                  unsigned page: drawn there it says the page is signed, which it is not. */}
              {!doc.signature && (
                <div className="span-6 sigpreview">
                  <span className={`sigink font-${v.fontkey}`}>{v.typedname || 'Your name'}</span>
                </div>
              )}
            </div>
            {/* KEYED ON THE DOCUMENT. SignHere keeps the looked-up signature in its own state
                and only draws it once the driver has asked for it. Without a key React reuses the
                same instance when the packet moves to the next form, so the signature from the
                last one was still drawn on it - the next document arrived looking signed. Each
                document is a separate signing act and gets a fresh control to make it with. */}
            <SignHere key={token} busy={busy}
              proven={unlocked ? { dob: v.dob, ssn: v.ssn } : null}
              onUnlocked={() => setUnlocked(true)}
              lookup={async ({ dob, ssn }) => (await call(`/${token}/read`, { dob, ssn })).signature}
              onSubmit={submit}
              hint={doc.signature
                ? 'This will be signed with your signature on file.'
                : 'This becomes your signature on file, and cannot be changed afterwards.'} />
          </div>
        )}
      </div></div>
    </PublicShell>
    </>
  )
}

