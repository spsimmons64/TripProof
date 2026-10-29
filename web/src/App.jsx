import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { AlertTriangle, Building2, CalendarClock, Car, CreditCard, DollarSign, FileCheck2, FileText, FlaskConical, Gauge, Handshake, ListChecks, MapPin, Route as RouteIcon, User, ShieldAlert, ShieldCheck, Users } from 'lucide-react'
import { api, auth } from './lib/api.js'
import { keepAlive, signOut } from './lib/session.js'
import { Modal } from './admin/common.jsx'
import { setDisplayTimeZone } from './lib/format.js'
import TopBar from './components/TopBar.jsx'
import Login from './pages/Login.jsx'
import ResetPassword from './pages/ResetPassword.jsx'
import Apply from './pages/Apply.jsx'
import Arrivals from './components/Arrivals.jsx'
import ToReview from './pages/ToReview.jsx'
import AccountUsers from './pages/Users.jsx'
import DriverApply from './pages/DriverApply.jsx'
import SignDocument from './pages/SignDocument.jsx'
import UploadDocument from './pages/UploadDocument.jsx'
import EmployerReply from './pages/EmployerReply.jsx'
import RoadTest from './pages/RoadTest.jsx'
import { typedInUpperCase } from './lib/casing.js'
import Dashboard from './pages/Dashboard.jsx'
import Trips from './pages/Trips.jsx'
import Dispatch from './pages/Dispatch.jsx'
import Shifts from './pages/Shifts.jsx'
import ProblemAlert from './components/ProblemAlert.jsx'
import SavedList from './pages/SavedList.jsx'
import DriverApp from './driver/DriverApp.jsx'
import TripDetail from './pages/TripDetail.jsx'
import Import from './pages/Import.jsx'
import Drivers from './pages/Drivers.jsx'
import Vehicles from './pages/Vehicles.jsx'
import SubjectDetail from './pages/SubjectDetail.jsx'
import Company from './pages/Company.jsx'
import FeeSchedules from './pages/FeeSchedules.jsx'
import Payers from './pages/Payers.jsx'
import MapWindow from './pages/MapWindow.jsx'
import RandomTesting from './pages/RandomTesting.jsx'
import SupervisorRecord, { SupervisorBanner } from './components/SupervisorRecord.jsx'
import Audits from './pages/Audits.jsx'
import AuditDetail from './pages/AuditDetail.jsx'
import Billing from './pages/Billing.jsx'
import AdminApp from './admin/AdminApp.jsx'

const UserContext = createContext(null)
export const useUser = () => useContext(UserContext)

function Shell({ user, children }) {
  const billingAccess = ['owner', 'admin'].includes(user.role)
  const nav = [
    [null, [
      ['/', Gauge, 'Dashboard'],
      ['/dispatch', CalendarClock, 'Dispatch'],
    ]],
    // Who and what the work is done with, and for: the people and things dispatch draws on.
    ['Assets', [
      ['/drivers', Users, 'Drivers'],
      ['/vehicles', Car, 'Vehicles'],
      ['/passengers', User, 'Passengers'],
      ['/locations', MapPin, 'Locations'],
    ]],
    // Both directions of being checked. An external audit is somebody else asking to see the
    // file; the random testing programme is the carrier checking on itself all year against a
    // rate it has to meet. They belong together because they are the same question asked from
    // two sides, and the names say which side.
    ['Auditing', [
      ['/random-testing', FlaskConical, 'D&A Random Testing'],
      ['/audits', FileCheck2, 'External Audits'],
    ]],
    ['Settings', [
      ['/company', Building2, 'Company'],
      // What the company charges and what each payer pays it. Named "Fee Schedules" here
      // and `payerrates` in the schema, because the table called feeschedule is TripProof's
      // own charges to its customers and the two must never be taken for one another.
      // The price lists first, then who pays under them: a payer's state line names its
      // schedule, so the schedule has to exist before it can be chosen.
      ['/rates', DollarSign, 'Fee Schedules'],
      ['/payers', Handshake, 'Payers'],
      ...(billingAccess ? [['/users', Users, 'Users']] : []),
    ]],
  ]
  const due = ['past_due', 'unpaid'].includes(user.subscription?.status)
  // The email brings a new supervisor here; the banner is what they see if they came on their
  // own, and it stays until they have signed.
  const [signing, setSigning] = useState(
    new URLSearchParams(window.location.search).get('sign') === 'supervisor')
  const [owes, setOwes] = useState(Boolean(user.owessupervisorrecord))
  return (
    <div className="app">
      <TopBar user={user} />
      <ProblemAlert />
      {user.launched && <StaffBanner user={user} />}
      {owes && <SupervisorBanner onOpen={() => setSigning(true)} />}
      {signing && (
        <SupervisorRecord onClose={() => setSigning(false)}
          onSigned={() => setOwes(false)} />
      )}
      {due && (
        <div className="billbanner" role="alert">
          <AlertTriangle size={16} />
          <span><b>Your last payment didn’t go through.</b> {billingAccess ? 'Update your card to avoid interruption.' : 'Ask your account owner to update the payment card.'}</span>
          {billingAccess && <NavLink to="/billing">Update card</NavLink>}
        </div>
      )}
      <div className="shell">
        <nav className="side">
          {nav.map(([section, links]) => (
            <div key={section || 'main'}>
              {section && <div className="section">{section}</div>}
              {links.map(([to, Icon, label]) => (
                <NavLink key={to} to={to} end={to === '/'}><Icon size={16} /> {label}</NavLink>
              ))}
            </div>
          ))}
        </nav>
        <main>{children}</main>
      </div>
      {/* Work that came back on its own, said once in the corner. */}
      <Arrivals />
    </div>
  )
}

