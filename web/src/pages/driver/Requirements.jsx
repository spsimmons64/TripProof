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

// The three ways of looking at one driver, in the order an office works through them.
// Every driver can operate an ordinary vehicle, so that is not something to declare - these are
// what they are cleared for beyond it. Ticked cumulatively, because the thresholds are nested: a
// CDL vehicle is always a commercial motor vehicle, and 26,001 lb always needs a CDL. Ticking one
// ticks what it implies and unticking one clears what depends on it, so the set is always a set
// that can exist. The record keeps the highest level reached, not three separate flags.

// The standings that are a requirement not met, as against one still on its way.
const FAILED = ['failed', 'expired', 'overdue']

// Where an employer inquiry stands, in a word for the head of its panel.
const SPHI_STANDING = { notasked: 'Not Asked', waiting: 'Waiting', toreview: 'Not Reviewed',
  answered: 'Answered', effort: 'Good Faith Effort' }

const SPHI_CHANNELS = { email: 'Email', fax: 'Fax', mail: 'Mail', phone: 'Telephone',
  inperson: 'In person' }

// Where a request goes, by channel - and what the employer record already holds for it. The
// office picks the channel; the address is offered, not imposed, because the one on an application
// is the one the driver remembered.
const SEND_TO = {
  email: (x) => x.email || '',
  fax: (x) => x.fax || '',
  mail: (x) => [x.address1, x.city, x.state, x.zip].filter(Boolean).join(', '),
  phone: (x) => x.phone || '',
  inperson: (x) => x.contactname || '',
}

const BLANK_INCIDENT = { occurredon: '', confirmed: false, note: '' }

