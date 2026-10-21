// Driver page - what more than one of its sections uses. Moved out of
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

// One license, and the copies of its two sides. The license has to exist before a copy can belong
// to it, so it is written first and the copies are filed against it.
export async function saveLicense(id, license, copies) {
  const body = { ...license, endorsements: (license.endorsements || []).join('') || null,
    issued: license.issued || null, originalissued: license.originalissued || null,
    expires: license.expires || null }
  const saved = await api.post(`/drivers/${id}/licenses`, body)
  // The id of the license just written. Falling back to finding it in the returned list keeps the
  // copies from being dropped if that ever stops being sent - filing the license and losing its
  // copy is a silent half-success, which is the worst kind.
  const recordid = saved.recordid
    || (saved.licenses || []).find((l) => l.number === body.number && l.state === body.state)?.recordid
  if (!recordid) throw new Error('The license was saved but its copy could not be filed against it')
  if (copies?.front || copies?.back) {
    const form = new FormData()
    if (copies.front) form.append('front', copies.front)
    if (copies.back) form.append('back', copies.back)
    await api.post(`/drivers/${id}/licenses/${recordid}/copy`, form)
  }
}

// What somebody needs to know about a driver this morning, in the order they need it: what is
// waiting on the office, what stops this driver going out, what is about to run out, and what has
// been happening. Everything here is read from the same engine the requirements list reads.
export function usePlaygroundHeight(ref, deps) {
  const [room, setRoom] = useState(null)
  useEffect(() => {
    const fit = () => {
      const box = ref.current
      const yard = box?.closest('main')
      if (!box || !yard) return
      const pad = parseFloat(getComputedStyle(yard).paddingBottom) || 0
      const top = box.getBoundingClientRect().top - yard.getBoundingClientRect().top
      setRoom(Math.max(300, Math.floor(yard.clientHeight - top - pad)))
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, deps)   // eslint-disable-line react-hooks/exhaustive-deps
  return room
}

// An accident as 49 CFR 390.15(b) and 382.303 ask about it. Every one of the three questions that
// decide whether a test was owed starts unanswered, because in the hour after an accident nobody
// knows whether a citation was issued, and recording that as "no" would be a lie that excuses a
// test.
export const BLANK_CRASH = { occurredon: '', location: '', fatalities: '', injuries: '',
                      injurytreatedaway: '', towaway: '', hazmatreleased: '', cited: '', atfault: '',
                      note: '' }

// And back again, keeping "nobody has said" distinct from "no".
const BACK = (v) => (v === null || v === undefined ? '' : v ? 'yes' : 'no')

// A date with the hour on it, because the testing windows are counted in hours.
export const when = (v) => new Date(String(v).replace(' ', 'T')).toLocaleString('en-US',
  { month: '2-digit', day: '2-digit', year: 'numeric', hour: 'numeric', minute: '2-digit' })

export const CRASH_STATE = {
  owed: ['A test was required', 'st-expired'],
  unknown: ['Not decided yet', 'st-ordered'],
  notrequired: ['No test required', 'st-inactive'],
  tested: ['Tested', 'st-active'],
  part: ['Partly tested', 'st-expiring'],
  excused: ['Not tested - reason on file', 'st-expiring'],
}

// One accident on this driver, as the form that writes it and the form that answers it later.
//
// These are the same form because they are the same record: an accident is written up in the hour
// it happens, when nobody yet knows whether a citation was issued, and the citation arrives days
// later. There was one copy of this inside post-accident testing and the register had none, which
// is how the register came to be a thing you could read and not a thing you could keep.
export const FROM_ROW = (x) => ({
  recordid: x.recordid,
  occurredon: String(x.occurredon).replace(' ', 'T').slice(0, 16),
  location: x.location || '', fatalities: x.fatalities ?? '', injuries: x.injuries ?? '',
  injurytreatedaway: BACK(x.injurytreatedaway), towaway: BACK(x.towaway),
  hazmatreleased: BACK(x.hazmatreleased), cited: BACK(x.cited), atfault: BACK(x.atfault),
  note: x.note || '',
})

export const unread = (s) => Boolean(s.record) && !s.record.norecord && s.record.reviewstate !== 'reviewed'
