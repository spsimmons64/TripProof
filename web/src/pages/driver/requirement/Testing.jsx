// Requirement dialogs - Testing. Moved out of
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
import { DETAIL, SCREEN_RESULTS, plural, standingOf } from './common.jsx'

// RequirementDetail, when source.kind === 'drugtest'.
export function DrugTestingDialog({ busy, err, file, filing, form, id, loadTesting, needsResult, onChanged, onClose, r, reload, results, setCrash, setFiling, setForm, setTestHistory, setViewing, source, testHistory, testing, viewing }) {
    const held = testing?.prohibited || null
    // The absence of a violation is not permission. 49 CFR 382.301(a) bars safety-sensitive work
    // until a negative controlled substances result is in hand, so a driver with a clean sheet and
    // no test on file is not cleared - they are untested, which is its own red state.
    const pre = testing?.preemployment || {}
    const dot = (held?.program || testing?.program) === 'dot'
    // Newest first, so the first is the last test.
    const lastTest = (testing?.tests || [])[0] || null
    const testTable = (tests, viewable) => (
      <table className="residencetable recordtable">
        <thead><tr><th>Collected</th><th>Reason</th><th>Result</th>{viewable && <th />}</tr></thead>
        <tbody>
          {tests.map((x) => (
            <tr key={x.recordid}>
              <td>{x.collectedon ? date(x.collectedon) : '-'}</td>
              <td>{testing.reasons?.[x.reason] || x.reason}</td>
              <td className={['positive', 'refusal', 'adulterated', 'substituted']
                .includes(x.result) ? 'st-expired'
                : x.result === 'cancelled' ? 'st-inactive' : 'st-active'}>
                {testing.results?.[x.result] || x.result}
              </td>
              {viewable && (
                <td className="actions">
                  {x.documentid && (
                    <button type="button" className="linkbtn edit"
                      onClick={() => setViewing({ documentid: x.documentid,
                        filename: r.name })}>View</button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    )

    if (filing === true) {
      return (
        <Modal title={`Add ${r.name}`} onClose={() => setFiling(false)} width={680}
          footer={<>
            <button type="button" className="primary" disabled={busy} onClick={file}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setFiling(false)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-2">Why Tested
                <select value={form.reason || source.which}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}>
                  {(testing?.offer || Object.keys(testing?.reasons || {})).map((v) =>
                    <option key={v} value={v}>{testing?.reasons?.[v] || v}</option>)}
                </select>
              </label>
              <label className="field span-2">Collected
                <input type="date" value={form.effectiveon}
                  onChange={(e) => setForm({ ...form, effectiveon: e.target.value })} />
              </label>
              <label className="field span-2">Result
                <select value={form.result}
                  onChange={(e) => setForm({ ...form, result: e.target.value })}>
                  {!needsResult && <option value="">Not stated</option>}
                  {needsResult && <option value="">Choose</option>}
                  {results.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
              <label className="field span-6">Test Result
                <input type="file"
                  onChange={(e) => setForm({ ...form, file: e.target.files[0] || null })} />
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
            {lastTest?.documentid && (
              <button type="button" className="primary"
                onClick={() => setViewing({ documentid: lastTest.documentid, filename: r.name })}>
                <Eye size={14} /> View
              </button>
            )}
            <button type="button" onClick={() => setFiling(true)}>
              <Plus size={13} /> Add A Test
            </button>
            {source.which === 'postaccident' && (
              <button type="button" onClick={() => { setCrash(BLANK_CRASH); setFiling('accident') }}>
                <Plus size={13} /> Record An Accident
              </button>
            )}
            <button type="button" disabled={!(testing?.tests || []).length}
              onClick={() => setTestHistory(true)}>
              <History size={13} /> History
            </button>
            <button type="button" onClick={onClose}>Close</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <ProhibitionPanel id={id} held={held} testing={testing} dot={dot}
              onView={setViewing}
              onChanged={async () => { await loadTesting(); reload(); onChanged?.() }} />
            {!held && testing && pre.state !== 'received' && (
              <div className="notice bad">
                No drug or alcohol violation on file - and no negative controlled substances result
                either. 49 CFR 382.301(a) does not permit this driver to perform safety-sensitive
                functions until one is on hand.{pre.why ? ` ${pre.why}.` : ''}
              </div>
            )}
            {/* The last test only, opened from the footer. Every test is in the History. */}
            {lastTest && testTable([lastTest], false)}
          </div>
        </Modal>
        {testHistory && (
          <Modal title={`${r.name} - History`} onClose={() => setTestHistory(false)} width={DETAIL}
            footer={<button type="button" onClick={() => setTestHistory(false)}>Close</button>}>
            <div className="stack">{testTable(testing?.tests || [], true)}</div>
          </Modal>
        )}
        {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
          onClose={() => setViewing(null)} />}
      </>
    )
  
}

// RequirementDetail, when source.kind === 'credential' && source.which === 'DRUG_SCREEN' && !filing.
export function DrugScreenDialog({ asked, busy, err, markRead, onClose, r, readRecord, results, setFiling, setTestHistory, setViewing, shown, testHistory, unchecked, viewing }) {
    const screens = shown
    const last = screens[0] || null
    const screenTable = (list, viewable) => (
      <table className="residencetable recordtable">
        <thead><tr><th>Collected</th><th>Type</th><th>Result</th><th>Status</th>
          {viewable && <th />}</tr></thead>
        <tbody>
          {list.map((x) => {
            const waiting = unchecked.has(x.documentid) || x.needsreading
            const [says, tone] = waiting ? ['Not Reviewed', 'st-ordered']
              : ['positive', 'refusal'].includes(x.result) ? ['Not Passed', 'st-expired']
                : standingOf(x, results)
            return (
              <tr key={x.recordid}>
                <td>{x.effectiveon ? date(x.effectiveon) : '-'}</td>
                <td>{x.screentype || '-'}</td>
                <td className={['positive', 'refusal'].includes(x.result) ? 'st-expired'
                  : x.result ? 'st-active' : undefined}>
                  {SCREEN_RESULTS[x.result] || '-'}
                </td>
                <td className={tone}>{says}</td>
                {viewable && (
                  <td className="actions">
                    {x.documentid && (
                      <button type="button" className="linkbtn edit"
                        onClick={() => setViewing({ documentid: x.documentid, filename: r.name,
                          check: unchecked.has(x.documentid),
                          record: x.needsreading ? x : null })}>
                        {waiting ? 'Review' : 'View'}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    )
    const lastWaiting = last && (unchecked.has(last.documentid) || last.needsreading)
    return (
      <>
        <Modal title={r.name} onClose={onClose} brief={r?.description} width={DETAIL}
          footer={<>
            {last?.documentid && (
              <button type="button" className="primary"
                onClick={() => setViewing({ documentid: last.documentid, filename: r.name,
                  check: unchecked.has(last.documentid),
                  record: last.needsreading ? last : null })}>
                <Eye size={14} /> {lastWaiting ? 'Review' : 'View'}
              </button>
            )}
            <button type="button" onClick={() => setFiling(true)}>
              <Plus size={13} /> Add A Screen
            </button>
            <button type="button" disabled={!screens.length} onClick={() => setTestHistory(true)}>
              <History size={13} /> History
            </button>
            <button type="button" onClick={onClose}>Close</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            {asked}
            {last ? screenTable([last], false)
              : <div className="muted">No {plural(r.name)} On File For This Driver</div>}
          </div>
        </Modal>
        {testHistory && (
          <Modal title={`${r.name} - History`} onClose={() => setTestHistory(false)} width={DETAIL}
            footer={<button type="button" onClick={() => setTestHistory(false)}>Close</button>}>
            <div className="stack">{screenTable(screens, true)}</div>
          </Modal>
        )}
        {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
          onClose={() => setViewing(null)}
          action={<>
            {viewing.check && (
              <button type="button" className="primary" disabled={busy}
                onClick={() => { markRead(viewing.documentid); setViewing(null) }}>
                {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
              </button>
            )}
            {!viewing.check && viewing.record && (
              <button type="button" className="primary" disabled={busy}
                onClick={() => { readRecord(viewing.record); setViewing(null) }}>
                {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
              </button>
            )}
          </>} />}
      </>
    )
  
}
