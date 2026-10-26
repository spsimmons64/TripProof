// Requirement dialogs - Mvr. Moved out of
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
import { DETAIL, MVR_FINDING, expiry } from './common.jsx'
import { CdlisFields } from './Records.jsx'

// RequirementDetail, when source.kind === 'mvr' && !filing.
export function MvrDialog({ busy, cancelMvr, coverage, data, err, form, mvrHistory, onClose, r, records, reviewMvr, setFiling, setForm, setMvrHistory, setViewing, viewing }) {
    const states = coverage?.required || []
    return (
      <>
      {/* One panel per license, each with the last record pulled on it. */}
      <PanelsDialog title={r.name} brief={r?.description} err={err} width={DETAIL}
        onClose={onClose}
        empty={<div className="notice warn">
          {coverage?.why || 'No licenses are on file, so there is nothing to say which states to ask.'}
        </div>}>
        {states.length > 0 && (coverage?.cards || []).map((s) => {
          const label = `${s.state} ${s.number}`
          const rec = s.record
          return (
            <ItemPanel key={s.licenseid} title={label}
              status={s.active ? ['Active', 'st-active'] : ['Inactive', 'st-inactive']}
              facts={[
                { label: 'Last record',
                  tone: rec ? (expiry(s.expireson) === 'st-expired' ? 'st-expired' : 'st-active')
                    : s.ordered ? undefined : 'st-expired',
                  value: rec ? (rec.norecord ? 'None available'
                    : rec.issuedon ? date(rec.issuedon) : 'On file') : 'Not on file' },
                { label: 'Expires', tone: expiry(s.expireson),
                  value: s.expireson ? date(s.expireson) : '-' },
                { label: 'Review',
                  tone: unread(s) ? 'st-ordered' : rec?.finding === 'disqualified' ? 'st-expired'
                    : rec?.finding ? 'st-active' : undefined,
                  value: !rec || rec.norecord ? '-' : unread(s) ? 'Not reviewed'
                    : MVR_FINDING[rec.finding] || 'Reviewed' },
                { label: 'Order', tone: s.ordered ? 'st-ordered' : undefined,
                  value: s.ordered ? `Ordered ${date(s.ordered.orderedon)}` : 'None outstanding' },
              ]}
              actions={<>
                      {rec?.documentid && (
                        <button type="button" className={unread(s) ? 'primary' : undefined}
                          onClick={() => {
                            // Seeded from the record, so a reader sees what is already there and
                            // changes it rather than retyping it from nothing.
                            setForm({ ...form, mvrid: rec.recordid, result: 'qualified', note: '',
                              selfcert: rec.selfcert || '',
                              medcertstatus: rec.medcertstatus || '',
                              medcertexpires: rec.medcertexpires || '',
                              medvariancetype: rec.medvariancetype || '',
                              medvariance: rec.medvariance || '' })
                            setViewing({ documentid: rec.documentid, review: unread(s),
                              filename: `Motor vehicle record - ${label}` })
                          }}>
                          <Eye size={14} /> {unread(s) ? 'Review' : 'View'}
                        </button>
                      )}
                      {/* A request already out stops both ordering again and filing by hand: the
                          answer on its way is what fills it. Cancel it first. */}
                      {s.ordered ? (
                        <button type="button" disabled={busy}
                          onClick={() => cancelMvr(s.ordered.recordid)}>
                          <X size={13} /> Cancel Order
                        </button>
                      ) : (
                        <>
                          <button type="button"
                            onClick={() => { setForm({ ...form, licenseid: s.licenseid,
                              licensenumber: s.number, licenselabel: label }); setFiling('mvr-order') }}>
                            <Send size={13} /> Order
                          </button>
                          <button type="button"
                            onClick={() => { setForm({ ...form, licenseid: s.licenseid, file: null,
                              result: '', note: '', licenselabel: label }); setFiling('mvr-upload') }}>
                            <FileUp size={13} /> Upload
                          </button>
                        </>
                      )}
                      <button type="button"
                        disabled={!records.some((x) => x.licenseid === s.licenseid)}
                        onClick={() => setMvrHistory(s)}>
                        <History size={13} /> History
                      </button>
                    </>} />
          )
        })}
      </PanelsDialog>
      {mvrHistory && (
        <Modal title={`Motor Vehicle Records - ${mvrHistory.state} ${mvrHistory.number}`}
          onClose={() => setMvrHistory(null)} width={DETAIL}
          footer={<button type="button" onClick={() => setMvrHistory(null)}>Close</button>}>
          <div className="stack">
            <table className="residencetable recordtable">
              <thead><tr><th>Record</th><th>Ordered</th><th>Received</th><th>Status</th><th /></tr></thead>
              <tbody>
                {records.filter((x) => x.licenseid === mvrHistory.licenseid).map((x) => (
                  <tr key={x.recordid}>
                    <td>{x.effectiveon ? date(x.effectiveon) : '-'}</td>
                    <td>{x.orderedon ? date(x.orderedon) : '-'}</td>
                    <td>{x.receivedon ? date(x.receivedon) : '-'}</td>
                    <td className={x.cancelledon ? 'st-inactive' : x.receivedon
                      ? (x.determination === 'reviewed' ? 'st-active' : 'st-ordered') : 'st-ordered'}>
                      {x.cancelledon ? 'Canceled' : x.receivedon
                        ? (x.determination === 'reviewed' ? 'Reviewed' : 'Not reviewed') : 'Ordered'}
                    </td>
                    <td className="actions">
                      {x.documentid && (
                        <button type="button" className="linkbtn edit"
                          onClick={() => setViewing({ documentid: x.documentid,
                            filename: `Motor vehicle record - ${mvrHistory.state} ${mvrHistory.number}` })}>
                          View
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)}
        action={viewing.review && (
          <button type="button" className="primary" onClick={reviewMvr}
            disabled={busy || (form.result === 'restricted' && !form.note.trim())}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
        )}
        panel={viewing.review && (
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-3">What does it conclude?
                <select value={form.result}
                  onChange={(e) => setForm({ ...form, result: e.target.value })}>
                  {Object.entries(MVR_FINDING).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
              <label className="field span-6">
                Note{form.result === 'restricted' ? ' *' : ''}
                <textarea value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })} />
              </label>
            </div>
            {/* A CDLIS record carries the State's answer about medical qualification, and this is
                where somebody is reading it. Asking only on the filing form would mean a record
                that came back against an order was never asked at all. */}
            {data?.cdl && <CdlisFields data={data} form={form} setForm={setForm} />}
            {form.medcertstatus === 'notcertified' && (
              <div className="notice bad">
                The State shows this driver as not certified. They may not operate a commercial
                motor vehicle, and the certificate on file does not override it.
              </div>
            )}
            {form.result === 'disqualified' && (
              <div className="notice bad">
                This stops the driver from the moment it is saved. It does not wait for the annual review.
              </div>
            )}
          </div>
        )} />}
      </>
    )
  
}

// RequirementDetail, when filing === 'mvr-order'.
export function MvrOrderDialog({ busy, err, form, orderMvr, setFiling }) {
    return (
      <Modal title="Order A Driving Record" onClose={() => setFiling(false)} width={520}
        footer={<>
          <button type="button" className="primary" disabled={busy} onClick={orderMvr}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Yes'}
          </button>
          <button type="button" onClick={() => setFiling(false)}>No</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="askorder">
            <span className="askmark">?</span>
            <p>Order MVR for License {form.licensenumber}?</p>
          </div>
        </div>
      </Modal>
    )
  
}

// RequirementDetail, when filing === 'mvr-upload'.
export function MvrUploadDialog({ busy, data, err, form, setFiling, setForm, uploadMvr }) {
    return (
      <Modal title="File A Driving Record" onClose={() => setFiling(false)}
        footer={<>
          <button type="button" className="primary"
            disabled={busy || !form.file
              || (form.result === 'restricted' && !form.note.trim())}
            onClick={uploadMvr}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => setFiling(false)}>Cancel</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {/* The license came with the row that was clicked - it is stated, not chosen again. */}
          <div className="muted small">{form.licenselabel}</div>
          <div className="profileform">
            <label className="field span-3">Date On The Record
              <input type="date" value={form.effectiveon}
                onChange={(e) => setForm({ ...form, effectiveon: e.target.value })} />
            </label>
            {/* Read now or read later, but never silently counted as read. */}
            <label className="field span-3">What does it conclude?
              <select value={form.result}
                onChange={(e) => setForm({ ...form, result: e.target.value })}>
                <option value="">Not reviewed yet</option>
                {Object.entries(MVR_FINDING).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="field span-6">The Record *
              <input type="file"
                onChange={(e) => setForm({ ...form, file: e.target.files[0] || null })} />
            </label>
            <label className="field span-6">
              Note{form.result === 'restricted' ? ' *' : ''}
              <textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </label>
          </div>
          {/* For a CDL holder the driving record carries more than the driving history: the State
              holds their self-certification and their medical qualification status, and under
              49 CFR 383.71 that is what governs - not the certificate in this office's file. The
              questions are asked here, while somebody has the record open, because that is the
              only moment anybody is looking at it. */}
          {data?.cdl && (
            <>
              <hr className="formrule" />
              <CdlisFields data={data} form={form} setForm={setForm} />
              {form.medcertstatus === 'notcertified' && (
                <div className="notice bad">
                  The State shows this driver as not certified. They may not operate a commercial
                  motor vehicle, and the certificate on file does not override it.
                </div>
              )}
            </>
          )}
          {form.result === 'disqualified' && (
            <div className="notice bad">
              This stops the driver from the moment it is saved. It does not wait for the annual review.
            </div>
          )}
        </div>
      </Modal>
    )
  
}
