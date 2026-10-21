import { useState } from 'react'
import { Printer } from 'lucide-react'
import { Modal } from '../admin/common.jsx'
import { printHtml } from '../lib/printing.js'
import DocumentViewer from './DocumentViewer.jsx'

// A document as it was signed: the wording that was on screen at the time, the signature under it,
// and the stamp that says which signing this was. Built from the record rather than from a stored
// copy, so what is read now is what was attested to then.
//
// Shared, because it is opened from the driver's file, from the review queue and from the dashboard
// - and a document that reads differently depending on where it was opened from is not evidence.
// `action` is a button the caller wants beside Close - replacing this copy, most often.
export default function SignedDocViewer({ doc, action, onClose, brief, asPdf }) {
  const [blocked, setBlocked] = useState(false)
  // A government form signed on the form itself is a FILE, and the file is what has to be read
  // before anybody accepts it. Shown through the same viewer every other stored document uses.
  if (doc.documentid) {
    return <DocumentViewer id={doc.documentid} name={doc.title} action={action}
      onClose={onClose} />
  }
  // Drawn as a PDF by the server rather than laid out here as a page.
  //
  // A document read on screen and the same document printed have to be the same document, and
  // HTML in a dialog reflows to whatever window it is in - which is not what anybody will put in
  // front of an auditor. The PDF is already how this file leaves the building, in the audit
  // packet and in the driver's own copy, so reading it this way is reading what will be sent.
  if (asPdf) {
    // Just the title: the viewer puts the company in front of whatever it is given, and a name
    // carrying it already comes out saying it twice.
    return <DocumentViewer path={asPdf} name={doc.title} action={action} onClose={onClose} />
  }
  return (
    <Modal title={[doc.company, doc.title].filter(Boolean).join(' · ')} onClose={onClose} wide
      brief={brief}
      footer={<>
        {/* Rebuilt from the record, so what prints is the markup and the stylesheet that are on
            screen - not a second copy of them kept for printing. */}
        <button type="button" onClick={() => setBlocked(!printHtml(
          [doc.company, doc.title].filter(Boolean).join(' - '), doc.css, doc.html))}>
          <Printer size={14} /> Print
        </button>
        {action}<button type="button" onClick={onClose}>Close</button>
      </>}>
      {blocked && (
        <div className="notice warn">
          The print window was blocked. Allow pop-ups for this site and try again.
        </div>
      )}
      <style>{doc.css}</style>
      <div className="appview signedview" dangerouslySetInnerHTML={{ __html: doc.html }} />
    </Modal>
  )
}
