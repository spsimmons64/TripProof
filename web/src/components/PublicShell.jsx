// The frame every page a driver sees stands in: who this is, whose company it is, and what they
// are being asked to do. Applying and signing are the same person on the same errand, so they wear
// the same header and footer rather than each inventing one.
// `scroll` lets the window do the scrolling instead of the panel inside it. The application wizard
// wants the opposite - a fixed frame with its own panes moving inside - so this is asked for rather
// than assumed.
export default function PublicShell({ company, what = 'Driver application', scroll, children }) {
  return (
    <div className={`applyshell${scroll ? ' pagescroll' : ''}`}>
      <header className="applyhead">
        <div className="brandmark">TripProof Online</div>
        {company && <div className="applyco">{company}<span>{what}</span></div>}
      </header>
      <main className="applymain">{children}</main>
      <footer className="applyfoot">
        <span>&copy; {new Date().getFullYear()} TripProof Online. All rights reserved.</span>
        <span>Web Design By Arrowleaf Technologies, LLC</span>
      </footer>
    </div>
  )
}
