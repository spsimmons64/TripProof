import { useState } from 'react'
import { Loader2, MapPin, UserPlus, Wrench } from 'lucide-react'
import { api } from '../lib/api.js'
import { useLoad } from './ui.jsx'
import { tzDateTime } from '../lib/format.js'
import { Modal } from '../admin/common.jsx'

// The warning that something is open, wherever it is shown.
//
// It names the thing. "A driver has reported a problem" tells a dispatcher only that they must go
// and find out what it is; the fault, the driver, when they said it and whether anyone has picked
// up are what decide whether this is a tyre or a trip that needs covering - so they are on the
// strip, not behind a click.
//
// The dispatch board and the trip page are two views of one fact. Written out twice they drifted
// at once, so they say it in the same words, from here.
export function ProblemBanner({ issue, kinds, children }) {
  return (
    <div className="notice bad">
      <div>
        <b>{(kinds || {})[issue.kind] || issue.kind}</b>
        {issue.note ? ` - ${issue.note}` : ''}
        <div>
          {issue.drivername}, {tzDateTime(issue.raisedon)}
          {issue.acknowledgedon
            ? ` · seen ${tzDateTime(issue.acknowledgedon)}` : ' · not yet acknowledged'}
        </div>
      </div>
      {children}
    </div>
  )
}

// What the driver has said is wrong, and what the office is going to do about it.
//
// Read as facts rather than as a sentence: a dispatcher is looking for which driver, where, and
// how long ago, and a wrapped paragraph makes them hunt for each one.
//
// The three acts are kept apart because they are three different things. SEEING it answers the
// driver, who is standing somewhere wanting to know whether anyone picked up. DOING something -
// taking the van off the road, putting somebody else on the trip - changes the day's work and
// opens the screen that does it. SAYING WHAT WAS DONE closes the record, and is chosen from a
// list rather than typed, because a month of free text cannot answer how often a van came off
// the road, which is the question that decides whether to keep the van.
export default function IssueDialog({ issue, kinds, title, onOut, onReassign,
                                      onClose, onDone }) {
  // What has actually been done to this leg since it was reported, read from the record. The
  // list of ways to close the problem is built from it: "another driver took the trip" is
  // offered when another driver took the trip, and not before.
  const [was] = useLoad(() => api.get(`/issues/${issue.recordid}/changed`), [issue.recordid])
  const [kind, setKind] = useState('')
  const [resolution, setResolution] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const act = async (fn) => {
    setBusy(true); setErr(null)
    try {
      await fn()
      // The bell is on a minute's timer of its own, so without this it goes on showing a problem
      // that has just been dealt with until the timer comes round - and an alert that is still
      // lit after you have answered it is how people learn to stop believing alerts. The toast
      // and the bell already share this bus: whichever notices first tells the other.
      window.dispatchEvent(new CustomEvent('tripproof:arrived'))
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  const seen = () => act(async () => {
    await api.post(`/issues/${issue.recordid}/seen`, {}); onDone()
  })
  const close = () => act(async () => {
    await api.post(`/issues/${issue.recordid}/resolve`, { kind, resolution }); onDone()
  })
  const where = issue.latitude != null
    ? `${Number(issue.latitude).toFixed(5)}, ${Number(issue.longitude).toFixed(5)}` : null
  // "Something else" names nothing on its own, so it is the one answer that has to be written out.
  const ready = kind && (kind !== 'other' || resolution.trim())

  return (
    <Modal width={640} title={title || 'A Problem'} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Close</button>
        {!issue.acknowledgedon && (
          <button type="button" disabled={busy} onClick={seen}>Seen It</button>
        )}
        <button type="button" className="primary" disabled={busy || !ready} onClick={close}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Dealt With'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="kv">
          <dt>Problem</dt>
          <dd>{(kinds || {})[issue.kind] || issue.kind}</dd>
          {issue.note && <><dt>What They Said</dt><dd>{issue.note}</dd></>}
          <dt>Driver</dt>
          <dd>{issue.drivername || '-'}</dd>
          <dt>Reported</dt>
          <dd>{tzDateTime(issue.raisedon)}</dd>
          {where && <>
            <dt>Where</dt>
            <dd className="row">
              <span className="mono">{where}</span>
              <button type="button" onClick={() => window.open(
                `https://www.google.com/maps/search/?api=1&query=${issue.latitude},${issue.longitude}`,
                '_blank', 'noopener')}>
                <MapPin size={14} /> Open The Map
              </button>
            </dd>
          </>}
          <dt>Acknowledged</dt>
          <dd>{issue.acknowledgedon ? tzDateTime(issue.acknowledgedon) : 'Not yet'}</dd>
        </div>

        {/* The two that change the day's work, rather than only recording it. Each opens the
            screen that does the job - this dialog does not pretend to do it itself. */}
        <div className="row">
          {onOut && issue.vehiclename && (
            <button type="button" onClick={onOut}>
              <Wrench size={14} /> Take {issue.vehiclename} Off The Road
            </button>
          )}
          {onReassign && issue.legid && (
            <button type="button" onClick={onReassign}>
              <UserPlus size={14} /> Change The Driver Or Vehicle
            </button>
          )}
        </div>

        {/* Read, not asked. Where the record can answer, it says what it is answering from
            rather than offering somebody a line to claim instead. */}
        {was && Object.keys(was.changed).length > 0 && (
          <div className="kv">
            <dt>Already Done</dt>
            <dd>{Object.values(was.changed).join(' · ')}</dd>
          </div>
        )}

        <div className="profileform">
          <label className="field span-6">What Was Done About It
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Choose…</option>
              {Object.entries(was?.offer || {}).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field span-6">Note
            <textarea value={resolution} onChange={(e) => setResolution(e.target.value)} /></label>
        </div>
      </div>
    </Modal>
  )
}
