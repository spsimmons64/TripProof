import { useEffect, useRef } from 'react'
// MapLibre 6 is ESM-only and has no default export, so these come in by name.
// `Map` is aliased because the global of that name is used elsewhere in this file's
// neighbours and shadowing it here would be a trap for the next person.
import { Map as MapLibreMap, Marker, Popup, NavigationControl, LngLatBounds, setWorkerUrl }
  from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

// MapLibre parses tiles in a Web Worker whose URL it works out at runtime from its own
// module URL. A bundler cannot see that, so the file is never emitted and the browser asks
// for one that is not there - "Worker failed to load". vite.config.js copies it beside the
// bundle and this says where it went. Told explicitly rather than left to be guessed, and
// named .js because nginx serves .mjs as application/octet-stream, which no browser will
// run as a worker.
setWorkerUrl(`${import.meta.env.BASE_URL}assets/maplibre-gl-worker.js`)

// Where everybody is: the company's base, and each driver's last reported position.
//
// MapLibre GL JS, which is the renderer and carries no tiles of its own. What it draws is
// whatever style it is handed, and that is decided by the server:
//
//   * A MapTiler style URL, where a key is configured. Vector tiles, so the map stays sharp
//     at any zoom and the styling is ours to change.
//   * Otherwise the raster style below, built here from OpenStreetMap's own tiles. No key and
//     no account, so the dashboard has a working map before anybody signs up for anything.
//
// Both go through the same renderer, so adding the key changes how the map looks and nothing
// about how it works.
// How a pin is paced.
//
// A leg is drawn over the wall-clock time it actually took, so the pin's speed across the
// ground is the vehicle's real speed. That matters for more than looks: a pin that sits
// still for twenty-seven seconds and then darts reads as a vehicle accelerating hard, and
// somebody watching a zoomed-in map would swear the driver was speeding.
//
// Two things are measured per vehicle, because neither can be assumed:
//
//   journey pace - how much time passes between fixes, as the VEHICLE stamped them. This is
//     what a leg is worth. A dropped fix doubles it, and the leg is twice as long.
//   arrival pace - how often new positions reach this screen, in wall clock. This is the
//     budget: finish a leg about when the next one lands and the motion never stops.
//
// Live, the two are the same and a leg is drawn in real time at true speed. Replayed fast,
// arrival pace is the shorter of the two and everything is scaled down by one honest factor
// rather than some legs sprinting and others crawling.
const GLIDE = 3200              // until a vehicle has been seen twice and can be measured
const LEAD = 1.06               // finish a shade after the next fix is due, never before
// Nothing glides for less than this or more than this, however odd the gap.
const SHORTEST = 700
// High enough that a doubled leg is still drawn at the right speed rather than being cut
// short - cutting it short is exactly the thing that makes a driver look like he floored it.
// A leg longer than this is a break, and BROKEN below jumps it.
const LONGEST = 150000
// A gap this many times the usual means the vehicle was not being watched - it was off, or
// out of signal. That is a resumption, not a journey, so the pin goes straight there rather
// than sailing across the county in a straight line it never drove.
const BROKEN = 6

function stamp(value) {
  return Date.parse(`${String(value || '').replace(' ', 'T')}Z`)
}

const RASTER = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}

// A proper teardrop pin whose point sits on the coordinate, rather than a disc centred over
// it. Drawn as SVG so it stays sharp at any zoom and on any screen, and so the two kinds read
// apart at a glance: the base is a building, a driver is the heading arrow every map uses for
// something moving. The arrow turns to the reported heading where there is one.
const HOUSE = 'M17 10.4 L23.2 15.6 H21.4 V21.4 H12.6 V15.6 H10.8 Z'
const ARROW = 'M17 9.8 L22.3 21.6 L17 18.8 L11.7 21.6 Z'

