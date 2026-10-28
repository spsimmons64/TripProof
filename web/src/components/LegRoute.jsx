import { useEffect, useRef } from 'react'
import { Map as MapLibreMap, Marker, NavigationControl, LngLatBounds } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { RASTER } from './FleetMap.jsx'

// One leg as it was driven: the driver's reported positions drawn as a line, from setting off to
// the end of the trip, with the pickup in green and the drop-off in red. A leg not driven yet
// shows only those two pins. Same map style as the dashboard (FleetMap), so it looks the same.
export default function LegRoute({ route, style }) {
  const box = useRef(null)
  useEffect(() => {
    if (!box.current) return undefined
    const map = new MapLibreMap({ container: box.current, style: style || RASTER, center: [-98.6, 39.8], zoom: 3,
                                  attributionControl: { compact: true } })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    const spots = [...route.points, route.pickup, route.dropoff].filter(Boolean)
    map.on('load', () => {
      if (route.points.length > 1) {
        map.addSource('driven', { type: 'geojson',
          data: { type: 'Feature', geometry: { type: 'LineString', coordinates: route.points } } })
        map.addLayer({ id: 'driven-edge', type: 'line', source: 'driven',
          layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 8 } })
        map.addLayer({ id: 'driven', type: 'line', source: 'driven',
          layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#1c6979', 'line-width': 5 } })
      }
      if (spots.length) {
        const bounds = spots.reduce((b, p) => b.extend(p), new LngLatBounds(spots[0], spots[0]))
        map.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 0 })
      }
    })
    if (route.pickup) new Marker({ color: '#1d7a4c' }).setLngLat(route.pickup).addTo(map)
    if (route.dropoff) new Marker({ color: '#b42318' }).setLngLat(route.dropoff).addTo(map)
    return () => map.remove()
  }, [route, style])
  return (
    <div className="legroute">
      <div ref={box} className="legroutemap" />
      <div className="legroutekey">
        <span><i className="keypin keypick" /> Pickup</span>
        <span><i className="keypin keydrop" /> Drop-off</span>
        {route.points.length > 1 ? <span><i className="keyline" /> Route driven</span>
          : <span className="muted">{route.driven ? 'No GPS positions were reported on this leg.' : 'Not driven yet.'}</span>}
      </div>
    </div>
  )
}
