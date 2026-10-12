import { useState } from 'react'
import DocumentViewer from '../components/DocumentViewer.jsx'
import { Link, useParams } from 'react-router-dom'
import { Eye, FileText, PauseCircle } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, datetime, money, through, tzDateTime } from '../lib/format.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'

export default function TripDetail() {
  const { id } = useParams()
  const [trip, error, reload] = useLoad(() => api.get(`/trips/${id}`), [id])
  const [phi, setPhi] = useState(null)
  const [viewing, setViewing] = useState(null)      // the credential whose file is being read
  if (!trip) return <Loading error={error} />
  const atRisk = trip.checks.some((c) => c.outcome !== 'pass')

  // Member identity is fetched only on request, and the server logs each reveal.
  const reveal = async () => setPhi(await api.get(`/trips/${id}/phi`))
  const setBilling = async (billingstatus) => { await api.patch(`/trips/${id}`, { billingstatus }); reload() }

  return (
    <div className="stack">
      <div className="pagehead">
        <div>
          <div className="small"><Link to="/trips">Trips</Link></div>
          <h1 className="row">Trip <span className="mono" style={{ fontSize: 20 }}>{trip.externalid}</span>
            {atRisk ? <Badge state="atrisk" /> : <Badge state="clean" />}</h1>
          <div className="muted">{date(trip.tripdate)} · {trip.brokername || 'Unknown broker'} · {trip.servicelevel || 'level not given'} · {money(trip.billedamount)} · {trip.billingstatus}</div>
        </div>
        <div className="row">
          {trip.billingstatus === 'unbilled' && atRisk && <button onClick={() => setBilling('held')}><PauseCircle size={14} /> Hold from billing</button>}
          {trip.billingstatus === 'held' && <button onClick={() => setBilling('unbilled')}>Release hold</button>}
          {!phi && <button onClick={reveal}><Eye size={14} /> Show member details</button>}
        </div>
      </div>

      {phi && (
        <div className="card">
          <h3>Member</h3>
          <div>{phi.member.membername || '-'} · ID {phi.member.memberid || '-'} {phi.member.memberdob ? `· DOB ${phi.member.memberdob}` : ''}</div>
          <div className="small muted">This view was recorded in the access log.</div>
        </div>
      )}

      {trip.legs.map((leg) => {
        const checks = trip.checks.filter((c) => c.legid === leg.recordid)
        const lp = phi?.legs?.[leg.recordid]
        return (
          <div className="card" key={leg.recordid}>
            <h2>Leg {leg.legnumber} · pickup {datetime(leg.pickupat)}</h2>
            <div className="row muted" style={{ marginBottom: 12 }}>
              <span>Driver: {leg.driverid ? <Link to={`/drivers/${leg.driverid}`}>{leg.drivername}</Link> : (leg.driverexternal || 'none')}</span>
              <span>· Vehicle: {leg.vehicleid ? <Link to={`/vehicles/${leg.vehicleid}`}>{leg.unit || 'vehicle'}{leg.modelyear ? ` (${leg.modelyear})` : ''}</Link> : (leg.vehicleexternal || 'none')}</span>
              <span>· Signature {leg.signature ? 'yes' : 'no'} · GPS {leg.gps ? 'yes' : 'no'}</span>
            </div>
            {lp && <div className="small muted" style={{ marginBottom: 12 }}>From {lp.pickupaddress || '-'} to {lp.dropoffaddress || '-'}</div>}
            <div className="tablewrap"><table>
              <thead><tr><th>Requirement</th><th>Rule set</th><th>Result</th><th>Evidence</th><th>Covered</th></tr></thead>
              <tbody>{checks.map((c) => (
                <tr key={c.code + c.family}>
                  <td>{c.description}<div className="small muted">{c.code}</div></td>
                  <td className="small">{c.family} v{c.version} {!c.verified && <Badge state="unverified" />}</td>
                  <td><Badge state={c.outcome} /></td>
                  <td className="small">
                    {c.outcome === 'pass' && c.credentialid ? (
                      <>#{c.number || '-'} · issued {date(c.issuedon)} · expires {c.expireson ? date(c.expireson) : 'none printed'}
                        {c.documentid && <> · <a href="#" onClick={(e) => { e.preventDefault(); setViewing(c) }}><FileText size={12} /> file</a></>}</>
                    ) : c.outcome === 'pass' ? 'Meets rule' : <span className="error">{c.reason}</span>}
                  </td>
                  <td className="small">{c.windowstart ? `${date(c.windowstart)} ${through(c.windowend)}` : '-'}</td>
                </tr>
              ))}</tbody>
            </table></div>
          </div>
        )
      })}
      {trip.run && <div className="small muted">Checked {tzDateTime(trip.run.finished)} by engine {trip.run.engineversion} ({trip.run.reason}). Run {trip.run.recordid}.</div>}
      {viewing && (
        <DocumentViewer id={viewing.documentid} name={viewing.filename || viewing.typename}
          onClose={() => setViewing(null)} />
      )}
    </div>
  )
}
