// Requirement dialogs - AnnualReview. Moved out of
// Requirements.jsx, which had grown too large to work in safely.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../../../lib/states.js'
import { api } from '../../../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../../../lib/live.js'
import { date } from '../../../lib/format.js'
import { Bubble, Loading, useLoad } from '../../../components/ui.jsx'
import { Modal } from '../../../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../../../components/Pager.jsx'
import { useUser } from '../../../App.jsx'
import SignatureBlock from '../../../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../../../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../../../components/DocumentViewer.jsx'
import ApplicantForm from '../../../components/ApplicantForm.jsx'
import SignedDocViewer from '../../../components/SignedDocViewer.jsx'
import { PhoneInput } from '../../../components/MaskedInput.jsx'
import LicenseDialog from '../../../components/LicenseDialog.jsx'
import TestDialog from '../../../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../../../components/WithdrawDialog.jsx'
import { Email, Phone } from '../../../components/Contact.jsx'
import { BLANK_CRASH, CRASH_STATE, FROM_ROW, unread, when } from '../common.jsx'
import { DriverLicenses } from '../Licenses.jsx'
import { ProhibitionPanel } from '../Testing.jsx'
import { CrashDialog } from '../Accidents.jsx'
import { DETAIL, MVR_FINDING } from './common.jsx'

