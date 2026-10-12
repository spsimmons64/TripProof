import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Modal } from '../admin/common.jsx'

// Taking back a record that was filed against the wrong driver.
//
// One component for the three places it happens - a drug or alcohol test, an accident, a day of
// duty hours - because it is one act with one shape: say what will be undone, require a reason,
// keep the row.
//
// WITHDRAWN, NOT DELETED, in all three cases. Each of these is a record a regulation asks the
// carrier to KEEP: 49 CFR 382.401 for the testing records, 390.15(b) for the accident register,
// 395.8(k)(1) for records of duty status. A row that simply disappears out of one of those is
// indistinguishable from a cover-up, while a row marked withdrawn, with a date, a person and a
// reason against it, reads as the correction it is.
export default function WithdrawDialog({ title, what, warn, busy, err, onConfirm, onClose }) {
  const [why, setWhy] = useState('')
  return (
    <Modal title={title} onClose={onClose} width={620}
      footer={<>
        <button type="button" className="primary" disabled={busy || why.trim().length < 3}
          onClick={() => onConfirm(why.trim().toUpperCase())}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Withdraw'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="notice warn">
          {what}{warn ? ` ${warn}` : ''}
        </div>
        <div className="profileform">
          <label className="field span-6">Why *
            <input value={why} className="upper" autoFocus
              onChange={(e) => setWhy(e.target.value.toUpperCase())} />
          </label>
        </div>
        <div className="small muted">
          The record is kept and marked withdrawn, with this reason against it. It is not deleted.
        </div>
      </div>
    </Modal>
  )
}

// What the withdrawal actually changed. Shown rather than assumed: the one that matters is a
// return-to-duty test, where taking it back puts a bar BACK on a driver who was clear to work
// a moment ago, and nobody should have to work that out for themselves.
export function WithdrawnDialog({ undone, note, onClose }) {
  return (
    <Modal title="Withdrawn" onClose={onClose} width={620}
      footer={<button type="button" onClick={onClose}>Close</button>}>
      <div className="stack">
        {!undone?.length ? (
          <div className="notice">
            Withdrawn. Nothing else on this driver's file was relying on it.
          </div>
        ) : (
          <div className="notice warn stack">
            <div><b>What has changed</b></div>
            {undone.map((u) => <div key={u} className="small">{u}</div>)}
          </div>
        )}
        {note && <div className="small muted">{note}</div>}
      </div>
    </Modal>
  )
}