// A van in side profile, facing the way it is going, with the driver's name under it. Read
// across a map far quicker than a disc: you can see at a glance which way somebody is headed
// and who it is, without hovering anything.
//
// It flips rather than rotates. A side-profile van turned to a bearing of 270 degrees is a
// van driving upside down; flipping it reads correctly at every heading, and the exact
// bearing is in the popup where a number belongs.
function van(name, heading = null) {
  const el = document.createElement('span')
  el.className = 'vanpin'
  const west = heading !== null && heading !== undefined
    && Number(heading) > 180 && Number(heading) < 360
  el.innerHTML = `
    <svg class="vanbody${west ? ' west' : ''}" width="46" height="24" viewBox="0 0 46 24"
         aria-hidden="true">
      <path d="M4 16 V9 C4 7.3 5.3 6 7 6 H25 L33 11 H40 C41.7 11 43 12.3 43 14 V16
               C43 17.1 42.1 18 41 18 H6 C4.9 18 4 17.1 4 16 Z"
            fill="#ffa52f" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/>
      <rect x="7.6" y="8.2" width="6.4" height="4.2" rx="1" fill="#fff" fill-opacity=".92"/>
      <rect x="16" y="8.2" width="6.4" height="4.2" rx="1" fill="#fff" fill-opacity=".92"/>
      <path d="M25.4 7.6 L31.4 11 H25.4 Z" fill="#fff" fill-opacity=".92"/>
      <circle cx="13" cy="18.2" r="3.4" fill="#16343b" stroke="#fff" stroke-width="1.2"/>
      <circle cx="35" cy="18.2" r="3.4" fill="#16343b" stroke="#fff" stroke-width="1.2"/>
    </svg>
    <span class="vanname"></span>`
  el.querySelector('.vanname').textContent = name || ''
  return el
}

function pin(colour, glyph, heading = null) {
  const el = document.createElement('span')
  el.className = 'mappin'
  const turn = heading === null || heading === undefined
    ? '' : ` transform="rotate(${Number(heading)} 17 16)"`
  el.innerHTML = `
    <svg width="32" height="42" viewBox="0 0 34 44" aria-hidden="true">
      <path d="M17 42.5 C17 42.5 2.5 25.8 2.5 16 A14.5 14.5 0 1 1 31.5 16 C31.5 25.8 17 42.5 17 42.5 Z"
            fill="${colour}" stroke="#fff" stroke-width="2.5" stroke-linejoin="round"/>
      <circle cx="17" cy="16" r="9.2" fill="#fff" fill-opacity=".94"/>
      <path d="${glyph}" fill="${colour}"${turn}/>
    </svg>`
  return el
}

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

function clock(value) {
  const t = String(value || '').replace('T', ' ')
  return t.slice(11, 19) || '-'
}