// A tab opened by the admin portal's "Launch": keep the staff session token from the URL fragment
// for this tab only, drop the fragment from history, and continue into the customer portal.
if (window.location.pathname === '/launch') {
  const t = new URLSearchParams(window.location.hash.slice(1)).get('token')
  if (t) auth.set(t)
  window.history.replaceState(null, '', '/')
}

// The map opened on a second screen, by the same means. sessionStorage is per browsing
// context and a new tab does NOT reliably inherit a copy of it - the behaviour differs
// between browsers and some block it outright - so the session is handed over explicitly,
// exactly as Launch does: in the fragment, which is never sent to the server, and removed
// from history the moment it has been read.
if (window.location.pathname === '/map') {
  const t = new URLSearchParams(window.location.hash.slice(1)).get('token')
  if (t) {
    auth.set(t)
    window.history.replaceState(null, '', '/map')
  }
}

// Two minutes before an idle sign-in ends: one question, Yes or No - the confirmation every other
// question in the application is, copied from the MVR order. Yes renews it; No signs out now.
function StillThere({ onYes }) {
  return (
    <Modal title="Stay Signed In" onClose={onYes} width={520}
      footer={<>
        <button type="button" className="primary" onClick={onYes}>Yes</button>
        <button type="button" onClick={signOut}>No</button>
      </>}>
      <div className="stack">
        <div className="askorder"><span className="askmark">?</span><p>Do you want to stay signed in?</p></div>
      </div>
    </Modal>
  )
}

function StaffBanner({ user }) {
  const exit = () => { auth.clear(); window.close(); window.location.assign('/login') }
  return (
    <div className="staffbanner" role="status">
      <ShieldAlert size={16} />
      <span>You’re in <b>{user.accountname}</b>’s portal as TripProof staff{user.role === 'auditor' ? ' (read-only)' : ''}. Everything you do here is logged under your name.</span>
      <button onClick={exit}>Exit</button>
    </div>
  )
}

