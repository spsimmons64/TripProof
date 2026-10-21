import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../lib/states.js'
import { api } from '../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../lib/live.js'
import { date } from '../lib/format.js'
import { Bubble, Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../components/Pager.jsx'
import { useUser } from '../App.jsx'
import SignatureBlock from '../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../components/DocumentViewer.jsx'
import ApplicantForm from '../components/ApplicantForm.jsx'
import SignedDocViewer from '../components/SignedDocViewer.jsx'
import { PhoneInput } from '../components/MaskedInput.jsx'
import LicenseDialog from '../components/LicenseDialog.jsx'
import TestDialog from '../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../components/WithdrawDialog.jsx'
import { Email, Phone } from '../components/Contact.jsx'

import { when } from './driver/common.jsx'
import { DriverInformation } from './driver/DriverInformation.jsx'
import { HiringDashboard, PendingBriefing } from './driver/Dashboard.jsx'
import { DriverActivity } from './driver/Activity.jsx'
import { HoursOfService } from './driver/HoursOfService.jsx'
import { TestingHistory } from './driver/Testing.jsx'
import { DriverFiles } from './driver/Files.jsx'
import { AccidentHistory } from './driver/Accidents.jsx'
import { Requirements } from './driver/Requirements.jsx'
// Other pages import these from here, as they always have.
export { Requirements } from './driver/Requirements.jsx'

// A driver under review: who they are, what they drive on, what has happened to them, and what is
// on file - then hire them or not.
//
// There is deliberately no list of what this driver owes. The catalog that produced that list has
// been removed, because a single "required for commercial / non-commercial" flag cannot say which
// rules reach a given driver: that depends on the vehicle, the commerce, the payer and the
// contract, and getting it approximately right is not good enough. The requirements engine that
// replaces it will read the same records this page already shows.

// How a driver's standing reads to a person.
const STANDING = {
  application: 'Application', appcor: 'Corrections', new: 'New', pending: 'Pending',
  hired: 'Active Driver', inactive: 'Inactive', declined: 'Declined',
}

// One mark, read at a glance, before any of the words beside it.
//
//   green tick    it is on file and current
//   blue dash     it is not asked of this driver
//   red cross     out of compliance - expired, or a determination that came back against them
//   gold clock    sent for, and somebody else is holding it up
//   teal eye      it arrived and nobody has read it - work for this office, not for anyone else
//   grey question nothing yet, or not enough is known to say
//
// The colour carries the urgency and the shape carries the meaning, so the two do not have to be
// read together and neither is doing the job alone.
// A driver who may not perform safety-sensitive functions. Said at the top of every section of
// the file, in the one colour this application keeps for failure, with every reason named.
//
// Not a badge and not a line of grey text. The consequence of somebody missing this is a driver in
// a vehicle who is federally prohibited from being in it, so it is the size of that consequence.
function NotCleared({ stops }) {
  if (!stops?.length) return null
  return (
    <div className="notcleared" role="alert">
      <span className="notclearedmark"><Ban size={26} strokeWidth={2.5} /></span>
      <div className="notclearedsays">
        <h2>Disqualified From Safety-Sensitive Functions</h2>
        <p>This driver must not be assigned to drive or perform safety-sensitive functions.</p>
        <ul>
          {stops.map((x) => (
            <li key={x.code}>{x.name}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

// The SPHI answers, in the form's own words.
const VERIFIED_SAYS = { yes: 'Yes', no: 'No', unable: 'Unable to verify' }

const ACCIDENT_SAYS = { no: 'No', yes: 'Yes', norecords: 'No records available' }

const SECTIONS = [
  // ONE dashboard, whoever the driver is. There used to be two - a hiring dashboard for an
  // applicant and a separate overview for somebody driving - and they shared nothing but a place
  // in the menu: different panels, different headings, a different shape to the page. Hiring
  // somebody does not change what their file is for, so the page does not change either. The one
  // thing that stops being a question is how far through qualification they were, and that panel
  // alone gives its place to what they have driven.
  ['dashboard', 'Dashboard', LayoutDashboard],
  ['information', 'Driver Information', IdCard],
  ['requirements', 'Requirements', ListChecks],
  ['activity', 'Driver Activity', History],
  ['files', 'Driver Files', FolderOpen],
  // Only where Chapter 14-90 reaches the driver. Hours of service is not a universal NEMT
  // obligation and a tab that is empty for most drivers is a tab in the way.
  ['hours', 'Hours Of Service', Clock, (r) => Boolean(r?.chapter1490)],
  // Every test on one list. The requirement dialogs each answer a rule - was the pre-employment
  // test done, is follow-up testing current - but 49 CFR 382.401 asks the employer to KEEP the
  // testing records, and that is one history rather than four answers.
  ['testing', 'D&A Testing History', FlaskConical],
  // 49 CFR 390.15(b) keeps the register, and it is a register of what happened while driving
  // for THIS carrier - so it is not a question to put to somebody who has not driven here yet.
  ['accidents', 'Accident History', Car,
   (r) => Boolean(r?.hiredon) || ['hired', 'inactive'].includes(r?.status)],
]

export default function DriverReview({ id, driver, record, onDone }) {
  const [chosen, setSection] = useState('dashboard')
  // There is one dashboard now, so nothing is swapped underneath anybody. An old link carrying
  // the retired 'overview' section lands on it rather than on nothing.
  const section = chosen === 'overview' ? 'dashboard' : chosen
  const [signedDoc, setSignedDoc] = useState(null)
  const [viewingFile, setViewingFile] = useState(null)
  const [briefing, setBriefing] = useState(false)
  // Which requirement somebody came here to look at, carried from whichever dashboard row they
  // clicked, so the requirements page lands on that row rather than at the top of a long list.
  const [focusReq, setFocusReq] = useState(null)
  // Both of these put somebody on a roster or turn them away, and neither can be taken back from
  // this screen. They get asked first, the way an MVR order does.
  const [deciding, setDeciding] = useState(null)       // 'hire' | 'decline' | 'deactivate'
  // Whether they may drive at all, read apart from whichever section is open - it has to be true
  // on the files page and the activity page as much as on the dashboard.
  const [standing, setStanding] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const topRef = useRef(null)
  const bodyRef = useRef(null)

  // This screen is often open while somebody else is acting on it - a driver signing from a link,
  // a second person in the office filing what just came back.
  const readStanding = () => api.get(`/drivers/${id}/standing`).then(setStanding).catch(() => {})
  const refresh = () => { onDone?.(); readStanding() }
  useRefreshOnFocus(refresh)
  useWatch('driver', id, refresh, { watching: true })
  useEffect(() => { readStanding() }, [id])   // eslint-disable-line react-hooks/exhaustive-deps

  // Arriving here from a toast about a document that was just signed: open it, and take the
  // question out of the address bar so a reload does not open it a second time.
  const wanted = params.get('signed')
  useEffect(() => {
    if (!wanted) return
    setParams({}, { replace: true })
    api.get(`/drivers/${id}/signed/${wanted}`).then(setSignedDoc).catch((e) => setErr(e.message))
  }, [wanted])   // eslint-disable-line react-hooks/exhaustive-deps

  // The panel of sections stays in view as the work beside it scrolls, parked directly under the
  // sticky title - whose height moves with the name, so it is measured, not guessed.
  useEffect(() => {
    const top = topRef.current, body = bodyRef.current
    if (!top || !body) return undefined
    const set = () => body.style.setProperty('--reviewtop', `${top.offsetHeight}px`)
    set()
    const watch = new ResizeObserver(set)
    watch.observe(top)
    return () => watch.disconnect()
  })

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const hire = () => act(async () => {
    await api.post(`/drivers/${id}/hire`, { confirm: true })
    onDone?.()
    navigate('/drivers')
  })

  const decline = () => act(async () => {
    await api.post(`/drivers/${id}/application/decision`, { action: 'decline', note: '' })
    navigate('/drivers')
  })

  // Taking somebody off the roster. The opposite of hiring, and until now the only way to do it
  // was by hand in the database.
  const deactivate = () => act(async () => {
    await api.post(`/drivers/${id}/deactivate`, {})
    onDone?.()
    navigate('/drivers')
  })

  // Whatever was answered by a signature can be read back as it was signed.
  const viewSigned = (doctype) => act(async () => {
    setSignedDoc(await api.get(`/drivers/${id}/signed/${doctype}`))
  })

  return (
    <div className="review">
      {/* The title and the decision are one block: it holds at the top of the playground and the
          file runs under it. Nothing between them can shift, so there is no height to guess at. */}
      <div className="reviewtop" ref={topRef}>
        <div className="pagehead">
          {/* The driver, and where they stand - one block, because the status is a fact about the
              person rather than a control. */}
          <div>
            <h1 className="row">{driver}</h1>
            <div className={`namestatus st-${record?.status || 'unknown'}`}>
              {STANDING[record?.status] || record?.status || '-'}
              {record?.status === 'pending' && (
                <button type="button" className="statusask" onClick={() => setBriefing(true)}
                  aria-label="What Pending status means">?</button>
              )}
            </div>
          </div>
          <div className="row headactions">
            <Link className="btn back" to="/drivers"><ChevronLeft size={14} /> Back to drivers list</Link>
          </div>
        </div>
        {/* The line between who this is and the work on them. Not a browser rule: a teal bar that
            fades out to the right, with the brand's orange tick on its leading edge - the same
            mark the headings in this application carry. */}
        <hr className="reviewrule" />
        {/* Above the work, not inside it: whatever somebody came to this file to do, they find
            this out first. */}
        <NotCleared stops={standing?.adverse} />
      </div>

      {err && <div className="notice bad">{err}</div>}

      <div className="reviewbody" ref={bodyRef}>
        <nav className="reviewnav card">
          {SECTIONS.filter(([, , , when]) => !when || when(record)).map(([key, label, Icon]) => (
            <button key={key} type="button" className={section === key ? 'on' : undefined}
              onClick={() => setSection(key)}>
              <Icon size={15} /> {label}
            </button>
          ))}
          {/* The decision sits with the file rather than over it: somebody makes it after working
              down this menu, not before they have read anything. Which decision is still open
              depends on where the driver already is - offering to hire somebody who is already on
              the roster is an act with no meaning, and the one thing that IS still open for them
              is coming off it. */}
          <div className="navdecide">
            {record?.status === 'hired' ? (
              <button type="button" className="bigaction bad" disabled={busy}
                onClick={() => setDeciding('deactivate')}>
                <UserX size={18} /> <span>Deactivate This Driver</span>
              </button>
            ) : (
              <>
                <button type="button" className="bigaction go" disabled={busy}
                  onClick={() => setDeciding('hire')}>
                  <UserCheck size={18} /> <span>Hire This Driver</span>
                </button>
                <button type="button" className="bigaction bad" disabled={busy}
                  onClick={() => setDeciding('decline')}>
                  <UserX size={18} /> <span>Do Not Hire</span>
                </button>
              </>
            )}
          </div>
        </nav>

        <div className="reviewcols">
          {section === 'information' && (
            <DriverInformation record={record} onSaved={() => onDone?.()} />
          )}
          {section === 'dashboard' && (
            <HiringDashboard id={id}
              onGo={(to, code) => { setSection(to); setFocusReq(code || null) }} />
          )}
          {section === 'activity' && <DriverActivity id={id} />}
          {section === 'requirements' && (
            <Requirements id={id} onChanged={refresh} focus={focusReq}
              onGoSection={setSection} />
          )}
          {section === 'files' && <DriverFiles id={id} onView={setViewingFile} onViewSigned={viewSigned} onChanged={refresh} onGo={(to, code) => { setSection(to); setFocusReq(code || null) }} />}
          {section === 'hours' && <HoursOfService id={id} onChanged={refresh} />}
          {section === 'testing' && <TestingHistory id={id} onChanged={refresh} />}
          {section === 'accidents' && <AccidentHistory id={id} onChanged={refresh} />}
        </div>
      </div>

      {deciding && (
        <Modal title={deciding === 'hire' ? 'Hire This Driver'
          : deciding === 'deactivate' ? 'Deactivate This Driver' : 'Do Not Hire'}
          onClose={() => setDeciding(null)}
          footer={<>
            <button type="button" className="primary" disabled={busy}
              onClick={() => { const go = deciding; setDeciding(null)
                return go === 'hire' ? hire() : go === 'deactivate' ? deactivate() : decline() }}>
              {busy ? <Loader2 size={15} className="spin" /> : 'Yes'}
            </button>
            <button type="button" onClick={() => setDeciding(null)}>No</button>
          </>}>
          <div className="stack">
            <div className="askorder">
              <span className="askmark">?</span>
              <p>{deciding === 'hire' ? `Hire ${driver}?`
                : deciding === 'deactivate' ? `Deactivate ${driver}?` : `Decline ${driver}?`}</p>
            </div>
          </div>
        </Modal>
      )}

      {briefing && <PendingBriefing onClose={() => setBriefing(false)} />}

      {/* A file being read is drawn last, so it lands on top of whatever opened it. */}
      {signedDoc && <SignedDocViewer doc={signedDoc} onClose={() => setSignedDoc(null)} />}
      {viewingFile && (
        <DocumentViewer id={viewingFile.documentid} name={viewingFile.filename || viewingFile.name}
          onClose={() => setViewingFile(null)} />
      )}
    </div>
  )
}

// Hours of service - F.A.C. 14-90.006.
//
// Not a document. FDOT issues no hours-of-service form: the rule sets limits on what a driver may
// actually do, and the way to know whether they were kept is to look at the work. So this is the
// work - a row per day - and the requirement reads these rows. The limits and the rolling
// seven-day window are the server's (app/hos.py), so this screen never does arithmetic of its
// own that could disagree with the requirement it feeds.
const HOS_ROWS = 10