// Wheelchair securement failures on this driver. Only a confirmed one removes them, and securement
// training dated after it brings them back.
function SecurementRecord({ id, r, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/securement-incidents`), [id])
  const [adding, setAdding] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); await reload(); onChanged?.(); return true }
    catch (e) { setErr(e.message); return false } finally { setBusy(false) }
  }
  const save = () => act(async () => {
    if (!adding.occurredon) throw new Error('Say when it happened')
    await api.post(`/drivers/${id}/securement-incidents`, { ...adding, note: adding.note || null })
    setAdding(null)
  })
  return (
    <>
      <Modal title={r.name} onClose={onClose} brief={r?.description} width={DETAIL}
        footer={<>
          <button type="button" onClick={() => { setErr(null); setAdding({ ...BLANK_INCIDENT }) }}>
            <Plus size={13} /> Record A Failure
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {(err || error) && <div className="notice bad">{err || error}</div>}
          {!data ? <Loading /> : (
            <table className="residencetable recordtable">
              <thead><tr><th>Date</th><th>Note</th><th>Confirmed</th><th /></tr></thead>
              <tbody>
                {data.incidents.map((x) => (
                  <tr key={x.recordid}>
                    <td>{date(x.occurredon)}</td>
                    <td>{x.note || '-'}</td>
                    <td className={x.confirmed ? 'st-expired' : 'st-ordered'}>{x.confirmed ? 'Yes' : 'No'}</td>
                    <td className="actions">
                      {!x.confirmed && (
                        <button type="button" className="linkbtn edit" disabled={busy}
                          onClick={() => act(() => api.post(`/drivers/${id}/securement-incidents/${x.recordid}/confirm`, {}))}>
                          Confirm
                        </button>
                      )}
                      <button type="button" className="linkbtn" disabled={busy}
                        onClick={() => act(() => api.post(`/drivers/${id}/securement-incidents/${x.recordid}/withdraw`, {}))}>
                        Withdraw
                      </button>
                    </td>
                  </tr>
                ))}
                {!data.incidents.length && <tr><td colSpan={4}>No securement failures recorded.</td></tr>}
              </tbody>
            </table>
          )}
        </div>
      </Modal>
      {adding && (
        <Modal title="Record A Securement Failure" onClose={() => setAdding(null)} width={620}
          footer={<>
            <button type="button" className="primary" disabled={busy} onClick={save}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setAdding(null)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-3">Date *
                <input type="date" value={adding.occurredon}
                  onChange={(e) => setAdding({ ...adding, occurredon: e.target.value })} />
              </label>
              <label className="field span-3">Confirmed
                <select value={adding.confirmed ? 'yes' : 'no'}
                  onChange={(e) => setAdding({ ...adding, confirmed: e.target.value === 'yes' })}>
                  <option value="no">Not yet</option>
                  <option value="yes">Yes</option>
                </select>
              </label>
              <label className="field span-6">Note
                <textarea value={adding.note} onChange={(e) => setAdding({ ...adding, note: e.target.value })} />
              </label>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}

const BLANK_VIOLATION = { occurredon: '', violation: '', convictedon: '', atfault: '', onnemt: true, note: '' }

// What DCH 914.2.5 counts: moving violations a driver was convicted of and at fault for on NEMT
// work, and accidents in the register where they were at fault. Two removes them from service.
function AtFaultRecord({ id, r, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/moving-violations`), [id])
  const [adding, setAdding] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); await reload(); onChanged?.(); return true }
    catch (e) { setErr(e.message); return false } finally { setBusy(false) }
  }
  const yesno = (v) => (v === null || v === undefined ? 'Not said' : v ? 'Yes' : 'No')
  const counts = (v) => v.atfault && v.onnemt && v.convictedon
  const save = () => act(async () => {
    if (!adding.occurredon || !adding.violation.trim()) throw new Error('Say when, and what the violation was')
    await api.post(`/drivers/${id}/moving-violations`, { ...adding,
      convictedon: adding.convictedon || null,
      atfault: adding.atfault === '' ? null : adding.atfault === 'yes', note: adding.note || null })
    setAdding(null)
  })
  return (
    <>
      <Modal title={r.name} onClose={onClose} brief={r?.description} width={DETAIL}
        footer={<>
          <button type="button" onClick={() => { setErr(null); setAdding({ ...BLANK_VIOLATION }) }}>
            <Plus size={13} /> Add Moving Violation
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {(err || error) && <div className="notice bad">{err || error}</div>}
          {!data ? <Loading /> : (
            <>
              <h3 className="formsection">Moving Violations</h3>
              <table className="residencetable recordtable">
                <thead><tr><th>Date</th><th>Violation</th><th>Convicted</th><th>At Fault</th>
                  <th>Counts</th><th /></tr></thead>
                <tbody>
                  {data.violations.map((v) => (
                    <tr key={v.recordid}>
                      <td>{date(v.occurredon)}</td>
                      <td>{v.violation}</td>
                      <td>{v.convictedon ? date(v.convictedon) : 'No'}</td>
                      <td>{yesno(v.atfault)}</td>
                      <td className={counts(v) ? 'st-expired' : undefined}>{counts(v) ? 'Yes' : 'No'}</td>
                      <td className="actions">
                        <button type="button" className="linkbtn" disabled={busy}
                          onClick={() => act(() => api.post(`/drivers/${id}/moving-violations/${v.recordid}/withdraw`, {}))}>
                          Withdraw
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!data.violations.length && <tr><td colSpan={6}>No moving violations recorded.</td></tr>}
                </tbody>
              </table>
              <h3 className="formsection">Accidents</h3>
              <table className="residencetable recordtable">
                <thead><tr><th>Date</th><th>Where</th><th>At Fault</th><th>Counts</th></tr></thead>
                <tbody>
                  {data.accidents.map((a) => (
                    <tr key={a.recordid}>
                      <td>{date(a.occurredon)}</td>
                      <td>{a.location || '-'}</td>
                      <td>{yesno(a.atfault)}</td>
                      <td className={a.atfault ? 'st-expired' : undefined}>{a.atfault ? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
                  {!data.accidents.length && <tr><td colSpan={4}>No accidents recorded.</td></tr>}
                </tbody>
              </table>
            </>
          )}
        </div>
      </Modal>
      {adding && (
        <Modal title="Add Moving Violation" onClose={() => setAdding(null)} width={720}
          footer={<>
            <button type="button" className="primary" disabled={busy} onClick={save}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setAdding(null)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-2">Date *
                <input type="date" value={adding.occurredon}
                  onChange={(e) => setAdding({ ...adding, occurredon: e.target.value })} />
              </label>
              <label className="field span-4">Violation *
                <input value={adding.violation}
                  onChange={(e) => setAdding({ ...adding, violation: e.target.value })} />
              </label>
              <label className="field span-2">Convicted On
                <input type="date" value={adding.convictedon}
                  onChange={(e) => setAdding({ ...adding, convictedon: e.target.value })} />
              </label>
              <label className="field span-2">At Fault
                <select value={adding.atfault} onChange={(e) => setAdding({ ...adding, atfault: e.target.value })}>
                  <option value="">Nobody has said</option>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </label>
              <label className="field span-2">On NEMT Work
                <select value={adding.onnemt ? 'yes' : 'no'}
                  onChange={(e) => setAdding({ ...adding, onnemt: e.target.value === 'yes' })}>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </label>
              <label className="field span-6">Note
                <textarea value={adding.note} onChange={(e) => setAdding({ ...adding, note: e.target.value })} />
              </label>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}

// Every requirement backed by one document - a signed form, a certificate - opens in the one layout
// (components/RequirementDialogs.jsx): the latest on file, its standing, and View. Which extras it
// carries is read off the rule rather than kept in a list here - a rule that recurs gets the expiry,
// the next upload and its history - so a requirement added tomorrow opens the way the others do.
// A form completed again from the same dialog - a new W-4 when withholding changes. The I-9 is
// completed once.
const COMPLETED_AGAIN = new Set(['W4'])

// Where a screening came from. Only the first two are the authority itself.
const PROVENANCE = { fdle: 'FDLE', ahca: 'AHCA Clearinghouse', vendor: 'Screening vendor' }

// The company's own drug screen: the panel run, and what came back.
const SCREEN_TYPES = ['5-Panel', '10-Panel', '12-Panel', 'Other']

const SCREEN_RESULTS = { negative: 'Negative', negativedilute: 'Negative-Dilute', positive: 'Positive',
  refusal: 'Refusal', cancelled: 'Cancelled' }

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

// The medical certification block on a CDLIS driving record. Asked in two places - when the office
// files a record it fetched, and when it reads one that came back against an order - because those
// are two different moments and a record only ever goes through one of them. Written once, so the
// two cannot drift into asking different questions.
function CdlisFields({ data, form, setForm }) {
  return (
    <section className="cdlisblock">
      {/* Its own section with its own heading, because it IS its own section: everything else on
          these forms is about the driving history, and this is the State's answer to a different
          question that happens to arrive on the same sheet of paper. The heading carries the
          context, so the labels under it do not repeat "on the record" four times. */}
      <h3 className="formsection">Medical Certification On The Record</h3>
      <div className="profileform">
        <label className="field span-3">Self-Certification
          <select value={form.selfcert || ''}
            onChange={(e) => setForm({ ...form, selfcert: e.target.value })}>
            <option value="">Choose</option>
            {Object.entries(data?.selfcerts || {}).map(([v, l]) =>
              <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="field span-3">Medical Status
          <select value={form.medcertstatus || ''}
            onChange={(e) => setForm({ ...form, medcertstatus: e.target.value })}>
            <option value="">Choose</option>
            {Object.entries(data?.medcertstatuses || {}).map(([v, l]) =>
              <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="field span-3">Expires
          <input type="date" value={form.medcertexpires || ''} min="1900-01-01" max="2100-12-31"
            onChange={(e) => setForm({ ...form, medcertexpires: e.target.value })} />
        </label>
        <label className="field span-3">Variance
          <select value={form.medvariancetype || ''}
            onChange={(e) => setForm({ ...form, medvariancetype: e.target.value })}>
            <option value="">None</option>
            {Object.entries(data?.medvariances || {}).map(([v, l]) =>
              <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        {/* Only once there is one to describe. The reference and the limitation are the part of a
            variance that cannot be chosen from a list - an SPE certificate is limited to the kind
            of vehicle the driver was evaluated in, and that limit is the whole of what it says. */}
        {form.medvariancetype && (
          <label className="field span-6">Variance Reference And Any Limitation On It
            <input value={form.medvariance || ''}
              placeholder={form.medvariancetype === 'spe'
                ? 'SPE-2026-00123, straight truck only'
                : 'Exemption reference, expires 03/2028'}
              onChange={(e) => setForm({ ...form, medvariance: e.target.value })} />
          </label>
        )}
      </div>
    </section>
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

// What kind of query it is, in the Clearinghouse's own two words. A full query is run before
// hiring and needs the driver's electronic consent; a limited query is the annual one.
const QUERY_KIND = { CLEARINGHOUSE_PREEMP: 'Full', CLEARINGHOUSE: 'Limited' }

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
    const said = data?.answer === null || data?.answer === undefined
      ? '' : String(data.answer ? 1 : 0)
    const answer = (value) => act(async () => {
      await api.post(`/drivers/${id}/requirements/${r.code}/fact`,
        { answer: value === '' ? null : value === '1' })
      reload(); onChanged?.()
    })
    return (
      <Modal title={r.name} onClose={onClose} brief={r?.description} width={DETAIL}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {/* Read, not asked. Where TripProof worked the answer out, it shows what it worked it
              out from rather than offering somebody a Yes and a No to overrule arithmetic with. */}
          {data?.reading ? (
            <div className="kv">
              <dt>{data.reading.what}</dt>
              <dd>{data.reading.value
                ? `${date(data.reading.value)} · ${data.reading.age} years old`
                : `Not on file - set it on ${data.reading.where}`}</dd>
            </div>
          ) : (
            <p className="factask">{data?.question}</p>
          )}
          {!data?.reading && (
          <div className="formactions">
            <button type="button" className={said === '1' ? 'primary' : undefined} disabled={busy}
              onClick={() => answer('1')}>Yes</button>
            <button type="button" className={said === '0' ? 'danger on' : undefined} disabled={busy}
              onClick={() => answer('0')}>No</button>
            {/* Withdrawing a determination has to be possible, or one made by mistake stands for
                ever. */}
            {said !== '' && (
              <button type="button" className="right" disabled={busy} onClick={() => answer('')}>
                Not assessed
              </button>
            )}
          </div>
          )}
          {said === '0' && !data?.reading && (
            <div className="notice bad">
              The driver is not qualified while this stands - 49 CFR 391.11(b)(2).
            </div>
          )}
          {/* What the reading means. The detail payload carries the rule, not the verdict, so
              this says it from the same two numbers the engine used. */}
          {data?.reading && (data.reading.value ? (
            data.reading.age >= 21
              ? <div className="notice">This driver meets the minimum age for interstate operation.</div>
              : <div className="notice bad">
                  This driver is under 21. 49 CFR 391.11(b)(1) does not permit them to operate a
                  commercial motor vehicle in interstate commerce, and nothing can be filed that
                  changes it.
                </div>
          ) : (
            <div className="notice warn">
              The driver&rsquo;s date of birth is not on file, so their age cannot be established.
            </div>
          ))}
        </div>
      </Modal>
    )
  }

  // Nothing to file and nothing to upload. An endorsement is obtained from the licensing State,
  // so what this panel can usefully do is say which are missing and what getting them involves.
  if (source.kind === 'licensematch') {
    const rec = records[0]
    const missing = rec?.missing || []
    return (
      <Modal title="Endorsements For The Vehicle This Driver Will Operate" onClose={onClose} brief={r?.description}
        width={720}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <div className="stack">
          <div className="kv">
            <dt>Required for this work</dt>
            <dd>{(rec?.needed || []).map((c) => `${c} (${ENDORSEMENT_NAMES[c] || c})`).join(', ')
                 || 'None stated'}</dd>
            <dt>Carried by the license</dt>
            <dd>{(rec?.held || []).map((c) => `${c} (${ENDORSEMENT_NAMES[c] || c})`).join(', ')
                 || 'None'}</dd>
          </div>
          {missing.length > 0 ? (
            <>
              <div className="notice bad">
                This driver does not hold the{' '}
                {missing.map((c) => `${c} (${ENDORSEMENT_NAMES[c] || c})`).join(', ')}{' '}
                endorsement{missing.length === 1 ? '' : 's'}, so they are not qualified for the
                vehicle they are being taken on to operate.
              </div>
              {/* Entry-level driver training lives here rather than as a requirement of its own:
                  the carrier does not hold the certificate, the State checks the Registry before
                  it will test. So it is part of obtaining the endorsement, said beside it. */}
              {missing.some((c) => 'PSH'.includes(c)) && (
                <div className="notice">
                  A first P, S or H endorsement cannot be taken until entry-level driver training is
                  completed with a provider on FMCSA&rsquo;s Training Provider Registry, who reports
                  it to FMCSA - 49 CFR Part 380 Subpart F. The State checks that before it will
                  administer the test. Nothing is filed here; the requirement clears when the
                  license on file carries the endorsement.
                </div>
              )}
              <div className="row">
                <a className="btn" href="https://tpr.fmcsa.dot.gov/" target="_blank"
                  rel="noreferrer">
                  <ExternalLink size={13} /> Training Provider Registry
                </a>
              </div>
            </>
          ) : (
            <div className="muted">
              The license on file carries every endorsement this work requires.
            </div>
          )}
        </div>
      </Modal>
    )
  }

  // What the licensing State holds about this driver's medical qualification, read off the driving
  // record rather than off the certificate in the filing cabinet. There is nothing to file here -
  // the record it reads is filed on the driving record requirement - so this reads, compares, and
  // says where to go if the two disagree.
  if (source.kind === 'cdlismedical') {
    const rec = records[0]
    const card = data?.card
    return (
      <Modal title="CDLIS Medical Certification Status" onClose={onClose} brief={r?.description} width={DETAIL}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <div className="stack">
          {!rec ? (
            <div className="muted">
              No driving record on file carries medical certification information for this driver.
              Obtain the CDLIS record from the licensing State and file it against the driving
              record requirement.
            </div>
          ) : (
            <>
              <div className="kv">
                <dt>Self-certification</dt>
                <dd>{data?.selfcerts?.[rec.selfcert] || 'Not stated on the record'}</dd>
                <dt>Medical status</dt>
                <dd className={rec.medcertstatus === 'notcertified' ? 'st-expired' : 'st-active'}>
                  {data?.medcertstatuses?.[rec.medcertstatus] || 'Not stated on the record'}
                </dd>
                <dt>Medical expiry on the record</dt>
                <dd>{rec.medcertexpires ? date(rec.medcertexpires) : '-'}</dd>
                <dt>Medical variance</dt>
                <dd>{rec.medvariancetype
                  ? `${data?.medvariances?.[rec.medvariancetype] || rec.medvariancetype}`
                    + (rec.medvariance ? ` - ${rec.medvariance}` : '')
                  : 'None'}</dd>
                <dt>Read from the record dated</dt>
                <dd>{rec.effectiveon ? date(rec.effectiveon) : '-'}</dd>
              </div>
              {/* The comparison is the point of the whole requirement, so it is stated rather than
                  left for somebody to make by looking from one line to another. */}
              {rec.determination === 'conflict' && (
                <div className="notice bad">
                  The medical certificate on file expires {card ? date(card) : 'on another date'} and
                  the State&rsquo;s record says {date(rec.medcertexpires)}. Under 49 CFR 383.71 the
                  electronically supplied medical information governs. Settle it with the licensing
                  State before this driver operates a commercial motor vehicle.
                </div>
              )}
              {rec.determination === 'notcertified' && (
                <div className="notice bad">
                  The State shows this driver as not certified. The certificate in this file does
                  not override it, and the driver may not operate a commercial motor vehicle.
                </div>
              )}
              {rec.determination === 'excepted' && (
                <div className="notice">
                  Self-certified as excepted or intrastate, so the State does not carry medical
                  status for this driver. The certificate on file is what governs.
                </div>
              )}
            </>
          )}
        </div>
      </Modal>
    )
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

  // Every licensing authority this driver owes a record from, and where each one stands.
  //
  // 49 CFR 391.23(a)(1) asks for a record from each authority the driver held a license in over the
  // preceding three years, so the question is coverage by STATE - not whether some record exists.
  // Showing one record and a silence is how a file with Delaware missing reads as complete.
  // The qualification file as a whole: not a document but the rest of the file, so it reads as the
  // PHI acknowledgement does - one row, where it stands today - with what it is still waiting on
  // listed beneath, and the file itself to hand over from here.
  if (derived) {
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

  if (source.kind === 'mvr' && !filing) {
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
                      {x.cancelledon ? 'Cancelled' : x.receivedon
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

  // Ordering asks for nothing at all: the license came with the row that was clicked, and TripProof
  // does not pull the record, the office does. So it is a question, not a form.
  if (filing === 'mvr-order') {
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

  if (filing === 'mvr-upload') {
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

  // A signed document is one document. What the office wants is to read it - or, if it was signed
  // on paper and never went through the wizard, to put the paper copy up. Not a table with a link
  // in it. The same reasoning as the license copy below.
  // Everything this driver has been asked for on this requirement, answered or not. The question
  // somebody asks before chasing them a fourth time.
  if (asks) {
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

  // 49 CFR 391.31 - one event with one output, so this dialog is about TESTS rather than about
  // documents. Three ways it can be answered, and the screen says which applies:
  //
  //   the test itself      sent to an examiner, who administers it and signs the certificate
  //   an equivalent        391.33: a valid CDL already held, which the engine reads for itself
  //   a paper copy         a certificate from before this company used TripProof
  if (source.kind === 'roadtest' && filing !== 'against') {
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
    const since = records?.[0]?.effectiveon || null
    return (
      <Modal title="Random Testing Pool" onClose={onClose} brief={r?.description} width={720}
        footer={<>
          <button type="button" disabled={busy}
            onClick={() => act(async () => {
              await api.put(`/drivers/${id}/random-pool`, { on: since ? null : today })
            })}>
            {busy ? <Loader2 size={15} className="spin" />
              : since ? <><X size={13} /> Take Out Of The Pool</>
                : <><Plus size={13} /> Put In The Pool</>}
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <dl className="askfacts">
            <div><dt>In the pool</dt><dd>{since ? `Since ${date(since)}` : 'No'}</dd></div>
            {r?.authority && <div><dt>Authority</dt><dd>{r.authority}</dd></div>}
            {r?.citation && <div><dt>Citation</dt><dd>{r.citation}</dd></div>}
          </dl>
          {/* Being in a pool is only half the answer: 382.305 is a rate met across a year, and a
              pool nobody draws from tests nobody. The draws are the company's record rather than
              this driver's, so this says where they are kept instead of showing them here. */}
          <div className="notice">
            The selections drawn from this pool are kept on the company's record - Company,
            Company Requirements, Random testing selections.
          </div>
        </div>
      </Modal>
    )
  }

  // Driving experience is read off the licenses' dates, so it is answered where they are entered.
  if (source.kind === 'licensecopy' || source.kind === 'license' || source.kind === 'drivingexperience') {
    return (
      <>
      <Modal title="Licenses Held" onClose={onClose} brief={r?.description} width={DETAIL}
        footer={<>
          <button type="button" onClick={() => setFiling('add-license')}>
            <Plus size={13} /> Add a license
          </button>
          <button type="button" disabled={busy} onClick={() => askForIt('DRIVER_LICENSE')}>
            <Send size={13} /> Ask the driver for it
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          {asked}
          <DriverLicenses id={id} bare onChanged={onChanged}
            pending={unchecked} onReviewed={markRead}
            adding={filing === 'add-license'}
            onAdding={(open) => setFiling(open ? 'add-license' : false)} />
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


  // FDOT 725-030-11 under F.A.C. 14-90.0041. The form ends in a determination the examiner makes,
  // and that determination is the compliance question - so it is recorded as an examination with a
  // result, not as a file somebody attached. What is NOT here is the health history and the
  // examination findings the form also carries: the examiner keeps the complete examination, the
  // transit system keeps the certificate, and an employer has no reason to hold a driver's medical
  // history.
  if (source.kind === 'transitmedical') {
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

  // Previous employer safety performance history - 49 CFR 391.23(d), (e) and (i).
  //
  // What is on screen is not "is the answer here". It is one row per previous employer and, under
  // each, every attempt made to reach them: 391.23(i) satisfies the requirement with a documented
  // good faith effort, so the asking IS the evidence where the answer never comes.
  if (source.kind === 'employerhistory') {
    if (filing === 'upload' && inq) {
      return (
        <Modal title="Upload The Reply" onClose={() => setFiling('send')} width={680}
          footer={<>
            <button type="button" className="primary" disabled={busy || !att.file}
              onClick={uploadReply}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setFiling('send')}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="muted small">{inq.employer}</div>
            <div className="profileform">
              <label className="field span-3">Who Answered
                <input value={att.sentto} className="upper"
                  onChange={(e) => setAtt({ ...att, sentto: e.target.value.toUpperCase() })} /></label>
              <label className="field span-6">The Reply *
                <input type="file"
                  onChange={(e) => setAtt({ ...att, file: e.target.files[0] || null })} /></label>
              <label className="field span-6">Note
                <textarea value={att.note}
                  onChange={(e) => setAtt({ ...att, note: e.target.value })} /></label>
            </div>
          </div>
        </Modal>
      )
    }

    if (filing === 'sent' && confirmed) {
      const emailed = confirmed.channel === 'email'
      return (
        <Modal title={emailed ? 'Request Sent' : 'Attempt Recorded'} width={520}
          onClose={() => setFiling('send')}
          footer={<button type="button" className="primary"
            onClick={() => setFiling('send')}>Done</button>}>
          <div className="askorder">
            <span className="askmark"><Check size={28} strokeWidth={3} /></span>
            <p>
              {emailed
                ? <>The request went to <b>{confirmed.to}</b> for {confirmed.employer}.</>
                : <>Recorded against {confirmed.employer}: {(sphi?.channels?.[confirmed.channel]
                    || confirmed.channel).toLowerCase()}{confirmed.to ? <> to <b>{confirmed.to}</b></> : null}.</>}
            </p>
          </div>
        </Modal>
      )
    }

    // Every attempt made on this employer. It is the record 391.23(i) asks to see, so it is kept
    // whole rather than summarised into the one line the table shows.
    // What came back, and what this office makes of it. A reply arrives from outside: it may say
    // the driver was dismissed, or that there are accidents on their record, and none of that has
    // been seen by anybody here until somebody reads it. So the requirement waits on the reading,
    // not on the answer - SPHI section 9.
    if (filing === 'reply' && inq) {
      return (
        <>
        <Modal title={inq.employer} onClose={() => setFiling(false)} width={900} tall flush
          footer={<>
            {!inq.reviewedon && (
              <button type="button" className="primary" disabled={busy} onClick={reviewReply}>
                {busy ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
              </button>
            )}
            <button type="button" onClick={() => setFiling(false)}>Close</button>
          </>}>
          <div className="stack docstack">
            {err && <div className="notice bad readstamp">{err}</div>}
            {/* The form they filled in and signed, read here rather than from behind a button.
                Every answer is on it, so listing a handful of them above it said the same things
                twice and left the rest invisible. */}
            {inq.documentid
              ? <DocumentPane id={inq.documentid} name={`SPHI - ${inq.employer}`}
                  className="docview docfill" />
              : <div className="muted">The reply is on file but carries no document.</div>}
            {inq.reviewedon && (
              <div className="muted small readstamp">Read {date(inq.reviewedon)}.</div>
            )}
          </div>
        </Modal>
        {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
          onClose={() => setViewing(null)} />}
        </>
      )
    }

    if (filing === 'history' && inq) {
      return (
        <Modal title={`${inq.employer} - History`} onClose={() => setFiling('send')} width={820}
          footer={<button type="button" onClick={() => setFiling('send')}>Close</button>}>
          <div className="stack">
            {inq.attempts.length === 0
              ? <div className="muted">Nothing has been tried yet.</div>
              : (
                <table className="residencetable attempttable">
                  <thead><tr><th>When</th><th>How</th><th>To</th><th>Outcome</th></tr></thead>
                  <tbody>
                    {inq.attempts.map((a) => (
                      <tr key={a.recordid}>
                        <td>{date(a.senton)}</td>
                        <td>{sphi?.channels?.[a.channel] || a.channel}</td>
                        <td>{a.sentto || '-'}</td>
                        <td>{[a.outcome, a.note].filter(Boolean).join(' - ') || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
          </div>
        </Modal>
      )
    }

    // The good faith effort as the document 391.23(i) asks for: who was asked, everything that was
    // tried, how it ended, and somebody's signature saying that is what happened.
    if (filing === 'gfe') {
      const tried = inq?.attempts?.length || 0
      const closing = (sphi?.gfeclosing || []).includes(gfe.status)
      const needsAttempt = closing && gfe.status !== 'received' && tried === 0
      return (
        <Modal title="Good Faith Effort Documentation" width={820}
          onClose={() => setFiling('send')}
          footer={<>
            {/* An ending that is certified is filed by the signing itself. "Still pending" is not
                certified by anybody - it is a note about where things stand - so it is the one
                that still has something to press. */}
            {!closing && (
              <button type="button" className="primary" disabled={busy} onClick={closeEffort}>
                {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
              </button>
            )}
            <button type="button" onClick={() => setFiling('send')}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            {/* Whose document this is and what it is. A page pulled out of this file months from
                now is anonymous without it - and an auditor is reading the document, not the
                dialog that happened to be around it. */}
            <div className="dialoghead">
              <span className="co">{me?.accountname}</span>
              <h2>Safety Performance History Investigation</h2>
              <span className="sub">Good Faith Effort Documentation · 49 CFR 391.23(i)</span>
            </div>

            <h3 className="formsection">Driver</h3>
            <dl className="askfacts">
              <div><dt>Driver</dt><dd>{sphi?.driver?.name || '-'}</dd></div>
              <div><dt>Driver ID</dt><dd>{sphi?.driver?.drivernumber || '-'}</dd></div>
              <div><dt>Date of hire</dt>
                <dd>{sphi?.driver?.hiredon ? date(sphi.driver.hiredon) : 'Not hired yet'}</dd></div>
            </dl>

            <h3 className="formsection">Previous Employer</h3>
            <dl className="askfacts">
              <div><dt>Employer</dt><dd>{inq?.employer || '-'}</dd></div>
              <div><dt>Contact</dt><dd>{inq?.contactname || '-'}</dd></div>
              <div><dt>Phone</dt><dd><Phone number={inq?.phone} /></dd></div>
              <div><dt>Email</dt><dd><Email address={inq?.email} /></dd></div>
              <div><dt>Fax</dt><dd>{inq?.fax || '-'}</dd></div>
              <div><dt>Employed</dt>
                <dd>{[inq?.employedfrom && date(inq.employedfrom),
                      inq?.employedthrough && date(inq.employedthrough)]
                  .filter(Boolean).join(' to ') || '-'}</dd></div>
            </dl>

            {/* Every attempt, which is what the effort IS. Added from the dialog behind this one,
                because an attempt is a thing that happened rather than a line on a form. */}
            <h3 className="formsection">Attempts ({tried})</h3>
            {tried === 0 ? (
              <div className="notice bad">
                Nothing has been tried yet. A good faith effort is filed over attempts that were
                actually made, so there is nothing to certify here.
              </div>
            ) : (
              <table className="residencetable recordtable">
                <thead><tr><th>Date</th><th>Method</th><th>Sent to</th><th>Result</th></tr></thead>
                <tbody>
                  {inq.attempts.map((a) => (
                    <tr key={a.recordid}>
                      <td>{date(a.senton)}</td>
                      <td>{sphi?.channels?.[a.channel] || a.channel}</td>
                      <td>{a.sentto || '-'}</td>
                      <td>{[a.outcome, a.note].filter(Boolean).join(' - ') || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <h3 className="formsection">Determination</h3>
            <div className="asklist">
              {Object.entries(sphi?.gfestatus || {}).map(([v, l]) => (
                <label key={v} className="askrow">
                  <span className="askwhat">{l}</span>
                  <span className="askpick">
                    <input type="radio" name="gfestatus" checked={gfe.status === v}
                      onChange={() => setGfe({ ...gfe, status: v })} />
                  </span>
                </label>
              ))}
            </div>
            <div className="profileform">
              <label className="field span-6">Notes
                <textarea rows={3} value={gfe.note} className="upper"
                  onChange={(e) => setGfe({ ...gfe, note: e.target.value.toUpperCase() })} />
              </label>
            </div>

            {/* The certification. Signed with the signer's own signature already on file - the one
                adopted behind a date of birth and a Social Security number - exactly as the
                request itself is signed. Nobody types their name here. */}
            {closing && (
              <div className="signhereblock">
                <p className="muted small">
                  I certify that the employer made a good faith effort to obtain the driver's
                  required safety performance history from the previous employer identified above.
                  The attempts documented in this record represent the actions taken to obtain the
                  required information.
                </p>
                <dl className="askfacts">
                  <div><dt>Completed by</dt><dd>{sphi?.certifier?.name || '-'}</dd></div>
                  <div><dt>Title</dt><dd>{sphi?.certifier?.title || '-'}</dd></div>
                </dl>
                {/* The signing act every document in this software uses: Sign Document, then the
                    date of birth and Social Security number, then the signature on file is looked
                    up and applied. Nothing is drawn on the line until that has happened. */}
                <SignatureBlock
                  signature={gfesig || (inq?.effortsignedon
                    ? { typedname: inq.effortsignature, fontkey: inq.effortfontkey || 'modern' }
                    : null)}
                  onSigned={(sig) => { setGfesig(sig); closeEffort() }}
                  label="Signature" action="Sign Document" />
              </div>
            )}
          </div>
        </Modal>
      )
    }

    // One dialog per employer: what has been tried, how to try again, and the signature that lets
    // it go. The history is here rather than in a screen of its own because the next attempt is
    // decided by reading the last one - a third letter to an address that bounced twice is not a
    // good faith effort, it is a habit.
    if (filing === 'send' && inq) {
      const signed = Boolean(inq.requestsignedon)
      const sending = att.channel === 'email'
      return (
        <Modal title={inq.employer} onClose={() => setFiling(false)} width={860}
          footer={<>
            <button type="button" className="primary"
              disabled={busy || !att.sentto.trim() || (!signed && !sphi?.signature)}
              onClick={sendRequest}>
              {busy ? <Loader2 size={15} className="spin" />
                : sending ? <><Send size={13} /> Send it</> : <><Plus size={13} /> Record it</>}
            </button>
            <button type="button" disabled={!inq.attempts.length}
              onClick={() => setFiling('history')}>
              <History size={13} /> History{inq.attempts.length ? ` (${inq.attempts.length})` : ''}
            </button>
            {/* A reply that came back on paper or by fax. The same answer; the only difference is
                that nobody typed it in, so what is kept is the page they sent. */}
            {!inq.respondedon && (
              <button type="button"
                onClick={() => { setAtt({ ...att, sentto: inq.contactname || '', note: '',
                  file: null }); setFiling('upload') }}>
                <Plus size={13} /> Upload
              </button>
            )}
            {/* Offered whenever the employer has not answered: the dialog says what is being
                filed over, and refuses when there is nothing behind it. */}
            {!inq.effortclosedon && !inq.respondedon && (
              <button type="button" onClick={() => { setAtt({ ...att, note: '' }); setFiling('gfe') }}>
                <FileSignature size={13} /> File GFE
              </button>
            )}
            <button type="button" onClick={() => setFiling(false)}>Close</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}

            <section>
              <h3 className="formsection">Send It</h3>
              <div className="profileform">
                <label className="field span-2">How
                  <select value={att.channel}
                    onChange={(e) => setAtt({ ...att, channel: e.target.value,
                      sentto: (SEND_TO[e.target.value] || (() => ''))(inq) })}>
                    {Object.entries(sphi?.channels || {}).map(([v, l]) =>
                      <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
                <label className="field span-4">
                  {att.channel === 'email' ? 'Email address'
                    : att.channel === 'fax' ? 'Fax number'
                      : att.channel === 'phone' ? 'Telephone' : 'Address'}
                  <input value={att.sentto}
                    onChange={(e) => setAtt({ ...att, sentto: e.target.value })} />
                </label>
                {/* The link the employer answers on. On the form because a fax or a letter has to
                    carry it, and somebody on the telephone has to be able to read it out. */}
                {!inq.respondedon && (
                  <label className="field span-6">Link they answer on
                    <code className="linkline">{inq.link}</code>
                  </label>
                )}
                {!sending && (
                  <>
                    <label className="field span-2">On
                      <input type="date" value={att.senton}
                        onChange={(e) => setAtt({ ...att, senton: e.target.value })} /></label>
                    <label className="field span-2">Outcome
                      <select value={att.outcome}
                        onChange={(e) => setAtt({ ...att, outcome: e.target.value })}>
                        <option value="">Not stated</option>
                        <option value="sent">Sent</option>
                        <option value="failed">Failed to send</option>
                        <option value="noanswer">No answer</option>
                        <option value="refused">Refused</option>
                      </select>
                    </label>
                    <label className="field span-6">Note
                      <textarea value={att.note}
                        onChange={(e) => setAtt({ ...att, note: e.target.value })} /></label>
                  </>
                )}
              </div>
              {!sending && (
                <p className="muted small">
                  TripProof does not send by {(sphi?.channels?.[att.channel] || att.channel).toLowerCase()}.
                  Send it yourself and record it here.
                </p>
              )}
            </section>

            {/* A previous employer is being asked to release somebody's history to a stranger. A
                named person putting their name to it is what makes that a request. */}
            <section>
              <h3 className="formsection">Signed By</h3>
              {/* The hand itself, as it will appear on the request - a statement of what is
                  about to be signed, not a step to repeat per employer. */}
              {(signed || sphi?.signature) ? (
                <div className="signfields">
                  <div className="signbox">
                    <span className="signlabel">Signature Of Requestor</span>
                    <div className="signline">
                      <span className={`sigink font-${signed ? inq.requestfontkey || 'modern'
                        : sphi.signature.fontkey}`}>
                        {signed ? inq.requestsignature : sphi.signature.typedname}
                      </span>
                    </div>
                  </div>
                  <div className="signbox datebox">
                    <span className="signlabel">Signature Date</span>
                    <div className="signline">
                      {date(signed ? inq.requestsignedon : today)}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="notice warn">
                  A request goes out over somebody&rsquo;s name. Set up your signature in your
                  profile, and it will be used for this and every request afterwards.
                </div>
              )}
            </section>
          </div>
        </Modal>
      )
    }

    const found = sphi?.inquiries || []
    return (
      <>
      {/* One panel per employer, laid out as the driving records are: who and when in the head,
          where the inquiry stands beneath, and what can be done about it below. */}
      <PanelsDialog title={r.name} brief={r?.description} err={err} width={DETAIL} onClose={onClose}
        empty={<div className="muted">
          No DOT-regulated employers in the last three years are on this driver&rsquo;s
          application, so there is nobody to ask.
        </div>}>
        {found.map((x) => {
          const last = (x.attempts || [])[0]
          const unreadReply = x.respondedon && !x.reviewedon
          const tone = x.state === 'answered' ? 'st-active' : x.state === 'effort' ? 'st-inactive'
            : x.state === 'toreview' || x.state === 'waiting' ? 'st-ordered' : 'st-expired'
          const send = () => {
            const channel = x.email ? 'email' : x.fax ? 'fax' : 'mail'
            setInq(x)
            setAtt({ channel, sentto: SEND_TO[channel](x), senton: '', outcome: '',
              note: '', signature: '' })
            setFiling('send')
          }
          return (
            <ItemPanel key={x.recordid} title={x.employer}
              status={[SPHI_STANDING[x.state] || x.state, tone]}
              facts={[
                { label: 'Employed',
                  value: [date(x.employedfrom), date(x.employedthrough)].filter(Boolean).join(' - ') || '-' },
                { label: 'Last asked', tone: last ? undefined : 'st-expired',
                  value: last ? `${SPHI_CHANNELS[last.channel] || last.channel} ${date(last.senton)}` : 'Not asked' },
                { label: 'Reply', tone: x.respondedon ? undefined : last ? 'st-ordered' : undefined,
                  value: x.respondedon ? date(x.respondedon) : last ? 'None yet' : '-' },
                { label: 'Review',
                  tone: unreadReply ? 'st-ordered' : x.reviewedon ? 'st-active' : undefined,
                  value: unreadReply ? 'Not reviewed' : x.reviewedon ? date(x.reviewedon)
                    : x.effortclosedon ? `Good faith effort ${date(x.effortclosedon)}` : '-' },
              ]}
              actions={<>
                      {unreadReply ? (
                        <button type="button" className="primary" onClick={() => {
                          setInq(x); setAtt({ ...att, outcome: '', note: '' }); setFiling('reply')
                        }}><Eye size={14} /> Review</button>
                      ) : x.respondedon ? (
                        <button type="button" onClick={() => {
                          setInq(x)
                          if (x.documentid) {
                            setViewing({ documentid: x.documentid, filename: `SPHI - ${x.employer}` })
                          } else {
                            setAtt({ ...att, outcome: '', note: '' }); setFiling('reply')
                          }
                        }}><Eye size={14} /> View</button>
                      ) : x.effortclosedon && x.effortdocumentid ? (
                        <button type="button" onClick={() => setViewing({
                          documentid: x.effortdocumentid, filename: `Good faith effort - ${x.employer}` })}>
                          <Eye size={14} /> View
                        </button>
                      ) : null}
                      {/* Asking again is always open until somebody has answered. */}
                      {!x.respondedon && (
                        <button type="button" className={last ? undefined : 'primary'} onClick={send}>
                          <Send size={13} /> {last ? 'Ask Again' : 'Send Inquiry'}
                        </button>
                      )}
                      <button type="button" disabled={!(x.attempts || []).length}
                        onClick={() => setSphiHistory(x)}>
                        <History size={13} /> History
                      </button>
                    </>} />
          )
        })}
      </PanelsDialog>
      {/* Every time this employer was asked, how, and what came of it. */}
      {sphiHistory && (
        <Modal title={`${sphiHistory.employer} - History`} onClose={() => setSphiHistory(null)}
          width={DETAIL}
          footer={<button type="button" onClick={() => setSphiHistory(null)}>Close</button>}>
          <table className="residencetable recordtable">
            <thead><tr><th>Date</th><th>How</th><th className="growcol">Sent To</th><th>Outcome</th></tr></thead>
            <tbody>
              {(sphiHistory.attempts || []).map((a) => (
                <tr key={a.recordid}>
                  <td>{date(a.senton)}</td>
                  <td>{SPHI_CHANNELS[a.channel] || a.channel}</td>
                  <td className="growcol">{a.sentto || '-'}</td>
                  <td>{a.outcome || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Modal>
      )}
      {/* The form they sent back, opened straight from the row. */}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)} />}
      </>
    )
  }

  // Drug and alcohol testing, and the bar a positive produces.
  //
  // The return-to-duty process is not one process. Only a driver under 49 CFR Part 382 goes through
  // a DOT-qualified substance abuse professional, and only there does the SAP's determination gate
  // the return-to-duty test (40.305). Under a CTD, broker or company program there is an
  // evaluation and a return to duty, but there is no DOT SAP in it - so this screen never calls one
  // by the other's name. What it says is what the program actually requires.
  if (source.kind === 'drugtest') {
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

  // Adding a record is its own dialog, the way ordering an MVR and adding a license are. A form
  // living inside the list means the list and the thing being added are on screen at once, each
  // pretending the other is not there.
  // Ordering asks for nothing: the requirement already says what is being sent for, and TripProof
  // does not pull it - the office does. So it is a question, laid out as the driving record's
  // question is, because they are the same question about different things.
  if (filing === 'order') {
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

  if (filing === 'against') {
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

  if (filing === true) {
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

  // Read from a list, the same as the PHI acknowledgement: the latest record only, Reviewed or Not
  // Reviewed, and View / Close. An empty file falls through to the dialog below, which offers the
  // upload and the request to the driver.
  const latest = source.kind === 'credential'
    && shown.find((x) => x.documentid)
  if (latest && !filing) {
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

  return (
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

// 49 CFR asks nothing of this - a broker does. What the screen has to be clear about is what is
// being bought, what it costs, and that the answer is the vendor's finding rather than a verdict on
// the driver: somebody here still has to read it and decide.
//
// What is on offer is not named here. The tiers come from the price list, so adding one or
// changing what it costs is an administrator's job and not a release.
function BackgroundScreening({ id, item, onClose, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/background`), [id])
  const [picked, setPicked] = useState(null)
  const [extras, setExtras] = useState([])     // the add-ons bought on top of the report
  const [upload, setUpload] = useState(null)   // a screening run somewhere else
  const [viewing, setViewing] = useState(null) // the report, open
  const [reviewing, setReviewing] = useState(null)  // and what somebody concluded from it
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!data) {
    return (
      <Modal title={item.name} onClose={onClose} width={720}
        footer={<button type="button" onClick={onClose}>Close</button>}>
        <Loading error={error} />
      </Modal>
    )
  }
  const running = data.orders.find((o) => !o.receivedon)
  const money = (c) => `$${((c || 0) / 100).toFixed(2)}`
  // The first on offer until somebody says otherwise, rather than a SKU written in here - what
  // an account carries is the vendor's business and differs between companies.
  const reports = data.reports || []
  const tier = picked ?? reports[0]?.sku ?? ''
  // An order carries the SKU it was placed under. The account may since have stopped carrying it,
  // so the name is looked up and the SKU itself stands in when it is gone.
  const named = (sku) => (reports.find((x) => x.sku === sku) || {}).name || sku
  const chosen = reports.find((r) => r.sku === tier)
  const total = (chosen?.price || 0)
    + (data.addons || []).filter((a) => extras.includes(a.flag))
        .reduce((n, a) => n + (a.price || 0), 0)

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); await reload(); onChanged?.() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (viewing) {
    return <DocumentViewer id={viewing} name="Background Screening"
      onClose={() => setViewing(null)} />
  }

  // What the office concluded. Its own act with its own record of who did it: the report being on
  // file and somebody having read it are two different facts, and an auditor asks about both.
  if (reviewing) {
    const say = (finding) => act(async () => {
      await api.post(`/drivers/${id}/reports/BACKGROUND_SCREENING/${reviewing.recordid}/reviewed`,
                     { finding })
      setReviewing(null)
    })
    return (
      <Modal title="What Does It Say?" width={560} onClose={() => setReviewing(null)}
        footer={<button type="button" onClick={() => setReviewing(null)}>Cancel</button>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="kv">
            <dt>Report</dt><dd>{named(reviewing.tier)}</dd>
            <dt>Came back</dt><dd>{date(reviewing.receivedon)}</dd>
          </div>
          <p className="muted small">
            Recorded against your name. The report stays on file whatever is chosen here.
          </p>
          <div className="formactions">
            {Object.entries(data.outcomes || {}).map(([v, l]) => (
              <button key={v} type="button" className={v === 'clear' ? 'primary' : undefined}
                disabled={busy} onClick={() => say(v)}>{l}</button>
            ))}
          </div>
        </div>
      </Modal>
    )
  }

  // A report run somewhere else. The requirement asks for a screening on file, not for one this
  // product ordered, so filing one is a first-class thing to do rather than a fallback.
  if (upload) {
    const fileIt = async () => {
      setBusy(true); setErr(null)
      try {
        const body = new FormData()
        body.append('issuedon', upload.issuedon)
        if (upload.outcome) body.append('outcome', upload.outcome)
        if (upload.note.trim()) body.append('note', upload.note.trim())
        if (upload.file) body.append('file', upload.file)
        await api.post(`/drivers/${id}/reports/BACKGROUND_SCREENING`, body)
        setUpload(null); await reload(); onChanged?.()
      } catch (e) { setErr(e.message) } finally { setBusy(false) }
    }
    return (
      <Modal title="File A Background Screening" onClose={() => setUpload(null)} width={620}
        footer={<>
          <button type="button" onClick={() => setUpload(null)}>Cancel</button>
          <button type="button" className="primary"
            disabled={busy || !upload.issuedon || !upload.file} onClick={fileIt}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-3">Date On The Report *
              <input type="date" value={upload.issuedon}
                onChange={(e) => setUpload({ ...upload, issuedon: e.target.value })} />
            </label>
            <label className="field span-3">The Report *
              <input type="file"
                onChange={(e) => setUpload({ ...upload, file: e.target.files[0] || null })} />
            </label>
            {/* Read now or read later, but never silently counted as read. */}
            <label className="field span-3">What Does It Conclude?
              <select value={upload.outcome}
                onChange={(e) => setUpload({ ...upload, outcome: e.target.value })}>
                <option value="">Not reviewed yet</option>
                {Object.entries(data.outcomes || {}).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </label>
            <label className="field span-3">Note
              <textarea value={upload.note}
                onChange={(e) => setUpload({ ...upload, note: e.target.value })} />
            </label>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title={item.name} onClose={onClose} brief={item.description} width={880}
      footer={<>
        {/* Filing one obtained elsewhere is always on offer. A company with no account of its own
            still has drivers who were screened - by a broker, by a previous employer's vendor, or
            on paper - and the requirement is satisfied by the report, not by where it came from. */}
        <button type="button" disabled={busy} onClick={() => setUpload({
          issuedon: '', outcome: '', note: '', file: null })}>
          <FileUp size={14} /> File One You Already Have
        </button>
        {!running && data.available && reports.length > 0 && (
          <button type="button" className="primary" disabled={busy || !tier}
            onClick={() => act(() => api.post(`/drivers/${id}/background/order`,
              { reportsku: tier, addons: extras }))}>
            {busy ? <Loader2 size={15} className="spin" /> : `Order - ${money(total)}`}
          </button>
        )}
        {running && (
          <button type="button" disabled={busy}
            onClick={() => act(() => api.post(`/drivers/${id}/background/${running.recordid}/refresh`, {}))}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Check for the result'}
          </button>
        )}
        <button type="button" onClick={onClose}>Close</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {/* What has already been ordered, first. Somebody opening this dialog is far more often
            asking "where is the one we did" than "what shall we buy", and the answer was at the
            bottom under everything else. */}
        {data.orders.length > 0 && (
          <table className="residencetable recordtable">
            {/* The actions column is given its width: the table lays out fixed, so without it
                six columns share the room equally and two buttons end up stacked on top of each
                other in a sixth of it. */}
            <thead><tr><th>Ordered</th><th>Depth</th><th>Charged</th><th>Came back</th>
              <th>Status</th><th style={{ width: 250 }} /></tr></thead>
            <tbody>
              {data.orders.map((o) => (
                <tr key={o.recordid}>
                  <td>{date(o.orderedon)}</td>
                  <td>{named(o.tier)}</td>
                  <td>{o.chargecents == null ? '-' : money(o.chargecents)}</td>
                  <td>{o.receivedon ? date(o.receivedon) : '-'}</td>
                  <td className={o.receivedon ? 'st-active' : 'st-ordered'}>
                    {o.vendorstatus === 'failed' ? 'Could not be run'
                      : o.receivedon ? (o.reviewstate === 'reviewed' ? 'Read' : 'Needs reading')
                        : o.vendorstatus === 'waiting' ? 'Waiting for the driver' : 'Running'}
                  </td>
                  {/* Buttons, not prose - the column keeps them on one line rather than
                      wrapping a label a word at a time. */}
                  <td className="actions">
                    <span className="row">
                      {/* The report itself. Nothing can be concluded from one nobody has opened,
                          so reading comes before the finding and not beside it. */}
                      {o.documentid && (
                        <button type="button" onClick={() => setViewing(o.documentid)}>
                          <Eye size={13} /> View
                        </button>
                      )}
                      {o.receivedon && o.reviewstate !== 'reviewed' && (
                        <button type="button" disabled={busy}
                          onClick={() => setReviewing(o)}>Record Finding</button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* No account, no ordering - and said in a way somebody can act on, because the thing
            that fixes it is two screens away and they would otherwise have to guess. */}
        {!data.available && (
          <div className="notice warn">
            <div>
              <b>This company has no account with backgroundchecks.com yet</b>, so nothing can be
              ordered from here. Set one up under Company &rsaquo; Background Checks - the company
              is billed directly and its own name goes on the paperwork the driver signs.
              <div className="small" style={{ marginTop: 4 }}>
                A screening run somewhere else can still be filed against this requirement.
              </div>
            </div>
          </div>
        )}

        {!data.available ? null : running ? (
          <div className="stack">
            <div className="notice">
              {named(running.tier)} was ordered {date(running.orderedon)}
              {running.orderedbyname ? ` by ${running.orderedbyname}` : ''}. It has not come back
              yet.
              {running.vendor === 'certn'
                ? ' It will arrive on its own; checking is for when you do not want to wait.'
                : ' Check for the result when you want to know where it has got to.'}
            </div>
            {/* What is finished inside it and what is not. A report sits at "running" until
                its slowest part comes back, and a county court can take days - so an office
                looking at one that has not moved since Tuesday can see that it is one search
                outstanding rather than something gone wrong. */}
            {(data.progress || []).length > 0 && (
              <table className="residencetable recordtable">
                <thead><tr><th>Part of the report</th><th>Where it has got to</th></tr></thead>
                <tbody>
                  {data.progress.map((p) => (
                    <tr key={p.what}>
                      <td>{p.what}</td>
                      <td className={p.done ? 'st-active' : 'st-ordered'}>{p.state}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {/* Waiting on the DRIVER, not on the vendor - and that is the one kind of waiting an
                office can do something about. They have been emailed a link; this is the same
                form, opened here, for a driver who is stood in front of somebody. */}
            {running.vendorstatus === 'waiting' && running.vendor === 'backgroundchecks' && (
              <div className="notice warn">
                  <div>
                  <b>Waiting for the driver to fill it in.</b> Nothing is searched until they
                  have given their own details and signed the disclosures. We have emailed them
                  this link, and so has backgroundchecks.com.
                  {running.inviteurl && (
                    <div className="small" style={{ marginTop: 6 }}>
                      <b>Their link</b> - read it out, or send it again:
                      <div className="mono" style={{ wordBreak: 'break-all' }}>
                        {running.inviteurl}
                      </div>
                    </div>
                  )}
                </div>
                <span className="pushright">
                  <ApplicantForm script={data.widgetscript} reportKey={running.vendorref}
                    onDone={(how) => { if (how === 'complete') act(async () => {}) }} />
                </span>
              </div>
            )}
          </div>
        ) : (
          <>
            {data.skuproblem && <div className="notice warn">{data.skuproblem}</div>}
            <h3 className="formsection">What To Order</h3>
            {/* Their reports, at the prices this company pays them. Nothing here is TripProof's
                to price - we do not sell it and take no part of it. */}
            {reports.map((r) => (
              <label key={r.sku} className={`tierpick${tier === r.sku ? ' on' : ''}`}>
                <input type="radio" name="tier" value={r.sku} checked={tier === r.sku}
                  onChange={() => setPicked(r.sku)} />
                <span className="tierbody">
                  <span className="tiername">{r.name} <b>{money(r.price)}</b></span>
                  <span className="tiercovers">{r.covers}</span>
                </span>
              </label>
            ))}
            {(data.addons || []).length > 0 && (
              <>
                <h3 className="formsection">Add To It</h3>
                {data.addons.map((a) => (
                  <label key={a.flag} className="check">
                    <input type="checkbox" checked={extras.includes(a.flag)}
                      onChange={(e) => setExtras(e.target.checked
                        ? [...extras, a.flag] : extras.filter((x) => x !== a.flag))} />
                    {a.name} <b>{money(a.price)}</b>
                  </label>
                ))}
              </>
            )}
          </>
        )}

      </div>
    </Modal>
  )
}

// Where a driver stands against the exclusion lists.
//
// Two moments, and they look nothing alike. Almost always: clear, and the only thing worth showing
// is the run of months proving somebody checked. Rarely: a possible match, which is urgent, is not
// an accusation - names repeat - and can only be settled on OIG's own site against the SSN.
const OIG_SEARCH = 'https://exclusions.oig.hhs.gov/'

// Where a report is actually obtained. TripProof does not pull any of these - somebody signs in at
// the authority's own site and runs the query - so the panel that asks for one says where to go.
const REPORT_SITES = {
  CLEARINGHOUSE_PREEMP: ['Clearinghouse', 'https://clearinghouse.fmcsa.dot.gov/'],
}

// Who gave the training. No federal rule names a trainer, and these three cover every way a
// driver actually gets trained: the company does it, a course is bought, or a broker requires
// its own module.
const TRAINED_BY = ['In-House', 'Training Organization', 'Broker/Contractor']

// How wide a requirement reads. One number, because a dialog whose width changes with whichever
// requirement opened it looks like a mistake.
//
// 900 is measured rather than chosen: it is the narrowest the dialog goes with nothing wrapping -
// every cell on the widest row (a date, a provider, a date AND a tester's name, a state, a
// button) on one line, and all three footer actions on one line including "Add passenger
// assistance and wheelchair securement training", which is the longest label any of these
// dialogs produce. It was 1180 while the columns were badly sized; once they took the width
// they actually need, most of that was empty.
const DETAIL = 900

const PAGE = 12

// What reading one driving record concludes - kept apart from the annual review's finding.
const MVR_FINDING = {
  qualified: 'Qualified',
  restricted: 'Restricted',
  disqualified: 'Disqualified',
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

const BLANK_EXAM = (today) => ({
  examtype: 'biennial', examinedon: today, result: 'meets', qualifiedthrough: '',
  examinername: '', examinerlicense: '', examinerstate: '', examinertype: '',
  correctivelenses: false, hearingaid: false, otherrestriction: '',
  tempreason: '', followupon: '', file: null,
})

// What one examination says about the driver, in the row's own Status column.
const examStanding = (rec) => {
  if (rec.result === 'temporary') return ['Temporarily disqualified', 'st-expired']
  if (rec.result === 'doesnotmeet') return ['Does not meet standards', 'st-expired']
  const band = expiry(rec.expireson)
  if (band === 'st-expired') return ['Expired', 'st-expired']
  if (band === 'st-expiring') return ['Expiring', 'st-expiring']
  return [rec.result === 'meetsperiodic' ? 'Qualified, periodic' : 'Qualified', 'st-active']
}

// How one filed record stands, in its own column and its own colour - never a badge inside a cell.
// A determination that went against the driver outranks any date: a positive test does not become
// current again because the paperwork is recent.
const ADVERSE = ['positive', 'refusal', 'flagged', 'failed', 'notqualified', 'disqualified']

const LOOKING = ['review', 'potential', 'pending']

// What each endorsement letter is, so a screen says "P (passenger)" rather than make somebody know.
const ENDORSEMENT_NAMES = {
  H: 'hazardous materials', N: 'tank vehicle', P: 'passenger',
  S: 'school bus', T: 'double/triple trailers', X: 'tank and hazardous materials',
}

// "Medical Certificate" becomes "Medical Certificates". A name already plural is left alone, so
// "Motor Vehicle Records" does not grow a second s.
const plural = (name) => (/s$/i.test(name || '') ? name : `${name}s`)

// When a record is good from and through. Two dates saying one thing, so one column says it.
const valid = (rec) => {
  const from = rec.effectiveon ? date(rec.effectiveon) : null
  const to = rec.expireson ? date(rec.expireson) : null
  if (from && to) return `${from} through ${to}`
  if (from) return `From ${from}`
  return to ? `Through ${to}` : '-'
}

const standingOf = (rec, results) => {
  const said = (rec.determination || '').toLowerCase()
  const label = (results.find(([v]) => v === rec.determination) || [])[1] || rec.determination
  if (ADVERSE.includes(said)) return [label, 'st-expired']
  if (LOOKING.includes(said)) return [label, 'st-ordered']
  const band = expiry(rec.expireson)
  if (band === 'st-expired') return ['Expired', 'st-expired']
  if (band === 'st-expiring') return ['Expiring', 'st-expiring']
  return [label || 'Active', 'st-active']
}

// Room, running out, gone: green beyond a month, gold inside one, red once the date has passed.
const EXPIRY_WARN_DAYS = 30

const expiry = (on) => {
  if (!on) return undefined
  const midnight = new Date()
  midnight.setHours(0, 0, 0, 0)
  const days = Math.round((new Date(`${String(on).slice(0, 10)}T00:00:00`) - midnight) / 86400000)
  return days < 0 ? 'st-expired' : days <= EXPIRY_WARN_DAYS ? 'st-expiring' : 'st-active'
}

const ANNUAL_FINDING = { qualified: 'Qualified',
  corrective: 'Qualified - corrective action required',
  notqualified: 'Disqualified' }

const SOURCE_SITES = {
  OIG_LEIE: ['OIG exclusion list', OIG_SEARCH],
  SAM_EXCLUSIONS: ['SAM.gov', 'https://sam.gov/search'],
}

// Lists no longer offered, kept only so a check already recorded against one still reads as what it
// was. A screening history is a record of what somebody did, not of what the software offers today.
const RETIRED_SOURCES = { FL_AHCA: 'Florida sanctioned providers' }

const sourceName = (code) =>
  (SOURCE_SITES[code] || [])[0] || RETIRED_SOURCES[code] || code || 'OIG exclusion list'

function ExclusionDetail({ id, r, which, records, onClose, onChanged }) {
  const today = new Date().toISOString().slice(0, 10)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [mode, setMode] = useState(null)              // 'record' | 'settle'
  const [viewing, setViewing] = useState(null)
  const [history, setHistory] = useState(false)
  const [page, setPage] = useState(0)
  const [f, setF] = useState({ source: 'OIG_LEIE', checkedon: today, names: '', result: 'clear',
    note: '', file: null, verdict: 'clear' })

  // Only the list this requirement is about. A SAM.gov match is not settled from the OIG dialog.
  const mine = records.filter((x) => !which || x.source === which)
  const open = mine.find((x) => x.determination === 'review')
  // A confirmed exclusion nobody has lifted. It is the only thing on this screen that stops a
  // driver working, so it is the only thing with a way out of it.
  const barred = mine.find((x) => x.determination === 'flagged' && !x.liftedon)
  // The latest screening against the list this requirement is about. The requirement shows what
  // the most recent check returned; every check is in the History.
  const latest = mine[0] || null
  const pages = Math.ceil(mine.length / PAGE)
  const from = page * PAGE
  const shown = mine.slice(from, from + PAGE)

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); setMode(null); onChanged() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const record = () => act(async () => {
    const body = new FormData()
    body.append('source', f.source)
    body.append('checkedon', f.checkedon)
    body.append('namessearched', f.names)
    body.append('result', f.result)
    if (f.note) body.append('note', f.note)
    if (f.file) body.append('file', f.file)
    await api.post(`/drivers/${id}/exclusion-checks`, body)
  })

  const reinstate = () => act(async () => {
    const body = new FormData()
    body.append('liftedon', f.checkedon)
    body.append('reason', f.note)
    body.append('file', f.file)
    await api.post(`/drivers/${id}/exclusion-checks/${barred.recordid}/reinstate`, body)
  })

  const settle = () => act(async () => {
    const body = new FormData()
    body.append('result', f.verdict)
    body.append('verifymethod', open.source === 'SAM_EXCLUSIONS' ? 'samrecord' : 'ssn')
    if (f.note) body.append('note', f.note)
    body.append('file', f.file)
    await api.post(`/drivers/${id}/exclusion-checks/${open.recordid}/settle`, body)
  })

  // Recording a check is its own dialog. Laid over the list, the two were on screen at once,
  // each pretending the other was not there.
  if (mode === 'record') {
    return (
      <Modal title="Record A Check You Ran" onClose={() => setMode(null)}
        footer={<>
          <button type="button" className="primary" disabled={busy || !f.names.trim()}
            onClick={record}>
            {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => setMode(null)}>Cancel</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-2">List
              <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>
                {Object.entries(SOURCE_SITES).map(([k, [label]]) =>
                  <option key={k} value={k}>{label}</option>)}
              </select>
            </label>
            <label className="field span-2">Checked On
              <input type="date" value={f.checkedon}
                onChange={(e) => setF({ ...f, checkedon: e.target.value })} />
            </label>
            <label className="field span-2">Result
              <select value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}>
                <option value="clear">Clear</option>
                <option value="potential">Possible match</option>
                <option value="confirmed">Excluded</option>
              </select>
            </label>
            {/* OIG holds only the name known at exclusion, so former and maiden names have to be
                searched separately - and the record has to say which were tried. */}
            <label className="field span-6">Names Searched
              <input value={f.names} className="upper"
                onChange={(e) => setF({ ...f, names: e.target.value.toUpperCase() })} />
            </label>
            <label className="field span-6">Screenshot
              <input type="file" onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
            </label>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <>
      <Modal title={r.name} onClose={onClose} brief={r?.description} width={DETAIL}
        footer={mode === 'reinstate' ? <button type="button" onClick={onClose}>Close</button> : <>
          {/* Left: the site for the list this requirement is about, and recording a check run
              there. Right: what is on file. */}
          <span className="footactions">
            {SOURCE_SITES[which] && (
              <a className="btn" href={SOURCE_SITES[which][1]} target="_blank" rel="noreferrer">
                <ExternalLink size={13} /> {SOURCE_SITES[which][0]}
              </a>
            )}
            <button type="button" onClick={() => setMode('record')}>
              <Plus size={13} /> Record a check I ran
            </button>
          </span>
          {latest && (
            <button type="button" onClick={() => setViewing({ path:
              `/drivers/${id}/exclusion-checks/${latest.recordid}/record`,
              filename: 'Search Audit Record' })}>
              <FileText size={13} /> Search Audit Record
            </button>
          )}
          <button type="button" disabled={!mine.length} onClick={() => setHistory(true)}>
            <History size={13} /> History
          </button>
          <button type="button" onClick={onClose}>Close</button>
        </>}>
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}

          {barred && (
            <div className="notice bad stack">
              <div>
                <b>Excluded &ndash; this driver cannot work on Medicaid trips.</b>
                <div className="small">
                  Every trip they carry is an overpayment. An exclusion does not lapse: OIG lifts it
                  only on application, and only in writing.
                </div>
              </div>
              {mode !== 'reinstate' ? (
                <div className="row">
                  <button type="button" onClick={() => setMode('reinstate')}>
                    Record a reinstatement
                  </button>
                </div>
              ) : (
                <div className="stack">
                  <div className="profileform">
                    <label className="field span-2">Reinstated On
                      <input type="date" value={f.checkedon}
                        onChange={(e) => setF({ ...f, checkedon: e.target.value })} />
                    </label>
                    <label className="field span-4">Notice Of Reinstatement *
                      <input type="file"
                        onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
                    </label>
                    <label className="field span-6">What Lifted It *
                      <textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
                    </label>
                  </div>
                  <div className="row">
                    <button type="button" className="primary"
                      disabled={busy || !f.file || !f.note.trim()} onClick={reinstate}>
                      {busy ? <Loader2 size={15} className="spin" /> : 'Lift the exclusion'}
                    </button>
                    <button type="button" onClick={() => setMode(null)}>Cancel</button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* A possible match comes first and crowds everything else out. */}
          {open && <PossibleMatch record={open} f={f} setF={setF} busy={busy}
            settling={mode === 'settle'} onSettle={settle} onStart={() => setMode('settle')}
            onCancel={() => setMode(null)} />}

          {!latest && <div className="notice warn">This driver has never been screened.</div>}

          {latest && (
            <dl className="askfacts">
              <div><dt>Screening type</dt><dd>{SCREENING_TYPE[latest.source] || sourceName(latest.source)}</dd></div>
              <div><dt>Last screened</dt><dd>{date(latest.effectiveon)}</dd></div>
              <div><dt>Database version</dt><dd>{listVersion(latest)}</dd></div>
              <div><dt>Screening outcome</dt>
                <dd className={outcomeOf(latest)[1]}>{outcomeOf(latest)[0]}</dd></div>
              <div><dt>Next screening</dt><dd>{date(nextScreening(latest))}</dd></div>
              <div><dt>Verification status</dt><dd>{verificationOf(latest)}</dd></div>
              <div><dt>Evidence</dt>
                <dd>{latest.documentid ? 'Search audit record and screenshot' : 'Search audit record'}</dd></div>
            </dl>
          )}
        </div>
      </Modal>
      {history && (
        <Modal title={`${r.name} - History`} onClose={() => setHistory(false)} width={DETAIL}
          footer={<button type="button" onClick={() => setHistory(false)}>Close</button>}>
          <div className="stack">
            <table className="residencetable screeningtable">
              <thead><tr><th>Screened</th><th>List</th><th>Version</th><th>Outcome</th>
                <th>Verification</th><th /></tr></thead>
              <tbody>
                {shown.map((x) => (
                  <tr key={x.recordid}>
                    <td>{x.effectiveon ? date(x.effectiveon) : '-'}</td>
                    <td>{SCREENING_TYPE[x.source] || sourceName(x.source)}</td>
                    <td>{listVersion(x)}</td>
                    {/* Shorter in the history, where it repeats down the column. */}
                    <td className={outcomeOf(x)[1]}>
                      {x.determination === 'clear' ? 'No Match' : outcomeOf(x)[0]}
                    </td>
                    <td>{verificationOf(x)}</td>
                    <td className="actions">
                      <button type="button" className="linkbtn edit"
                        onClick={() => setViewing({ path:
                          `/drivers/${id}/exclusion-checks/${x.recordid}/record`,
                          filename: 'Search Audit Record' })}>
                        Record
                      </button>
                      {x.documentid && (
                        <button type="button" className="linkbtn edit"
                          onClick={() => setViewing({ documentid: x.documentid, filename: 'Screening evidence' })}>
                          Screenshot
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* A screening history only grows - a driver of two years has twenty-four rows from
                the monthly job alone - so it is paged rather than left to run off the bottom. */}
            {pages > 1 && (
              <div className="pager">
                <span className="muted small">
                  {from + 1}&ndash;{Math.min(from + PAGE, mine.length)} of {mine.length}
                </span>
                <div className="row">
                  <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>
                    <ChevronLeft size={14} /> Newer
                  </button>
                  <button type="button" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
                    Older <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
      {viewing && <DocumentViewer id={viewing.documentid} path={viewing.path} name={viewing.filename}
        onClose={() => setViewing(null)} />}
    </>
  )
}

// What a screening concluded, and in what colour.
const outcomeOf = (x) => (x.determination === 'clear' ? ['No match found', 'st-active']
  : x.determination === 'flagged'
    ? [x.liftedon ? `Excluded, lifted ${date(x.liftedon)}` : 'Excluded',
      x.liftedon ? 'st-inactive' : 'st-expired']
    : ['Possible match', 'st-ordered'])

// Whether a person has to settle it, and whether they have.
const verificationOf = (x) => (x.verifiedon
  ? `Verified ${date(x.verifiedon)}${x.verifiedbyname ? ` by ${x.verifiedbyname}` : ''}`
  : x.determination === 'review' ? 'Required' : 'Not required')

// The published list as people name it - "October 2026" - from the date OIG stamped on the file.
// A check somebody ran on the site by hand was not run against a downloaded list.
// SAM.gov publishes daily, so its version is the file's own date.
const listVersion = (x) => {
  if (!x.datasetstamp) return 'Searched on the site'
  if (x.source === 'SAM_EXCLUSIONS') return date(x.datasetstamp)
  const d = new Date(x.datasetstamp)
  return Number.isNaN(d.getTime()) ? x.datasetstamp
    : d.toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

// OIG republishes monthly, SAM.gov daily.
const nextScreening = (x) => {
  const d = new Date(`${String(x.effectiveon).slice(0, 10)}T00:00:00`)
  if (x.source === 'SAM_EXCLUSIONS') d.setDate(d.getDate() + 1)
  else d.setMonth(d.getMonth() + 1)
  return d.toISOString().slice(0, 10)
}

const SCREENING_TYPE = { OIG_LEIE: 'OIG LEIE', SAM_EXCLUSIONS: 'SAM.gov' }

// A name came back on the list. Shown side by side, because what the person is doing is comparing
// two records - and the discriminators are the whole job.
function PossibleMatch({ record, f, setF, busy, settling, onSettle, onStart, onCancel }) {
  let listed = []
  try { listed = JSON.parse(record.candidatesjson || '[]') } catch { listed = [] }
  return (
    <div className="notice warn stack">
      <div>
        <b>A possible match &ndash; somebody has to settle this.</b>
        <div className="small">Names repeat. This is not an accusation.</div>
      </div>
      {listed.map((c, i) => (
        <div key={i} className="small">
          {[`${c.firstname} ${c.middle || ''} ${c.lastname}`.replace(/\s+/g, ' ').trim(),
            c.dob ? `DOB ${c.dob}` : null, [c.city, c.state].filter(Boolean).join(', '),
            c.general, c.excltype, c.agency, c.samnumber && `SAM number ${c.samnumber}`]
            .filter(Boolean).join(' \u00b7 ')}
        </div>
      ))}
      {/* SAM.gov carries no SSN at all, so a SAM match is settled by opening the exclusion itself
          and comparing it with what is known about the driver. */}
      <div className="small">
        {record.source === 'SAM_EXCLUSIONS'
          ? <>Settle it on SAM.gov &ndash; open the exclusion by its SAM number and compare it with
            this driver.</>
          : <>Settle it with the Social Security number on OIG&rsquo;s site &ndash; it is the only
            place that can answer definitively.</>}
      </div>
      {!settling ? (
        <div className="row">
          {record.source === 'SAM_EXCLUSIONS' ? (
            <a className="btn" href={SOURCE_SITES.SAM_EXCLUSIONS[1]} target="_blank" rel="noreferrer">
              <ExternalLink size={13} /> Open SAM.gov
            </a>
          ) : (
            <a className="btn" href={OIG_SEARCH} target="_blank" rel="noreferrer">
              <ExternalLink size={13} /> Open OIG verify
            </a>
          )}
          <button type="button" onClick={onStart}>Settle it</button>
        </div>
      ) : (
        <div className="stack">
          <div className="profileform">
            <label className="field span-3">What did OIG say?
              <select value={f.verdict} onChange={(e) => setF({ ...f, verdict: e.target.value })}>
                <option value="clear">Not this person</option>
                <option value="confirmed">This is the same person</option>
              </select>
            </label>
            <label className="field span-3">Screenshot *
              <input type="file" onChange={(e) => setF({ ...f, file: e.target.files[0] || null })} />
            </label>
            <label className="field span-6">Note
              <textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
            </label>
          </div>
          <div className="row">
            <button type="button" className="primary" disabled={busy || !f.file} onClick={onSettle}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={onCancel}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
