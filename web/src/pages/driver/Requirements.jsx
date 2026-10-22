// Driver page - Requirements. Moved out of
// pages/DriverReview.jsx, which had grown too large to work in safely.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../../lib/states.js'
import { api } from '../../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../../lib/live.js'
import { date } from '../../lib/format.js'
import { Bubble, Loading, useLoad } from '../../components/ui.jsx'
import { Modal } from '../../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../../components/Pager.jsx'
import { useUser } from '../../App.jsx'
import SignatureBlock from '../../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../../components/DocumentViewer.jsx'
import ApplicantForm from '../../components/ApplicantForm.jsx'
import SignedDocViewer from '../../components/SignedDocViewer.jsx'
import { PhoneInput } from '../../components/MaskedInput.jsx'
import LicenseDialog from '../../components/LicenseDialog.jsx'
import TestDialog from '../../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../../components/WithdrawDialog.jsx'
import { Email, Phone } from '../../components/Contact.jsx'
import { BLANK_CRASH, CRASH_STATE, FROM_ROW, unread, when } from './common.jsx'
import { DriverLicenses } from './Licenses.jsx'
import { ProhibitionPanel } from './Testing.jsx'
import { CrashDialog } from './Accidents.jsx'

import { BLANK_EXAM } from './requirement/common.jsx'
import { MvrDialog, MvrOrderDialog, MvrUploadDialog } from './requirement/Mvr.jsx'
import { EmployerHistoryDialog } from './requirement/EmployerHistory.jsx'
import { DrugScreenDialog, DrugTestingDialog } from './requirement/Testing.jsx'
import { TransitMedicalDialog } from './requirement/TransitMedical.jsx'
import { RoadTestDialog } from './requirement/RoadTest.jsx'
import { AnnualReviewDialog } from './requirement/AnnualReview.jsx'
import { BackgroundScreening, ExclusionDetail } from './requirement/Screening.jsx'
import { AtFaultRecord, CdlisMedicalDialog, DriverFactDialog, LicenseMatchDialog, LicensesHeldDialog, RandomPoolDialog, SecurementRecord } from './requirement/Records.jsx'
import { LatestDocumentDialog, QualificationFileDialog, QuestionnaireDialog, RequestHistoryDialog } from './requirement/Documents.jsx'
import { AddRecordDialog, FileAgainstDialog, GeneralRequirementDialog, OrderReportDialog } from './requirement/General.jsx'

// The three ways of looking at one driver, in the order an office works through them.
// Every driver can operate an ordinary vehicle, so that is not something to declare - these are
// what they are cleared for beyond it. Ticked cumulatively, because the thresholds are nested: a
// CDL vehicle is always a commercial motor vehicle, and 26,001 lb always needs a CDL. Ticking one
// ticks what it implies and unticking one clears what depends on it, so the set is always a set
// that can exist. The record keeps the highest level reached, not three separate flags.

// The standings that are a requirement not met, as against one still on its way.
const FAILED = ['failed', 'expired', 'overdue']

// Every requirement backed by one document - a signed form, a certificate - opens in the one layout
// (components/RequirementDialogs.jsx): the latest on file, its standing, and View. Which extras it
// carries is read off the rule rather than kept in a list here - a rule that recurs gets the expiry,
// the next upload and its history - so a requirement added tomorrow opens the way the others do.
// A form completed again from the same dialog - a new W-4 when withholding changes. The I-9 is
// completed once.
const COMPLETED_AGAIN = new Set(['W4'])

// What is asked of this driver, and why it is asked.
//
// Nothing on this screen is stored. The rules come from compliancerules, the facts are assembled
// from the company and its fleet, and each answer is read from the record that already holds it -
// so this cannot drift out of step with the MVR or the review the way the old checklist did.
//
// Three groups, because they are three different jobs. What is outstanding is work. What is
// unanswerable is a question for the office, not for the driver - a rule that cannot be decided
// says which fact it is waiting on. What does not reach this driver is listed last and collapsed,
// because the reason a thing is NOT asked is worth being able to check and is not worth the room.

// The three kinds of obligation in a driver's file, in the order an office reads them: what the
// driver has to agree to, what the law asks, and what this company asks on top.
// The regulatory ones split again, by whether the thing is wanted before the driver starts work or
// is owed by somebody already on the books. `predrive` sits with the first: the road test, the
// medical card and the pre-employment test are all gathered while a hire is being decided, and
// somebody reading this list before taking a person on has to see them. Where it differs from
// `prehire` is what the dashboard does with it - a predrive item does not stand between the company
// and the hire, only between the driver and a vehicle - and the row says so in its own words.
const GROUPS = [
  ['consent', 'Driver Consents And Acknowledgements', null],
  ['regulatory', 'Federal And State Requirements (Pre-Hire)', ['prehire', 'predrive']],
  ['regulatory', 'Federal And State Requirements (Post Hire)', ['athire', 'ongoing']],
  ['company', 'Company Requirements', null],
  ['hr', 'Employment Onboarding', null],
]

// Once somebody is hired the hiring questions are answered, and a list of what is owed should
// not be half full of things that were settled months ago. But "pre-hire" is a stage, not a
// lifetime: the license, the driving record and the exclusion screenings are all asked before
// hiring AND go out of date afterwards, and hiding the stage hid the renewals with it.
//
// So what drops off a hired driver's list is the pre-hire work that is FINISHED - asked once,
// answered, never asked again. Anything that recurs stays, and so does anything still
// outstanding or gone wrong, whatever stage it belongs to. A panel with nothing left in it
// does not render, so the consents disappear by themselves once they are all signed rather
// than by being singled out.
const ONE_OFF = ['once', 'perhire']

const settledHistory = (i) => (i.duestage || 'prehire') === 'prehire'
  && ONE_OFF.includes(i.recurrence || 'once')
  && ['satisfied', 'expiring'].includes(i.status)

const HIRED_GROUPS = [
  ['regulatory', 'Federal And State Requirements', null],
  ['company', 'Company Requirements', null],
  ['consent', 'Driver Consents And Acknowledgements', null],
  ['hr', 'Employment Onboarding', null],
]

// Which section a row sits in. An HR obligation is its own section whatever its source: it is
// chased and kept, but it never stands between a qualified driver and a trip.
const sectionOf = (i) => (i.enforcement === 'hr' ? 'hr' : (i.grouping || 'regulatory'))

// Every source behind one qualification, on one line - the law, the program and the contract that
// each ask for it - with each named once.
// The authority and its citation, without saying the same word twice where the citation already
// begins with the authority's own short name - "Georgia DCH" and "DCH NEMT Part II".
const citedBy = (authority, citation) => {
  const tail = (authority || '').split(' ').pop()
  return tail && (citation || '').startsWith(`${tail} `)
    ? `${authority}${citation.slice(tail.length)}` : [authority, citation].filter(Boolean).join(' ')
}

const sourcesLine = (i) => [...new Set((i.sources?.length ? i.sources : [i]).map((x) =>
  (x.because === 'company' ? 'Company policy' : citedBy(x.authority, x.citation))))]

