// Driver page - Licenses. Moved out of
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
import { saveLicense, unread } from './common.jsx'

export function DriverLicenses({ id, onChanged, bare, adding: addingFrom, onAdding,
                         pending = new Set(), onReviewed }) {
  const [data, error, reload] = useLoad(() => api.get(`/drivers/${id}/licenses`), [id])
  const [addingOwn, setAddingOwn] = useState(false)
  const adding = addingFrom === undefined ? addingOwn : addingFrom
  const setAdding = onAdding || setAddingOwn
  // The license open in its own dialog, the copy open in the viewer, and the copy being uploaded.
  const [openId, setOpenId] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [copying, setCopying] = useState(false)
  const [sides, setSides] = useState({ front: null, back: null })
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const act = async (fn, key) => {
    setBusy(key); setErr(null)
    try { await fn(); reload(); onChanged?.() } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }

  const head = bare ? null : (
    <div className="infotabs">
      <h3>Licenses Held</h3>
      <div className="row panelactions">
        <button type="button" onClick={() => setAdding(true)}><Plus size={13} /> Add</button>
      </div>
    </div>
  )
  const panel = (children) => (bare
    ? <div className="stack">{head}{children}</div>
    : <div className="card qualcard">{head}<div className="infoform stack">{children}</div></div>)
  if (!data) return panel(<Loading error={error} />)
  const unread = (l) => Boolean(l.copydocumentid) && (pending.has(l.copydocumentid) || l.needsreading)
  const expiredOn = (l) => l.expires && new Date(`${l.expires}T00:00:00`) < new Date()
  // Expired outranks active: a license past its date is expired whatever the file says it is being
  // driven on, and that is the fact somebody needs to see.
  const standing = (l) => (expiredOn(l) ? ['st-expired', 'Expired']
    : l.active ? ['st-active', 'Active'] : ['st-inactive', 'Inactive'])
  const open = data.licenses.find((l) => l.recordid === openId)
  return panel(
    <>
      {err && !open && <div className="notice bad">{err}</div>}
      <table className="residencetable driverlicensetable">
        <thead><tr><th>License</th><th>Class</th><th>Endorsements</th><th>Valid</th><th>Status</th>
          <th /></tr></thead>
        <tbody>
          {data.licenses.map((l) => {
            const [cls, word] = standing(l)
            return (
            <tr key={l.recordid}>
              <td className="licensenumber">{[l.state, l.number].filter(Boolean).join(' ')}</td>
              <td>{l.classification || '-'}</td>
              {/* Stored as the letters run together, read as separate endorsements. */}
              <td>{(l.endorsements || '').split('').filter(Boolean).join(' · ') || '-'}</td>
              <td>
                {l.issued || l.expires
                  ? `${l.issued ? date(l.issued) : '?'} - ${l.expires ? date(l.expires) : '?'}`
                  : '-'}
              </td>
              <td className={cls}>{word}</td>
              <td className="actions">
                <button type="button" className={`linkbtn edit${unread(l) ? ' toread' : ''}`}
                  onClick={() => { setErr(null); setOpenId(l.recordid) }}>
                  {unread(l) ? 'Review' : 'View'}
                </button>
              </td>
            </tr>
            )
          })}
          {!data.licenses.length && <tr><td colSpan={6}>No licenses on file.</td></tr>}
        </tbody>
      </table>
      {open && (
        <Modal title="Driver's License" onClose={() => setOpenId(null)} width={620}
          footer={<>
            {open.copydocumentid ? (
              <button type="button" onClick={() => setViewing({ documentid: open.copydocumentid,
                filename: "Copy Of Driver's License" })}>
                <Eye size={14} /> View Copy
              </button>
            ) : (
              <button type="button" onClick={() => { setSides({ front: null, back: null }); setCopying(true) }}>
                <Plus size={13} /> Upload Copy
              </button>
            )}
            {/* Read it here, and say so here. A copy that came down an upload link is read
                against that request; any other copy against the license record itself. */}
            {unread(open) && (
              <button type="button" disabled={busy === 'review'}
                onClick={() => act(async () => {
                  if (pending.has(open.copydocumentid) && onReviewed) {
                    await onReviewed(open.copydocumentid)
                  } else {
                    await api.post(`/drivers/${id}/evidence/read`, {
                      sourcetable: 'driverlicenses', sourceid: open.recordid,
                      code: 'DRIVER_LICENSE_COPY',
                    })
                  }
                }, 'review')}>
                {busy === 'review' ? <Loader2 size={15} className="spin" /> : 'Mark As Reviewed'}
              </button>
            )}
            {!open.active && (
              <button type="button" disabled={busy === open.recordid}
                onClick={() => act(() => api.post(`/drivers/${id}/licenses/${open.recordid}/active`, {}),
                  open.recordid)}>
                {busy === open.recordid ? <Loader2 size={15} className="spin" /> : 'Make Active'}
              </button>
            )}
            <button type="button" onClick={() => setOpenId(null)}>Close</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <dl className="askfacts">
              <div><dt>License number</dt><dd>{open.number || '-'}</dd></div>
              <div><dt>State</dt><dd>{STATE_NAMES[open.state] || open.state || '-'}</dd></div>
              <div><dt>Class</dt><dd>{open.classification || '-'}</dd></div>
              <div><dt>Endorsements</dt>
                <dd>{(open.endorsements || '').split('').filter(Boolean).join(' · ') || '-'}</dd></div>
              <div><dt>Issued</dt><dd>{open.issued ? date(open.issued) : '-'}</dd></div>
              {open.originalissued && (
                <div><dt>Original issue</dt><dd>{date(open.originalissued)}</dd></div>
              )}
              <div><dt>Expires</dt><dd>{open.expires ? date(open.expires) : '-'}</dd></div>
              <div><dt>Status</dt><dd className={standing(open)[0]}>{standing(open)[1]}</dd></div>
              <div><dt>Copy</dt>
                <dd>{!open.copydocumentid ? 'Not on file' : unread(open) ? 'Not reviewed' : 'On file'}</dd></div>
              {open.note && <div><dt>Note</dt><dd>{open.note}</dd></div>}
            </dl>
          </div>
        </Modal>
      )}
      {viewing && <DocumentViewer id={viewing.documentid} name={viewing.filename}
        onClose={() => setViewing(null)} />}
      {copying && open && (
        <Modal title="Upload Copy Of Driver's License" onClose={() => setCopying(false)} width={620}
          footer={<>
            <button type="button" className="primary"
              disabled={busy === 'copy' || (!sides.front && !sides.back)}
              onClick={() => act(async () => {
                const form = new FormData()
                if (sides.front) form.append('front', sides.front)
                if (sides.back) form.append('back', sides.back)
                await api.post(`/drivers/${id}/licenses/${open.recordid}/copy`, form)
                setCopying(false)
              }, 'copy')}>
              {busy === 'copy' ? <Loader2 size={15} className="spin" /> : 'Save'}
            </button>
            <button type="button" onClick={() => setCopying(false)}>Cancel</button>
          </>}>
          <div className="stack">
            {err && <div className="notice bad">{err}</div>}
            <div className="profileform">
              <label className="field span-3">Front Of The License
                <input type="file" accept="image/*,application/pdf"
                  onChange={(e) => setSides({ ...sides, front: e.target.files[0] || null })} />
              </label>
              <label className="field span-3">Back Of The License
                <input type="file" accept="image/*,application/pdf"
                  onChange={(e) => setSides({ ...sides, back: e.target.files[0] || null })} />
              </label>
            </div>
          </div>
        </Modal>
      )}
      {adding && (
        <LicenseDialog copies onClose={() => setAdding(false)}
          onAdd={(license, copies) => act(async () => {
            await saveLicense(id, license, copies)
            setAdding(false)
          }, 'new')} />
      )}
    </>
  )
}
