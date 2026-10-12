import { useState } from 'react'
import { X } from 'lucide-react'
import { FieldError } from './LicenseDialog.jsx'

// Signing by somebody outside this company - a previous employer answering a safety performance
// inquiry, an examiner certifying a road test.
//
// They type their name and it is drawn in a hand. What is different from a driver or an office
// user is that nobody proves who they are first, because there is nothing to prove against: they
// have no account here, no date of birth we hold and no Social Security number we could ever ask
// for. So there is no lookup - the name is the signature, exactly as a name on a faxed form is.
//
// One component, so this cannot be rebuilt slightly differently on the next page that needs it.

const FONTS = [['modern', 'Modern'], ['signature', 'Inked'], ['quick', 'Quick'],
               ['hand', 'Handwritten'], ['cursive', 'Cursive'], ['fine', 'Fine'], ['bold', 'Bold']]

export default function OutsideSignDialog({ title = 'Sign', certification, name,
                                            onSigned, onClose }) {
  const [typedname, setTypedname] = useState(name || '')
  const [fontkey, setFontkey] = useState('modern')
  const [bad, setBad] = useState(null)

  const sign = (e) => {
    e.preventDefault()
    if (!typedname.trim()) { setBad('Type the name you want to sign with'); return }
    onSigned(typedname.trim().toUpperCase(), fontkey)
  }

  return (
    <div className="backdrop plain">
      <form className="modal" role="dialog" aria-modal="true" aria-label={title} onSubmit={sign}>
        <header><h2>{title}</h2>
          <button type="button" className="iconbtn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>
        <div className="body">
          <div className="stack">
            {certification && <p className="muted small">{certification}</p>}
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
