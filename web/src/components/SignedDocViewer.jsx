import { Modal } from '../admin/common.jsx'
import DocumentViewer from './DocumentViewer.jsx'

// A document as it was signed: the wording that was on screen at the time, the signature under it,
// and the stamp that says which signing this was. Built from the record rather than from a stored
// copy, so what is read now is what was attested to then.
//
// Shared, because it is opened from the driver's file, from the review queue and from the dashboard
// - and a document that reads differently depending on where it was opened from is not evidence.
// `action` is a button the caller wants beside Close - replacing this copy, most often.
export default function SignedDocViewer({ doc, action, onClose, brief }) {
  // A government form signed on the form itself is a FILE, and the file is what has to be read
  // before anybody accepts it. Shown through the same viewer every other stored document uses.
  if (doc.documentid) {
    return <DocumentViewer id={doc.documentid} name={doc.title} action={action}
      onClose={onClose} />
  }
  return (
    <Modal title={[doc.company, doc.title].filter(Boolean).join(' · ')} onClose={onClose} wide
      brief={brief}
      footer={<>{action}<button type="button" onClick={onClose}>Close</button></>}>
      <style>{doc.css}</style>
      <div className="appview signedview" dangerouslySetInnerHTML={{ __html: doc.html }} />
    </Modal>
  )
}
