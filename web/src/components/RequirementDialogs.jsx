import { Eye, Loader2 } from 'lucide-react'
import { Modal } from '../admin/common.jsx'
import DocumentViewer from './DocumentViewer.jsx'
import { date } from '../lib/format.js'

// The requirement dialogs, written once.
//
// A requirement backed by a document reads the way the PHI acknowledgement does, whatever the
// document is - a signed form, a certificate that renews, the questionnaire. Each of those used to
// carry its own copy of this dialog, and the copies drifted: one centred its empty line and one did
// not, one said "Upload Document" and another "+ Add", one put View first and another last. Every
// one of those differences was sent back as "not PHI style". There is one dialog now, so there is
// one style.

// Where the one document on file stands, as the word and the colour the Status column shows.
// Expired beats everything: a certificate that has run out has run out whether or not anybody has
// read it.
export function docStanding({ unread = false, lapsed = false } = {}) {
  if (lapsed) return ['Expired', 'st-expired']
  return unread ? ['Not Reviewed', 'st-ordered'] : ['Reviewed', 'st-active']
}

// One document, laid out as the PHI acknowledgement is.
//
//   on file  - one row, the latest only: Date | Document | <extra columns> | Status. The footer
//              opens it first (View, or Review while nobody has read it), then the dialog's own
//              actions, then Close.
//   empty    - one line in the middle saying so, and the ways to put one on file, then Close.
//
// `columns` are extra cells between Document and Status - an expiry date, where a screening came
// from - each { label, cell }. `notice` stands in for the empty line when there is something to
// say instead, such as a request already sent to the driver.
export function SingleDocumentDialog({ title, brief, err, notice, row, columns = [], onView,
                                       unread = false, actions, emptyActions, onClose,
                                       subject = 'Driver' }) {
  return (
    <Modal title={title} onClose={onClose} brief={brief} width={720}
      footer={row ? <>
        <button type="button" className="primary" onClick={onView}>
          <Eye size={14} /> {unread ? 'Review' : 'View'}
        </button>
        {actions}
        <button type="button" onClick={onClose}>Close</button>
      </> : <>
        {emptyActions}
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {notice}
        {row ? (
          <table className="residencetable recordtable">
            <thead><tr><th>Date</th><th>Document</th>
              {columns.map((c) => <th key={c.label}>{c.label}</th>)}<th>Status</th></tr></thead>
            <tbody>
              <tr>
                <td>{row.on ? date(row.on) : '-'}</td>
                <td>{row.document || title}</td>
                {columns.map((c) => <td key={c.label} className={c.tone}>{c.cell}</td>)}
                <td className={row.status[1]}>{row.status[0]}</td>
              </tr>
            </tbody>
          </table>
        ) : !notice && <div className="gridempty">No {title} On File For This {subject}</div>}
      </div>
    </Modal>
  )
}

// A document opened from a requirement, with the one act that belongs beside it: marking it read.
// `viewing.check` is a document that came in by an upload link and nobody has opened; `viewing.record`
// is a record the engine says this office has still to read. Either way, Mark As Reviewed.
export function ReadingViewer({ viewing, busy, onMarkRead, onReadRecord, onClose }) {
  if (!viewing) return null
  return (
    <DocumentViewer id={viewing.documentid} path={viewing.path} name={viewing.filename}
      onClose={onClose}
      action={<>
        {viewing.check && (
          <button type="button" className="primary" disabled={busy}
            onClick={() => { onMarkRead(viewing.documentid); onClose() }}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
          </button>
        )}
        {!viewing.check && viewing.record && (
          <button type="button" className="primary" disabled={busy}
            onClick={() => { onReadRecord(viewing.record); onClose() }}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
          </button>
        )}
      </>} />
  )
}

// One thing among several the requirement asks about - a license and the driving record pulled on
// it, a previous employer and the inquiry sent to them - laid out as the driving records are: what
// it is in the head with where it stands at the right, its facts in a row beneath, and what can be
// done about it at the foot. Each panel carries its own buttons, because each item is worked on its
// own: ordering Florida's record says nothing about Georgia's.
//
// `facts` are { label, value, tone }; `status` is [word, tone].
export function ItemPanel({ title, status, facts = [], actions }) {
  return (
    <section className="mvrpanel">
      <header>
        <span className="mvrlicense">{title}</span>
        {status && <span className={status[1]}>{status[0]}</span>}
      </header>
      <dl className="mvrfacts">
        {facts.map((f) => (
          <div key={f.label}><dt>{f.label}</dt><dd className={f.tone}>{f.value}</dd></div>
        ))}
      </dl>
      {actions && <footer>{actions}</footer>}
    </section>
  )
}

// A requirement answered item by item: one ItemPanel each, and only Close at the foot - everything
// that acts, acts on one item and sits on its panel. With no items, `empty` says why.
export function PanelsDialog({ title, brief, err, notice, empty, children, onClose, width = 900 }) {
  const items = [].concat(children || []).filter(Boolean)
  return (
    <Modal title={title} onClose={onClose} brief={brief} width={width}
      footer={<button type="button" onClick={onClose}>Close</button>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {notice}
        {items.length ? <div className="mvrpanels">{items}</div> : empty}
      </div>
    </Modal>
  )
}
