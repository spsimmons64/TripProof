import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useUser } from '../App.jsx'

export const canEdit = (user) => user?.platformrole === 'superadmin'
export const useCanEdit = () => canEdit(useUser())

// Opening a dialog puts the cursor in its first field, so it can be filled without reaching for
// the mouse. The close button in the header is skipped: it is not a field.
export function firstField(box) {
  return box?.querySelector('.body input:not([type="hidden"]):not([type="file"]):not([disabled]),'
    + ' .body select:not([disabled]), .body textarea:not([disabled])')
}

// A dialog is closed by its own controls - Cancel, Close, the X in the header - and by
// nothing else. It used to close on a click that landed on the backdrop, which is a stray
// click away from losing a half-filled form, and a form that takes two minutes to fill is
// not something to put behind a misclick. Removed here and from every hand-rolled dialog
// beside it; if one grows back, this is why it should not.
//
// `flush`: the body has no padding - for a dialog whose content is a grid running edge to edge.
// `tall`: the dialog fills the height it is allowed rather than shrinking to its content - for a
// dialog whose job is a list, where a short list and a long one should not be different shapes.
export function Modal({ title, onClose, children, footer, wide, width, flush, tall, brief }) {
  const box = useRef(null)
  useEffect(() => { firstField(box.current)?.focus() }, [])
  return (
    <div className="backdrop">
      <div ref={box} className={`modal${flush ? ' flush' : ''}${tall ? ' tall' : ''}`} style={width ? { width: `min(${width}px, 100%)` } : wide ? { width: 'min(960px, 100%)' } : undefined} role="dialog" aria-modal="true" aria-label={title}>
        <header><h2>{title}</h2><button className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
        {/* What this dialog is about, before anything it asks for. A requirement's own words,
            sitting between the header and the work, where somebody who has stopped to deal with
            this one thing will actually read them. */}
        <div className="body">{brief && <p className="dialogbrief">{brief}</p>}{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  )
}

// Form state + submit with error capture. `initial` seeds the fields; `submit(values)` returns a promise.
export function useForm(initial, submit) {
  const [values, setValues] = useState(initial)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => {
    const t = e?.target
    const v = t ? (t.type === 'checkbox' ? t.checked : t.value) : e
    setValues((prev) => ({ ...prev, [k]: v }))
  }
  const onSubmit = async (e) => {
    e?.preventDefault()
    setBusy(true); setError(null)
    try { await submit(values) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return { values, setValues, set, error, busy, onSubmit }
}

// Empty strings become null so optional fields clear rather than store "".
export const clean = (obj) => Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, v === '' ? null : v]))

// After creating a login or resending an invitation. With email set up the link went to the user;
// without it (development) the link is shown here, once, to pass on by hand.
export function InvitationSent({ invitation, onClose }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => { try { await navigator.clipboard.writeText(invitation.link); setCopied(true) } catch { /* select manually */ } }
  return (
    <Modal title={invitation.emailed ? 'Invitation Sent' : 'Invitation Link'} onClose={onClose}
      footer={<button className="primary" onClick={onClose}>Done</button>}>
      {invitation.emailed ? (
        <div>An email with a link to set a password is on its way to <b>{invitation.email}</b>. The link works once.</div>
      ) : (
        <>
          <div>Email isn’t set up on this server, so nothing was sent. Give <b>{invitation.email}</b> this link to set a password - it works once:</div>
          <div className="secret" style={{ wordBreak: 'break-all' }}>{invitation.link}</div>
          <div><button onClick={copy}>{copied ? 'Copied' : 'Copy link'}</button></div>
          <div className="small muted">Set SMTP_HOST (and the other SMTP_ settings) so invitations are emailed automatically.</div>
        </>
      )}
    </Modal>
  )
}

export const STATES = ['FL', 'GA', 'AL', 'SC', 'NC', 'TN', 'TX', 'CA', 'NY', 'PA', 'OH', 'IN', 'VA', 'MN']
export const SUBJECT_LABEL = { driver: 'Driver', vehicle: 'Vehicle', company: 'Company', trip: 'Trip leg' }
export const KIND_LABEL = {
  credential: 'Credential on file',
  vehicleage: 'Vehicle age',
  vehiclemileage: 'Vehicle mileage',
  driverage: 'Driver age',
  licenseyears: 'Years licensed',
  tripevidence: 'Trip evidence',
  obligation: 'Obligation (listed, not checked per trip)',
}
