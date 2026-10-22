// Requirement dialogs - RoadTest. Moved out of
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
import { DETAIL } from './common.jsx'

// RequirementDetail, when source.kind === 'roadtest' && filing !== 'against'.
export function RoadTestDialog({ active, busy, err, examiner, filing, onClose, r, reviewRoadTest, roadtests, sendRoadTest, setExaminer, setFiling, setViewing, viewing }) {
    const tests = roadtests?.tests || []
    const outstanding = tests.find((x) => x.state === 'waiting')
    // A test that was passed and read answers the requirement. 49 CFR 391.31 asks for one road
    // test, not an annual one, so there is nothing to send an examiner out for a second time.
    const settled = tests.find((x) => x.state === 'passed')

    if (filing === 'examiner') {
      return (
        <Modal title="Send To Examiner" onClose={() => setFiling(false)} width={620}
          footer={<>
            <button type="button" className="primary"
              disabled={busy || !examiner.name.trim() || !examiner.email.includes('@')}
              onClick={sendRoadTest}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Send It'}
            </button>
            <button type="button" onClick={() => setFiling(false)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-3">Examiner *
                <input value={examiner.name} className="upper"
                  onChange={(e) => setExaminer({ ...examiner, name: e.target.value.toUpperCase() })} />
              </label>
              <label className="field span-3">Email *
                <input type="email" value={examiner.email}
                  onChange={(e) => setExaminer({ ...examiner, email: e.target.value.toLowerCase() })} />
              </label>
              <label className="field span-3">Title
                <input value={examiner.title} className="upper"
                  onChange={(e) => setExaminer({ ...examiner, title: e.target.value.toUpperCase() })} />
              </label>
              <label className="field span-3">Organization
                <input value={examiner.organization} className="upper"
                  onChange={(e) => setExaminer({ ...examiner,
                    organization: e.target.value.toUpperCase() })} />
              </label>
            </div>
          </div>
        </Modal>
      )
    }

    return (
      <>
      <Modal title={r.name} onClose={onClose} brief={r?.description} width={DETAIL}
        footer={<>
          {/* A test already out stops another being sent: two examiners testing one driver on one
              requirement would leave two answers with nothing to say which belongs to which. */}
          {!outstanding && !settled && (
            <button type="button" disabled={busy} onClick={() => setFiling('examiner')}>
              <Send size={13} /> Send To Examiner
            </button>
          )}
          <button type="button" onClick={() => setFiling('against')}>
            <Plus size={13} /> Upload
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {/* 49 CFR 391.33: a driver who holds a valid CDL has already demonstrated this, and the
              engine reads the license for itself. Said here so nobody sends an examiner out for a
              test the regulation does not ask for. */}
          {active && !tests.length && (
            <div className="notice good">
              Answered by the license on file - 49 CFR 391.33 accepts a valid CDL in place of a
              road test. A test may still be given if this company wants one.
            </div>
          )}
          {!tests.length && !active && (
            <div className="muted">No road test on file for this driver.</div>
          )}
          {tests.length > 0 && (
            <table className="residencetable recordtable">
              <thead><tr><th>Tested</th><th>Examiner</th><th>Result</th><th /></tr></thead>
              <tbody>
                {tests.map((x) => (
                  <tr key={x.recordid}>
                    <td>{x.testedon ? date(x.testedon) : '-'}</td>
                    <td>{x.examinername || x.sentto || '-'}</td>
                    <td className={x.state === 'passed' ? 'st-active'
                      : x.state === 'failed' ? 'st-expired'
                        : x.state === 'toreview' ? 'st-ordered' : 'st-expiring'}>
                      {x.says}
                    </td>
                    <td className="actions">
                      {x.state === 'toreview' && x.documentid && (
                        <button type="button" className="linkbtn edit toread"
                          onClick={() => setViewing({ documentid: x.documentid,
                            filename: 'Road test', roadtest: x.recordid })}>
                          Review
                        </button>
                      )}
                      {x.state !== 'toreview' && x.documentid && (
                        <button type="button" className="linkbtn edit"
                          onClick={() => setViewing({ documentid: x.documentid,
                            filename: 'Road test' })}>View</button>
                      )}
                      {x.state === 'waiting' && (
                        <span className="mvrordered">Sent {date(x.senton)}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Modal>
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)}
        action={viewing.roadtest && (
          <button type="button" className="primary" disabled={busy}
            onClick={async () => { await reviewRoadTest(viewing.roadtest); setViewing(null) }}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
          </button>
        )} />}
      </>
    )
  
}