export default function App() {
  // The driver's app is a different application that happens to be served from the same place:
  // its own session, its own API, no office shell around it. Answered before anything else is
  // decided, so a phone never loads the dispatcher's world to throw it away.
  const path = window.location.pathname
  if (path === '/drive' || path.startsWith('/drive/')) return <DriverApp />
  const [user, setUser] = useState(undefined)
  const [token, setToken] = useState(auth.get())

  // Free text is typed and stored UPPER CASE and email addresses lower case, in every form there
  // is. Listened for at the document in the capture phase, so the value is already cased by the
  // time it reaches the field's own onChange - one rule, rather than one per field.
  useEffect(() => {
    document.addEventListener('input', typedInUpperCase, true)
    return () => document.removeEventListener('input', typedInUpperCase, true)
  }, [])

  // Signed in, in the main window: the sign-in is renewed while somebody works and ends after an
  // hour without. The map window lives on this one's, so it does not run its own.
  const [idle, setIdle] = useState(false)
  const keeper = useRef(null)
  useEffect(() => {
    if (!user || window.location.pathname === '/map') return undefined
    keeper.current = keepAlive({ onWarn: setIdle })
    return () => keeper.current?.stop()
  }, [user])

  useEffect(() => {
    if (!token) { setUser(null); return }
    // Timestamps are shown in the user's own time zone, so set it before anything renders.
    api.get('/auth/me').then((u) => { setDisplayTimeZone(u.usertimezone); setUser(u) }).catch(() => setUser(null))
  }, [token])

  // The fleet map on its own, for a second screen. Inside the signed-in split - it reads
  // the company's own positions - but outside the shell, because a window somebody keeps
  // open all day beside their work wants the whole glass, not a column of navigation.
  if (window.location.pathname === '/map') {
    // No session in this tab means it was not opened from the application - somebody typed
    // the address, or a browser setting blocked the context being inherited. Say that,
    // rather than showing a login box that will sign them in and then leave them looking at
    // a map with no way back to anything.
    if (!token) {
      return (
        <div className="mapwindow">
          <header><h2>Current Driver Locations</h2></header>
          <p className="reqaside">
            Open this from the dashboard - the Full screen button beside the map. This window
            borrows the session from the tab that opened it and has none of its own.
          </p>
        </div>
      )
    }
    return <Routes><Route path="/map" element={<MapWindow />} /></Routes>
  }

  // Invitation / reset links work whether or not someone is signed in on this browser.
  if (window.location.pathname === '/reset') return <ResetPassword />
  // A driver applying to a company signs in to nothing: their session is the application itself,
  // so this route stands outside the signed-in/signed-out split.
  if (/^\/account\/[^/]+\/apply\/?$/.test(window.location.pathname)) {
    return <Routes><Route path="/account/:accountnumber/apply" element={<DriverApply />} /></Routes>
  }
  // A driver signing one document from a link the office sent them: the same standing as applying -
  // they sign in to nothing, and the link says only which document is on the table.
  if (/^\/sign\/[^/]+\/?$/.test(window.location.pathname)) {
    return <Routes><Route path="/sign/:token" element={<SignDocument />} /></Routes>
  }
  // And a driver sending one document the office asked them for. Same standing again: the link says
  // which document is wanted, not who is holding it.
  if (/^\/upload\/[^/]+\/?$/.test(window.location.pathname)) {
    return <Routes><Route path="/upload/:token" element={<UploadDocument />} /></Routes>
  }
  // And a previous employer answering a safety performance history request. They have no account
  // here at all - the link is the whole of their relationship with this software.
  if (/^\/employer-reply\/[^/]+\/?$/.test(window.location.pathname)) {
    return <Routes><Route path="/employer-reply/:token" element={<EmployerReply />} /></Routes>
  }
  // And an examiner administering a road test. Same standing again: the link is the whole of their
  // relationship with this software - 49 CFR 391.31.
  if (/^\/road-test\/[^/]+\/?$/.test(window.location.pathname)) {
    return <Routes><Route path="/road-test/:token" element={<RoadTest />} /></Routes>
  }
  if (user === undefined) return null
  if (!user) {
    return (
      <Routes>
        <Route path="/apply" element={<Apply />} />
        <Route path="*" element={<Login onLogin={(t) => { auth.set(t); setUser(undefined); setToken(t) }} />} />
      </Routes>
    )
  }
  // TripProof staff get the admin portal; their internal account holds no customer data.
  // An online application that isn't finished: the applicant goes back to it, wherever they land.
  if (user.accountstatus === 'setup' && !user.platformrole) return <Apply resume />
  const stillthere = idle && <StillThere onYes={() => keeper.current?.stay()} />
  // Subscription lapsed: the Billing page is all there is until it's paid.
  if (user.billinghold) {
    return (
      <UserContext.Provider value={user}>
        <div className="app"><TopBar user={user} /><main className="holdmain"><Billing hold /></main></div>
        {stillthere}
      </UserContext.Provider>
    )
  }
  if (user.platformrole && !user.launched) {
    return <UserContext.Provider value={user}><AdminApp user={user} />{stillthere}</UserContext.Provider>
  }
  return (
    <UserContext.Provider value={user}>
      <Shell user={user}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/review" element={<ToReview />} />
          <Route path="/users" element={<AccountUsers />} />
          <Route path="/dispatch" element={<Dispatch />} />
          <Route path="/vehicle-assignments" element={<Shifts />} />
          <Route path="/trips" element={<Trips />} />
          <Route path="/trips/:id" element={<TripDetail />} />
          <Route path="/import" element={<Import />} />
          <Route path="/drivers" element={<Drivers />} />
          <Route path="/drivers/:id" element={<SubjectDetail kind="driver" />} />
          <Route path="/vehicles" element={<Vehicles />} />
          <Route path="/passengers" element={<SavedList key="passengers" kind="passengers" />} />
          <Route path="/locations" element={<SavedList key="places" kind="places" />} />
          <Route path="/vehicles/:id" element={<SubjectDetail kind="vehicle" />} />
          <Route path="/company" element={<Company />} />
          <Route path="/payers" element={<Payers />} />
          <Route path="/rates" element={<FeeSchedules />} />
          {/* It lives on the Company page as a tab now; the path it was built on still
              lands on it. */}
          <Route path="/payments" element={<Company tab="merchant" />} />
          {/* The two live as tabs on the company page; the paths still work on their own so a
              link to one lands on the right tab. */}
          <Route path="/company/:tab" element={<Company />} />
          {/* The documents live under Company Requirements now, filed against the requirement
              they answer rather than in a list of their own. An old link lands there. */}
          <Route path="/documents" element={<Company tab="requirements" />} />
          <Route path="/random-testing" element={<RandomTesting />} />
          <Route path="/audits" element={<Audits />} />
          <Route path="/audits/:id" element={<AuditDetail />} />
          <Route path="/billing" element={<Company tab="billing" />} />
          <Route path="/login" element={<Navigate to="/" />} />
          <Route path="/apply" element={<Navigate to="/" />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Shell>
      {stillthere}
    </UserContext.Provider>
  )
}
