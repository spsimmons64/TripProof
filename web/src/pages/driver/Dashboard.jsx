// Driver page - Dashboard. Moved out of
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
import { unread, when } from './common.jsx'

// Everything that has happened to this application, newest first.
// A pending driver is not being managed, they are being DECIDED ON.
//
// So the whole screen answers one question - can this person be hired, and what stands between
// here and that decision - and anything that does not bear on it is left off. The obligations a
// driver picks up on their first day are real and are not reasons to decline anybody.
//
// The useful cut is WHO each outstanding thing is waiting on. "12 outstanding" is noise; "three of
// them are waiting on you" is a list of things to do this morning.
// What Pending means, said on the screen where somebody is acting on it. The status is easy to
// read as "approved" - it is not, and a driver in it may not be put in a vehicle.
const PENDING_MEANS = [
  "Driver's license and driving record (MVR) verification",
  'Background screening and/or Level 2 screening, when required',
  'Drug and alcohol testing, when applicable',
  'FMCSA Drug & Alcohol Clearinghouse query, when applicable',
  'Safety Performance History Investigation (SPHI), when applicable',
  'DOT medical certification or other required medical examination',
  'Road test and Road Test Certificate, when required',
  'Required training, certifications, acknowledgements, and consent forms',
  'Any additional federal, state, broker, payer, or company requirements',
]

