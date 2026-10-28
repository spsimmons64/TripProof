import { useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../lib/api.js'
import { SsnInput } from './MaskedInput.jsx'
import { DEFAULT_FONT, SIGNATURE_FONTS } from '../lib/signatureFonts.js'

// An account user's signature, on the same terms a driver's is.
//
// A password proves a session, not a person. So a user signs the way a driver signs their
// application: the signature is created once behind a date of birth and a Social Security number,
// and every signing afterwards is that same hand, proved again the same way. Nothing of the
// signature is shown until the pair has been checked by the server, and nothing is drawn on a
// document until it has actually been signed.

// The hands to sign in, as the application offers them. All self-hosted; no outside requests.
const FONTS = SIGNATURE_FONTS

const today = () => new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })

// The signature and date blanks as they read on the form: empty, until it is signed.
export default function SignatureBlock({ signature, onSigned, label = 'Signature Of Reviewer',
                                         action = 'Sign' }) {
  const [asking, setAsking] = useState(false)
  return (
    <div className="signblock span-12">
      <div className="signfields">
        <div className="signbox">
          <span className="signlabel">{label}</span>
          <div className="signline">
            {signature ? <span className={`sigink font-${signature.fontkey}`}>{signature.typedname}</span> : null}
            {/* What was signed with, beside what it looks like: which signature on file this is,
                who it belongs to, how they proved it, and where from. */}
            {signature ? <SignatureStamp signature={signature} /> : null}
          </div>
        </div>
        <div className="signbox datebox">
          <span className="signlabel">Signature Date</span>
          <div className="signline">{signature ? today() : null}</div>
        </div>
      </div>
      {!signature && (
        <div className="field signaction">
          <button type="button" className="primary" onClick={() => setAsking(true)}>{action}</button>
        </div>
      )}
      {asking && <UserSignDialog title={action} onClose={() => setAsking(false)}
        onSigned={(sig) => { setAsking(false); onSigned(sig) }} />}
    </div>
  )
}

function SignatureStamp({ signature }) {
  const adopted = String(signature.adoptedon || '').replace('T', ' ').slice(0, 19)
  return (
    <span className="sigstamp">
      <span>Signed electronically · {signature.signername}</span>
      <span>{signature.recordid}</span>
      <span>{adopted} UTC · IP {signature.ip || 'not recorded'}</span>
    </span>
  )
}

// Two stages, as the driver's is: prove who you are, then sign. A user who has never signed is
// setting the pair that will unlock their signature from now on.
function UserSignDialog({ title, onClose, onSigned }) {
  const [v, setV] = useState({ dob: '', ssn: '', typedname: '', fontkey: DEFAULT_FONT })
  const [bad, setBad] = useState({})
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [onfile, setOnfile] = useState(null)
  const [design, setDesign] = useState(false)
  const ready = Boolean(onfile) || design
  const set = (k) => (e) => { setBad(({ [k]: _gone, ...rest }) => rest); setV({ ...v, [k]: e.target.value }) }

  const lookup = async () => {
    const problems = {}
    if (!v.dob) problems.dob = 'The birth date is required'
    if (v.ssn.replace(/\D/g, '').length !== 9) problems.ssn = 'Enter all nine digits'
    setBad(problems)
    if (Object.keys(problems).length) return
    setBusy(true); setErr(null)
    try {
      const me = await api.get('/auth/me/signature')
      const r = await api.post('/auth/me/signature/verify', { dob: v.dob, ssn: v.ssn })
      if (r.signature) { setOnfile(r.signature); setDesign(false) }
      else { setOnfile(null); setDesign(true); setV((s) => ({ ...s, typedname: s.typedname || me.name })) }
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const sign = async () => {
    if (design && !v.typedname.trim()) { setBad({ typedname: 'Type the name you want to sign with' }); return }
    setBusy(true); setErr(null)
    try {
      onSigned(await api.post('/auth/me/signature',
        design ? v : { dob: v.dob, ssn: v.ssn, typedname: '', fontkey: onfile.fontkey }))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const submit = (e) => { e.preventDefault(); if (ready) sign(); else lookup() }

  return (
    <div className="backdrop">
      <form className="modal" role="dialog" aria-modal="true" aria-label={title} onSubmit={submit}>
        <header><h2>{title}</h2>
          <button type="button" className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="body">
          <div className="profileform">
            <label className={`field span-3${bad.dob ? ' bad' : ''}`}>Date Of Birth *
              <input type="date" value={v.dob} onChange={set('dob')} disabled={ready} />
              {bad.dob && <span className="fielderr" role="alert">{bad.dob}</span>}
            </label>
            <label className={`field span-3${bad.ssn ? ' bad' : ''}`}>Social Security Number *
              <SsnInput value={v.ssn} onChange={set('ssn')} disabled={ready} />
              {bad.ssn && <span className="fielderr" role="alert">{bad.ssn}</span>}
            </label>
            {design && (
              <>
                <label className={`field span-4${bad.typedname ? ' bad' : ''}`}>Sign As *
                  <input value={v.typedname} onChange={set('typedname')} />
                  {bad.typedname && <span className="fielderr" role="alert">{bad.typedname}</span>}
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
                  ? 'This becomes your signature on file. It signs everything you sign from now on '
                    + 'and cannot be changed afterwards, so check it before you sign.'
                  : 'Your signature on file. Everything you sign carries this hand.'}
              </p>
            </>
          )}
          {err && <div className="error">{err}</div>}
        </div>
        <footer>
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy}>
            {busy ? (ready ? 'Signing…' : 'Looking…') : ready ? 'Sign' : 'Lookup Signature'}
          </button>
        </footer>
      </form>
    </div>
  )
}
