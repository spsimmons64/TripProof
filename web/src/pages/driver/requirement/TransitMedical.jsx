// Requirement dialogs - TransitMedical. Moved out of
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
import { BLANK_EXAM, DETAIL, expiry, valid } from './common.jsx'

// RequirementDetail, when source.kind === 'transitmedical'.
export function TransitMedicalDialog({ busy, crash, crashes, err, exam, fileTransitMedical, filing, id, loadAccidents, onChanged, onClose, r, records, reload, setCrash, setExam, setFiling, setViewing, source, today, viewing }) {
    if (filing === 'exam') {
      const periodic = exam.result === 'meetsperiodic'
      const temporary = exam.result === 'temporary'
      const failed = exam.result === 'doesnotmeet' || temporary
      return (
        <Modal title="Add Bus Transit Medical Examination" onClose={() => setFiling(false)} width={760}
          footer={<>
            <button type="button" className="primary" onClick={fileTransitMedical}
              disabled={busy || !exam.examinedon || (periodic && !exam.qualifiedthrough)
                || (temporary && !exam.tempreason.trim())}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setFiling(false)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}

            <section>
              <h3 className="formsection">Examination</h3>
              <div className="profileform">
                <label className="field span-3">Examination
                  <select value={exam.examtype}
                    onChange={(e) => setExam({ ...exam, examtype: e.target.value })}>
                    {Object.entries(EXAM_TYPE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
                <label className="field span-3">Date Of Examination
                  <input type="date" value={exam.examinedon}
                    onChange={(e) => setExam({ ...exam, examinedon: e.target.value })} />
                </label>
                <label className="field span-3">Medical Examiner
                  <input value={exam.examinername} className="upper"
                    onChange={(e) => setExam({ ...exam, examinername: e.target.value.toUpperCase() })} />
                </label>
                <label className="field span-1">Type
                  <select value={exam.examinertype}
                    onChange={(e) => setExam({ ...exam, examinertype: e.target.value })}>
                    <option value="" />
                    {EXAMINER_TYPES.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                </label>
                <label className="field span-1">License
                  <input value={exam.examinerlicense} className="upper"
                    onChange={(e) => setExam({ ...exam, examinerlicense: e.target.value.toUpperCase() })} />
                </label>
                <label className="field span-1">State
                  <input value={exam.examinerstate} className="upper" maxLength={2}
                    onChange={(e) => setExam({ ...exam, examinerstate: e.target.value.toUpperCase() })} />
                </label>
              </div>
            </section>

            <section>
              <h3 className="formsection">Restrictions</h3>
              <div className="profileform">
                <label className="field check sharerow span-2">
                  <input type="checkbox" checked={exam.correctivelenses}
                    onChange={(e) => setExam({ ...exam, correctivelenses: e.target.checked })} />
                  Corrective lenses
                </label>
                <label className="field check sharerow span-2">
                  <input type="checkbox" checked={exam.hearingaid}
                    onChange={(e) => setExam({ ...exam, hearingaid: e.target.checked })} />
                  Hearing aid
                </label>
                <label className="field span-6">Other
                  <textarea rows={4} value={exam.otherrestriction}
                    onChange={(e) => setExam({ ...exam, otherrestriction: e.target.value })} />
                </label>
              </div>
            </section>

            <section>
              <h3 className="formsection">Qualification</h3>
              <div className="profileform">
                <label className="field span-4">Result
                  <select value={exam.result}
                    onChange={(e) => setExam({ ...exam, result: e.target.value })}>
                    {Object.entries(EXAM_RESULT).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
                {/* Two years unless the examiner shortened it, and they say so here. */}
                {!failed && (
                  <label className="field span-2">
                    Qualified through{periodic ? ' *' : ''}
                    <input type="date" value={exam.qualifiedthrough}
                      onChange={(e) => setExam({ ...exam, qualifiedthrough: e.target.value })} />
                  </label>
                )}
                {/* What a temporary disqualification has that the other results do not: why it
                    stands, and the date it is looked at again. */}
                {temporary && (
                  <label className="field span-6">Reason *
                    <input value={exam.tempreason}
                      onChange={(e) => setExam({ ...exam, tempreason: e.target.value })} />
                  </label>
                )}
                <label className="field span-3">Follow Up On
                  <input type="date" value={exam.followupon}
                    onChange={(e) => setExam({ ...exam, followupon: e.target.value })} />
                </label>
                <label className="field span-3">Certificate
                  <input type="file"
                    onChange={(e) => setExam({ ...exam, file: e.target.files[0] || null })} />
                </label>
              </div>
            </section>
          </div>
        </Modal>
      )
    }

    return (
      <>
        <Modal title="Bus Transit Medical Examinations" onClose={onClose} brief={r?.description} width={DETAIL}
          footer={<>
            <button type="button" onClick={() => { setExam(BLANK_EXAM(today)); setFiling('exam') }}>
              <Plus size={13} /> Add Bus Transit Medical Examination
            </button>
            <button type="button" onClick={onClose}>Close</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            {!records.length && (
              <div className="muted">No Bus Transit Medical Examinations On File For This Driver</div>
            )}
            {records.length > 0 && (
              <table className="residencetable examtable">
                <thead><tr><th>Examination</th><th>Examiner</th><th>Valid</th><th>Status</th>
                  <th /></tr></thead>
                <tbody>
                  {records.map((rec) => {
                    const [says, tone] = examStanding(rec)
                    return (
                      <tr key={rec.recordid}>
                        <td>{EXAM_TYPE[rec.examtype] || rec.examtype}</td>
                        <td>{[rec.examinername, rec.examinertype].filter(Boolean).join(', ') || '-'}</td>
                        <td>{valid(rec)}</td>
                        <td className={tone}>{says}</td>
                        <td className="actions">
                          {rec.documentid && (
                            <button type="button" className="linkbtn edit"
                              onClick={() => setViewing({ documentid: rec.documentid,
                                filename: 'Bus transit medical examination' })}>
                              View
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
            {/* The accident register belongs to post-accident testing and nowhere else. 382.303 is
                the only reason this office asks these questions, and they are not questions to ask
                about somebody who has not driven for this company yet. */}
            {source.which === 'postaccident' && (
              <>
                <h3 className="formsection">Accidents</h3>
                {!(crashes?.accidents || []).length && (
                  <div className="muted">No Accidents On File For This Driver</div>
                )}
              </>
            )}
            {source.which === 'postaccident' && (crashes?.accidents || []).length > 0 && (
              <table className="residencetable recordtable">
                <thead><tr><th>When</th><th>Where</th><th>382.303</th><th /></tr></thead>
                <tbody>
                  {crashes.accidents.map((x) => {
                    const [says, tone] = CRASH_STATE[x.state] || [x.state, 'st-inactive']
                    return (
                      <tr key={x.recordid}>
                        <td>{x.occurredon ? when(x.occurredon) : '-'}</td>
                        <td>{x.location || '-'}</td>
                        <td className={tone}>{says}</td>
                        <td className="actions">
                          <button type="button" className="linkbtn edit"
                            onClick={() => { setCrash(FROM_ROW(x)); setFiling('accident') }}>
                            {x.state === 'unknown' ? 'Answer' : 'Open'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </Modal>
        {filing === 'accident' && (
          <CrashDialog id={id} initial={crash}
            onClose={() => { setCrash(BLANK_CRASH); setFiling(false) }}
            onSaved={async () => { await loadAccidents(); reload(); onChanged?.() }} />
        )}
        {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
          onClose={() => setViewing(null)} />}
      </>
    )
  
}

// FDOT 725-030-11 under F.A.C. 14-90.0041. What is kept is the certification - the occasion, the
// examiner, the determination and how long it stands. The health history and examination findings
// on the form are not kept: the examiner holds the complete examination, the system holds the
// certificate, and an employer has no reason to be storing a driver's medical history.
const EXAM_TYPE = {
  preemployment: 'Preemployment',
  biennial: 'Biennial',
  followup: 'Follow up',
  returntoduty: 'Return to duty',
}

const EXAM_RESULT = {
  meets: 'Meets standards',
  meetsperiodic: 'Meets standards, periodic evaluation required',
  doesnotmeet: 'Does not meet standards',
  temporary: 'Temporarily disqualified',
}

const EXAMINER_TYPES = ['MD', 'DO', 'PA', 'ARNP']

// What one examination says about the driver, in the row's own Status column.
const examStanding = (rec) => {
  if (rec.result === 'temporary') return ['Temporarily disqualified', 'st-expired']
  if (rec.result === 'doesnotmeet') return ['Does not meet standards', 'st-expired']
  const band = expiry(rec.expireson)
  if (band === 'st-expired') return ['Expired', 'st-expired']
  if (band === 'st-expiring') return ['Expiring', 'st-expiring']
  return [rec.result === 'meetsperiodic' ? 'Qualified, periodic' : 'Qualified', 'st-active']
}
