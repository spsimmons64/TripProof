// How text is typed, everywhere, once.
//
// Every free-text field in the application is entered and stored UPPER CASE, and every email
// address lower case. That was being done field by field - a `.toUpperCase()` hung on one onChange
// in five, which meant a form written last week obeyed the rule and one written this morning did
// not, and nobody could tell by looking. The rule now lives in one place and applies to every
// input the application renders, including the ones nobody has written yet.
//
// It runs on the DOM event rather than in each component's state, because that is the only point
// every form already shares. React reads the field's value out of the DOM when the event reaches
// it, so rewriting the value here - before the event has bubbled anywhere - is what the component
// receives and what it ultimately saves.

// Fields whose value is not prose and would be destroyed by having its case changed. A secret is
// already excluded by being a password, but a publishable key, a merchant id and an endpoint are
// typed in the open and matter character for character.
const EXACT = new Set(['password', 'number', 'date', 'datetime-local', 'time', 'month', 'week',
                       'file', 'checkbox', 'radio', 'range', 'color', 'hidden', 'submit',
                       'button', 'image', 'reset'])

// Read off the field itself: an address or a web address is lower case wherever it appears.
const LOWER = /e-?mail|website|\burl\b|domain|endpoint/i

function wanted(el) {
  // `data-case` is the field saying so itself: "none" where the value is a key or a code the
  // other end will compare literally, "lower" or "upper" to settle it outright.
  const said = el.dataset?.case
  if (said === 'none') return null
  if (said === 'lower') return 'lower'
  if (said === 'upper') return 'upper'

  const tag = el.tagName
  if (tag !== 'INPUT' && tag !== 'TEXTAREA') return null
  if (tag === 'INPUT') {
    const type = (el.getAttribute('type') || 'text').toLowerCase()
    if (EXACT.has(type)) return null
    if (type === 'email') return 'lower'
  }
  // What the field is called, in every way it says so. Most of this application's inputs carry no
  // name or id at all - what they are is written in the <label> wrapped around them, so that is
  // where "Website" and "Contact Email" are actually found.
  const says = `${el.name || ''} ${el.id || ''} ${el.getAttribute('placeholder') || ''} `
    + (el.closest('label')?.textContent || '')
  return LOWER.test(says) ? 'lower' : 'upper'
}

// React stores the value it last rendered on the node and skips the change when what it reads back
// is the same string, so the setter it shadowed has to be the one used - otherwise a field that is
// already upper case silently stops reporting changes.
const nativeValue = (el) => Object.getOwnPropertyDescriptor(
  el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
  'value').set

export function typedInUpperCase(event) {
  const el = event.target
  if (!el || typeof el.value !== 'string') return
  const want = wanted(el)
  if (!want) return
  const cased = want === 'lower' ? el.value.toLowerCase() : el.value.toUpperCase()
  if (cased === el.value) return
  // Case changes nothing about length, so the caret and any selection are put back exactly where
  // the typist left them - otherwise every keystroke throws them to the end of the field.
  const { selectionStart: a, selectionEnd: b } = el
  nativeValue(el).call(el, cased)
  try { el.setSelectionRange(a, b) } catch { /* a type that has no caret to restore */ }
}