// When it falls due, shown on the row rather than as a heading now that the headings say what
// kind of thing it is.
const STAGE = { prehire: 'Before hiring', predrive: 'Before driving', athire: 'Once hired',
                ongoing: 'Ongoing' }

const STAGE_ORDER = ['prehire', 'predrive', 'athire', 'ongoing']

export function Requirements({ id, onChanged, focus, onGoSection }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/requirements`), [id])
  const [open, setOpen] = useState(null)
  // A link that names a requirement opens it. The dashboard says what is wrong and this is how it
  // hands somebody the thing itself, rather than the page the thing is somewhere on.
  const [params, setParams] = useSearchParams()
  const wanted = params.get('req')
  useEffect(() => {
    if (!wanted || !data) return
    const found = data.items.find((i) => i.code === wanted)
    if (found) setOpen(found)
    // Taken out of the address once it has been acted on, so a refresh does not reopen it.
    setParams((p) => { p.delete('req'); return p }, { replace: true })
  }, [wanted, data])
  // Arriving from a dashboard row: the list is long and the thing somebody clicked is usually
  // not at the top of it. The row is scrolled to rather than opened - they asked to see where it
  // sits, which is a different request from "open this".
  // Scrolling it into view is half the job: it puts the row in front of somebody without saying
  // which row it is, and every line on this list looks like the one above it. So the row marks
  // itself as it arrives. The mark is applied AFTER the scroll settles - started at the same
  // moment it would be half over by the time the row got here - and removed when it has played,
  // so nothing on the page is left permanently different for having been visited once.
  //
  // Once, and once only. This waits on `data` because the row has to exist before it can be
  // scrolled to - but `data` reloads every time anything on this page is saved, and without the
  // guard below every edit sent the page scurrying back to whatever was clicked on the way in and
  // lit it up again. Somebody filing three documents watched the first one flash at them three
  // times. The arrival is a single event; this remembers that it has happened.
  const landed = useRef(null)
  useEffect(() => {
    if (!focus || !data) return undefined
    if (landed.current === focus) return undefined
    const row = document.getElementById(`req-${focus}`)
    if (!row) return undefined
    landed.current = focus
    row.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const start = setTimeout(() => row.classList.add('landed'), 320)
    const end = setTimeout(() => row.classList.remove('landed'), 320 + 2200)
    return () => { clearTimeout(start); clearTimeout(end); row.classList.remove('landed') }
  }, [focus, data])
  // What is asked of a driver depends on facts kept elsewhere - the company's answers, the fleet -
  // so this list can go stale while it sits open in a tab. Answering a question on the company page
  // and coming back here should show the new answer, not the one from before you left.
  useRefreshOnFocus(reload, !open)
  if (!data) return <div className="card qualcard"><h3>Requirements</h3><Loading error={error} /></div>

  // The server already decided this, and decided it the same way the engine does - whether
  // anything is being held back until hire. Reading it rather than working it out again keeps
  // the two from drifting.
  const onbooks = Boolean(data.hired)
  const live = data.items.filter((i) => i.applies === true)
  const undecided = data.items.filter((i) => i.applies === null)
  // A deadline that has gone by is not a deadline. "Before hiring", printed beside a driver who
  // was hired in March, reads as a thing still to be arranged rather than as a thing that is
  // either done or late, so for somebody already on the roster it is not printed at all.
  const passed = (i) => onbooks && ['prehire', 'athire'].includes(i.duestage || 'prehire')

  const rows = (list) => list.map((i) => (
    <div key={i.code} id={`req-${i.code}`} className="factrow reqrow">
      <div className="reqmark"><Bubble state={i.status} /></div>
      <div className="factwhat reqname">
        {i.name}
        <span className="factcite">
          {/* The stage decides which section a requirement sits in; the sentence it prints is its
              own where the stage is not the whole truth - the safety performance history belongs
              before hiring and is due 30 days after it.
              And where the company is the one asking, the federal citation does not belong here at
              all: printing it beside a requirement the regulation does not impose tells an auditor
              the carrier cannot tell its own obligations from the law's. */}
          {[...sourcesLine(i), passed(i) ? null : i.duetext || STAGE[i.duestage]]
            .filter(Boolean).join(' · ')}
        </span>
        {/* A rule nobody can decide is not a rule holding anything up - it is a question nobody
            has answered, and the only useful thing to print is the question and where to answer
            it. The rule's own note is about what the requirement means, which is no help to
            somebody who does not yet know whether it reaches them at all. */}
        {i.applies === null
          ? <span className="factasking">{i.why}</span>
          // A requirement that fails says why and what to do, on the row where it is first seen.
          : FAILED.includes(i.status) && i.why
            ? <span className="factasking factfails">{i.why}</span>
            // Waiting on somebody here: say on what, so a document already read that still needs
            // something else does not look as if it is waiting to be read.
            : i.status === 'review' && i.why
              ? <span className="factasking factwaits">{i.why}</span>
              : i.note && <span className="factnote">{i.note}</span>}
      </div>
      <div className="reqdo">
        {/* Disabled rather than hidden: the column stays straight down the page, and a button
            that is there and dead says "nothing to see" more plainly than a gap does. */}
        <button type="button" disabled={i.readonly} onClick={() => setOpen(i)}>
          <FileUp size={13} /> Details
        </button>
      </div>
    </div>
  ))

  // What kind of obligation it is, which is a different question from when it falls due. When is
  // still on every row, next to the citation, because it is the thing somebody needs while they
  // are deciding whether to take a person on.
  const grouped = (key, stages) => live
    .filter((i) => sectionOf(i) === key)
    .filter((i) => !stages || stages.includes(i.duestage || 'prehire'))
    .filter((i) => !onbooks || !settledHistory(i))
    .sort((a, b) => STAGE_ORDER.indexOf(a.duestage) - STAGE_ORDER.indexOf(b.duestage))

  // Four answers, each to its own question: hired, onboarding, and qualified for each program.
  // Only a program whose every requirement is met reads Qualified; unknown never does.
  const ov = data.overview
  const toneOf = (x) => ({ Qualified: 'st-active', Complete: 'st-active', 'Not Applicable': 'st-inactive',
    'Not Qualified': 'st-expired', Overdue: 'st-expired' }[x] || 'st-ordered')

  return (
    <>
      {ov && (
        <div className="card factpanel">
          <h3 className="reqhead">Qualification Overview</h3>
          <dl className="askfacts overviewfacts">
            <div><dt>Employment</dt><dd>{ov.employment}</dd></div>
            <div><dt>Employment Onboarding</dt>
              <dd className={toneOf(ov.onboarding.status)}>{ov.onboarding.status}</dd></div>
            {/* The program and its standing on one line, what stands in the way listed beneath. */}
            {ov.programs.map((pg) => (
              <div key={pg.program} className="ovprogram"><dt>{pg.label}</dt>
                <dd className={toneOf(pg.status)}>{pg.status}</dd>
                {pg.reasons.length > 0 && (
                  <ul className="ovreasons">{pg.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
                )}
              </div>
            ))}
          </dl>
        </div>
      )}
      {(onbooks ? HIRED_GROUPS : GROUPS).map(([key, title, stages]) => {
        const list = grouped(key, stages)
        if (!list.length) return null
        return (
          <div key={title} className="card factpanel">
            <h3 className="reqhead">{title}</h3>
            {rows(list)}
          </div>
        )
      })}


      {undecided.length > 0 && (
        <div className="card factpanel">
          <h3 className="reqhead">Waiting On An Answer From The Company</h3>
          {/* Said once at the top rather than on every row: none of these is stopping anybody. */}
          <p className="reqaside">
            Nothing here is holding this driver up. Each one depends on something about the company
            that nobody has answered yet, so TripProof cannot say whether it reaches this driver.
          </p>
          {rows(undecided)}
        </div>
      )}

      {open && (
        <RequirementDetail id={id} code={open.code} onClose={() => setOpen(null)}
          // One requirement can send somebody to another: a review that cannot be completed for
          // want of a driving record points at the requirement that orders one, rather than
          // growing an ordering control of its own.
          onOpen={(c) => setOpen(data.items.find((i) => i.code === c) || null)}
          onGoSection={onGoSection}
          // The banner above this screen reads the same gate these requirements feed, so a
          // change here has to reach it now rather than at the next poll. Anything that lifts a
          // bar lifts it on the spot, which is what somebody filing the last piece expects to see.
          onChanged={() => { reload(); onChanged?.() }} />
      )}
    </>
  )
}

// One requirement, what is held against it, and the form that would answer it.
//
// There is no dialog per requirement and no switch on the requirement's code. The rule says what
// kind of evidence it takes - a document, a query, a test, a signature - and where that evidence
// lives, and the form follows from that. So a new rule about a new report is a row in the database
// and this screen already knows how to work it.

const RESULTS = {
  report: [['clear', 'Clear'], ['review', 'Needs a look'], ['flagged', 'Adverse']],
  drugtest: [['negative', 'Negative'], ['positive', 'Positive'], ['refusal', 'Refusal'],
    ['cancelled', 'Cancelled']],
  annualreview: [['qualified', 'Qualified'], ['notqualified', 'Disqualified']],
}

// Section 2 of the I-9 - 8 CFR 274a.2(b)(1)(ii).
//
// The driver signed Section 1. This is the employer's certification, which is a different person
// making a different statement under penalty of perjury, so it is signed rather than clicked. Not
// one box on it is typed: the company is the company on file, the first day of work is the hire
// date on the driver's record, and the name and title are whoever is signing. What the screen asks
// of a person is the only part that is theirs - that they looked at the documents, and will put
// their name to having looked.
function CertifyI9({ id, onClose, onDone }) {
  const [data, error] = useLoad(() => api.get(`/drivers/${id}/signed/I9/certification`), [id])
  const [signature, setSignature] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const file = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/drivers/${id}/signed/I9/certify`, { signatureid: signature.recordid })
      onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <Modal title="Certify Section 2 Of The I-9" onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={!signature || busy} onClick={file}>
          {busy ? <Loader2 size={15} className="spin" /> : 'File Certification'}
        </button>
      </>}>
      {!data ? <Loading error={error} /> : (
        <div className="stack">
          <dl className="askfacts">
            <div><dt>Employee</dt><dd>{data.employee}</dd></div>
            <div><dt>First day of employment</dt>
              <dd>{data.firstday ? date(data.firstday) : 'Not recorded'}</dd></div>
            <div><dt>Employer or authorized representative</dt><dd>{data.who}</dd></div>
            <div><dt>Business name</dt><dd>{data.orgname || '-'}</dd></div>
            <div><dt>Business address</dt><dd>{data.orgaddress || '-'}</dd></div>
          </dl>
          <SignatureBlock signature={signature} onSigned={setSignature}
            label="Signature Of Employer Or Authorized Representative" action="Sign" />
          {err && <div className="error">{err}</div>}
        </div>
      )}
    </Modal>
  )
}

