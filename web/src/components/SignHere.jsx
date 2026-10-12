import { useState } from 'react'
import PublicSignDialog from './PublicSignDialog.jsx'

// The signature block on a public document, whole: the line, the date, the stamp under it, and the
// two acts in the order they go in.
//
//   Sign      proves who you are, looks up the signature on file, and puts it on the page
//   Submit    files the document
//
// One component, because this has been built three times on three pages and come out differently
// every time - a hand drawn before anybody signed, a dialog that filed the document itself, a
// signature with no stamp behind it. A page that signs something uses this and gets the process;
// it does not get to assemble its own.

// `proven` is a date of birth and Social Security number this session has ALREADY checked. Where
// it is given, signing a second document does not ask for them again: the person signing the W-4
// proved who they were a moment ago to sign the I-9, and asking twice inside one sitting is a
// wall where there should be a page turn. The signing act itself is unchanged - the driver still
// asks for their signature on each document, and each one gets its own stamp.
export default function SignHere({ lookup, onSubmit, label = 'Signature Of Driver',
                                   action = 'Sign This Document', submit = 'Submit Document',
                                   busy, hint, proven, onUnlocked }) {
  const [signing, setSigning] = useState(false)
  const [signed, setSigned] = useState(null)
  const [err, setErr] = useState(null)

  return (
    <>
      <div className="signblock">
        <div className="signfields">
          <div className="signbox">
            <span className="signlabel">{label}</span>
            {/* Blank until it is signed. A drawn name on an unsigned page says the page is
                signed, which it is not. */}
            <div className="signline">
              {signed && (
                <>
                  <span className={`sigink font-${signed.fontkey}`}>
                    {signed.typedname || signed.onfile?.typedname}
                  </span>
                  {/* What is behind the hand: which signature on file this is, whose it is, when
                      it was adopted and how it was proved. */}
                  {signed.onfile && (
                    <span className="sigstamp">
                      <span>Signed electronically · {signed.onfile.signername}</span>
                      <span>{signed.onfile.recordid}</span>
                      <span>
                        Adopted {String(signed.onfile.adoptedon).replace('T', ' ').slice(0, 19)} UTC
                        {' · IP '}{signed.onfile.ip || 'not recorded'}
                      </span>
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="signbox datebox">
            <span className="signlabel">Signature Date</span>
            <div className="signline">
              {signed ? new Date().toLocaleDateString('en-US') : null}
            </div>
          </div>
        </div>
        <div className="field signaction">
          {!signed ? (
            <button type="button" className="primary" disabled={busy}
              onClick={async () => {
                if (!proven?.dob || !proven?.ssn) { setSigning(true); return }
                setErr(null)
                try {
                  const onfile = await lookup(proven)
                  if (!onfile) { setSigning(true); return }   // none on file: design one
                  setSigned({ dob: proven.dob, ssn: proven.ssn, typedname: '',
                              fontkey: onfile.fontkey, design: false, onfile })
                }
                catch (e) { setErr(e.message); setSigning(true) }
              }}>
              {action}
            </button>
          ) : (
            <button type="button" className="primary" disabled={busy}
              onClick={() => onSubmit(signed)}>
              {busy ? 'Submitting…' : submit}
            </button>
          )}
        </div>
      </div>
      {err && <p className="small bad">{err}</p>}
      {hint && (
        <p className="small muted">
          {signed ? 'Check your signature above, then submit the document.' : hint}
        </p>
      )}
      {signing && (
        <PublicSignDialog title={action} onClose={() => setSigning(false)}
          lookup={lookup}
          onSigned={async (how) => {
            setSigned(how)
            // Proving it here opens the gate for the rest of this visit, exactly as the driver
            // application does: the first signature asks, the ones after it do not.
            onUnlocked?.()
          }} />
      )}
    </>
  )
}
