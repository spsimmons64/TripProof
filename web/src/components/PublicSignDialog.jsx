import { useState } from 'react'
import { X } from 'lucide-react'
import { SsnInput } from './MaskedInput.jsx'
import { FieldError, useFirstField } from './LicenseDialog.jsx'
import { DEFAULT_FONT, SIGNATURE_FONT_PAIRS } from '../lib/signatureFonts.js'

// Signing, on a public link, in the two stages it is in everywhere else in this software: prove
// who you are, then sign. The signature on file is not shown - and cannot be used - until the date
// of birth and Social Security number have been checked against this driver by the server. A
// driver who has never signed anything here designs one, and that is the only time there is
// anything to type.
//
// One component for every public page that signs, so the act cannot drift into something else on
// one of them: `lookup` proves the pair and answers with the signature on file (or none), and
// `onSigned` is handed what to sign with.

const FONTS = SIGNATURE_FONT_PAIRS

export default function PublicSignDialog({ title = 'Sign Document', lookup, onSigned, onClose }) {
  const [v, setV] = useState({ dob: '', ssn: '', typedname: '', fontkey: DEFAULT_FONT })
  const [bad, setBad] = useState({})
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [onfile, setOnfile] = useState(null)     // the signature the lookup found, if any
  const [design, setDesign] = useState(false)    // designing one, because there is none
  const box = useFirstField()
  const ready = Boolean(onfile) || design
  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setV({ ...v, [k]: e.target.value })
  }

  const look = async () => {
    const problems = {}
    if (!v.dob) problems.dob = 'The birth date is required'
    if (v.ssn.replace(/\D/g, '').length !== 9) problems.ssn = 'Enter all nine digits'
    setBad(problems)
    if (Object.keys(problems).length) return
    setBusy(true); setErr(null)
    try {
      const found = await lookup({ dob: v.dob, ssn: v.ssn })
      if (found) { setOnfile(found); setDesign(false) }
      else { setOnfile(null); setDesign(true) }
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const sign = async () => {
    if (design && !v.typedname.trim()) {
      setBad({ typedname: 'Type the name you want to sign with' })
      return
    }
    setBusy(true); setErr(null)
    try {
      // The signature on file travels with the signing, so the page can show what was signed
      // with - which signature it is, whose, and how it was proved - and not merely how it looks.
      await onSigned({ dob: v.dob, ssn: v.ssn,
        typedname: design ? v.typedname : '',
        fontkey: design ? v.fontkey : onfile.fontkey, design, onfile })
      onClose()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const submit = (e) => { e.preventDefault(); if (ready) sign(); else look() }

  return (
    <div className="backdrop plain">
      <form ref={box} className="modal" role="dialog" aria-modal="true" aria-label={title}
        onSubmit={submit}>
        <header><h2>{title}</h2>
          <button type="button" className="iconbtn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>
        <div className="body">
          <div className="profileform">
            <label className={`field span-3${bad.dob ? ' bad' : ''}`}>Date Of Birth *
              <input type="date" value={v.dob} onChange={set('dob')} disabled={ready} />
              <FieldError message={bad.dob} />
            </label>
            <label className={`field span-3${bad.ssn ? ' bad' : ''}`}>Social Security Number *
              <SsnInput value={v.ssn} onChange={set('ssn')} disabled={ready} />
              <FieldError message={bad.ssn} />
            </label>
            {design && (
              <>
                <label className={`field span-4${bad.typedname ? ' bad' : ''}`}>Sign As *
                  <input value={v.typedname} className="upper"
                    onChange={(e) => {
                      setBad(({ typedname: _g, ...rest }) => rest)
                      setV({ ...v, typedname: e.target.value.toUpperCase() })
                    }} />
                  <FieldError message={bad.typedname} />
                </label>
                <label className="field span-2">Style
                  <select value={v.fontkey} onChange={set('fontkey')}>
                    {FONTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
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
                  ? 'This becomes your signature on file. It cannot be changed afterwards, so '
                    + 'check it before you sign.'
                  : 'Your signature on file. This document is signed with it.'}
              </p>
            </>
          )}
          {err && <div className="error">{err}</div>}
        </div>
        <footer>
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy}>
            {busy ? 'Looking…' : ready ? 'Sign Document' : 'Lookup Signature'}
          </button>
        </footer>
      </form>
    </div>
  )
}
