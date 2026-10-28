import { formatPhone } from '../lib/masks.js'
// An email address and a telephone number are the two things on a screen somebody wants to ACT on
// rather than read, and on a telephone or a desktop with a mail client the action is one tap. Every
// place that shows one goes through here, so a number is dialable on the drivers list, in a
// requirement panel and on an employer's record without each of those having to remember.
//
// These are links rather than buttons on purpose, and they are the exception to this application's
// rule that anything which acts is a button. A button acts on the data in TripProof; these hand the
// address or the number to whatever the person uses for mail and telephone calls and do nothing
// here at all. They are an address, which is what a link is for.
//
// A row that opens something when clicked is the awkward case: the whole row navigates, and a link
// inside it must not do both. So the click is stopped here rather than at each call site.
const stop = (e) => e.stopPropagation()

// Only the digits are dialable. A number typed as (727) 555-1212 or 727.555.1212 is the same
// number, and tel: wants it without the furniture; what is SHOWN is left exactly as it was entered.
const dialable = (number) => {
  const digits = String(number).replace(/[^\d+]/g, '')
  if (!digits) return null
  // A leading + is an international prefix somebody typed deliberately, so it is kept.
  return digits.startsWith('+') ? digits : (digits.length === 10 ? `+1${digits}` : digits)
}

export function Email({ address, children }) {
  const to = (address || '').trim()
  if (!to || !to.includes('@')) return <>-</>
  return <a className="contactlink" href={`mailto:${to}`} onClick={stop}>{children || to}</a>
}

export function Phone({ number, children }) {
  const typed = (number || '').trim()
  const to = typed && dialable(typed)
  if (!to) return <>-</>
  // Every number read the same way, (813) 555-1212, however it was typed in.
  const shown = typed.replace(/\D/g, '').replace(/^1/, '').length === 10 ? formatPhone(typed) : typed
  return <a className="contactlink" href={`tel:${to}`} onClick={stop}>{children || shown}</a>
}
