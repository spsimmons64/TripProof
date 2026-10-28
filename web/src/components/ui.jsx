import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Ban, Check, CheckCircle2, Clock, Eye, Minus, Undo2, X, XCircle } from 'lucide-react'

// Loads once on mount (and whenever deps change). Returns [data, error, reload].
//
// Never shows one subject's record under another subject's name.
//
// The bug this fixes was quiet and everywhere: `data` survived a change of dependency, so moving
// from one driver to the next rendered the PREVIOUS driver's record until the new request landed -
// underneath the new driver's name. On a fast connection that is a flicker. On a slow one, or when
// the second request fails, it is one person's screening history shown as somebody else's.
//
// A change of subject clears what is held. A refresh of the SAME subject does not, because
// blanking the page on every reload is its own kind of wrong.
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [n, setN] = useState(0)
  const asking = JSON.stringify(deps)
  const asked = useRef(asking)
  if (asked.current !== asking) {
    asked.current = asking
    setData(null)
    setError(null)
  }
  useEffect(() => {
    let live = true
    setError(null)
    fn().then((d) => live && setData(d)).catch((e) => live && setError(e.message))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n])
  return [data, error, () => setN((x) => x + 1)]
}

// `page`: the whole page is waiting - the animated mark, in the middle of the work area.
// `box`: the same mark, in the middle of a dialog whose content is still coming.
export function Loading({ error, page, box }) {
  if (error) return <div className="notice bad"><XCircle size={16} /> {error}</div>
  if (!page && !box) return <div className="muted">Loading…</div>
  return (
    <div className={`pageloading${box ? ' inbox' : ''}`} role="status" aria-label="Loading">
      <svg className="loader" viewBox="0 0 96 96" aria-hidden="true">
        <circle className="ring" cx="48" cy="48" r="44" />
        <circle className="orbit" cx="48" cy="48" r="44" />
        <path className="shield" d="M48 22 L68 29 V46 C68 60 59 69 48 74 C37 69 28 60 28 46 V29 Z" />
        <path className="tick" d="M38 48 L45 55 L58 41" />
      </svg>
    </div>
  )
}

const STATE = {
  current: ['good', CheckCircle2, 'Current'],
  expiring: ['warn', Clock, 'Expiring'],
  expired: ['bad', XCircle, 'Expired'],
  revoked: ['bad', XCircle, 'Revoked'],
  future: ['neutral', Clock, 'Not yet valid'],
  replaced: ['neutral', CheckCircle2, 'Replaced'],
  pass: ['good', CheckCircle2, 'Pass'],
  fail: ['bad', XCircle, 'Fail'],
  nosubject: ['bad', AlertTriangle, 'Unmatched'],
  atrisk: ['bad', AlertTriangle, 'At risk'],
  clean: ['good', CheckCircle2, 'Credentialed'],
  pending: ['neutral', Clock, 'Not checked'],
  stub: ['warn', AlertTriangle, 'Incomplete'],
  unverified: ['warn', AlertTriangle, 'Unverified'],
  draft: ['info', Clock, 'Draft'],
  published: ['good', CheckCircle2, 'Published'],
  retired: ['neutral', Clock, 'Retired'],
  primary: ['good', CheckCircle2, 'Primary source'],
  secondary: ['warn', AlertTriangle, 'Secondary source'],
  active: ['good', CheckCircle2, 'Active'],
  // A driver who has been taken on and is on the roster now.
  hired: ['good', CheckCircle2, 'Active Driver'],
  // A driver's own standing, which is not the same as whether their credentials are in order.
  applicant: ['info', Clock, 'Application'],
  corrections: ['warn', Undo2, 'Corrections'],
  newdriver: ['warn', AlertTriangle, 'New'],
  awaiting: ['warn', Clock, 'Pending'],
  declined: ['bad', XCircle, 'Declined'],
  // Not a stage of employment but a bar on driving, which can sit on a driver at any stage. It
  // takes the place of the status pill in a list, because somebody scanning for a driver to send
  // out needs the thing that stops them before the thing that describes them.
  disqualified: ['bad', Ban, 'Disqualified'],
  inactive: ['bad', XCircle, 'Inactive'],
  setup: ['warn', Clock, 'Setup'],
  disabled: ['neutral', XCircle, 'Disabled'],
  invited: ['warn', Clock, 'Invited'],
  changes: ['warn', Clock, 'Pending changes'],
  warn: ['warn', AlertTriangle, 'Warning'],
  bad: ['bad', XCircle, 'Problem'],
  phi: ['warn', AlertTriangle, 'PHI'],
  staff: ['info', CheckCircle2, 'TripProof staff'],
  info: ['info', CheckCircle2, 'Info'],
  verified: ['good', CheckCircle2, 'Verified'],
  // subscriptions and invoices (Stripe's words)
  trialing: ['info', Clock, 'Free trial'],
  past_due: ['bad', AlertTriangle, 'Past due'],
  unpaid: ['bad', XCircle, 'Unpaid'],
  canceled: ['neutral', XCircle, 'Canceled'],
  incomplete: ['warn', Clock, 'Incomplete'],
  incomplete_expired: ['neutral', XCircle, 'Expired'],
  paid: ['good', CheckCircle2, 'Paid'],
  open: ['warn', Clock, 'Due'],
  void: ['neutral', XCircle, 'Void'],
  uncollectible: ['bad', XCircle, 'Uncollectible'],
}

// Account/user status pills share one width so a column of them lines up whatever the word.
const STATUS_PILLS = new Set(['active', 'hired', 'inactive', 'setup', 'disabled', 'invited',
                              'applicant', 'corrections', 'newdriver', 'awaiting', 'declined',
                              'disqualified'])

export function Badge({ state, children }) {
  const [tone, Icon, label] = STATE[state] || ['neutral', Clock, state]
  return <span className={`badge ${tone}${STATUS_PILLS.has(state) ? ' status' : ''}`}><Icon size={12} /> {children || label}</span>
}

export function Tile({ label, value, sub, className = '' }) {
  return (
    <div className={`card tile ${className}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}


// The status mark beside a requirement: one circle, one colour, one glyph.
//
// There were two of these - the driver's list had this, and the company's list hand-rolled a
// bare <span className="bubble ..."> with its own vocabulary of tones. The second drew nothing
// at all, because the styling was scoped to `.review` and the company page is not inside it. A
// requirement that is satisfied should look satisfied wherever it is listed, so there is one
// component and one map.
export const MARK = {
  satisfied: ['received', Check],
  expiring: ['received', Check],
  notapplicable: ['waived', Minus],
  expired: ['blocked', X],
  failed: ['blocked', X],
  overdue: ['blocked', X],
  ordered: ['ordered', Clock],
  review: ['reading', Eye],
}

export function Bubble({ state = 'satisfied' }) {
  const [tone, Icon] = MARK[state] || ['todo', null]
  return (
    <span className={`bubble ${tone}`} aria-hidden="true">
      {Icon ? <Icon size={16} strokeWidth={tone === 'blocked' ? 3 : 2} /> : '?'}
    </span>
  )
}