function RequirementDetail({ id, code, onClose, onChanged, onOpen, onGoSection }) {
  const me = useUser()
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/requirements/${code}`), [id, code])
  const [filing, setFiling] = useState(false)
  const [certifying, setCertifying] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [testHistory, setTestHistory] = useState(false)
  const [mvrHistory, setMvrHistory] = useState(null)
  const [annualHistory, setAnnualHistory] = useState(false)
  const [credHistory, setCredHistory] = useState(false)   // every one of a renewed credential
  const [signedDoc, setSignedDoc] = useState(null)
  const [loadingSigned, setLoadingSigned] = useState(false)
  const [annual, setAnnual] = useState(null)
  const [completing, setCompleting] = useState(null)
  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({ effectiveon: today, expireson: '', result: '', note: '',
    issuer: '', testedon: '', testedby: '',
    file: null, front: null, back: null, licenseid: '',
    selfcert: '', medcertstatus: '', medcertexpires: '', medvariancetype: '', medvariance: '' })
  const [exam, setExam] = useState(() => BLANK_EXAM(today))
  const [pending, setPending] = useState(null)
  const [testing, setTesting] = useState(null)
  const [crashes, setCrashes] = useState(null)   // the accident register, with the 382.303 call
  const [reports, setReports] = useState(null)  // everything sent for and everything back
  const [crash, setCrash] = useState(BLANK_CRASH)
  const [sphi, setSphi] = useState(null)
  const [inq, setInq] = useState(null)          // the employer being acted on
  const [sphiHistory, setSphiHistory] = useState(null)   // an employer's attempts, opened
  const [confirmed, setConfirmed] = useState(null)   // what just went out, once it has
  const [mysig, setMysig] = useState(null)      // whether this user has a signature at all
  const [att, setAtt] = useState({ channel: 'email', sentto: '', senton: '', outcome: '',
                                   note: '', signature: '' })
  // 49 CFR 391.23(i): how the investigation ended, and the note behind it.
  const [gfe, setGfe] = useState({ status: 'noresponse', note: '' })
  // What was signed in this sitting. Signing is its own act - Sign Document, date of birth and
  // Social Security number, lookup, sign - and nothing is drawn until it has happened.
  const [gfesig, setGfesig] = useState(null)
  // Everything this driver has ever been asked for on this requirement. Not the same question as
  // "is something in flight" - this is the one somebody asks before chasing a driver a fourth time.
  const [asks, setAsks] = useState(null)
  // 49 CFR 391.31. One event with one output, so this is the tests themselves, not documents.
  const [roadtests, setRoadtests] = useState(null)
  const [examiner, setExaminer] = useState({ name: '', email: '', title: '', organization: '' })

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); reload(); onChanged?.() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const loadAnnual = () => api.get(`/drivers/${id}/annual-reviews`).then(setAnnual)
    .catch((e) => setErr(e.message))

  // A requirement nobody has chased reads differently from one where the driver was asked a
  // fortnight ago and has not answered, so what was asked is loaded with the dialog rather than
  // shown only for the moment after the asking.
  const loadPending = async (kind, which) => {
    try {
      if (kind === 'signature') {
        const got = await api.get(`/drivers/${id}/signing-requests`)
        setPending((got.requests || []).find((x) => x.doctype === which) || null)
      } else if (kind === 'credential' || kind === 'licensecopy'
                 || kind === 'applicationanswered' || kind === 'applicationanswer') {
        // A license copy is asked for as the license itself, which is what it becomes.
        const code = kind === 'licensecopy' ? 'DRIVER_LICENSE'
          : kind.startsWith('applicationanswer') ? 'PREEMP_DA_QUESTIONNAIRE' : which
        const got = await api.get(`/drivers/${id}/upload-requests`)
        setPending((got.requests || []).find((x) => x.credentialcode === code) || null)
      }
    } catch { setPending(null) }
  }
  useEffect(() => {
    if (data?.source?.kind) loadPending(data.source.kind, data.source.which)
  }, [data?.source?.kind, data?.source?.which, id])   // eslint-disable-line react-hooks/exhaustive-deps

  // Whether this driver may drive today is a different question from whether their file is in
  // order, and the drug and alcohol requirement is where the two meet.
  const loadTesting = () => api.get(`/drivers/${id}/testing`).then(setTesting)
    .catch((e) => setErr(e.message))
  // 49 CFR 390.15(b) keeps the register; 382.303 decides which of those accidents owed a test. The
  // two are read together because they are the same event seen twice.
  const loadAccidents = () => api.get(`/drivers/${id}/accidents`).then(setCrashes)
    .catch((e) => setErr(e.message))
  const loadReports = () => api.get(`/drivers/${id}/reports/${source.which}`).then(setReports)
    .catch((e) => setErr(e.message))
  const loadRoadTests = () => api.get(`/drivers/${id}/road-tests`).then(setRoadtests)
    .catch((e) => setErr(e.message))

  const sendRoadTest = () => act(async () => {
    await api.post(`/drivers/${id}/road-tests`, examiner)
    await loadRoadTests()
    setExaminer({ name: '', email: '', title: '', organization: '' })
    setFiling(false)
  })

  const reviewRoadTest = (recordid) => act(async () => {
    await api.post(`/drivers/${id}/road-tests/${recordid}/reviewed`, {})
    await loadRoadTests()
  })

  // Reading it is what answers it, so this is its own act with its own record of who did it.
  const reviewReport = (reportid, finding) => act(async () => {
    await api.post(`/drivers/${id}/reports/${source.which}/${reportid}/reviewed`, { finding })
    await loadReports()
  })

  const cancelReport = (reportid) => act(async () => {
    await api.del(`/drivers/${id}/reports/${source.which}/${reportid}`)
    await loadReports()
  })


  useEffect(() => {
    if (data?.source?.kind === 'drugtest') { loadTesting(); loadAccidents() }
    if (data?.source?.kind === 'report') loadReports()
    if (data?.source?.kind === 'roadtest') loadRoadTests()
  }, [data?.source?.kind, id])   // eslint-disable-line react-hooks/exhaustive-deps

  // 391.23 is answered employer by employer, and 391.23(i) counts the asking where the answer
  // never comes - so what this loads is the inquiries and every attempt made on each.
  const loadSphi = () => api.get(`/drivers/${id}/employer-inquiries`).then(setSphi)
    .catch((e) => setErr(e.message))
  useEffect(() => {
    if (data?.source?.kind === 'employerhistory') loadSphi()
  }, [data?.source?.kind, id])   // eslint-disable-line react-hooks/exhaustive-deps

  // Email is the only channel TripProof can actually send on, so it is the only one that sends.
  // The rest are attempts the office made elsewhere and records here - which 391.23(i) counts just
  // the same, because it asks what the carrier did, not what this software did.
  const sendRequest = () => act(async () => {
    if (att.channel === 'email') {
      await api.post(`/drivers/${id}/employer-inquiries/${inq.recordid}/email`,
        { to: att.sentto || null })
    } else {
      await api.post(`/drivers/${id}/employer-inquiries/${inq.recordid}/attempts`, {
        channel: att.channel, sentto: att.sentto || null, outcome: att.outcome || null,
        note: att.note || null, senton: att.senton || null,
      })
    }
    const got = await api.get(`/drivers/${id}/employer-inquiries`)
    setSphi(got)
    setInq((got.inquiries || []).find((x) => x.recordid === inq.recordid) || null)
    // Sending is the thing being recorded, so it is confirmed rather than left to be inferred from
    // a row quietly changing behind the dialog.
    setConfirmed({ channel: att.channel, to: att.sentto, employer: inq.employer })
    setFiling('sent')
  })

  // A reply that came back on paper or by fax. It is the same answer, and the only thing missing
  // is that nobody typed it in - so what is kept is the page they sent.
  const uploadReply = () => act(async () => {
    const body = new FormData()
    if (att.sentto) body.append('respondedby', att.sentto)
    if (att.note) body.append('note', att.note)
    if (att.file) body.append('file', att.file)
    await api.post(`/drivers/${id}/employer-inquiries/${inq.recordid}/response`, body)
    const got = await api.get(`/drivers/${id}/employer-inquiries`)
    setSphi(got)
    setInq((got.inquiries || []).find((x) => x.recordid === inq.recordid) || null)
    setFiling('send')
  })

  const reviewReply = () => act(async () => {
    await api.post(`/drivers/${id}/employer-inquiries/${inq.recordid}/review`, {})
    const got = await api.get(`/drivers/${id}/employer-inquiries`)
    setSphi(got)
    setInq((got.inquiries || []).find((x) => x.recordid === inq.recordid) || null)
    setFiling(false)
  })

  const closeEffort = () => act(async () => {
    await api.post(`/drivers/${id}/employer-inquiries/${inq.recordid}/good-faith`,
      { status: gfe.status, note: gfe.note || null })
    await loadSphi()
    // Back to the list of employers, which is where somebody is when they are working through
    // them - not back into the dialog for the one they have just finished with.
    setFiling(false)
    setGfesig(null)
  })

  useEffect(() => {
    if (data?.source?.kind === 'annualreview') loadAnnual()
  }, [data?.source?.kind, id])   // eslint-disable-line react-hooks/exhaustive-deps

  const completeAnnual = () => act(async () => {
    if (annual?.due?.open) { setCompleting(annual.due.open); return }
    await api.post(`/drivers/${id}/annual-review/start`, {})
    const got = await api.get(`/drivers/${id}/annual-reviews`)
    setAnnual(got)
    if (got?.due?.open) setCompleting(got.due.open)
  })

  if (!data) {
    return <Modal title="Requirement" onClose={onClose}><Loading error={error} /></Modal>
  }
  const { requirement: r, source, records, credentialtype, orderable, signable, signed,
          licenses, coverage, derived } = data
  // Training is the one kind of credential that records who gave it.
  const trained = credentialtype?.category === 'training'
  // And some training is not finished when the class is - Florida asks for the skill to be
  // demonstrated, not merely attended.
  const tested = Boolean(credentialtype?.requirestesting)
  // Documents the driver sent in that nobody in the office has read. A requirement does not stand
  // on one of these, so the row says so and offers the one thing that changes it.
  const unchecked = new Set(data.awaitingreview || [])
  // Keyed by what was asked for rather than by the document, because a signature has no document
  // of its own - it is rebuilt from the record every time it is read.
  const unchecked2 = new Set(data.unreadasks || [])
  const canFile = ['credential', 'report', 'drugtest'].includes(source.kind)
  const active = records[0]
  // The newest document on file, for the footer's View. A requirement can hold several records -
  // a driver may hold two licences, and training can be redone - so "View" has to mean something
  // definite, and the most recent is what anybody opening the requirement is asking about.
  // `records` arrives newest first.
  const newest = records.find((x) => x.documentid)
  // Whether somebody in this office has already read what was sent and said it answers the rule.
  const verified = records.some((x) => x.source === 'filed' && x.determination === 'reviewed')
  // A reading is not a second document. Verifying what the driver sent files evidence pointing at
  // the very same file, and listing both puts one piece of paper on the screen twice - once as the
  // thing and once as the fact that somebody looked at it.
  const shown = source.kind === 'applicationanswer'
    ? records.filter((x) => x.source !== 'filed' || !records.some(
        (y) => y !== x && y.source !== 'filed' && y.documentid === x.documentid))
    : records

  // A report's answers come from the server, which is the only thing that knows what it will
  // accept. Keeping a second copy here is how the page came to offer an answer the server had
  // stopped taking.
  const served = Object.entries(reports?.outcomes || {})
  const results = served.length ? served : (RESULTS[source.kind] || [])
  // Where the answer IS the record there is no filing it without one, and no blank option either.
  const fillingOrder = source.kind === 'report'
    && (reports?.reports || []).some((x) => x.state === 'ordered')
  const needsResult = source.kind === 'report' && served.length > 0 && !fillingOrder
    && !Object.keys(reports?.outcomes || {}).some((k) => k === 'clear')

  // The link is shown as well as sent, so the office can read it out to somebody with no email.
  const asked = pending && (
    <div className="notice warn stack">
      <div>
        Asked {date(pending.senton || pending.createdon)}
        {pending.sentto ? ` - sent to ${pending.sentto}` : ' - this driver has no email address'}.
        Not answered yet.
      </div>
      <code className="linkline">{pending.link}</code>
    </div>
  )

  // Sending for something is recording that it was asked for, not fetching it - TripProof does not
  // pull an MVR or a PSP, the office does, at the source.
  const order = () => act(async () => {
    if (source.kind === 'report') {
      await api.post(`/drivers/${id}/reports/${source.which}/order`, {})
      await loadReports()
    } else await api.post(`/drivers/${id}/mvrs/order`, {})
  })

  const ask = () => act(async () => {
    await api.post(`/drivers/${id}/signing-requests`, { doctype: signable })
    await loadPending('signature', signable)
  })

  // Some requirements can only be answered by paper the driver holds and the company does not. The
  // asking is itself a fact: a requirement nobody has chased reads differently from one where the
  // driver was asked a fortnight ago and has not answered.
  const markRead = (documentid) => act(async () => {
    await api.post(`/drivers/${id}/sent-documents/${documentid}/reviewed`, {})
  })

  // A record read where it lives, rather than only where it arrived. The engine decides which
  // records still want reading; this records the act against the record itself, which is the one
  // place a reading is kept whatever kind of thing was read.
  // A drug screen on file with no result: the result is recorded against it, here.
  const recordResult = (credentialid, result) => act(async () => {
    await api.put(`/credentials/${credentialid}/result`, { result })
  })

  const readRecord = (rec) => act(async () => {
    await api.post(`/drivers/${id}/evidence/read`, {
      sourcetable: rec.sourcetable, sourceid: rec.recordid, code,
    })
  })

  // Reading a document already on file and saying it answers the rule. The paper is here - the
  // driver sent it with their questionnaire - so this records the reading rather than asking the
  // office to upload a second copy of what they are looking at.
  // A document the driver signed down a link, read by somebody here.
  const markSignedRead = () => act(async () => {
    await api.post(`/drivers/${id}/signed/${source.which}/reviewed`, {})
  })

  const verifyWith = (documentid) => act(async () => {
    await api.post(`/drivers/${id}/requirements/${code}/verified`, { documentid })
  })

  // What was asked for here, under both names it can go out as: a document to sign, or a document
  // to send in.
  const askedDoctype = signable || null
  const askedCode = source.kind === 'licensecopy' ? 'DRIVER_LICENSE'
    : source.kind === 'applicationanswered' ? 'PREEMP_DA_QUESTIONNAIRE'
      : source.kind === 'applicationanswer' ? 'RTD_DOCUMENTATION'
        : source.kind === 'credential' ? source.which : null
  const showHistory = () => act(async () => {
    const q = [askedDoctype && `doctype=${askedDoctype}`, askedCode && `code=${askedCode}`]
      .filter(Boolean).join('&')
    setAsks((await api.get(`/drivers/${id}/asks?${q}`)).asks || [])
  })

  const askForIt = (code = source.which) => act(async () => {
    await api.post(`/drivers/${id}/upload-requests`, { code })
    await loadPending('credential', code)
  })

  const openSigned = () => {
    setLoadingSigned(true)
    api.get(`/drivers/${id}/signed/${source.which}`).then(setSignedDoc).catch((e) => setErr(e.message))
  }

  // Front and back go up together and come back as one PDF - see app/images.py. Either side on
  // its own is accepted, because a license photographed once is better than one filed twice.
  const fileCopy = () => act(async () => {
    const body = new FormData()
    if (form.front) body.append('front', form.front)
    if (form.back) body.append('back', form.back)
    await api.post(`/drivers/${id}/licenses/${active.recordid}/copy`, body)
    setFiling(false)
    setForm({ ...form, front: null, back: null })
    onClose()
  })

  const reviewMvr = () => act(async () => {
    await api.post(`/drivers/${id}/mvrs/${form.mvrid}/reviewed`, {
      finding: form.result, note: form.note || null,
      // Left out where the reader said nothing, so reading a record for its convictions cannot
      // wipe what the State said about medical qualification.
      selfcert: form.selfcert || null, medcertstatus: form.medcertstatus || null,
      medcertexpires: form.medcertexpires || null,
      medvariancetype: form.medvariancetype || null, medvariance: form.medvariance || null,
    })
    setViewing(null)
  })

  // A request placed by mistake, asked of the wrong authority, or never going to be answered would
  // otherwise block the license for good - nothing else can be asked for or filed while one is out.
  const fileTransitMedical = () => act(async () => {
    const body = new FormData()
    Object.entries({
      examtype: exam.examtype, examinedon: exam.examinedon, result: exam.result,
      qualifiedthrough: exam.qualifiedthrough, examinername: exam.examinername,
      examinerlicense: exam.examinerlicense, examinerstate: exam.examinerstate,
      examinertype: exam.examinertype, otherrestriction: exam.otherrestriction,
      tempreason: exam.result === 'temporary' ? exam.tempreason : '',
      followupon: exam.followupon,
    }).forEach(([k, v]) => { if (v) body.append(k, v) })
    if (exam.correctivelenses) body.append('correctivelenses', 'true')
    if (exam.hearingaid) body.append('hearingaid', 'true')
    if (exam.file) body.append('file', exam.file)
    await api.post(`/drivers/${id}/transit-medicals`, body)
    setFiling(false)
    setExam(BLANK_EXAM(today))
  })

  const cancelMvr = (mvrid) => act(async () => {
    await api.post(`/drivers/${id}/mvrs/${mvrid}/cancel`, {})
  })

  const orderMvr = () => act(async () => {
    await api.post(`/drivers/${id}/mvrs/order`, { licenseid: form.licenseid })
    setFiling(false)
  })

  const uploadMvr = () => act(async () => {
    // Only a request outstanding on THIS license is the one being filled - and a request that was
    // withdrawn is not outstanding, whatever its dates look like. It keeps its place in the
    // history because somebody did ask a licensing authority a question, usually for money.
    const outstanding = records.find((x) => x.orderedon && !x.receivedon && !x.cancelledon
      && x.licenseid === form.licenseid) || null
    const body = new FormData()
    body.append('licenseid', form.licenseid)
    if (outstanding) body.append('mvrid', outstanding.recordid)
    body.append('issuedon', form.effectiveon)
    body.append('file', form.file)
    if (form.result) body.append('finding', form.result)
    if (form.note) body.append('note', form.note)
    // What a CDLIS record carries beyond the driving history. Only sent where it was asked for.
    for (const k of ['selfcert', 'medcertstatus', 'medcertexpires', 'medvariancetype',
      'medvariance']) {
      if (form[k]) body.append(k, form[k])
    }
    await api.post(`/drivers/${id}/mvrs`, body)
    setFiling(false)
  })

  const fileAgainst = () => act(async () => {
    const body = new FormData()
    body.append('effectiveon', form.effectiveon)
    if (form.note) body.append('note', form.note)
    body.append('file', form.file)
    await api.post(`/drivers/${id}/requirements/${code}/document`, body)
    setFiling(false)
    setForm({ ...form, file: null, note: '' })
    if (source.kind === 'signature') onClose()
  })

  const file = () => act(async () => {
    const body = new FormData()
    if (source.kind === 'credential') {
      body.append('credentialtypeid', credentialtype.recordid)
      body.append('subjectid', id)
      body.append('issuedon', form.effectiveon)
      if (form.expireson) body.append('expireson', form.expireson)
      if (form.issuer.trim()) body.append('issuer', form.issuer.trim())
      if (form.testedon) body.append('testedon', form.testedon)
      if (form.testedby.trim()) body.append('testedby', form.testedby.trim())
      if (credentialtype?.requiresprovenance) {
        if (!form.provenance) throw new Error('Choose where the screening came from')
        body.append('provenance', form.provenance)
      }
      if (source.which === 'DRUG_SCREEN') {
        if (!form.screentype || !form.screenresult) throw new Error('Choose the type and the result')
        body.append('screentype', form.screentype)
        body.append('result', form.screenresult)
      }
      if (form.file) body.append('file', form.file)
      await api.post('/credentials', body)
    } else if (source.kind === 'report') {
      body.append('issuedon', form.effectiveon)
      if (form.result) body.append('outcome', form.result)
      if (form.note) body.append('note', form.note)
      if (form.file) body.append('file', form.file)
      await api.post(`/drivers/${id}/reports/${source.which}`, body)
      await loadReports()
    } else if (source.kind === 'drugtest') {
      // Sent as a form rather than as JSON, because the result comes with a lab report and the
      // endpoint has always taken one - it was the posting that could not carry it.
      body.append('reason', form.reason || source.which)
      body.append('collectedon', form.effectiveon)
      body.append('result', form.result || 'negative')
      if (form.note) body.append('note', form.note)
      if (form.file) body.append('file', form.file)
      await api.post(`/drivers/${id}/testing/tests`, body)
      // The panel behind this dialog is read from its own endpoint, so filing a test has to go
      // and fetch it again - otherwise the requirement turns red and the panel still says there
      // is no violation on file, which is the same record disagreeing with itself.
      await loadTesting()
    }
    setFiling(false)
    setForm({ effectiveon: today, expireson: '', result: '', note: '', file: null })
  })

  // A requirement with nothing to file: the carrier makes a determination and the determination IS
  // the evidence. Answered here, where somebody is dealing with the requirement, rather than on a
  // field buried in the driver's information page that nobody would think to go and set.
  if (source.kind === 'driverfact') {
    return <DriverFactDialog {...{ act, busy, data, err, id, onChanged, onClose, r, reload }} />
  }

  // Nothing to file and nothing to upload. An endorsement is obtained from the licensing State,
  // so what this panel can usefully do is say which are missing and what getting them involves.
  if (source.kind === 'licensematch') {
    return <LicenseMatchDialog {...{ onClose, r, records }} />
  }

  // What the licensing State holds about this driver's medical qualification, read off the driving
  // record rather than off the certificate in the filing cabinet. There is nothing to file here -
  // the record it reads is filed on the driving record requirement - so this reads, compares, and
  // says where to go if the two disagree.
  if (source.kind === 'cdlismedical') {
    return <CdlisMedicalDialog {...{ data, onClose, r, records }} />
  }

  // Exclusion screening reads nothing like the other requirements, because most of the time there
  // is nothing to do and occasionally there is something urgent. The monthly job writes the clean
  // months on its own; what a person comes here for is either to record a check they ran on OIG's
  // own site, or to settle a possible match - which can only be done there, against the SSN.
  if (source.kind === 'exclusioncheck') {
    return <ExclusionDetail id={id} r={r} which={source.which} records={records} onClose={onClose}
      onChanged={() => { reload(); onChanged?.() }} />
  }

  // The §391.25 annual review: one determination about one driver, at least once every 12 months,
  // reached by reading every driving record received in the period. It is not opened by a record
  // arriving - it comes round on its own clock - so this offers to start it when it is owed and
  // shows what it will be performed against.
  // Ordered from Certn rather than fetched from a government site, so the office chooses how deep
  // to go and TripProof places the order. The depth is recorded with it: a Core search coming back
  // clear is not evidence that a Complete one would have.
  if (r.code === 'BACKGROUND_SCREENING') {
    return <BackgroundScreening id={id} item={r} onClose={onClose}
      onChanged={() => { onChanged?.(); }} />
  }

  // Read the way the PHI acknowledgement is: the latest completed review, one row, and View. The
  // review itself is run from the footer - started when one is owed, completed when one is open.
  if (source.kind === 'annualreview' && !filing) {
    return <AnnualReviewDialog {...{ annual, annualHistory, busy, completeAnnual, completing, err, id, loadAnnual, onChanged, onClose, onOpen, r, setAnnualHistory, setCompleting, setViewing, viewing }} />
  }

  // Every licensing authority this driver owes a record from, and where each one stands.
  //
  // 49 CFR 391.23(a)(1) asks for a record from each authority the driver held a license in over the
  // preceding three years, so the question is coverage by STATE - not whether some record exists.
  // Showing one record and a silence is how a file with Delaware missing reads as complete.
  // The qualification file as a whole: not a document but the rest of the file, so it reads as the
  // PHI acknowledgement does - one row, where it stands today - with what it is still waiting on
  // listed beneath, and the file itself to hand over from here.
  if (derived) {
    return <QualificationFileDialog {...{ act, busy, derived, err, id, onClose, r, today }} />
  }

  if (source.kind === 'mvr' && !filing) {
    return <MvrDialog {...{ busy, cancelMvr, coverage, data, err, form, mvrHistory, onClose, r, records, reviewMvr, setFiling, setForm, setMvrHistory, setViewing, viewing }} />
  }

  // Ordering asks for nothing at all: the license came with the row that was clicked, and TripProof
  // does not pull the record, the office does. So it is a question, not a form.
  if (filing === 'mvr-order') {
    return <MvrOrderDialog {...{ busy, err, form, orderMvr, setFiling }} />
  }

  if (filing === 'mvr-upload') {
    return <MvrUploadDialog {...{ busy, data, err, form, setFiling, setForm, uploadMvr }} />
  }

  // A signed document is one document. What the office wants is to read it - or, if it was signed
  // on paper and never went through the wizard, to put the paper copy up. Not a table with a link
  // in it. The same reasoning as the license copy below.
  // Everything this driver has been asked for on this requirement, answered or not. The question
  // somebody asks before chasing them a fourth time.
  if (asks) {
    return <RequestHistoryDialog {...{ asks, r, setAsks }} />
  }

  // 49 CFR 391.31 - one event with one output, so this dialog is about TESTS rather than about
  // documents. Three ways it can be answered, and the screen says which applies:
  //
  //   the test itself      sent to an examiner, who administers it and signs the certificate
  //   an equivalent        391.33: a valid CDL already held, which the engine reads for itself
  //   a paper copy         a certificate from before this company used TripProof
  if (source.kind === 'roadtest' && filing !== 'against') {
    return <RoadTestDialog {...{ active, busy, err, examiner, filing, onClose, r, reviewRoadTest, roadtests, sendRoadTest, setExaminer, setFiling, setViewing, viewing }} />
  }

  if (source.kind === 'signature' && filing !== 'against') {
    // Signed down a link and not yet read by anybody here. The same state, and the same two words,
    // as a document the driver uploaded or a report that came back from an order.
    const unread = unchecked2.has(source.which)
    if (signedDoc) {
      return (
        <>
          {/* No explanation on the document itself where the list dialog has already given it.
              Every other signed requirement opens straight into the document, so the brief is the
              only place its reason appears and it stays; the application is read from a list that
              says it first, and saying it twice makes the reader wonder what they missed. */}
          {/* Read as the PDF the server draws - the same file the audit packet carries and the
              driver is sent - and without the explanation, which the list dialog in front of it
              has already given. */}
          <SignedDocViewer doc={signedDoc} onClose={onClose}
            asPdf={`/drivers/${id}/signed/${source.which}/pdf`}
            brief={undefined}
            action={unread && (
              /* Reading it is the last thing anybody does here, so this closes rather than
                 dropping back into a view that would set about re-opening the same document.

                 Except on the I-9, where reading it is not the last thing: Section 2 underneath
                 is the employer's own statement under penalty of perjury, and it is unsigned
                 until somebody here signs it. Marking that form read and walking away leaves an
                 I-9 that is half a form. */
              source.which === 'I9'
                ? (
                  <button type="button" className="primary" disabled={busy}
                    onClick={() => setCertifying(true)}>
                    Certify Section 2
                  </button>
                ) : (
                  <button type="button" className="primary" disabled={busy}
                    onClick={async () => { await markSignedRead(); onClose() }}>
                    {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
                  </button>
                )
            )} />
          {certifying && (
            <CertifyI9 id={id} onClose={() => setCertifying(false)}
              /* Certifying produces a NEW document - the employee's page with Section 2 written
                 onto it - and the person who just signed it is the person who most wants to see
                 it. So the viewer stays open and reloads onto the certified copy, rather than
                 everything closing and leaving them to find their way back to the form they were
                 looking at a second ago. */
              onDone={() => { setCertifying(false); openSigned(); reload(); onChanged?.() }} />
          )}
        </>
      )
    }
    // The employment application is READ FROM A LIST rather than thrown straight at the reader.
    //
    // Every other signed document here is one thing signed once, so opening the requirement and
    // opening the document are the same act. An application is not: a driver can submit a new one
    // on being rehired, and an office looking at this requirement is usually asking WHICH one is
    // on file and whether anybody has read it - a question the document itself cannot answer
    // because it never says what else is beside it.
    //
    // Only when there IS something to list. With an empty file the question is not "which one is
    // on file" but "how do I get one on it", and the branch below already answers that - it
    // offers the upload and the request for the driver to sign it, both of which this dialog
    // would otherwise hide behind a line saying there is nothing here.
    // THE document on file, not a history of them.
    //
    // The requirement is answered by the latest one. An application re-signed on rehire replaces
    // the one before it; a PHI acknowledgement signed against a reissued policy replaces the
    // acknowledgement of the old policy. Listing every copy asks the reader to work out which one
    // counts, and they all look alike - two rows reading "Copy filed by the office" on the same
    // date tell somebody nothing except that they should probably worry. `records` arrives newest
    // first, so the first is the one that answers it.
    const onfile = shown
      .filter((x) => x.sourcetable === 'documentsignatures' || x.documentid)
      .slice(0, 1)
    if (!loadingSigned && onfile.length) {
      const x = onfile[0]
      return (
        <>
        <SingleDocumentDialog title={r.name} brief={r?.description} err={err}
          notice={COMPLETED_AGAIN.has(source.which) ? asked : null} unread={unread}
          // Signed here, or a copy somebody filed - the row says which, because they are not the
          // same evidence.
          row={{ on: x.effectiveon || x.recordedon,
                 document: x.sourcetable === 'documentsignatures' ? r.name : 'Copy filed by the office',
                 status: docStanding({ unread: x.needsreading || unread }) }}
          // Open whichever kind is actually on file: the latest, whether a copy filed after an
          // earlier signing or the signing itself.
          onView={() => (x.sourcetable !== 'documentsignatures' && x.documentid
            ? setViewing({ documentid: x.documentid, filename: r.name })
            : signed ? openSigned() : setLoadingSigned(true))}
          // A form completed again - a new W-4 when withholding changes. The I-9 is done once.
          actions={COMPLETED_AGAIN.has(source.which) && <>
            <button type="button" onClick={() => setFiling('against')}>
              <FileUp size={13} /> Upload Document
            </button>
            {signable && (
              <button type="button" disabled={busy} onClick={ask}>
                <FileSignature size={13} /> Ask the driver to sign
              </button>
            )}
          </>}
          onClose={onClose} />
        {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
          onClose={() => setViewing(null)} />}
        </>
      )
    }
    if (signed) {
      if (!loadingSigned) openSigned()
      return <Modal title={r.name} onClose={onClose}><Loading error={err} /></Modal>
    }
    // A copy somebody filed, rather than a signing. Reached the same way and so it drops the
    // explanation the same way: the list dialog in front of it has already given it, and this is
    // the third door into this viewer that had to be told so.
    if (active?.documentid) {
      return (
        <DocumentViewer id={active.documentid} name={r.name} onClose={onClose}
          brief={undefined}
          action={
            <button type="button" onClick={() => setFiling('against')}>
              <Plus size={13} /> Upload a new copy
            </button>
          } />
      )
    }
    // Nothing signed and nothing filed: the empty file, and the two ways to put one on it. The
    // paper copy is filed in a dialog of its own.
    return (
      <SingleDocumentDialog title={r.name} brief={r?.description} err={err} notice={asked}
        emptyActions={<>
          <button type="button" onClick={() => setFiling('against')}>
            <FileUp size={13} /> Upload Document
          </button>
          {signable && (
            <button type="button" disabled={busy} onClick={ask}>
              <FileSignature size={13} /> Ask the driver to sign
            </button>
          )}
        </>}
        onClose={onClose} />
    )
  }

  // The questionnaire is one document too, and is worked exactly as a signed one is: read it if it
  // is here, and if it is not, ask the driver for it or put up the paper copy. A table listing one
  // row that opens one document was a table for the sake of having a table.
  if (source.kind === 'applicationanswered' && filing !== 'against') {
    return <QuestionnaireDialog {...{ askForIt, asked, busy, err, markRead, onClose, r, readRecord, records, setFiling, setViewing, unchecked, viewing }} />
  }

  // The license requirement opens the licenses themselves - the same table the driver page shows,
  // because a license, its dates and its copy are one thing and are worked in one place. Nothing is
  // duplicated here; it is the same component.
  // 49 CFR 382.305. The driver's half of it: are they in the pool, and since when.
  //
  // The date lives on the driver record and could already be typed into the middle of Driver
  // Information - but the requirement that depends on it was a separate screen that could not
  // touch it, so the mark said "nothing on file" and offered nothing to do about it. The same
  // shape as the license: one record, two ways in, one component behind both.
  if (source.kind === 'poolmember') {
    return <RandomPoolDialog {...{ act, busy, err, id, onClose, r, records, today }} />
  }

  // Driving experience is read off the licenses' dates, so it is answered where they are entered.
  if (source.kind === 'licensecopy' || source.kind === 'license' || source.kind === 'drivingexperience') {
    return <LicensesHeldDialog {...{ askForIt, asked, busy, err, filing, id, markRead, onChanged, onClose, r, readRecord, setFiling, setViewing, unchecked, viewing }} />
  }


  // FDOT 725-030-11 under F.A.C. 14-90.0041. The form ends in a determination the examiner makes,
  // and that determination is the compliance question - so it is recorded as an examination with a
  // result, not as a file somebody attached. What is NOT here is the health history and the
  // examination findings the form also carries: the examiner keeps the complete examination, the
  // transit system keeps the certificate, and an employer has no reason to hold a driver's medical
  // history.
  if (source.kind === 'transitmedical') {
    return <TransitMedicalDialog {...{ busy, crash, crashes, err, exam, fileTransitMedical, filing, id, loadAccidents, onChanged, onClose, r, records, reload, setCrash, setExam, setFiling, setViewing, source, today, viewing }} />
  }

  // Previous employer safety performance history - 49 CFR 391.23(d), (e) and (i).
  //
  // What is on screen is not "is the answer here". It is one row per previous employer and, under
  // each, every attempt made to reach them: 391.23(i) satisfies the requirement with a documented
  // good faith effort, so the asking IS the evidence where the answer never comes.
  if (source.kind === 'employerhistory') {
    return <EmployerHistoryDialog {...{ att, busy, closeEffort, code, confirmed, err, filing, gfe, gfesig, inq, me, onClose, r, reviewReply, sendRequest, setAtt, setFiling, setGfe, setGfesig, setInq, setSphiHistory, setViewing, signed, sphi, sphiHistory, today, uploadReply, viewing }} />
  }

  // Drug and alcohol testing, and the bar a positive produces.
  //
  // The return-to-duty process is not one process. Only a driver under 49 CFR Part 382 goes through
  // a DOT-qualified substance abuse professional, and only there does the SAP's determination gate
  // the return-to-duty test (40.305). Under a CTD, broker or company program there is an
  // evaluation and a return to duty, but there is no DOT SAP in it - so this screen never calls one
  // by the other's name. What it says is what the program actually requires.
  if (source.kind === 'drugtest') {
    return <DrugTestingDialog {...{ busy, err, file, filing, form, id, loadTesting, needsResult, onChanged, onClose, r, reload, results, setCrash, setFiling, setForm, setTestHistory, setViewing, source, testHistory, testing, viewing }} />
  }

  // Adding a record is its own dialog, the way ordering an MVR and adding a license are. A form
  // living inside the list means the list and the thing being added are on screen at once, each
  // pretending the other is not there.
  // Ordering asks for nothing: the requirement already says what is being sent for, and TripProof
  // does not pull it - the office does. So it is a question, laid out as the driving record's
  // question is, because they are the same question about different things.
  if (filing === 'order') {
    return <OrderReportDialog {...{ busy, err, order, r, setFiling }} />
  }

  if (filing === 'against') {
    return <FileAgainstDialog {...{ busy, err, fileAgainst, form, r, setFiling, setForm, source }} />
  }

  if (filing === true) {
    return <AddRecordDialog {...{ busy, credentialtype, err, file, fillingOrder, form, needsResult, r, results, setFiling, setForm, source, tested, trained }} />
  }

  // DCH 914.2.5: two at-fault moving violations and/or accidents on NEMT work remove a driver from
  // service. Nothing is filed against it - the two lists are what it counts.
  // DCH 907.16: a confirmed failure to secure a wheelchair removes the driver until retrained.
  if (source.kind === 'securementclear') {
    return <SecurementRecord id={id} r={r} onClose={onClose}
      onChanged={() => { reload(); onChanged?.() }} />
  }

  if (source.kind === 'atfaultcount') {
    return <AtFaultRecord id={id} r={r} onClose={onClose}
      onChanged={() => { reload(); onChanged?.() }} />
  }

  // The company's own drug screen, laid out as the regulated drug test is: the last screen only,
  // View / Add / History / Close in the footer, and every screen in the History.
  if (source.kind === 'credential' && source.which === 'DRUG_SCREEN' && !filing) {
    return <DrugScreenDialog {...{ asked, busy, err, markRead, onClose, r, readRecord, recordResult, results, setFiling, setTestHistory, setViewing, shown, testHistory, unchecked, viewing }} />
  }

  // Read from a list, the same as the PHI acknowledgement: the latest record only, Reviewed or Not
  // Reviewed, and View / Close. An empty file falls through to the dialog below, which offers the
  // upload and the request to the driver.
  const latest = source.kind === 'credential'
    && shown.find((x) => x.documentid)
  if (latest && !filing) {
    return <LatestDocumentDialog {...{ act, askForIt, asked, busy, credHistory, credentialtype, err, latest, markRead, onClose, r, readRecord, setCredHistory, setFiling, setViewing, shown, today, unchecked, viewing }} />
  }

  return <GeneralRequirementDialog {...{ ask, askForIt, asked, busy, canFile, cancelReport, data, err, latest, markRead, newest, onClose, order, orderable, r, readRecord, records, reports, results, reviewReport, setFiling, setViewing, shown, signable, source, tested, today, trained, unchecked, verified, verifyWith, viewing }} />
}
