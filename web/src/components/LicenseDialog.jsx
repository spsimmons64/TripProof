import { useEffect, useRef, useState } from 'react'
import { AlertCircle, X } from 'lucide-react'
import { STATE_NAMES } from '../lib/states.js'
import { UpperInput } from './MaskedInput.jsx'

// A driver's license, asked for the same way wherever it is asked for.
//
// The applicant fills this in on the way through their application, and the office fills the same
// thing in when it corrects a record or adds a license somebody forgot to mention. They were two
// forms asking for the same document in different words, which is how a file ends up holding a
// class the office chose from a free-text box and endorsements nobody validated. One form now.
//
// The number is typed twice because it is the one field nobody can check against anything: a
// transposed digit reads perfectly and matches no record at the state.

export const LICENSE_CLASSES = [
  ['A', 'Class A - Commercial, combination vehicles'],
  ['B', 'Class B - Commercial, heavy straight vehicles'],
  ['C', 'Class C - Small vehicles'],
  ['D', 'Class D - Non-commercial operator'],
  ['E', 'Class E - Operator'],
  ['M', 'Class M - Motorcycle'],
  ['O', 'Other'],
]

export const ENDORSEMENTS = [
  ['H', 'H - Placarded Hazmat'],
  ['T', 'T - Double/Triple Trailers'],
  ['N', 'N - Tank Vehicles'],
  ['S', 'S - School Bus'],
  ['P', 'P - Passengers'],
  ['X', 'X - Placarded Hazmat & Tank Vehicles'],
]

