// Driver page - Accidents. Moved out of
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
import { BLANK_CRASH, CRASH_STATE, FROM_ROW, usePlaygroundHeight, when } from './common.jsx'

// yes / no / nobody has said, as the server stores it.
const TRI = (v) => (v === 'yes' ? 1 : v === 'no' ? 0 : null)

export function CrashDialog({ id, initial, onSaved, onClose }) {
  const [crash, setCrash] = useState(initial || BLANK_CRASH)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      if (!crash.occurredon) throw new Error('Say when the accident happened')
      const body = {
        occurredon: crash.occurredon,
        location: crash.location.toUpperCase() || null,
        fatalities: crash.fatalities === '' ? null : Number(crash.fatalities),
        injuries: crash.injuries === '' ? null : Number(crash.injuries),
        injurytreatedaway: TRI(crash.injurytreatedaway),
        towaway: TRI(crash.towaway),
        hazmatreleased: TRI(crash.hazmatreleased),
        cited: TRI(crash.cited),
        atfault: TRI(crash.atfault),
        note: crash.note.toUpperCase() || null,
      }
      if (crash.recordid) await api.post(`/drivers/${id}/accidents/${crash.recordid}`, body)
      else await api.post(`/drivers/${id}/accidents`, body)
      await onSaved?.()
      onClose()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const ask = (k, label) => (
    <label className="field span-3">{label}
      <select value={crash[k]} onChange={(e) => setCrash({ ...crash, [k]: e.target.value })}>
        <option value="">Nobody has said</option>
        <option value="yes">Yes</option>
        <option value="no">No</option>
      </select>
    </label>
  )

  return (
    <Modal title={crash.recordid ? 'Accident' : 'Record An Accident'} onClose={onClose} width={720}
      footer={<>
        <button type="button" className="primary" disabled={busy} onClick={save}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
        <button type="button" onClick={onClose}>Cancel</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          {/* The hour, not just the day: the 8 and 32 hour windows run from it. */}
          <label className="field span-2">When *
            <input type="datetime-local" value={crash.occurredon}
              disabled={Boolean(crash.recordid)}
              onChange={(e) => setCrash({ ...crash, occurredon: e.target.value })} />
          </label>
          <label className="field span-2">Fatalities
            <input type="number" min="0" value={crash.fatalities}
              onChange={(e) => setCrash({ ...crash, fatalities: e.target.value })} />
          </label>
          <label className="field span-2">Injuries
            <input type="number" min="0" value={crash.injuries}
              onChange={(e) => setCrash({ ...crash, injuries: e.target.value })} />
          </label>
          <label className="field span-6">Where
            <input value={crash.location} className="upper"
              onChange={(e) => setCrash({ ...crash, location: e.target.value.toUpperCase() })} />
          </label>
          {ask('injurytreatedaway', 'Anybody treated away from the scene?')}
          {ask('towaway', 'Any vehicle towed from the scene?')}
          {ask('cited', 'Was this driver cited?')}
          {ask('atfault', 'Was this driver at fault?')}
          {/* 390.15(b)(2) names this one outright, and fuel from the vehicle's own tank is not
              it. The register was storing the column and no form ever asked the question. */}
          {ask('hazmatreleased', 'Hazardous materials released?')}
          <label className="field span-6">Note
            <textarea rows={3} value={crash.note} className="upper"
              onChange={(e) => setCrash({ ...crash, note: e.target.value.toUpperCase() })} />
          </label>
        </div>
      </div>
    </Modal>
  )
}

// Every accident this driver has had here - 49 CFR 390.15(b).
//
// The register and post-accident testing are the same events seen twice, and until now only the
// testing view existed: accidents could be written up from inside the drug and alcohol
// requirement and read back nowhere else. 390.15(b) is addressed to the carrier and asks it to
// KEEP the register, which is a list, not an answer to a question about one rule.
export function AccidentHistory({ id, onChanged }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/accidents`), [id])
  const [page, setPage] = useState(1)
  const [pagesize, setPagesize] = useState(PAGE_SIZES[0])
  const [editing, setEditing] = useState(null)
  const [pulling, setPulling] = useState(null)
  const [undone, setUndone] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const card = useRef(null)
  const room = usePlaygroundHeight(card, [id, data])

  if (!data) {
    return <div className="card qualcard"><h3>Accident History</h3><Loading error={error} /></div>
  }
  const crashes = data.accidents || []
  const pages = Math.max(1, Math.ceil(crashes.length / pagesize))
  const at = Math.min(page, pages)
  const shown = crashes.slice((at - 1) * pagesize, at * pagesize)
  const num = (v) => (v === null || v === undefined ? '-' : String(v))

  return (
    <>
      <div className="card qualcard activitycard" ref={card}
        style={room ? { height: room } : undefined}>
        <h3 className="withact">
          <span>Accident History</span>
          <button type="button" onClick={() => setEditing(BLANK_CRASH)}>
            <Plus size={13} /> Record An Accident
          </button>
        </h3>
        <div className="hireband">
          {!crashes.length ? <div className="hireempty">No accidents recorded</div> : (
            <table className="residencetable recordtable">
              <thead><tr><th>When</th><th className="growcol">Where</th>
                <th>Fatalities</th><th>Injuries</th><th>Hazmat</th><th>382.303</th><th /></tr></thead>
              <tbody>
                {shown.map((x) => {
                  const [says, tone] = CRASH_STATE[x.state] || [x.state, 'st-inactive']
                  return (
                    <tr key={x.recordid}>
                      <td>{x.occurredon ? when(x.occurredon) : '-'}</td>
                      <td className="growcol">{x.location || '-'}</td>
                      <td>{num(x.fatalities)}</td>
                      <td>{num(x.injuries)}</td>
                      <td>{x.hazmatreleased === null || x.hazmatreleased === undefined
                        ? '-' : x.hazmatreleased ? 'Yes' : 'No'}</td>
                      <td className={tone}>{says}</td>
                      <td className="actions">
                        <button type="button" className="linkbtn edit"
                          onClick={() => setEditing(FROM_ROW(x))}>
                          {x.state === 'unknown' ? 'Answer' : 'Open'}
                        </button>
                        {/* An accident against the wrong name does not sit there looking wrong:
                            382.303 reads it and may decide the driver owes a post-accident
                            test, which then holds up their file. */}
                        <button type="button" className="linkbtn edit"
                          onClick={() => setPulling(x)}>Withdraw</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
        <Pager total={crashes.length} page={at} pagesize={pagesize} noun="accidents"
          onPage={setPage} onPageSize={(n) => { setPagesize(n); setPage(1) }} />
      </div>
      {editing && (
        <CrashDialog id={id} initial={editing} onClose={() => setEditing(null)}
          onSaved={async () => { await reload(); onChanged?.() }} />
      )}
      {pulling && (
        <WithdrawDialog title="Withdraw This Accident" busy={busy} err={err}
          what={`The accident of ${pulling.occurredon ? when(pulling.occurredon) : 'no date'}`
            + `${pulling.location ? ` at ${pulling.location}` : ''} will be withdrawn.`}
          warn="It comes off this driver's record and off the company's accident register."
          onClose={() => setPulling(null)}
          onConfirm={(reason) => {
            setBusy(true); setErr(null)
            api.post(`/drivers/${id}/accidents/${pulling.recordid}/withdraw`, { reason })
              .then((out) => { setPulling(null); setUndone(out); reload(); onChanged?.() })
              .catch((e) => setErr(e.message)).finally(() => setBusy(false))
          }} />
      )}
      {undone && (
        <WithdrawnDialog undone={undone.undone} onClose={() => setUndone(null)} />
      )}
    </>
  )
}
