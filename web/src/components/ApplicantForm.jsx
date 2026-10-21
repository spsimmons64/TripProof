import { useState } from 'react'
import { ClipboardCheck, Loader2 } from 'lucide-react'

// The driver fills in their own details, here, rather than going somewhere else to do it.
//
// backgroundchecks.com is told an email address and nothing more: no name, no date of birth, no
// Social Security number. They email the applicant a link, and the applicant enters those
// themselves along with their FCRA authorisation. That is the right way round - the disclosure is
// the applicant's to give - but it means the screening sits untouched until the driver opens an
// email, and a driver standing at the counter on their first day is the easiest moment there will
// ever be to get it done.
//
// So their widget is opened here instead. It is their form, their fields and their storage: what
// the driver types goes to them and never through TripProof, which is the whole point. All this
// holds is the report key, which TripProof already has.

// Loaded once per page and shared. Two copies of a widget script on one document is how you get
// two modals, and the second one is always the one that will not close.
const loaded = {}

function load(src) {
  if (!src) return Promise.reject(new Error('Screening is not switched on for this installation.'))
  if (loaded[src]) return loaded[src]
  loaded[src] = new Promise((resolve, reject) => {
    const tag = document.createElement('script')
    tag.src = src
    tag.async = true
    tag.onload = () => resolve()
    tag.onerror = () => {
      // A failed load must not be remembered as a load, or every later press fails silently
      // against a promise that resolved to nothing.
      delete loaded[src]
      reject(new Error('The application form could not be loaded. Check the connection and try '
                       + 'again - nothing has been lost.'))
    }
    document.head.appendChild(tag)
  })
  return loaded[src]
}

export default function ApplicantForm({ script, reportKey, onDone }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const open = async () => {
    setBusy(true); setErr(null)
    try {
      await load(script)
      const widget = window.ClearChecksApplicantWidget?.init({
        reportKey,
        onSuccess: (got) => {
          setBusy(false)
          // They answer with the key and whether the applicant got to the end of it. A form
          // closed half-finished is not a finished application, and saying it is would put a
          // driver on the road against a screening nobody has run.
          onDone?.(got?.application_complete ? 'complete' : 'partial', got)
        },
        onClose: () => { setBusy(false); onDone?.('closed') },
        onError: (e) => {
          setBusy(false)
          setErr(e?.message || 'The application form could not be opened.')
        },
      })
      if (!widget) throw new Error('The application form did not load properly. Try again.')
      widget.open()
    } catch (e) {
      setErr(e.message); setBusy(false)
    }
  }

  return (
    <>
      {err && <div className="notice bad">{err}</div>}
      <button type="button" disabled={busy || !script || !reportKey} onClick={open}>
        {busy ? <Loader2 size={15} className="spin" /> : <ClipboardCheck size={14} />}
        {' '}Fill It In Now
      </button>
    </>
  )
}
