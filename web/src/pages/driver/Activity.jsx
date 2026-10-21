// Driver page - Activity. Moved out of
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
import { usePlaygroundHeight, when } from './common.jsx'

// Whose act each line was. The kind of person comes before the name, because "the driver did this"
// and "we did this" are read differently and a name alone does not say which.
const ACTOR = {
  driver: ['Driver', 'actdriver'],
  office: ['Office', 'actoffice'],
  outside: ['Outside', 'actoutside'],
}

// A driver's history only grows, so it is paged rather than left to run off the bottom of a very
// long page: the card fills the playground, the rows scroll inside it, and the pager stays put.
export function DriverActivity({ id }) {
  const [data, error] = useLoad(() => api.get(`/drivers/${id}/application/activity`), [id])
  // One-based, as the grids are - this uses the same Pager every grid in the application uses.
  const [page, setPage] = useState(1)
  const [pagesize, setPagesize] = useState(PAGE_SIZES[0])
  // Measured, not guessed. How much furniture sits above this list depends on the driver's name
  // wrapping, the banner, the tabs - so the band takes whatever is left between where it starts
  // and the bottom of the window, and the page itself never needs to scroll.
  const card = useRef(null)
  const room = usePlaygroundHeight(card, [id, data])

  if (!data) return <div className="card qualcard"><h3>Driver Activity</h3><Loading error={error} /></div>
  // Every stamp the same width, so the column beside it starts in the same place on every row:
  // 10/03/2026 01:01 PM, not 10/3/2026 1:01 PM.
  const when = (at) => {
    const d = new Date(String(at).replace(' ', 'T'))
    return [d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' }),
      d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })]
  }
  const total = data.events.length
  const pages = Math.max(1, Math.ceil(total / pagesize))
  const from = (Math.min(page, pages) - 1) * pagesize
  const shown = data.events.slice(from, from + pagesize)

  return (
    <div className="card qualcard activitycard" ref={card}
      style={room ? { height: room } : undefined}>
      <h3>Driver Activity</h3>
      {!total && <div className="muted" style={{ padding: '14px 20px' }}>
        Nothing has happened yet.
      </div>}
      <ol className="activityfeed">
        {shown.map((e, i) => {
          const [label, tone] = ACTOR[e.actor] || ACTOR.office
          const [day, time] = when(e.at)
          return (
            <li key={i} className={tone}>
              <div className="actwhen">{day} {time}</div>
              <span className={`actmark ${tone}`}>{label}</span>
              <div className="actbody">
                {/* The whole line, with the person in it. A column of names underneath made the
                    reader join two things up for themselves on every row. */}
                <div className="actwhat">{e.what}</div>

              </div>
            </li>
          )
        })}
      </ol>
      <Pager total={total} page={Math.min(page, pages)} pagesize={pagesize}
        onPage={setPage} onPageSize={(n) => { setPagesize(n); setPage(1) }} noun="entries" />
    </div>
  )
}
