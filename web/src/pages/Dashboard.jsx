import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Building2, Car, Crosshair, Maximize2, User, X,
} from 'lucide-react'
import DataGrid from '../components/DataGrid.jsx'
import FleetMap from '../components/FleetMap.jsx'
import { api, auth } from '../lib/api.js'
import { rememberMap } from '../lib/session.js'
import SignedDocViewer from '../components/SignedDocViewer.jsx'
import { date } from '../lib/format.js'
import { Loading, Tile, useLoad } from '../components/ui.jsx'
import { useRefreshOnFocus, useWatch } from '../lib/live.js'

// The first page anybody opens, and the only one that answers a question without being asked: can
// we run today, and what do I go and do about it.
//
// One list of work, not three. The engine has already put it in the order somebody does it - what
// stops the business, then what is owed, then what runs out - and splitting that across three
// boards made a reader join it back up for themselves.
//
// The REASON is only printed where it says something. Five rows of "Nothing on file yet." down a
// column tell nobody anything: the status beside the row already says the file is empty, so the
// sentence earns its place only when it adds to that - when the thing is due, what lapsed, what
// came back.

const MARK = { company: Building2, driver: User, vehicle: Car }

// What the row's standing is, in a word, in the vocabulary the rest of the application uses.
// The same state colours the record tables use - red for a stop, amber for owed, grey for a date
// still out in front of somebody.
const SAYS = {
  stop: ['Stops work', 'st-expired'],
  owed: ['Outstanding', 'st-ordered'],
  soon: ['Running out', 'st-inactive'],
}

// What the engine says when a thing is simply absent. That is the status, not a reason, and
// printing both is saying one thing twice.
const BARE = 'Nothing on file yet.'

// Where a trip itself has got to, in the house state colours.
const TRIPSTATE = {
  Unassigned: 'st-expired',
  Upcoming: 'st-inactive',
  'In progress': 'st-ordered',
  Completed: 'st-active',
  Canceled: 'st-inactive',
}

