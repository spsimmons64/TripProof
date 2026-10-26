// Requirement dialogs - what more than one of its parts uses. Moved out of
// Requirements.jsx, which had grown too large to work in safely.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Ban, Car, Check, ChevronLeft, Download, FlaskConical, LayoutDashboard, ChevronRight, Clock, ExternalLink, Eye, FileSignature, FileText, FileUp, FolderOpen, History, IdCard, ListChecks, Loader2, MoreHorizontal, Plus, X, Send, UserCheck, UserX } from 'lucide-react'
import { STATE_NAMES } from '../../../lib/states.js'
import { api } from '../../../lib/api.js'
import { useRefreshOnFocus, useWatch } from '../../../lib/live.js'
import { date } from '../../../lib/format.js'
import { Bubble, Loading, useLoad } from '../../../components/ui.jsx'
import { Modal } from '../../../admin/common.jsx'
import Pager, { PAGE_SIZES } from '../../../components/Pager.jsx'
import { useUser } from '../../../App.jsx'
import SignatureBlock from '../../../components/UserSignature.jsx'
import { ItemPanel, PanelsDialog, ReadingViewer, SingleDocumentDialog, docStanding } from '../../../components/RequirementDialogs.jsx'
import DocumentViewer, { DocumentPane } from '../../../components/DocumentViewer.jsx'
import ApplicantForm from '../../../components/ApplicantForm.jsx'
import SignedDocViewer from '../../../components/SignedDocViewer.jsx'
import { PhoneInput } from '../../../components/MaskedInput.jsx'
import LicenseDialog from '../../../components/LicenseDialog.jsx'
import TestDialog from '../../../components/TestDialog.jsx'
import WithdrawDialog, { WithdrawnDialog } from '../../../components/WithdrawDialog.jsx'
import { Email, Phone } from '../../../components/Contact.jsx'
import { BLANK_CRASH, CRASH_STATE, FROM_ROW, unread, when } from '../common.jsx'
import { DriverLicenses } from '../Licenses.jsx'
import { ProhibitionPanel } from '../Testing.jsx'
import { CrashDialog } from '../Accidents.jsx'

// Where a screening came from. Only the first two are the authority itself.
export const PROVENANCE = { fdle: 'FDLE', ahca: 'AHCA Clearinghouse', vendor: 'Screening vendor' }

export const SCREEN_RESULTS = { negative: 'Negative', negativedilute: 'Negative-Dilute', positive: 'Positive',
  refusal: 'Refusal', cancelled: 'Canceled' }

// How wide a requirement reads. One number, because a dialog whose width changes with whichever
// requirement opened it looks like a mistake.
//
// 900 is measured rather than chosen: it is the narrowest the dialog goes with nothing wrapping -
// every cell on the widest row (a date, a provider, a date AND a tester's name, a state, a
// button) on one line, and all three footer actions on one line including "Add passenger
// assistance and wheelchair securement training", which is the longest label any of these
// dialogs produce. It was 1180 while the columns were badly sized; once they took the width
// they actually need, most of that was empty.
export const DETAIL = 900

// What reading one driving record concludes - kept apart from the annual review's finding.
export const MVR_FINDING = {
  qualified: 'Qualified',
  restricted: 'Restricted',
  disqualified: 'Disqualified',
}

export const BLANK_EXAM = (today) => ({
  examtype: 'biennial', examinedon: today, result: 'meets', qualifiedthrough: '',
  examinername: '', examinerlicense: '', examinerstate: '', examinertype: '',
  correctivelenses: false, hearingaid: false, otherrestriction: '',
  tempreason: '', followupon: '', file: null,
})

// How one filed record stands, in its own column and its own colour - never a badge inside a cell.
// A determination that went against the driver outranks any date: a positive test does not become
// current again because the paperwork is recent.
const ADVERSE = ['positive', 'refusal', 'flagged', 'failed', 'notqualified', 'disqualified']

const LOOKING = ['review', 'potential', 'pending']

// "Medical Certificate" becomes "Medical Certificates". A name already plural is left alone, so
// "Motor Vehicle Records" does not grow a second s.
export const plural = (name) => (/s$/i.test(name || '') ? name : `${name}s`)

// When a record is good from and through. Two dates saying one thing, so one column says it.
export const valid = (rec) => {
  const from = rec.effectiveon ? date(rec.effectiveon) : null
  const to = rec.expireson ? date(rec.expireson) : null
  if (from && to) return `${from} through ${to}`
  if (from) return `From ${from}`
  return to ? `Through ${to}` : '-'
}

export const standingOf = (rec, results) => {
  const said = (rec.determination || '').toLowerCase()
  const label = (results.find(([v]) => v === rec.determination) || [])[1] || rec.determination
  if (ADVERSE.includes(said)) return [label, 'st-expired']
  if (LOOKING.includes(said)) return [label, 'st-ordered']
  const band = expiry(rec.expireson)
  if (band === 'st-expired') return ['Expired', 'st-expired']
  if (band === 'st-expiring') return ['Expiring', 'st-expiring']
  return [label || 'Active', 'st-active']
}

// Room, running out, gone: green beyond a month, gold inside one, red once the date has passed.
const EXPIRY_WARN_DAYS = 30

export const expiry = (on) => {
  if (!on) return undefined
  const midnight = new Date()
  midnight.setHours(0, 0, 0, 0)
  const days = Math.round((new Date(`${String(on).slice(0, 10)}T00:00:00`) - midnight) / 86400000)
  return days < 0 ? 'st-expired' : days <= EXPIRY_WARN_DAYS ? 'st-expiring' : 'st-active'
}
