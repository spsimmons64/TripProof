import { Printer } from 'lucide-react'
import { useEffect, useState } from 'react'
import { auth } from '../lib/api.js'
import { Modal } from '../admin/common.jsx'
import { printFile } from '../lib/printing.js'
import { useUser } from '../App.jsx'

// Any stored file, read on screen rather than thrown into a browser tab.
//
// A document out of a tab is anonymous: nothing on it says whose file it is, and a license
// photograph looks the same for every company in the country. So every document is read here, under
// a header naming the account it belongs to and the file it came from.
//
// The session is a bearer token rather than a cookie, so the file is fetched and shown from memory.
// `action` is a button the caller wants beside Close - replacing this copy, most often, and `panel`
// is anything the caller wants read alongside the document. Reading a record and saying what it
// concludes is one act, so the two are not two dialogs: the document gives up some of its height and
// the judgement is made under it, with the thing being judged still on screen.
// The document itself, with no dialog around it - for a screen that reads one in place rather than
// opening it. The fetching is the same: the session is a bearer token rather than a cookie, so the
// file is pulled with the header on and shown from memory.
export function DocumentPane({ id, name, className = 'docview' }) {
  const [file, setFile] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let url = null
    let live = true
    fetch(`/api/documents/${id}`, { headers: { Authorization: `Bearer ${auth.get()}` } })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || 'That file could not be opened')
        const blob = await r.blob()
        url = URL.createObjectURL(blob)
        if (live) setFile({ url, pdf: blob.type === 'application/pdf', name: name || 'Document' })
      })
      .catch((e) => live && setErr(e.message))
    return () => { live = false; if (url) URL.revokeObjectURL(url) }
  }, [id, name])

  if (err) return <div className="notice bad">{err}</div>
  if (!file) return <p className="muted">Opening…</p>
  return file.pdf
    ? <embed className={className} src={`${file.url}#toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
        type="application/pdf" />
    : <img className={className} src={file.url} alt={file.name} />
}

// `id` reads a stored document. `path` reads anything else the API will hand back as a
// file - a signed document drawn to PDF on request, which has no stored copy because it
// is rebuilt from the record every time it is read. Everything after the fetch is the
// same either way, which is the point: one viewer, one set of furniture, one print
// button, whatever is being read.
export default function DocumentViewer({ id, path, name, action, panel, onClose, brief }) {
  const user = useUser()
  const [file, setFile] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let url = null
    let live = true
    fetch(path ? `/api${path}` : `/api/documents/${id}`,
          { headers: { Authorization: `Bearer ${auth.get()}` } })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || 'That file could not be opened')
        const blob = await r.blob()
        const filename = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '')?.[1]
        url = URL.createObjectURL(blob)
        if (live) setFile({ url, pdf: blob.type === 'application/pdf', name: name || filename || 'Document' })
      })
      .catch((e) => live && setErr(e.message))
    return () => { live = false; if (url) URL.revokeObjectURL(url) }
  }, [id, path, name])

  // A dialog whose whole job is to read one document gives the document the room: no padding
  // around it, no border, no box inside a box. Where a panel is asked for - a rating to give while
  // the record is on screen - the document takes what is left above it.
  return (
    <Modal title={[user?.accountname, file?.name || name].filter(Boolean).join(' · ')}
      onClose={onClose} width={1120} tall flush
      footer={<>
        {/* The file itself goes to the printer, not the page around it. */}
        {file && (
          <button type="button" onClick={() => printFile(file.url, file.name)}>
            <Printer size={14} /> Print
          </button>
        )}
        {action}
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className={`docstack${panel ? ' haspanel' : ''}`}>
        {/* What this document IS, before the document itself. A dialog whose whole job is to show
            one page has no other room for it, so it rides as a band across the top rather than as
            a box inside the page. */}
        {brief && <p className="dialogbrief docbrief">{brief}</p>}
        {err && <div className="notice bad readstamp">{err}</div>}
        {!err && !file && <p className="muted readstamp">Opening…</p>}
        {file && (file.pdf
          // Something to read, not to operate: the reader's own furniture is turned off.
          ? <embed className="docview docfill" src={`${file.url}#toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
              type="application/pdf" />
          : <img className="docview docfill" src={file.url} alt={file.name} />)}
        {panel && <div className="docpanel"><hr />{panel}</div>}
      </div>
    </Modal>
  )
}
