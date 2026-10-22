// Requirement dialogs - General. Moved out of
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
import { DETAIL, PROVENANCE, SCREEN_RESULTS, plural, standingOf, valid } from './common.jsx'

// The company's own drug screen: the panel run, and what came back.
const SCREEN_TYPES = ['5-Panel', '10-Panel', '12-Panel', 'Other']

// What kind of query it is, in the Clearinghouse's own two words. A full query is run before
// hiring and needs the driver's electronic consent; a limited query is the annual one.
const QUERY_KIND = { CLEARINGHOUSE_PREEMP: 'Full', CLEARINGHOUSE: 'Limited' }

// RequirementDetail, when filing === 'order'.
export function OrderReportDialog({ busy, err, order, r, setFiling }) {
    return (
      <Modal title={`Order A ${r.name}`} onClose={() => setFiling(false)} width={520}
        footer={<>
          <button type="button" className="primary" disabled={busy}
            onClick={() => { order(); setFiling(false) }}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Yes'}
          </button>
          <button type="button" onClick={() => setFiling(false)}>No</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="askorder">
            <span className="askmark">?</span>
            <p>Order {r.name} for this driver?</p>
          </div>
        </div>
      </Modal>
    )
  
}

// RequirementDetail, when filing === 'against'.
export function FileAgainstDialog({ busy, err, fileAgainst, form, r, setFiling, setForm, source }) {
    return (
      <Modal title={`Add ${r.name}`} onClose={() => setFiling(false)} width={680}
        footer={<>
          <button type="button" className="primary" disabled={busy || !form.file}
            onClick={fileAgainst}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => setFiling(false)}>Cancel</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-2">
              {source.kind === 'credential' ? 'Issued'
                : source.kind === 'drugtest' ? 'Collected' : 'Dated'}
              <input type="date" value={form.effectiveon}
                onChange={(e) => setForm({ ...form, effectiveon: e.target.value })} />
            </label>
            <label className="field span-4">Copy *
              <input type="file"
                onChange={(e) => setForm({ ...form, file: e.target.files[0] || null })} />
            </label>
            <label className="field span-6">Note
              <textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </label>
          </div>
        </div>
      </Modal>
    )
  
}

// RequirementDetail, when filing === true.
export function AddRecordDialog({ busy, credentialtype, err, file, fillingOrder, form, needsResult, r, results, setFiling, setForm, source, tested, trained }) {
    return (
      <Modal title={`Add ${r.name}`} onClose={() => setFiling(false)} width={680}
        footer={<>
          <button type="button" className="primary"
            disabled={busy || (needsResult && !form.result)} onClick={file}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => setFiling(false)}>Cancel</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-2">
              {source.kind === 'credential' ? 'Issued'
                : source.kind === 'drugtest' ? 'Collected' : 'Dated'}
              <input type="date" value={form.effectiveon}
                onChange={(e) => setForm({ ...form, effectiveon: e.target.value })} />
            </label>
            {source.kind === 'credential' && (
              <label className="field span-2">Expires
                <input type="date" value={form.expireson}
                  onChange={(e) => setForm({ ...form, expireson: e.target.value })} />
              </label>
            )}
            {/* Training has somebody who gave it, and who that was is half the record. No federal
                rule names a trainer: a company may train its own drivers, buy a course, or be
                told by a broker to use the broker's module, and an auditor asking how a driver
                was trained is asking exactly this. Three answers cover every case, so it is
                chosen rather than typed - a free box gets "in house", "In-House", "internal"
                and "us" for the same answer, and none of them can be counted. */}
            {tested && (
              <>
                {/* F.A.C. 14-90.004(3)(d): trained AND tested before the driver operates the
                    applicable vehicle unsupervised. Two dates because they are two events, and
                    an office that only has the first has not met the rule. */}
                <label className="field span-2">Proficiency Tested
                  <input type="date" value={form.testedon}
                    onChange={(e) => setForm({ ...form, testedon: e.target.value })} />
                </label>
                <label className="field span-2">Tested By
                  <input value={form.testedby}
                    onChange={(e) => setForm({ ...form, testedby: e.target.value.toUpperCase() })} />
                </label>
              </>
            )}
            {trained && (
              <label className="field span-2">Trained By
                <select value={form.issuer}
                  onChange={(e) => setForm({ ...form, issuer: e.target.value })}>
                  <option value="">Choose</option>
                  {TRAINED_BY.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
            )}
            {credentialtype?.requiresprovenance ? (
              <label className="field span-2">Source *
                <select value={form.provenance || ''}
                  onChange={(e) => setForm({ ...form, provenance: e.target.value })}>
                  <option value="">Choose</option>
                  {Object.entries(PROVENANCE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
            ) : null}
            {/* The company's own drug screen: which panel was run, and what came back. */}
            {source.which === 'DRUG_SCREEN' && (
              <>
                <label className="field span-2">Type *
                  <select value={form.screentype || ''}
                    onChange={(e) => setForm({ ...form, screentype: e.target.value })}>
                    <option value="">Choose</option>
                    {SCREEN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </label>
                <label className="field span-2">Result *
                  <select value={form.screenresult || ''}
                    onChange={(e) => setForm({ ...form, screenresult: e.target.value })}>
                    <option value="">Choose</option>
                    {Object.entries(SCREEN_RESULTS).map(([v, l]) =>
                      <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
              </>
            )}
            {results.length > 0 && !fillingOrder && (
              <label className={`field ${needsResult ? 'span-4' : 'span-2'}`}>
                Result{needsResult ? ' *' : ''}
                <select value={form.result}
                  onChange={(e) => setForm({ ...form, result: e.target.value })}>
                  {!needsResult && <option value="">Not stated</option>}
                  {needsResult && <option value="">Choose</option>}
                  {results.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
            )}
            <label className="field span-6">
              {source.kind === 'drugtest' ? 'Test Result'
                : trained ? 'Certificate (recommended)' : 'Copy'}
              <input type="file"
                onChange={(e) => setForm({ ...form, file: e.target.files[0] || null })} />
            </label>
          </div>
        </div>
      </Modal>
    )
  
}

// Anything with no dialog of its own.
export function GeneralRequirementDialog({ ask, askForIt, asked, busy, canFile, cancelReport, data, err, latest, markRead, newest, onClose, order, orderable, r, readRecord, records, reports, results, reviewReport, setFiling, setViewing, shown, signable, source, tested, today, trained, unchecked, verified, verifyWith, viewing }) {  return (
    <>
      {/* A report's table carries five columns and a finding written out in full, so it gets the
          width a driving record's table gets rather than scrolling sideways inside a narrow one. */}
      {/* 680 was set when a requirement had a short name, three columns and two buttons. The
          names carry their citations now, the tables have grown a column at a time, and the
          actions spell out what they act on - so the description wrapped to six lines and
          "Add passenger assistance and wheelchair securement training" broke across two. */}
      <Modal title={r.name} onClose={onClose} brief={r?.description}
        width={source.kind === 'credential' && !shown.length ? 720 : DETAIL}
        footer={<>
          {/* Reading comes first, because reading is what most people opened this to do. It
              opens the most recent document on file; an older one is named by its own row. */}
          {source.kind !== 'report' && newest && (
            <button type="button" onClick={() => setViewing({
              documentid: newest.documentid, filename: r.name,
              check: unchecked.has(newest.documentid),
              record: newest.needsreading ? newest : null })}>
              <Eye size={14} /> {unchecked.has(newest.documentid) || newest.needsreading
                ? 'Review' : 'View'}
            </button>
          )}
          {/* A query, read the way the PHI acknowledgement is: the latest one opened from here,
              first, rather than from a button on its row. */}
          {source.kind === 'report' && (() => {
            const latest = (reports?.reports || [])[0]
            if (!latest || latest.state === 'ordered' || !latest.documentid) return null
            const reading = !latest.outcome
            return (
              <button type="button" className="primary" onClick={() => setViewing({
                documentid: latest.documentid, filename: r.name,
                review: reading ? latest.recordid : null })}>
                <Eye size={14} /> {reading ? 'Review' : 'View'}
              </button>
            )
          })()}
          {/* The way to the place the answer comes from, left of the dialog's own buttons: nobody
              can file a query they have not run, and the query is run at the authority's site. */}
          {source.kind === 'report' && REPORT_SITES[source.which] && (
            <a className="btn footlink" href={REPORT_SITES[source.which][1]}
              target="_blank" rel="noreferrer">
              <ExternalLink size={13} /> Open The {REPORT_SITES[source.which][0]}
            </a>
          )}
          {/* What can be done about it, which depends on what kind of thing would answer it. */}
          {canFile && source.kind !== 'report' && (
            <button type="button" onClick={() => setFiling(true)}>
              {source.kind === 'credential'
                ? <><FileUp size={13} /> Upload Document</>
                : <><Plus size={13} /> Add {r.name}</>}
            </button>
          )}
          {orderable && source.kind !== 'report' && (
            <button type="button" disabled={busy} onClick={order}>
              <Send size={13} /> Send for it
            </button>
          )}
          {/* A query already out stops BOTH: the answer on its way is what fills it, and a second
              order or a hand-filed result would leave two answers with nothing to say which belongs
              to which question. Cancel the order first, on the row, and these come back. */}
          {source.kind === 'report'
            && !(reports?.reports || []).some((x) => x.state === 'ordered') && (
            <>
              <button type="button" disabled={busy} onClick={() => setFiling('order')}>
                <Send size={13} /> Order
              </button>
              <button type="button" onClick={() => setFiling(true)}>
                <Plus size={13} /> Upload
              </button>
            </>
          )}
          {/* A query out and not back: file the answer when it comes, or call the order off. */}
          {source.kind === 'report' && (reports?.reports || [])[0]?.state === 'ordered' && (
            <>
              <button type="button" onClick={() => setFiling(true)}>
                <Plus size={13} /> Upload
              </button>
              <button type="button" disabled={busy}
                onClick={() => cancelReport(reports.reports[0].recordid)}>
                Cancel Order
              </button>
            </>
          )}
          {signable && (
            <button type="button" disabled={busy} onClick={ask}>
              <FileSignature size={13} /> Ask the driver to sign
            </button>
          )}
          {source.kind === 'credential' && (
            <button type="button" disabled={busy} onClick={() => askForIt()}>
              <Send size={13} /> Ask the driver for it
            </button>
          )}
          {/* A question only the applicant can answer, sent to them the same way anything else is
              asked of a driver - 49 CFR 40.25(j). */}
          {/* The questionnaire: only while there is nothing on file. Once it is answered it is
              read and viewed from the table, the same as any other record - asking again for
              something already held is not an action anybody wants offered. */}
          {source.kind === 'applicationanswered' && !records.length && (
            <>
              <button type="button" disabled={busy}
                onClick={() => askForIt('PREEMP_DA_QUESTIONNAIRE')}>
                <Send size={13} /> Send To Driver
              </button>
              {/* Or file the one they filled in on paper - it is the same answer, and the only
                  difference is that nobody typed it in. */}
              <button type="button" onClick={() => setFiling('against')}>
                <Plus size={13} /> Upload
              </button>
            </>
          )}
          {/* The verification: what closes this one is paperwork from the process itself - the
              SAP's determination, the return-to-duty result - which the applicant cannot supply by
              answering the question again. So there is nothing to send them, and the office files
              what it has been given. */}
          {/* The proof is held by the driver, not by this office: the SAP who evaluated them
              worked for somebody else. So where they have sent nothing, the only thing to do is
              ask them for it - and where they have, there is nothing to do here but read it, which
              happens on the row. */}
          {source.kind === 'applicationanswer' && !data.driverattached && (
            <button type="button" disabled={busy}
              onClick={() => askForIt('RTD_DOCUMENTATION')}>
              <Send size={13} /> Ask The Driver For It
            </button>
          )}
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {asked}
          {/* The same table a driving record gets, because it is the same job: sent for, filed,
              read, and what the office concluded from reading it. One row, because there is one
              query - unlike a license, of which a driver may hold several. */}
          {source.kind === 'report' && (() => {
            const all = reports?.reports || []
            // Nothing sent for and nothing on file is not a table with a row of dashes in it.
            if (!all.length) {
              return <div className="gridempty">No {r.name} On File For This Driver</div>
            }
            // The latest query only, as the PHI acknowledgement shows the latest signing: it is the
            // one that answers the requirement, and the footer opens it.
            const x = all[0]
            const ordered = x.state === 'ordered'
            const reading = !ordered && !x.outcome
            const stale = Boolean(x.expireson) && x.expireson < today
            return (
              <table className="residencetable recordtable">
                <thead><tr><th>Date</th><th>Document</th><th>Expires</th><th>Status</th></tr></thead>
                <tbody>
                  <tr>
                    <td>{ordered ? `Ordered ${date(x.orderedon)}` : x.issuedon ? date(x.issuedon) : '-'}</td>
                    <td>{QUERY_KIND[source.which] || r.name}</td>
                    {/* 49 CFR 382.701(b): a query stands for a year, worked out from the rule. */}
                    <td>{x.expireson ? date(x.expireson) : '-'}</td>
                    <td className={ordered || reading ? 'st-ordered' : stale
                      || x.outcome === 'prohibited' ? 'st-expired' : 'st-active'}>
                      {ordered ? 'Not Back Yet' : reading ? 'Not Reviewed' : stale ? 'Expired'
                        : reports?.outcomes?.[x.outcome] || 'Reviewed'}
                    </td>
                  </tr>
                </tbody>
              </table>
            )
          })()}
          {source.kind !== 'report' && !shown.length && (
            <div className={source.kind === 'credential'
              ? 'gridempty' : 'muted'}>
              No {plural(r.name)} On File For This Driver
            </div>
          )}
          {source.kind !== 'report' && shown.length > 0 && (
          <table className="residencetable recordtable">
            {/* Who trained the driver gets a column of its own on a training record, because it
                is a fact about the record rather than a decoration on another one. */}
            {/* Sized by what each column holds, not by where it sits. Exactly ONE column here
                has content that can grow: "Tested" carries a date and a person's name. "Valid"
                is a fixed-format date, "Trained by" is one of three dropdown values and
                "Status" is one word - none of them will ever need more room than they need
                today, so none of them should be given the slack. */}
            <thead><tr><th>Valid</th>{trained && <th>Trained by</th>}
              {tested && <th className="growcol">Tested</th>}<th>Status</th>
              {/* When there is no Tested column there is nothing on the row that can grow, so
                  the slack goes behind the buttons rather than into a date column. */}
              <th className={tested ? undefined : 'growcol'} /></tr></thead>
            <tbody>
              {shown.map((rec) => {
                // Either route in: a document that came down an upload link and nobody opened,
                // or any record the engine says this office has still to read.
                const waiting = unchecked.has(rec.documentid) || rec.needsreading
                // A rule the driver ANSWERED is closed by somebody reading what they sent and
                // saying it shows what the rule asks for. Until they have, the row offers the
                // reading; afterwards there is nothing left to do but look at it again.
                const toverify = source.kind === 'applicationanswer' && !verified
                // Read, or not read. That is the whole of what this column has to say about a
                // document whose standing is somebody's reading of it.
                const [says, tone] = waiting
                  ? ['Not Reviewed', 'st-ordered']
                  : source.kind === 'applicationanswer'
                    ? (verified ? ['Reviewed', 'st-active'] : ['Not Reviewed', 'st-ordered'])
                    : standingOf(rec, results)
                return (
                  <tr key={rec.recordid}>
                    <td>{valid(rec)}</td>
                    {trained && <td>{rec.issuer || 'Not recorded'}</td>}
                    {tested && (
                      <td className={`growcol ${rec.testedon ? '' : 'st-ordered'}`.trim()}>
                        {rec.testedon
                          ? `${date(rec.testedon)}${rec.testedby ? ` · ${rec.testedby}` : ''}`
                          : 'Not tested'}
                      </td>
                    )}
                    <td className={tone}>{says}</td>
                    <td className={`actions${tested ? '' : ' growcol'}`}>
                      {rec.documentid && (
                        <button type="button"
                          className={`linkbtn edit${waiting || toverify ? ' toread' : ''}`}
                          onClick={() => setViewing({ documentid: rec.documentid, filename: r.name,
                            check: unchecked.has(rec.documentid), verify: toverify,
                            record: rec.needsreading ? rec : null })}>
                          {waiting || toverify ? 'Review' : 'View'}
                        </button>
                      )}
                      {/* A record with nothing to look at is still a record somebody has to
                          accept - an exclusion screening, a pool membership, a license with no
                          copy attached. */}
                      {!rec.documentid && rec.needsreading && (
                        <button type="button" className="linkbtn edit toread" disabled={busy}
                          onClick={() => readRecord(rec)}>Mark As Reviewed</button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          )}
        </div>
      </Modal>
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)}
        action={<>
          {viewing.check && (
            <button type="button" className="primary" disabled={busy}
              onClick={() => { markRead(viewing.documentid); setViewing(null) }}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
            </button>
          )}
          {/* The same act for a record that did not come down an upload link - the license
              photographed on the application, a screening, a test result somebody filed. */}
          {!viewing.check && viewing.record && (
            <button type="button" className="primary" disabled={busy}
              onClick={() => { readRecord(viewing.record); setViewing(null) }}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
            </button>
          )}
          {/* Read, and found to show what the rule asks for. Made here because this is the only
              place anybody can honestly make it: with the document on screen. */}
          {viewing.verify && (
            <button type="button" className="primary" disabled={busy}
              onClick={() => { verifyWith(viewing.documentid); setViewing(null) }}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Return To Duty Verified'}
            </button>
          )}
          {/* The determination is made while looking at the query result, which is the only place
              anybody can honestly make it. */}
          {viewing.review && Object.entries(reports?.outcomes || {}).map(([v, l]) => (
            <button key={v} type="button" disabled={busy}
              className={v === 'prohibited' ? '' : 'primary'}
              onClick={() => { reviewReport(viewing.review, v); setViewing(null) }}>
              {l}
            </button>
          ))}
        </>} />}
    </>
  )
}

// Where a report is actually obtained. TripProof does not pull any of these - somebody signs in at
// the authority's own site and runs the query - so the panel that asks for one says where to go.
const REPORT_SITES = {
  CLEARINGHOUSE_PREEMP: ['Clearinghouse', 'https://clearinghouse.fmcsa.dot.gov/'],
}

// Who gave the training. No federal rule names a trainer, and these three cover every way a
// driver actually gets trained: the company does it, a course is bought, or a broker requires
// its own module.
const TRAINED_BY = ['In-House', 'Training Organization', 'Broker/Contractor']
