import { useState } from 'react'
import { Loader2, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import SignatureBlock from './UserSignature.jsx'

// A supervisor signing their own reasonable suspicion training record - 49 CFR 382.603.
//
// Somebody else recording that a supervisor was trained is not the supervisor saying they were.
// The person who decides whether a driver is sent for a test states what training they did and
// puts their name to it, in one act: section 4 of the record and section 6 of it are the same
// statement, and splitting them would leave the acknowledgment standing over an empty section.
//
// Signed in the application rather than through a link anybody holding the URL could use: a
// supervisor is by definition a user of this account, so what makes the signature theirs is
// signing in. The email only brings them here.
export default function SupervisorRecord({ who, onClose, onSigned }) {
  // Somebody else's record is read only, and only the copy they signed. Nobody signs this for
  // anybody, so the unsigned one is not offered here at all.
  const [data, error, reload] = useLoad(
    () => api.get(who ? `/account/users/${who.recordid}/supervisor-record`
                      : '/me/supervisor-record'), [who?.recordid])
  const [signature, setSignature] = useState(null)
  const [f, setF] = useState({ completedon: '', alcoholminutes: '', drugminutes: '',
                               provider: '', note: '', file: null })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return (
      <Modal title="Reasonable Suspicion Training Record" onClose={onClose} width={900}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }

  // What is still stopping this from being signed, named. A finishing action that is simply
  // grey, with the fields it is waiting on below the fold, is a dialog that looks broken -
  // and the person reading it has no way to find out which part it wants.
  const least = data.minutes || 60
  const missing = [
    !f.completedon && 'the date you finished',
    !(Number(f.alcoholminutes) >= least) && `${least} minutes on alcohol misuse`,
    !(Number(f.drugminutes) >= least) && `${least} minutes on controlled substances`,
    !signature && 'your signature',
  ].filter(Boolean)
  const ready = !missing.length

  const sign = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('completedon', f.completedon)
      body.append('alcoholminutes', f.alcoholminutes)
      body.append('drugminutes', f.drugminutes)
      if (f.provider.trim()) body.append('provider', f.provider.trim())
      if (f.note.trim()) body.append('note', f.note.trim())
      if (f.file) body.append('file', f.file)
      await api.post('/me/supervisor-record/sign', body)
      await reload()
      onSigned?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // Already signed: what is shown is the copy that was signed, read back from the signature.
  // The record can change afterwards - a note corrected, a provider renamed - and the words
  // somebody put their name to do not.
  const done = data.signed
  const body = done ? done.html : data.html
  const today = new Date().toISOString().slice(0, 10)

  return (
    <Modal title={who ? `Reasonable Suspicion Training - ${who.name}`
                      : 'Reasonable Suspicion Training Record'}
      onClose={onClose} width={900}
      footer={<>
        {!who && !done && data.owed && (
          <button type="button" className="primary" disabled={busy || !ready} onClick={sign}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Sign It'}
          </button>
        )}
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {done ? (
          <div className="notice good">
            Signed {date(done.signedon)} by {done.typedname}.
          </div>
        ) : data.because ? (
          <div className="notice warn">{data.because}</div>
        ) : who ? null : (
          <div className="notice warn">
            49 CFR 382.603. Read this, say what training you did and sign it. Nobody else can
            sign it for you - a record somebody fills in about you is not you saying you were
            trained.
          </div>
        )}
        {body && (
          <div className="card policyview" dangerouslySetInnerHTML={{ __html: body }} />
        )}
        {!who && !done && data.owed && (
          <>
            <section>
              <h3 className="formsection">The Training You Did</h3>
              <div className="profileform">
                <label className="field span-2">Date completed *
                  <input type="date" value={f.completedon} max={today}
                    onChange={(e) => setF({ ...f, completedon: e.target.value })} />
                </label>
                {/* The floor is on the input, not only in the check that gates the button.
                    382.603(b) is sixty minutes each, and a box that happily takes thirty is a
                    box that invites the one answer the section does not allow. */}
                <label className="field span-2">Alcohol misuse, minutes *
                  <input type="number" min={least} value={f.alcoholminutes}
                    onChange={(e) => setF({ ...f, alcoholminutes: e.target.value })} />
                </label>
                <label className="field span-2">Controlled substances, minutes *
                  <input type="number" min={least} value={f.drugminutes}
                    onChange={(e) => setF({ ...f, drugminutes: e.target.value })} />
                </label>
                <label className="field span-3">Training provider
                  <input value={f.provider} className="upper"
                    onChange={(e) => setF({ ...f, provider: e.target.value.toUpperCase() })} />
                </label>
                <label className="field span-3">Certificate
                  <input type="file"
                    onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
                </label>
                <label className="field span-6">Note
                  <input value={f.note} className="upper"
                    onChange={(e) => setF({ ...f, note: e.target.value.toUpperCase() })} />
                </label>
              </div>
            </section>
            <SignatureBlock signature={signature} onSigned={setSignature}
              label="Signature Of Supervisor" action="Sign" />
          </>
        )}
      </div>
    </Modal>
  )
}

// The one line at the top of every page while it is owed. It is not a nag: a supervisor who has
// not signed is a supervisor whose training the company cannot evidence, and the requirement
// behind it is the one that decides whether anybody here may call a reasonable suspicion test.
export function SupervisorBanner({ onOpen }) {
  return (
    <div className="billbanner" role="alert">
      <ShieldCheck size={16} />
      <span>
        <b>You are a reasonable suspicion supervisor.</b> Your 49 CFR 382.603 training record is
        waiting for your signature.
      </span>
      <button type="button" className="linkbtn edit" onClick={onOpen}>Read and sign it</button>
    </div>
  )
}

function date(value) {
  return value ? new Date(String(value).replace(' ', 'T')).toLocaleDateString('en-US',
    { month: '2-digit', day: '2-digit', year: 'numeric' }) : '-'
}