// Completing the annual review - 49 CFR 391.25.
//
// The driving record is not the requirement. 391.25(a) asks the carrier to obtain one; 391.25(b)
// asks somebody to CONSIDER it and decide whether the driver still meets the minimum
// requirements; 391.25(c)(2) asks for that determination in writing with the name of the person
// who made it. The panel could open a review and show the records, and then there was nothing to
// press: the review sat open for ever and the one act the regulation actually asks for could not
// be performed at all.
//
// Signed rather than clicked, with the reviewer's own signature, for the same reason Section 2 of
// the I-9 is: a name is what the rule asks for, and a button press is not a name.
function CompleteAnnualReview({ id, review, records, coverage, findings, needsreason,
                               onClose, onDone, onOrder }) {
  const [finding, setFinding] = useState('qualified')
  const [note, setNote] = useState('')
  const [signature, setSignature] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const unseen = (records || []).filter((x) => !x.norecord && x.reviewstate !== 'reviewed')
  const states = coverage?.required || []
  const missing = coverage?.missing || []
  const ready = Boolean(coverage?.complete)
  // Two findings are unreadable without a reason, and the server refuses them without one.
  const mustsay = (needsreason || []).includes(finding)

  const fileIt = async () => {
    setBusy(true); setErr(null)
    try {
      const body = new FormData()
      body.append('reviewid', review.recordid)
      body.append('finding', finding)
      if (note.trim()) body.append('note', note.trim())
      body.append('signatureid', signature.recordid)
      await api.post(`/drivers/${id}/annual-review`, body)
      onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <Modal title="Complete The Annual Review" onClose={onClose} width={760}
      footer={<>
        <button type="button" className="primary"
          disabled={!ready || !signature || busy || (mustsay && !note.trim())} onClick={fileIt}>
          {busy ? <Loader2 size={15} className="spin" /> : 'File The Review'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="muted small">
          Period {date(review.periodstart)} to {date(review.periodend)}
        </div>

        {/* Whether the review can be made at all: it is made against the active license, and
            that license needs a current driving record. */}
        {!states.length ? (
          <div className="notice bad">{coverage?.why}</div>
        ) : !ready && (
          <div className="notice bad">
            No current driving record for {missing.join(', ')}. The review cannot be completed
            until there is one.
          </div>
        )}

        {/* The active license and its record - what the reviewer signs for. */}
        <table className="residencetable mvrstatetable">
          <thead><tr><th>License</th><th>Record</th><th>Review</th><th /></tr></thead>
          <tbody>
            {states.map((s) => {
              const seen = s.record && !s.record.norecord && s.record.reviewstate !== 'reviewed'
              return (
                <tr key={s.state}>
                  <td>{s.state} {s.licenses.join(', ')}</td>
                  <td className={s.record ? (s.state_covered ? 'st-active' : 'st-expired')
                    : s.ordered ? undefined : 'st-expired'}>
                    {s.record
                      ? (s.record.norecord ? 'None available'
                        : s.record.issuedon ? date(s.record.issuedon) : 'On file')
                      : s.ordered ? `Ordered ${date(s.ordered.orderedon)}` : 'Not on file'}
                  </td>
                  <td className={seen ? 'st-ordered'
                    : s.record?.finding === 'disqualified' ? 'st-expired'
                      : s.record?.finding ? 'st-active' : undefined}>
                    {!s.record || s.record.norecord ? '-'
                      : seen ? 'Not yet read' : MVR_FINDING[s.record.finding] || 'Read'}
                  </td>
                  <td className="actions">
                    {!s.record && !s.ordered && (
                      <button type="button" className="linkbtn edit"
                        onClick={() => onOrder?.()}>Order</button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {/* A determination reached on a record nobody opened is the thing this requirement
            exists to prevent, so it is said plainly before the finding is chosen. */}
        {ready && unseen.length > 0 && (
          <div className="notice warn">
            {unseen.length === 1
              ? `The driving record for ${unseen[0].state} has not been read yet.`
              : `${unseen.length} driving records have not been read yet.`}
          </div>
        )}

        <div className="profileform">
          <label className="field span-6">Determination *
            <select value={finding} onChange={(e) => setFinding(e.target.value)}>
              {Object.entries(findings || ANNUAL_FINDING).map(([v, l]) =>
                <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field span-6">
            {mustsay ? 'What was found, and what is being done about it *' : 'Note'}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
        </div>
        <SignatureBlock signature={signature} onSigned={setSignature}
          label="Signature Of Reviewer" action="Sign" />
      </div>
    </Modal>
  )
}

// RequirementDetail, when source.kind === 'annualreview' && !filing.
export function AnnualReviewDialog({ annual, annualHistory, busy, completeAnnual, completing, err, id, loadAnnual, onChanged, onClose, onOpen, r, setAnnualHistory, setCompleting, setViewing, viewing }) {
    const lastReview = (annual?.reviews || []).find((x) => x.state === 'complete') || null
    return (
      <>
      <Modal title={r.name} onClose={onClose} brief={r?.description} width={720}
        footer={<>
          {lastReview && (
            <button type="button" className={annual?.due?.open || annual?.due?.startable ? undefined : 'primary'}
              onClick={() => setViewing({ path: `/drivers/${id}/signed/ANNUAL_REVIEW:${lastReview.recordid}/pdf`,
                filename: r.name })}>
              <Eye size={14} /> View
            </button>
          )}
          {/* One action. A review already open goes straight to its form; otherwise one is opened
              first - only on a new driving record or a disqualifying last review - and its form
              follows at once. */}
          {(annual?.due?.open || annual?.due?.startable) && (
            <button type="button" className="primary" disabled={busy} onClick={completeAnnual}>
              <Check size={13} /> Complete The Annual Review
            </button>
          )}
          <button type="button" disabled={!lastReview} onClick={() => setAnnualHistory(true)}>
            <History size={13} /> History
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {!annual ? <Loading /> : lastReview ? (
            <table className="residencetable recordtable">
              <thead><tr><th>Date</th><th>Document</th><th>Status</th></tr></thead>
              <tbody>
                <tr>
                  <td>{lastReview.reviewedon ? date(lastReview.reviewedon) : '-'}</td>
                  <td>{r.name}</td>
                  {/* A driving record received since this review has been reviewed by nobody, so
                      the review stands disqualified until another is completed. */}
                  <td className={annual.due?.newer || lastReview.finding === 'notqualified' ? 'st-expired'
                    : lastReview.finding === 'corrective' ? 'st-ordered' : 'st-active'}>
                    {annual.due?.newer ? 'Disqualified'
                      : ANNUAL_FINDING[lastReview.finding] || lastReview.finding || '-'}
                  </td>
                </tr>
              </tbody>
            </table>
          ) : (
            <div className="gridempty">No {r.name} On File For This Driver</div>
          )}
        </div>
      </Modal>
      {annualHistory && (
        <Modal title={`${r.name} - History`} onClose={() => setAnnualHistory(false)} width={DETAIL}
          footer={<button type="button" onClick={() => setAnnualHistory(false)}>Close</button>}>
          <div className="stack">
            <table className="residencetable recordtable">
              <thead><tr><th>Date</th><th>Record Reviewed</th><th>Finding</th><th /></tr></thead>
              <tbody>
                {(annual?.reviews || []).filter((x) => x.state === 'complete').map((x) => {
                  const rec = (x.records || [])[0]
                  return (
                    <tr key={x.recordid}>
                      <td>{x.reviewedon ? date(x.reviewedon) : '-'}</td>
                      <td>{rec ? `${[rec.state, rec.number].filter(Boolean).join(' ')}${rec.issuedon
                        ? ` dated ${date(rec.issuedon)}` : ''}` : '-'}</td>
                      <td className={x.finding === 'notqualified' ? 'st-expired'
                        : x.finding === 'corrective' ? 'st-ordered' : 'st-active'}>
                        {ANNUAL_FINDING[x.finding] || x.finding || '-'}
                      </td>
                      <td className="actions">
                        <button type="button" className="linkbtn edit"
                          onClick={() => setViewing({
                            path: `/drivers/${id}/signed/ANNUAL_REVIEW:${x.recordid}/pdf`,
                            filename: r.name })}>View</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
      {viewing && <DocumentViewer id={viewing.documentid} path={viewing.path} name={viewing.filename}
        onClose={() => setViewing(null)} />}
      {completing && (
        <CompleteAnnualReview id={id} review={completing}
          records={(annual?.reviews || []).find((x) => x.recordid === completing.recordid)?.records}
          coverage={annual?.coverage} findings={annual?.findings}
          needsreason={annual?.needsreason}
          onClose={() => setCompleting(null)}
          /* Ordering a driving record is the MVR requirement's own job, not a second copy of it
             bolted onto this dialog. */
          onOrder={() => { setCompleting(null); onOpen?.('MVR_ANNUAL') }}
          onDone={() => { setCompleting(null); loadAnnual(); onChanged?.() }} />
      )}
      </>
    )
  
}

const ANNUAL_FINDING = { qualified: 'Qualified',
  corrective: 'Qualified - corrective action required',
  notqualified: 'Disqualified' }