function ago(value) {
  const t = Date.parse(`${String(value).replace(' ', 'T')}Z`)
  if (Number.isNaN(t)) return ''
  const secs = Math.max(0, Math.round((Date.now() - t) / 1000))
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`
  return `${Math.round(secs / 3600)} h ago`
}

// Everything known about a vehicle, in the popup. A pin that only says a name is a pin you
// have to go somewhere else to understand, and the whole point of it is that you do not.
function details(d) {
  const mph = d.speed === null || d.speed === undefined ? null : Math.round(Number(d.speed))
  const dir = d.heading === null || d.heading === undefined
    ? null : COMPASS[Math.round(Number(d.heading) / 22.5) % 16]
  const lines = [
    // The job, first, because it is the thing somebody watching a van most wants to know.
    ...(d.trip ? [['Trip', `${d.trip}${d.leg ? ` · leg ${d.leg}` : ''}${d.service
      ? ` · ${d.service}` : ''}`]] : [['Trip', 'not on a job']]),
    ['Vehicle', d.vehicle ? `${d.vehicle}${d.make ? ` · ${d.make} ${d.model || ''}`.trimEnd()
      : ''}` : 'not identified'],
    ['State', d.standing ? 'Standing' : `Moving${dir ? ` ${dir}` : ''}`],
    ['Speed', mph === null ? '-' : `${mph} mph`],
    ['This run', `${d.miles} mi in ${d.minutes} min`],
    ['Average', d.avgmph ? `${d.avgmph} mph` : '-'],
    ['Started', clock(d.since)],
    ['Last fix', `${clock(d.recordedon)} · ${ago(d.recordedon)}`],
    ['Accuracy', d.accuracy ? `${d.accuracy} m` : '-'],
    ['Position', `${Number(d.latitude).toFixed(5)}, ${Number(d.longitude).toFixed(5)}`],
  ]
  return `<div class="pinpop"><b>${d.name}</b><dl>${lines
    .map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl></div>`
}

export default function FleetMap({ base, drivers = [], style = null, height = null,
                                   onTrouble = null, follow = null, full = false,
                                   view = null, onView = null, recentre = 0 }) {
  const box = useRef(null)
  const map = useRef(null)
  const pins = useRef([])
  // Driver markers are KEPT between updates, keyed by driver, and glided from where they are
  // to where they now are. Rebuilding them every few seconds makes a vehicle blink from place
  // to place instead of travelling, and throws away any popup open while watching it.
  //
  // Each entry holds the marker, the leg it is currently walking (from, to, when it started,
  // how long it has) and the bearing. A frame loop below moves them; the data effect only
  // ever sets a new destination.
  const moving = useRef(new Map())
  const frame = useRef(null)
  const fitted = useRef(false)
  // Who the map is keeping in view, read inside the frame loop. In a ref so changing it does
  // not tear down and rebuild the map.
  const chasing = useRef(follow)
  chasing.current = follow
  // Where this map is looking, reported out so another instance of it can start there.
  // Going full screen builds a second map - MapLibre binds a WebGL context to its container
  // and cannot be re-parented - and a second map that starts at its own default throws away
  // whatever the user had framed.
  const told = useRef(onView)
  told.current = onView
  // Read once, at construction. Deliberately not a dependency: it is a starting point, not
  // something the map should be dragged back to every time the caller re-renders.
  const opening = useRef(view)
  // Bumped by the caller to ask for the view back. A counter rather than a boolean, so
  // pressing the button twice works the second time.
  const recentred = useRef(recentre)
  // Held in a ref and never in the dependency list. A caller passing an inline arrow makes a
  // new function on every render, and an effect that rebuilds every pin whenever its callback
  // changes identity rebuilds them on every render.
  const trouble = useRef(onTrouble)
  trouble.current = onTrouble
  const fellback = useRef(false)

  useEffect(() => {
    if (!box.current || map.current) return undefined
    map.current = new MapLibreMap({
      container: box.current,
      style: style || RASTER,
      center: opening.current?.center || [-98.6, 39.8],
      zoom: opening.current?.zoom ?? 3,
      // Collapsed to the small round button, which expands when clicked. It cannot be taken
      // off altogether: OpenStreetMap's data is ODbL and its tile policy requires visible
      // credit, and MapTiler requires it on every plan. Compact is the least it allows.
      attributionControl: { compact: true },
    })
    map.current.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    // The wheel zooms in full screen, where there is no page behind the map for it to
    // scroll. In the dashboard panel it stays off, so moving down the page past the map
    // does not get swallowed by it.
    if (full) map.current.scrollZoom.enable()
    else map.current.scrollZoom.disable()
    // Opened where the caller said - so it must not then frame itself over the top.
    if (opening.current) fitted.current = true
    map.current.on('moveend', () => {
      const m2 = map.current
      if (!m2) return
      const mid = m2.getCenter()
      told.current?.({ center: [mid.lng, mid.lat], zoom: m2.getZoom() })
    })
    // Say what went wrong rather than leaving an empty frame, and where the vector style is
    // the thing that failed, drop to the raster tiles that need no key at all. A dashboard
    // with a plain map beats a dashboard with a blank rectangle.
    map.current.on('error', (e) => {
      const why = e?.error?.message || 'the map failed to load'
      if (!fellback.current && style) {
        fellback.current = true
        trouble.current?.(`${why} - showing the plain map instead.`)
        map.current?.setStyle(RASTER)
      } else if (!fellback.current) {
        trouble.current?.(why)
      }
    })
    const m = map.current

    // One loop for every pin, rather than a timer each. Eased so a vehicle looks like it is
    // driving - leaving and arriving gently - instead of sliding at a constant rate between
    // two points and stopping dead.
    const tick = (now) => {
      moving.current.forEach((held) => {
        if (!held.span) return
        const run = Math.min(1, (now - held.started) / held.span)
        const e = run < 0.5 ? 2 * run * run : 1 - ((-2 * run + 2) ** 2) / 2
        held.mark.setLngLat([
          held.from[0] + (held.to[0] - held.from[0]) * e,
          held.from[1] + (held.to[1] - held.from[1]) * e,
        ])
        if (run >= 1) held.span = 0
      })
      // Following happens here rather than when a fix arrives, so the map travels with the
      // pin instead of jumping to catch it up every few seconds.
      //
      // Not while the user is doing something, though. Re-centring sixty times a second
      // cancels whatever animation is in flight, which is why the zoom buttons appeared to
      // do nothing while following: each zoom was interrupted before it finished. Panning,
      // rotating and pinching were being fought the same way.
      const chased = chasing.current && moving.current.get(chasing.current)
      const busy = m.isZooming() || m.isRotating() || m.isMoving()
      if (chased && !busy) {
        const at = chased.mark.getLngLat()
        const mid = m.getCenter()
        // Eased toward the pin rather than locked to it: a map pinned exactly to a moving
        // marker shakes with every GPS wobble.
        m.setCenter([mid.lng + (at.lng - mid.lng) * 0.12,
                     mid.lat + (at.lat - mid.lat) * 0.12])
      }
      frame.current = requestAnimationFrame(tick)
    }
    frame.current = requestAnimationFrame(tick)

    return () => {
      if (frame.current) cancelAnimationFrame(frame.current)
      moving.current.clear()
      m.remove()
      map.current = null
    }
  }, [style, full])

  // Back to the yard. Not a reframe of everything - the one fixed thing on this map is where
  // the company operates from, and that is the reference somebody who has panned away wants.
  // The zoom is left where they put it; only the centre moves.
  useEffect(() => {
    const m = map.current
    if (!m || recentre === recentred.current) return
    recentred.current = recentre
    if (base) m.easeTo({ center: [base.lng, base.lat], duration: 600 })
  }, [recentre, base])

  useEffect(() => {
    const m = map.current
    if (!m) return
    // Only the fixed pins are redrawn. The driver pins are moved, below.
    pins.current.forEach((p) => p.remove())
    pins.current = []

    const bounds = new LngLatBounds()
    let placed = 0
    if (base) {
      pins.current.push(new Marker({ element: pin('#0f3a43', HOUSE), anchor: 'bottom' })
        .setLngLat([base.lng, base.lat])
        .setPopup(new Popup({ offset: 16 })
          .setHTML(`<b>${base.name}</b><br>${base.address}`))
        .addTo(m))
      bounds.extend([base.lng, base.lat]); placed += 1
    }
    drivers.forEach((d) => {
      const at = [Number(d.longitude), Number(d.latitude)]
      let held = moving.current.get(d.driverid)
      if (!held) {
        const mark = new Marker({ element: van(d.name, d.heading), anchor: 'center' })
          .setLngLat(at)
          .setPopup(new Popup({ offset: 16, maxWidth: '300px' }))
          .addTo(m)
        held = { mark, from: at, to: at, started: 0, span: 0,
                 reported: stamp(d.recordedon), arrived: performance.now(),
                 journey: null, arrival: null }
        moving.current.set(d.driverid, held)
      } else if (held.to[0] !== at[0] || held.to[1] !== at[1]) {
        const now = performance.now()
        const taken = stamp(d.recordedon)

        // What this leg is worth, as the vehicle stamped it.
        const leg = Number.isNaN(taken) || Number.isNaN(held.reported)
          ? null : Math.max(0, taken - held.reported)
        // How long it took to reach this screen.
        const wait = Math.max(0, now - held.arrived)
        held.reported = Number.isNaN(taken) ? held.reported : taken
        held.arrived = now

        // Both eased, so one late poll or one odd timestamp does not redefine normal.
        if (leg) held.journey = held.journey ? held.journey * 0.7 + leg * 0.3 : leg
        if (wait) held.arrival = held.arrival ? held.arrival * 0.7 + wait * 0.3 : wait

        // A new destination. It sets off from wherever it has got to, not from the last
        // reported point, so a fix arriving mid-glide does not snap the pin backwards.
        held.from = held.mark.getLngLat().toArray()
        held.to = at
        held.started = now

        // This leg's share of the usual, spent against the time the next fix is expected to
        // take. Live, that is the real duration of the leg and the pin moves at the real
        // speed; replayed, everything is scaled by the same factor.
        const share = leg && held.journey ? leg / held.journey : 1
        const budget = held.arrival || GLIDE
        if (share > BROKEN) {
          // Not a leg. The vehicle was off, or out of signal, and a straight line across
          // the gap is a road it never drove.
          held.mark.setLngLat(at)
          held.from = at
          held.span = 0
        } else {
          held.span = Math.min(LONGEST, Math.max(SHORTEST, budget * share * LEAD))
        }
      }
      // Turned to face the way it is travelling, and renamed if the roster changed, without
      // replacing the element - so the pin keeps its place in the DOM and any open popup
      // stays open.
      if (d.heading !== null && d.heading !== undefined) {
        const body = held.mark.getElement().querySelector('.vanbody')
        const west = Number(d.heading) > 180 && Number(d.heading) < 360
        body?.classList.toggle('west', west)
      }
      const tag = held.mark.getElement().querySelector('.vanname')
      if (tag && tag.textContent !== d.name) tag.textContent = d.name
      held.mark.getPopup()?.setHTML(details(d))
      bounds.extend(at); placed += 1
    })
    // Nothing is removed for being absent from one answer. A pin that vanishes because a
    // poll came back thin reads as "the vehicle is gone", which is never what happened -
    // the last known position is the honest thing to leave on the map.

    // Following reframes once, close in, and then the loop keeps up with it.
    if (follow) {
      const held = moving.current.get(follow)
      // Centre on them, but keep the zoom the user is at. Snapping to a fixed zoom every
      // time follow is switched on throws away whatever they had set up.
      if (held && !fitted.follow) m.easeTo({ center: held.mark.getLngLat() })
      fitted.follow = follow
      return
    }
    fitted.follow = null
    // Framed once. Re-framing on every update would wrench the view back every few seconds
    // and make it impossible to look anywhere else while a vehicle is moving.
    if (!fitted.current) {
      if (placed > 1) m.fitBounds(bounds, { padding: 60, maxZoom: 14, duration: 0 })
      else if (placed === 1) m.jumpTo({ center: bounds.getCenter(), zoom: 12 })
      // Nothing placed at all - the whole country, rather than a blank square in the Atlantic
      // where latitude zero and longitude zero meet.
      else m.jumpTo({ center: [-98.6, 39.8], zoom: 3 })
      fitted.current = placed > 0
    }
    m.resize()
  }, [base, drivers, follow])

  // Height from the stylesheet unless a caller insists, so it can scale with the window
  // rather than being a fixed number buried in a component.
  return (
    <div ref={box} className={`fleetmap${full ? ' fullmap' : ''}`}
      style={height ? { height } : undefined} />
  )
}
