import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../lib/api.js'
import { followMain } from '../lib/session.js'
import { Loading, useLoad } from '../components/ui.jsx'
import FleetMap from '../components/FleetMap.jsx'

// The map on its own, in its own window.
//
// A dispatcher watching vehicles is not reading a dashboard - they have the map open on a
// second screen all day while they work the phone in the first. An overlay inside the
// application cannot do that: it dies the moment they navigate, and it cannot be dragged
// anywhere. A route can, so this is a route.
//
// Opened as a popup window - no tab strip, no bookmarks bar, nothing but the map - which
// means it has no browsing context to inherit from. The session token lives in
// sessionStorage, which is per context, so the dashboard hands it over in the URL fragment
// and App.jsx adopts it here. A window with no session would land on the login page, which
// is the kind of thing nobody notices until a demo.
export default function MapWindow() {
  const [where, error, reload] = useLoad(() => api.get('/company/map'), [])
  const [following, setFollowing] = useState(null)
  const [recentre, setRecentre] = useState(0)
  const [trouble, setTrouble] = useState(null)

  // Only while anything is moving, as on the dashboard: a window left open on a parked
  // fleet should not ask the server for the same answer all night.
  const moving = Boolean(where?.drivers?.length)
  useEffect(() => {
    if (!moving) return undefined
    const again = setInterval(() => reload(), 3000)
    return () => clearInterval(again)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moving])

  useEffect(() => { document.title = 'Current Driver Locations - TripProof' }, [])
  // On the main window's sign-in: renewed when it renews, closed when it signs out.
  useEffect(() => followMain(), [])

  return (
    <div className="mapwindow">
      <header>
        <h2>Current Driver Locations</h2>
        {where?.drivers?.length > 0 && (
          <select className="mapfollow" value={following || ''}
            onChange={(e) => setFollowing(e.target.value || null)}>
            <option value="">Follow nobody - show everything</option>
            {where.drivers.map((d) => (
              <option key={d.driverid} value={d.driverid}>Follow {d.name}</option>
            ))}
          </select>
        )}
        {/* Re-centring stops following, as on the dashboard: a follow left on would drag
            the view straight back off the base. */}
        <button type="button" className="mapfull"
          onClick={() => { setFollowing(null); setRecentre((n) => n + 1) }}>
          Re-Center On Base
        </button>
        {/* Closes the window it was opened in. A script may only close what a script
            opened, which is how this is always reached - but a tab somebody typed the
            address into will stay put, and that is the browser's rule rather than
            something to work around. */}
        <button type="button" className="iconbtn" aria-label="Close"
          onClick={() => window.close()}><X size={20} /></button>
      </header>
      {trouble && <p className="reqaside st-expired">{trouble}</p>}
      {!where ? <Loading error={error} /> : (
        <FleetMap base={where.base} drivers={where.drivers} style={where.style}
          onTrouble={setTrouble} follow={following} recentre={recentre} full />
      )}
    </div>
  )
}
