import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Modal } from '../admin/common.jsx'

// Why a result already on the record is being changed. A correction is kept with what it replaced,
// who made it and why - so the why is asked for, every time.
export default function ReasonDialog({ title, onSave, onClose }) {
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const save = async () => {
    setBusy(true); setErr(null)
    try { await onSave(why.trim()); onClose() } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal title={title} onClose={onClose} width={560}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !why.trim()} onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <label className="field">Reason *
          <textarea value={why} className="upper"
            onChange={(e) => setWhy(e.target.value.toUpperCase())} autoFocus />
        </label>
      </div>
    </Modal>
  )
}
