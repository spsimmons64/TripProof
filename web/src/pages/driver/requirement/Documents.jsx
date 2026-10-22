// Requirement dialogs - Documents. Moved out of
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
import { DETAIL, PROVENANCE } from './common.jsx'

// RequirementDetail, when derived.
export function QualificationFileDialog({ act, busy, derived, err, id, onClose, r, today }) {
    const complete = derived.status === 'satisfied'
    return (
      <Modal title={r.name} onClose={onClose} brief={r?.description} width={720}
        footer={<>
          <button type="button" className="primary" disabled={busy}
            onClick={() => act(async () => { await api.download(`/drivers/${id}/files.zip`) })}>
            <Download size={14} /> Download Driver File
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <table className="residencetable recordtable">
            <thead><tr><th>Date</th><th>Document</th><th>Status</th></tr></thead>
            <tbody>
              <tr>
                <td>{date(today)}</td>
                <td>Driver qualification file</td>
                <td className={complete ? 'st-active' : derived.status === 'unknown' ? 'st-inactive'
                  : 'st-expired'}>
                  {complete ? 'Complete' : derived.status === 'unknown' ? 'Not Applicable' : 'Incomplete'}
                </td>
              </tr>
            </tbody>
          </table>
          {derived.missing.length > 0 && (
            <div className="field">Still Missing
              <ul className="ovreasons filemissing">
                {derived.missing.map((x) => <li key={x}>{x}</li>)}
              </ul>
            </div>
          )}
        </div>
      </Modal>
    )
  
}

// RequirementDetail, when asks.
export function RequestHistoryDialog({ asks, r, setAsks }) {
    return (
      <Modal title={`${r.name} - History`} onClose={() => setAsks(null)} width={760}
        footer={<button type="button" onClick={() => setAsks(null)}>Close</button>}>
        <div className="stack">
          {!asks.length ? (
            <div className="muted">This driver has never been asked for this.</div>
          ) : (
            <table className="residencetable recordtable">
              <thead><tr><th>Asked</th><th>Sent to</th><th>Status</th></tr></thead>
              <tbody>
                {asks.map((a) => (
                  <tr key={a.recordid}>
                    <td>{date(a.senton || a.createdon)}</td>
                    <td>{a.sentto || 'No email - link read out'}</td>
                    <td className={a.cancelledon ? 'st-inactive'
                      : a.answeredon ? 'st-active' : 'st-ordered'}>
                      {a.cancelledon ? `Withdrawn ${date(a.cancelledon)}`
                        : a.answeredon ? `Answered ${date(a.answeredon)}`
                          : 'Not answered yet'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Modal>
    )
  
}

// RequirementDetail, when source.kind === 'applicationanswered' && filing !== 'against'.
export function QuestionnaireDialog({ askForIt, asked, busy, err, markRead, onClose, r, readRecord, records, setFiling, setViewing, unchecked, viewing }) {
    // Laid out as the PHI acknowledgement is: the one on file, read from the table and opened with
    // View - or, with nothing on file, the request to the driver and the upload of a paper copy.
    // Answered or not; there is no history to it.
    const onfile = records.find((x) => x.documentid)
    const waiting = Boolean(onfile) && (unchecked.has(onfile.documentid) || onfile.needsreading)
    return (
      <>
      <SingleDocumentDialog title={r.name} brief={r?.description} err={err}
        notice={onfile ? null : asked} unread={waiting}
        row={onfile && { on: onfile.effectiveon || onfile.recordedon,
                         status: docStanding({ unread: waiting }) }}
        onView={() => setViewing({ documentid: onfile.documentid, filename: r.name,
          check: unchecked.has(onfile.documentid), record: onfile.needsreading ? onfile : null })}
        emptyActions={<>
          <button type="button" onClick={() => setFiling('against')}>
            <FileUp size={13} /> Upload Document
          </button>
          <button type="button" disabled={busy}
            onClick={() => askForIt('PREEMP_DA_QUESTIONNAIRE')}>
            <FileSignature size={13} /> Ask the driver to sign
          </button>
        </>}
        onClose={onClose} />
      <ReadingViewer viewing={viewing} busy={busy} onMarkRead={markRead} onReadRecord={readRecord}
        onClose={() => setViewing(null)} />
      </>
    )
  
}

// RequirementDetail, when latest && !filing.
export function LatestDocumentDialog({ act, askForIt, asked, busy, credHistory, credentialtype, err, latest, markRead, onClose, r, readRecord, setCredHistory, setFiling, setViewing, shown, today, unchecked, viewing }) {
    const waiting = unchecked.has(latest.documentid) || latest.needsreading
    // One that runs out is replaced, so its expiry, the next one and the ones before it belong in
    // the dialog - read off the rule's own recurrence, not a list kept by hand.
    const renewed = Boolean(r.recurrence) && r.recurrence !== 'once'
    const lapsed = renewed && latest.expireson && String(latest.expireson).slice(0, 10) < today
    const columns = [
      ...(renewed ? [{ label: 'Expires', cell: latest.expireson ? date(latest.expireson) : '-' }] : []),
      // Where it came from decides whether it can be relied on, so it can be recorded here when it
      // was not recorded at filing.
      ...(credentialtype?.requiresprovenance ? [{
        label: 'Source',
        tone: ['fdle', 'ahca'].includes(latest.provenance) ? undefined : 'st-ordered',
        cell: (
          <select value={latest.provenance || ''} disabled={busy}
            onChange={(e) => act(async () => {
              await api.put(`/credentials/${latest.recordid}/provenance`, { provenance: e.target.value })
            })}>
            <option value="" disabled>Not recorded</option>
            {Object.entries(PROVENANCE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        ),
      }] : []),
    ]
    return (
      <>
        <SingleDocumentDialog title={r.name} brief={r?.description} err={err}
          notice={renewed ? asked : null} unread={waiting} columns={columns}
          row={{ on: latest.effectiveon || latest.recordedon,
                 status: docStanding({ unread: waiting, lapsed }) }}
          onView={() => setViewing({ documentid: latest.documentid, filename: r.name,
            check: unchecked.has(latest.documentid), record: latest.needsreading ? latest : null })}
          // One that runs out is replaced: the next is uploaded or asked for from here, and the
          // ones before it are a click away.
          actions={renewed && <>
            <button type="button" onClick={() => setFiling(true)}>
              <FileUp size={13} /> Upload Document
            </button>
            <button type="button" disabled={busy} onClick={() => askForIt()}>
              <Send size={13} /> Ask the driver for it
            </button>
            <button type="button" onClick={() => setCredHistory(true)}>
              <History size={13} /> History
            </button>
          </>}
          onClose={onClose} />
        {credHistory && (
          <Modal title={`${r.name} - History`} onClose={() => setCredHistory(false)} width={DETAIL}
            footer={<button type="button" onClick={() => setCredHistory(false)}>Close</button>}>
            <div className="stack">
              <table className="residencetable recordtable">
                <thead><tr><th>Date</th><th>Document</th><th>Expires</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {shown.filter((x) => x.documentid).map((x) => {
                    const unreadOne = unchecked.has(x.documentid) || x.needsreading
                    const gone = x.expireson && String(x.expireson).slice(0, 10) < today
                    return (
                      <tr key={x.recordid || x.documentid}>
                        <td>{date(x.effectiveon || x.recordedon)}</td>
                        <td>{r.name}</td>
                        <td>{x.expireson ? date(x.expireson) : '-'}</td>
                        <td className={gone ? 'st-expired' : unreadOne ? 'st-ordered' : 'st-active'}>
                          {gone ? 'Expired' : unreadOne ? 'Not Reviewed' : 'Reviewed'}
                        </td>
                        <td className="actions">
                          <button type="button" className="linkbtn edit" onClick={() => setViewing({
                            documentid: x.documentid, filename: r.name,
                            check: unchecked.has(x.documentid), record: x.needsreading ? x : null })}>
                            View
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Modal>
        )}
        <ReadingViewer viewing={viewing} busy={busy} onMarkRead={markRead} onReadRecord={readRecord}
          onClose={() => setViewing(null)} />
      </>
    )
  
}