export function StateSelect({ value, onChange }) {
  return (
    <select value={value || ''} onChange={onChange}>
      <option value="">Choose</option>
      {Object.entries(STATE_NAMES).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
    </select>
  )
}

export function FieldError({ message }) {
  if (!message) return null
  return <span className="fielderr" role="alert"><AlertCircle size={13} aria-hidden="true" /> {message}</span>
}

export function useFirstField() {
  const box = useRef(null)
  useEffect(() => {
    box.current?.querySelector('.body input:not([type="hidden"]):not([disabled]),'
      + ' .body select:not([disabled]), .body textarea:not([disabled])')?.focus()
  }, [])
  return box
}

// `onAdd` receives the license with `endorsements` as an array of codes, and - where the caller
// asked for copies - the front and back files chosen, which it stores in its own way.
export const BLANK_LICENSE = { number: '', confirm: '', state: '', issued: '', expires: '',
                               originalissued: '', classification: '', commercial: '',
                               endorsements: [] }

// Whether it is a CDL, as the form holds it ('yes' / 'no' / '') and as the record keeps it.
export const commercialOf = (v) => (v === 'yes' || v === true ? true : v === 'no' || v === false ? false : null)
export const commercialWord = (v) => (v === true || v === 'yes' ? 'yes' : v === false || v === 'no' ? 'no' : '')

// What is wrong with a license as filled in, as {field: message}. Here rather than in the dialog
// because the driver fills the same form in from their own link, and two copies of these rules
// would be two definitions of a valid license.
export function licenseProblems(r) {
  const required = [['number', 'The license number is required'], ['state', 'The state is required'],
                    ['confirm', 'Enter the license number again'],
                    ['issued', 'The issue date is required'],
                    ['expires', 'The expiration date is required'],
                    ['classification', 'The classification is required'],
                    ['commercial', 'Say whether this is a commercial license']]
  const problems = Object.fromEntries(
    required.filter(([k]) => !String(r[k] ?? '').trim()).map(([k, m]) => [k, m]))
  if (!problems.confirm && r.number.trim() !== r.confirm.trim()) problems.confirm = 'The two do not match'
  if (!problems.expires && r.issued && r.expires < r.issued) problems.expires = 'Expires comes after issued'
  if (r.originalissued && r.issued && r.originalissued > r.issued) {
    problems.originalissued = 'The original issue date comes before the issue date'
  }
  return problems
}

// The fields themselves, with no dialog around them - the office adds a license in a modal and a
// driver fills the same thing in on a page of their own, and a license is a license either way.
export function LicenseFields({ r, setR, bad, setBad, copies = false,
                               front, setFront, back, setBack }) {
  const set = (k) => (e) => {
    setBad(({ [k]: _gone, ...rest }) => rest)
    setR({ ...r, [k]: e.target.value })
  }
  const toggle = (code) => () => setR({ ...r,
    endorsements: r.endorsements.includes(code)
      ? r.endorsements.filter((c) => c !== code) : [...r.endorsements, code] })
  // Endorsements only exist on a commercial license, so that answer decides whether they can be
  // picked. Asked rather than read off the class: Georgia's ordinary license is a Class C.
  const commercial = r.commercial === 'yes'
  const setClass = (e) => {
    setBad(({ classification: _gone, ...rest }) => rest)
    setR({ ...r, classification: e.target.value })
  }
  const setCommercial = (e) => {
    setBad(({ commercial: _gone, ...rest }) => rest)
    setR({ ...r, commercial: e.target.value,
      endorsements: e.target.value === 'yes' ? r.endorsements : [] })
  }
  const field = (k, label, span, node) => (
    <label className={`field span-${span}${bad[k] ? ' bad' : ''}`}>
      {label}{node}<FieldError message={bad[k]} />
    </label>
  )
  return (
    <>
      {field('number', 'License Number *', 3, <UpperInput value={r.number} onChange={set('number')} />)}
      {field('confirm', 'Re-Enter License Number *', 3,
        <UpperInput value={r.confirm} onChange={set('confirm')} onPaste={(e) => e.preventDefault()} />)}
      {field('state', 'License State *', 2, <StateSelect value={r.state} onChange={set('state')} />)}
      {field('issued', 'Issue Date *', 2, <input type="date" value={r.issued} onChange={set('issued')} />)}
      {field('expires', 'Expire Date *', 2, <input type="date" value={r.expires} onChange={set('expires')} />)}
      {/* Printed on some cards beside the issue date, which is usually the latest renewal. It is
          when the driver was first licensed, and so how long they have been driving. */}
      {field('originalissued', 'Original Issue Date (If Shown)', 2,
        <input type="date" value={r.originalissued || ''} onChange={set('originalissued')} />)}
      {field('classification', 'Classification *', 4, (
        <select value={r.classification} onChange={setClass}>
          <option value="">Choose</option>
          {LICENSE_CLASSES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
        </select>
      ))}
      {field('commercial', 'Commercial License (CDL) *', 2, (
        <select value={commercialWord(r.commercial)} onChange={setCommercial}>
          <option value="">Choose</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      ))}
      <div className={`span-6 endorsements${commercial ? '' : ' off'}`}>
        <span className="radioask">Endorsements</span>
        <div className="endorsementgrid">
          {ENDORSEMENTS.map(([code, label]) => (
            <label key={code}>
              <input type="checkbox" checked={r.endorsements.includes(code)}
                onChange={toggle(code)} disabled={!commercial} /> {label}
            </label>
          ))}
        </div>
      </div>
      {/* The office files the copies with the license; an applicant sends them at the step that
          asks for them, so the inputs are only here where they are wanted. */}
      {copies && (
        <>
          <label className="field span-3">Copy - Front
            <input type="file" accept="image/*,application/pdf"
              onChange={(e) => setFront(e.target.files?.[0] || null)} /></label>
          <label className="field span-3">Copy - Back
            <input type="file" accept="image/*,application/pdf"
              onChange={(e) => setBack(e.target.files?.[0] || null)} /></label>
        </>
      )}
    </>
  )
}


export default function LicenseDialog({ onAdd, onClose, initial, copies = false }) {
  // Correcting one starts from what is there, with the number already in both boxes.
  // Correcting one starts from what is there, with the number already in both boxes.
  const [r, setR] = useState({ ...BLANK_LICENSE,
                               ...(initial ? { ...initial, confirm: initial.number,
                                               commercial: commercialWord(initial.commercial) } : {}) })
  const [front, setFront] = useState(null)
  const [back, setBack] = useState(null)
  const [bad, setBad] = useState({})
  const box = useFirstField()
  const save = (e) => {
    e.preventDefault()
    const problems = licenseProblems(r)
    setBad(problems)
    if (!Object.keys(problems).length) {
      const { confirm: _typedtwice, ...license } = r
      onAdd(license, { front, back })
    }
  }
  return (
    <div className="backdrop">
      <form ref={box} className="modal" role="dialog" aria-modal="true" aria-label="Add a license" onSubmit={save}>
        <header><h2>{initial ? 'Correct This License' : "Driver's License"}</h2>
          <button type="button" className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="body">
          <div className="profileform">
            <LicenseFields r={r} setR={setR} bad={bad} setBad={setBad} copies={copies}
              front={front} setFront={setFront} back={back} setBack={setBack} />
          </div>
        </div>
        <footer><button type="button" onClick={onClose}>Cancel</button>
          <button className="primary">{initial ? 'Save' : 'Add'}</button></footer>
      </form>
    </div>
  )
}