// What Pending means and what happens next. Read once, not every time the file is opened, so it
// is asked for from the status it explains rather than taking the top of the dashboard.
export function PendingBriefing({ onClose }) {
  return (
    <Modal title="What Pending Status Means" onClose={onClose} width={1040}
      footer={<button type="button" onClick={onClose}>Close</button>}>
    <div className="hireexplain">
      <div className="card qualcard hiremeans">
        <h3 className="stagehead">What Pending Means</h3>
        <div className="hiremeansbody">
          <p>
            The driver's application has been reviewed and accepted for further processing.
            <b> Moving a driver to Pending does not mean the driver has been approved or is
            eligible to operate a vehicle.</b>
          </p>
          <p>
            While in Pending status, the company should complete and verify all required
            pre-employment and qualification requirements applicable to the driver. This may
            include:
          </p>
          <ul>
            {PENDING_MEANS.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </div>
      </div>

      {/* And what happens next, because the panel above says what Pending is NOT - somebody reading
          it should not have to work out for themselves what it takes to leave it. */}
      <div className="card qualcard hiremeans">
        <h3 className="stagehead">What Is Next</h3>
        <div className="hiremeansbody">
          <p>
            TripProof will track the driver's required qualification items and their completion
            status.
          </p>
          <p>
            Once all required pre-hire items have been completed and any items that would
            disqualify the driver have been reviewed, the company can make a final hiring decision.
          </p>
          <p>
            The driver may then be moved to Active status if qualified, or Not Hired if the company
            determines the driver does not meet its requirements.
          </p>
          <p className="hirewarn">
            <b>Important:</b> A driver in Pending status should not be assigned to or permitted to
            operate trips until the driver has been hired and all requirements necessary to legally
            perform those trips have been satisfied.
          </p>
        </div>
      </div>
    </div>
    </Modal>
  )
}

// How far through the list this driver is - and it is two lists, not one. What stands between the
// company and taking somebody on is the paperwork of employment; what stands between the driver and
// a vehicle is 382.301, 391.31 and 391.43. A company may finish the first while the second is still
// outstanding, and running the two together is what leaves a count nothing on the screen explains.
function Ring({ pct }) {
  const r = 46
  const circ = 2 * Math.PI * r
  return (
    <svg className="hiredonut" viewBox="0 0 110 110" role="img"
      aria-label={`${pct} percent complete`}>
      <circle cx="55" cy="55" r={r} className="donuttrack" />
      <circle cx="55" cy="55" r={r} className="donutdone"
        strokeDasharray={`${(circ * pct) / 100} ${circ}`} />
      <text x="55" y="55" className="donutpct">{pct}%</text>
    </svg>
  )
}

function Reading({ title, tally, blocking }) {
  const total = tally?.total || 0
  const done = tally?.done || 0
  const pct = total ? Math.round((done / total) * 100) : 100
  return (
    <div className="hirereading">
      <Ring pct={pct} />
      <div className="hirereadingof">
        <div className="hirereadingtitle">{title}</div>
        <div className="hireprogcount">{done} of {total} requirements complete</div>
        <div className="hireprogbar"><span style={{ width: `${pct}%` }} /></div>
        {/* Always drawn, empty or not. One reading carrying a line the other does not makes the
            two blocks different heights, and a centred row then puts the two bars at different
            levels - which reads as two graphs of different sizes. */}
        <div className="hireblocking">
          {blocking > 0 ? `${blocking} blocking ${blocking === 1 ? 'item' : 'items'}` : ''}
        </div>
      </div>
    </div>
  )
}

// A hired driver's file is not a hiring file. How far through the qualification they were is a
// question that has been answered; what matters once somebody is on the books is the work. So the
// pre-hire progress at the top of the dashboard gives its place to what they have driven, and
// every other panel below it stays exactly as it was - the chasing, the reviewing and the dates
// going out of date do not stop at hire, they are the job.
// Where a trip stands, in the house state colours - its own column, as every state is.
const TRIPSTATE = {
  completed: ['Completed', 'st-active'], inprogress: ['In Progress', 'st-ordered'],
  scheduled: ['Scheduled', 'st-inactive'], cancelled: ['Canceled', 'st-expired'],
  noshow: ['No-Show', 'st-expired'], aborted: ['Not Done', 'st-expired'],
  disputed: ['Disputed', 'st-ordered'],
}

function TripHistory({ id }) {
  const [data, error] = useLoad(() => api.get(`/drivers/${id}/trips`), [id])
  const [page, setPage] = useState(1)
  const trips = data?.trips || []
  const at = Math.min(page, Math.max(1, Math.ceil(trips.length / HIRE_ROWS)))
  const shown = trips.slice((at - 1) * HIRE_ROWS, at * HIRE_ROWS)
  return (
    <div className="card qualcard hirepanel hirewide">
      <h3 className="stagehead">Trip History
        {trips.length > 0 && <span className="countpill">{trips.length}</span>}</h3>
      <div className="hireband">
        {!data ? <Loading error={error} />
          : !trips.length ? <div className="hireempty">No trips yet</div> : (
            <table className="residencetable recordtable">
              <thead><tr><th>Date</th><th>Trip</th><th>Vehicle</th><th>Service</th>
                <th>Legs</th><th>Status</th></tr></thead>
              <tbody>
                {shown.map((t) => (
                  <tr key={t.recordid}>
                    <td>{date(t.tripdate)}</td>
                    <td>{t.externalid || '-'}</td>
                    <td>{t.vehicles || <span className="muted">Not recorded</span>}</td>
                    <td>{t.service || '-'}</td>
                    <td>{t.legs}</td>
                    <td className={(TRIPSTATE[t.state] || TRIPSTATE.scheduled)[1]}>
                      {(TRIPSTATE[t.state] || TRIPSTATE.scheduled)[0]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
      {trips.length > HIRE_ROWS && (
        <Pager small total={trips.length} page={at} pagesize={HIRE_ROWS} onPage={setPage}
          noun="trips" />
      )}
    </div>
  )
}

function PreHirePanel({ counts, waiting, stops }) {
  const chip = (n, label, tone) => (
    <span className="whochip">
      <span className={`countpill ${tone}`}>{n}</span>{label}
    </span>
  )
  return (
    <div className="card qualcard hireprog hirewide">
      <h3 className="stagehead">Pre-Hire Progress</h3>
      <div className="hireprogbody">
        <div className="hireprogpair">
          <Reading title="Ready To Hire" tally={counts?.hire} />
          <Reading title="Cleared To Drive" tally={counts?.drive} blocking={stops?.length || 0} />
        </div>
        <div className="hireprogwho">
          {chip(waiting.driver.length, 'Waiting on Driver', 'ondriver')}
          {chip(waiting.office.length, 'Waiting on Us', 'onus')}
          {chip(waiting.outside.length, 'Waiting on Third Party', 'onthird')}
        </div>
      </div>
    </div>
  )
}

const HIRE_ROWS = 5

function HirePanel({ title, items, empty, say, item, onGo, wide, column, tone }) {
  const [page, setPage] = useState(1)
  const total = items.length
  const pages = Math.max(1, Math.ceil(total / HIRE_ROWS))
  const at = Math.min(page, pages)
  const shown = items.slice((at - 1) * HIRE_ROWS, at * HIRE_ROWS)
  return (
    <div className={`card qualcard hirepanel${wide ? ' hirewide' : ''}${column ? ' hirecol' : ''}`}>
      <h3 className="stagehead">{title}
        {total > 0 && <span className={`countpill${tone ? ` ${tone}` : ''}`}>{total}</span>}</h3>
      {/* A fixed band whether it holds one row or five, so a column of these does not jump about
          as the counts change. */}
      <div className="hireband">
        {total ? (
          <ul className="hirelist">
            {shown.map((x) => (
              <li key={x.code}>
                {item ? item(x) : (
                  /* The requirement, and underneath it what is wrong with that requirement. Set
                     side by side the sentence had to share the row with a name long enough to
                     wrap, and the two columns drifted apart as the names changed length. Same
                     shape as Waiting On The Driver, which has read this way all along.

                     Which row was clicked travels with the click. Without it the requirements
                     page only knew somebody wanted to be there, not what they came for. */
                  <div className="askedrow">
                    <div className="askedtop">
                      <button type="button" className="linkbtn edit"
                        onClick={() => onGo?.(x.code)}>{x.name}</button>
                    </div>
                    <span className="askedby">{say(x)}</span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : <div className="hireempty">{empty}</div>}
      </div>
      {total > HIRE_ROWS && (
        <Pager small total={total} page={at} pagesize={HIRE_ROWS} onPage={setPage} noun="items" />
      )}
    </div>
  )
}

export function HiringDashboard({ id, onGo }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/dashboard`), [id])
  // This screen is read while somebody else is acting on it - a driver sending a document in from
  // a link. The toast already knows when something arrives, so the panels follow it rather than
  // waiting for the page to be opened again.
  useRefreshOnFocus(reload)
  useWatch('driver', id, reload, { watching: true })
  useEffect(() => {
    window.addEventListener('tripproof:arrived', reload)
    return () => window.removeEventListener('tripproof:arrived', reload)
  })
  if (!data) return <div className="card qualcard"><h3>Dashboard</h3><Loading error={error} /></div>

  const go = (code) => onGo?.('requirements', code)
  return (
    <div className="hiregrid">
      {data.driver?.status === 'hired'
        ? <TripHistory id={id} />
        : <PreHirePanel counts={data.counts} waiting={data.waiting} stops={data.stops} />}

      {/* The office's own queue, read before any of the chasing below it: it is the one list
          entirely within their power to clear. */}
      <HirePanel wide title="Waiting To Be Reviewed" items={data.unread} onGo={go}
        empty="Nothing to review" say={(x) => x.why} />

      <HirePanel column tone="ondriver" title="Waiting On The Driver" items={data.waiting.driver} onGo={go}
        empty="Nothing requested"
        item={(x) => (
          <div className="askedrow">
            <div className="askedtop">
              <span className="askedwhen">{x.askedon ? when(x.askedon) : '-'}</span>
              <button type="button" className="linkbtn edit"
                onClick={() => go(x.code)}>{x.name}</button>
            </div>
            <span className="askedby">Requested by {x.askedby || 'the office'}</span>
          </div>
        )} />

      <HirePanel column tone="onus" title="Waiting On Us" items={data.waiting.office} onGo={go}
        empty="Nothing to send for" say={(x) => x.why} />

      <HirePanel column tone="onthird" title="Waiting On A Third Party" items={data.waiting.outside} onGo={go}
        empty="Nothing outstanding" say={(x) => x.why} />

      {/* What this driver must qualify with that CAN go out of date. A document with a life is a
          different kind of obligation from one that is done once: it comes back round, and a
          screen that shows only what is outstanding today says nothing about next month. */}
      <div className="card qualcard hiretrack">
        <h3 className="stagehead">
          Validity-Tracked Documents
          {data.tracked.length > 0 && <span className="countpill">{data.tracked.length}</span>}
        </h3>
        {data.tracked.length ? (
          <ul className="hirelist tracklist">
            {data.tracked.map((x) => (
              <li key={x.code}>
                <span className="row trackwhat">
                  <Bubble state={x.band === 'expired' ? 'expired'
                    : x.band === 'expiring' ? 'expiring'
                      : x.band === 'none' ? 'ordered' : 'satisfied'} />
                  <button type="button" className="linkbtn edit"
                    onClick={() => go(x.code)}>{x.name}</button>
                </span>
                {/* A license expires; a screening falls due again. Same date, different fact -
                    and the recheck needs the day it was last done beside it, because that is what
                    somebody is being asked to repeat. */}
                <span className="trackwhen">
                  {x.on && (
                    <span className="tracklast">
                      {x.recurs === 'interval' ? 'Last checked' : 'Issued'} {date(x.on)}
                    </span>
                  )}
                  <span className={x.band === 'expired' ? 'st-expired'
                    : x.band === 'expiring' ? 'st-expiring'
                      : x.band === 'none' ? 'st-inactive' : 'st-active'}>
                    {x.band === 'none' ? 'Nothing on file'
                      : x.expireson
                        ? `${x.recurs === 'interval' ? 'Next due' : 'Expires'} ${date(x.expireson)}`
                        : 'On file'}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        ) : <div className="muted hirenone">Nothing this driver needs goes out of date.</div>}
      </div>
    </div>
  )
}