export default function Dashboard() {
  const [arrivals, arrivalsError, reloadArrivals] = useLoad(() => api.get('/arrivals'), [])
  const [where, whereError, reloadWhere] = useLoad(() => api.get('/company/map'), [])
  // Typed, not dragged. Dragging was fiddly, could only be done while the pin was wrong, and
  // a map is a poor instrument for a position somebody already knows to four decimal places.
  const [placing, setPlacing] = useState(null)
  const [maptrouble, setMaptrouble] = useState(null)
  const [following, setFollowing] = useState(null)
  // What the panel map is looking at, so going full screen opens on the same view rather
  // than starting over.
  const mapview = useRef(null)
  const [recentre, setRecentre] = useState(0)
  // Ask again while anything is moving. Only while - a dashboard that polls all day for a
  // fleet that is parked is a dashboard that costs battery and bandwidth for nothing.
  const anyMoving = Boolean(where?.drivers?.length)
  useEffect(() => {
    if (!anyMoving) return undefined
    const again = setInterval(() => reloadWhere(), 3000)
    return () => clearInterval(again)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anyMoving])
  const [work, workError, reloadWork] = useLoad(() => api.get('/attention'), [])
  const [showing, setShowing] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const navigate = useNavigate()
  // Five to a page on the top row, so the two panels hold the same number of rows and stand the
  // same height whatever is in them.
  const PER = 5
  const [attnPage, setAttnPage] = useState(1)
  const [docsPage, setDocsPage] = useState(1)
  const [rosterPage, setRosterPage] = useState(1)
  const [fleetPage, setFleetPage] = useState(1)

  const reload = () => { reloadArrivals(); reloadWork() }
  useRefreshOnFocus(reload)
  useWatch(null, 'all', reload, { seconds: 20 })

  const open = async (item) => {
    setBusy(item.recordid); setErr(null)
    try {
      if (item.kind === 'signed' && item.detail) {
        setShowing(await api.get(`/drivers/${item.subjectid}/signed/${item.detail}`))
      }
      await api.post(`/arrivals/${item.recordid}/reviewed`, {})
      reload()
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  if (!arrivals || !work) return <Loading error={arrivalsError || workError} />
  const items = arrivals.items || []
  const roster = work.roster || []
  const fleet = work.fleet || []
  const stops = work.stops.length

  const rows = [
    ...work.stops.map((r) => ({ ...r, rank: 'stop' })),
    ...work.owed.map((r) => ({ ...r, rank: 'owed' })),
    ...work.soon.map((r) => ({ ...r, rank: 'soon' })),
  ]

  return (
    <div className="stack">
      <div className="pagehead"><h1>Dashboard</h1></div>
      {err && <div className="notice bad">{err}</div>}

      {/* Where everybody is. The base comes off the company's own address; the drivers come
          from the positions they have reported, so an empty map is an empty map rather than
          four pins on four home addresses pretending to be live tracking. */}
      <div className="card mappanel">
        <h3 className="maphead">
          <span>Current Driver Locations</span>
          {/* Following is a choice, not a mode the map decides: a dispatcher watching one
              vehicle should not lose it because another reported. In the head beside the
              other map control rather than on a row of its own under the figures. */}
          {where?.drivers?.length > 0 && (
            <select className="mapfollow" value={following || ''}
              onChange={(e) => setFollowing(e.target.value || null)}>
              <option value="">Follow nobody - show everything</option>
              {where.drivers.map((d) => (
                <option key={d.driverid} value={d.driverid}>Follow {d.name}</option>
              ))}
            </select>
          )}
          {/* Re-centring stops following. The two ask the map for opposite things - one for
              the base, one for a vehicle that is moving away from it - and a follow left on
              would drag the view straight back off the base, so the button would look
              broken. Asking for the base is a decision to watch the whole fleet again. */}
          <button type="button" className="mapfull"
            onClick={() => { setFollowing(null); setRecentre((n) => n + 1) }}>
            <Crosshair size={14} /> Re-Center On Base
          </button>
          {/* A window of its own rather than a tab: no tab strip, no bookmarks bar, nothing
              but the map. It is named, so pressing this again brings the one that is already
              open back to the front instead of opening a sixth.
              The session rides in the fragment because sessionStorage is per browsing
              context and a new window does not reliably inherit a copy - the same handover
              the admin portal's Launch uses. */}
          <button type="button" className="mapfull" onClick={() => {
            const w = Math.min(1600, window.screen.availWidth)
            const h = Math.min(1000, window.screen.availHeight)
            const left = Math.max(0, Math.round((window.screen.availWidth - w) / 2))
            const top = Math.max(0, Math.round((window.screen.availHeight - h) / 2))
            const map = window.open(`/map#token=${encodeURIComponent(auth.get() || '')}`,
              'tripproof-map',
              `popup=yes,width=${w},height=${h},left=${left},top=${top}`)
            rememberMap(map)
            map?.focus()
          }}>
            <Maximize2 size={14} /> Full screen
          </button>
        </h3>
        {maptrouble && <p className="reqaside st-expired">{maptrouble}</p>}
        {!where ? <Loading error={whereError} /> : (
          <>
            {(!where.drivers.length || where.base?.precision !== 'address') && (
              <p className="reqaside">
                {!where.drivers.length && 'No driver has reported a position yet. '}
                {/* Said plainly where the pin is not the building. OpenStreetMap does not
                    hold every US street, and a pin that looks exact when it is a postcode
                    centroid is worse than one that admits it. */}
                {where.base && where.base.precision !== 'address'
                  && `The base pin is approximate - placed by ${
                    where.base.precision === 'town' ? 'town' : 'postcode'}.`}
                {where.base && where.base.precision === 'address'
                  && "The pin is this company's base."}
              </p>
            )}
            {/* The three figures this panel is about, in the house tiles, above the map.
                No "en route" among them: nothing records a trip in progress yet, and a tile
                reading 0 because the feature does not exist is worse than no tile. */}
            <div className="grid cols-4 maptiles">
              <Tile className="fill-teal" label="Drivers" value={roster.length}
                sub={`${roster.filter((d) => d.eligible).length} eligible to drive`} />
              {/* Real now that trips exist: drivers whose latest position falls inside a
                  leg. Counted off the same answer the map is drawn from, so the figure and
                  the pins cannot disagree. */}
              <Tile className={where.enroute ? 'fill-teal' : 'fill-light'} label="En route"
                value={where.enroute}
                sub={where.enroute ? 'on a job now' : 'nobody is on a job'} />
              <Tile className="fill-light" label="Reporting" value={where.drivers.length}
                sub={where.drivers.length === 1 ? 'position received'
                  : `${where.drivers.length ? 'positions received' : 'no device reporting yet'}`} />
              {/* A driver pressing Alert Base in their app. Nothing sends that yet, so it is
                  zero - and honestly zero, not borrowed from the compliance stops, which are
                  a different thing entirely and already have their own panel. Orange is kept
                  for when one actually comes in. */}
              <Tile className="fill-orange" label="Alerts" value={0}
                sub="no driver has alerted base" />
            </div>
            <FleetMap base={where.base} drivers={where.drivers} style={where.style}
              onTrouble={setMaptrouble} follow={following} recentre={recentre}
              onView={(v) => { mapview.current = v }} />
            {/* Always offered, not only while the pin is wrong: a base set once by hand must
                still be correctable, and the first attempt at this could only be used once. */}
            <div className="formactions baserow">
              {placing === null ? (
                <button type="button" className="linkbtn edit"
                  onClick={() => setPlacing({
                    latitude: where.base ? String(where.base.lat) : '',
                    longitude: where.base ? String(where.base.lng) : '',
                  })}>
                  Set The Base Position
                </button>
              ) : (
                <>
                  <label className="field">Latitude
                    <input value={placing.latitude} inputMode="decimal"
                      onChange={(e) => setPlacing({ ...placing, latitude: e.target.value })} />
                  </label>
                  <label className="field">Longitude
                    <input value={placing.longitude} inputMode="decimal"
                      onChange={(e) => setPlacing({ ...placing, longitude: e.target.value })} />
                  </label>
                  <button type="button" className="primary right"
                    disabled={!Number.isFinite(Number(placing.latitude))
                      || !Number.isFinite(Number(placing.longitude))
                      || placing.latitude === '' || placing.longitude === ''}
                    onClick={async () => {
                      try {
                        await api.put('/company/map/base', {
                          latitude: Number(placing.latitude),
                          longitude: Number(placing.longitude),
                        })
                        setPlacing(null)
                        await reloadWhere()
                      } catch (e) { setErr(e.message) }
                    }}>Save</button>
                  <button type="button" onClick={() => setPlacing(null)}>Cancel</button>
                </>
              )}
            </div>
          </>
        )}
      </div>

      <div className="dashsplit">
        <div className="dashstack">
          {/* Who may drive, and who may not. The roster's own page says why in full; this says
              which of the two somebody is, which is the question a dispatcher asks first. */}
          <DataGrid className="dashgrid"
            columns={[
              { id: 'name', label: 'Driver List' },
              { id: 'able', label: 'Eligible', width: 110, className: 'statecell' },
              { id: 'why', label: 'Why', width: '38%' },
            ]}
            rows={roster.slice((rosterPage - 1) * PER, rosterPage * PER)}
            pager={{ total: roster.length, page: rosterPage, pagesize: PER, noun: 'drivers',
              small: true, onPage: setRosterPage }}
            rowKey={(d) => d.recordid}
            onRowClick={(d) => navigate(d.link)}
            empty="No drivers"
            cells={(d) => [
              <b>{d.name}</b>,
              <span className={d.eligible ? 'st-active' : 'st-expired'}>
                {d.eligible ? 'Eligible' : 'Not eligible'}
              </span>,
              <span className="muted">{d.why}</span>,
            ]} />

          <DataGrid className="dashgrid"
            columns={[
              { id: 'name', label: 'Vehicle List' },
              { id: 'able', label: 'Eligible', width: 110, className: 'statecell' },
              { id: 'why', label: 'Why', width: '38%' },
            ]}
            rows={fleet.slice((fleetPage - 1) * PER, fleetPage * PER)}
            pager={{ total: fleet.length, page: fleetPage, pagesize: PER, noun: 'vehicles',
              small: true, onPage: setFleetPage }}
            rowKey={(v) => v.recordid}
            onRowClick={(v) => navigate(v.link)}
            empty="No vehicles"
            cells={(v) => [
              <b>{v.name}</b>,
              <span className={v.eligible ? 'st-active' : 'st-expired'}>
                {v.eligible ? 'Eligible' : 'Not eligible'}
              </span>,
              <span className="muted">{v.why}</span>,
            ]} />
        </div>

        <div className="dashstack">
          <DataGrid className="dashgrid"
            columns={[
              { id: 'name', label: 'Items Requiring Attention' },
              { id: 'who', label: 'Who', width: '26%' },
              { id: 'says', label: 'Status', width: 120, className: 'statecell' },
            ]}
            rows={rows.slice((attnPage - 1) * PER, attnPage * PER)}
            pager={{ total: rows.length, page: attnPage, pagesize: PER, noun: 'items',
              small: true, onPage: setAttnPage }}
            rowKey={(r) => `${r.where}-${r.who || ''}-${r.code}`}
            onRowClick={(r) => navigate(r.link)}
            empty="Nothing outstanding"
            cells={(r) => {
              const Icon = MARK[r.where] || Building2
              return [
                <b>{r.name}</b>,
                <><Icon size={12} /> {r.who || 'The company'}</>,
                <span className={SAYS[r.rank][1]}>{SAYS[r.rank][0]}</span>,
              ]
            }} />

        <DataGrid className="dashgrid"
          columns={[
            { id: 'label', label: 'Documents to Review' },
            { id: 'arrived', label: 'Arrived', width: 120 },
            { id: 'act', label: '', width: 170, className: 'actcell' },
          ]}
          rows={items.slice((docsPage - 1) * PER, docsPage * PER)}
          pager={{ total: items.length, page: docsPage, pagesize: PER, noun: 'documents',
            small: true, onPage: setDocsPage }}
          rowKey={(x) => x.recordid}
          empty="Nothing to review"
          cells={(x) => [
            <b>{x.label || 'A document arrived'}</b>,
            date(x.arrivedon),
            <button type="button" className="primary" disabled={busy === x.recordid}
              onClick={() => open(x)}>Open and read</button>,
          ]} />
        </div>
      </div>

      {showing && <SignedDocViewer doc={showing} onClose={() => setShowing(null)} />}
    </div>
  )
}
