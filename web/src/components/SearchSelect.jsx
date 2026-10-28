import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'

// A select that can be typed into: each letter narrows the list to the entries that contain what
// has been typed, anywhere in them - "BAY" finds BAYFRONT HOSPITAL and 100 BAY ST alike. Up and
// down move through what is left, Enter takes it, Escape puts things back as they were. The list
// stays shut until something is typed (or the down arrow pressed): clicking into the field only
// puts the cursor there.
//
// `items` are records with a `recordid`; `label(item)` is how each reads in the list and in the field.
export default function SearchSelect({ items, value, onChange, label, placeholder = 'Choose' }) {
  const [open, setOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const [typed, setTyped] = useState('')
  const [at, setAt] = useState(0)
  const box = useRef(null)
  const list = useRef(null)
  const chosen = items.find((i) => i.recordid === value)
  const shown = typed ? items.filter((i) => label(i).toUpperCase().includes(typed)) : items

  // Clicking anywhere else closes it without choosing.
  useEffect(() => {
    if (!open) return undefined
    const away = (e) => { if (!box.current?.contains(e.target)) { setOpen(false); setTyped('') } }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])
  // The highlighted entry stays in view as the arrows move it.
  useEffect(() => { list.current?.children[at]?.scrollIntoView({ block: 'nearest' }) }, [at, open])

  const take = (item) => { onChange(item.recordid); setOpen(false); setTyped('') }
  const key = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setAt((n) => Math.min(n + 1, shown.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setAt((n) => Math.max(n - 1, 0)) }
    else if (e.key === 'Enter') { if (open && shown[at]) { e.preventDefault(); take(shown[at]) } }
    else if (e.key === 'Escape') { setOpen(false); setTyped('') }
  }
  return (
    <div className="searchselect" ref={box}>
      <input value={open || focused ? typed : chosen ? label(chosen) : ''}
        placeholder={chosen ? label(chosen) : placeholder}
        className="upper" role="combobox" aria-expanded={open} aria-autocomplete="list"
        onFocus={() => setFocused(true)} onBlur={() => { setFocused(false); if (!open) setTyped('') }}
        onChange={(e) => { const t = e.target.value.toUpperCase(); setTyped(t); setOpen(Boolean(t)); setAt(0) }}
        onKeyDown={key} />
      <ChevronDown size={16} className="searchselectarrow" aria-hidden="true" />
      {open && (
        <ul className="searchselectlist" role="listbox" ref={list}>
          {shown.length ? shown.map((i, n) => (
            <li key={i.recordid} role="option" aria-selected={i.recordid === value}
              className={[n === at && 'at', i.recordid === value && 'on'].filter(Boolean).join(' ') || undefined}
              onMouseEnter={() => setAt(n)} onMouseDown={(e) => { e.preventDefault(); take(i) }}>
              {label(i)}
            </li>
          )) : <li className="none">Nothing matches {typed}</li>}
        </ul>
      )}
    </div>
  )
}
