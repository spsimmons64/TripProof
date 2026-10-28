import { useEffect, useRef, useState } from 'react'
import { Building2, ExternalLink, FileText, Loader2, ShieldCheck, Unplug, Users } from 'lucide-react'
import { api } from '../lib/api.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'

// A company's own account with backgroundchecks.com.
//
// Not ours, and that is the whole point of the screen. Under the FCRA the party obtaining a
// consumer report for employment purposes must be the party evaluating the consumer for
// employment, and that is the transport company deciding whether to hire the driver - never the
// software it decides with. So the company signs up for itself, its name appears on the
// disclosure the driver signs, and backgroundchecks.com bills it directly. TripProof holds the
// key and takes no cut.
//
// Everything below the sign-up state is read live from the vendor with the COMPANY'S key. None of
// it is copied into this database, because a price list or an invoice kept in two places is one
// that eventually disagrees with itself.

const money = (cents) => `$${((cents || 0) / 100).toFixed(2)}`

// Their dates arrive as {date, timezone_type, timezone} rather than a plain string.
const theirDate = (v) => {
  const raw = typeof v === 'string' ? v : v?.date
  if (!raw) return '-'
  const [y, m, d] = String(raw).slice(0, 10).split('-')
  return y ? `${m}/${d}/${y}` : '-'
}

export default function BackgroundChecks() {
  const [data, error, reload] = useLoad(() => api.get('/company/screening'))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [hosting, setHosting] = useState(false)   // their sign-up, inside one of our dialogs
  const [done, setDone] = useState(false)        // and the word that it worked
  const held = useRef(null)                       // the widget, waiting for the dialog to exist
  const host = useRef(null)

  // The dialog has to exist before the iframe can be moved into it, so opening waits for the
  // render rather than happening inside the click.
  useEffect(() => {
    if (!hosting || !held.current || !host.current) return
    held.current.open()
    const frame = document.getElementById('account-registration-widget-iframe')
    if (!frame) return
    host.current.appendChild(frame)
    // Theirs said fixed and full-screen. Here it is simply the contents of a box.
    frame.style.cssText = 'position:static;inset:auto;width:100%;height:100%;border:0;display:block;'
  }, [hosting])

  if (!data) return <Loading error={error} page />

  // Their widget drops a `position: fixed; inset: 0` iframe over the whole page and takes no
  // sizing options. The iframe is in OUR document, though, so once it exists it can be lifted
  // out and dropped into one of this application's own dialogs - 90vh, scrolling, with the same
  // header and close button as every other dialog here. Their page keeps its own scrollbar
  // inside the frame; nothing of what is in it is touched, and nothing could be.
  const connect = async () => {
    setBusy(true); setErr(null)
    try {
      await loadScript(data.widgetscript)
      const widget = window.ClearChecksWidget?.init({
        sourceToken: data.sourcetoken,
        // They hand back a STRING - their script calls onSuccess(data.apiToken) - and it is
        // encrypted. Only the server can turn it into a usable key, so it goes straight there
        // and is never kept in the browser.
        onSuccess: async (got) => {
          try {
            await api.post('/company/screening/connect',
                           { token: typeof got === 'string' ? got : got?.apiToken || got?.token })
            // Their widget closes itself the moment it succeeds, which leaves somebody who has
            // just spent five minutes signing up looking at the page they started on with no
            // word about whether it worked. This says so, and waits to be dismissed.
            setDone(true)
            shut(); reload()
          } catch (e) { shut(); setErr(e.message) }
        },
        // Their own close button inside the frame, and any error. Both have to take our dialog
        // down with them - their script removes its own wrapper but knows nothing about ours.
        onClose: () => shut(),
        onError: (e) => { shut(); setErr(e?.message || e || 'The sign-up could not be opened.') },
      })
      if (!widget) throw new Error('The sign-up form did not load. Try again.')
      held.current = widget
      setHosting(true)
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  // Closing from our header. Their own close button posts a message that reaches onClose, so
  // this is the other way in and has to do the same tidying.
  const shut = () => {
    document.getElementById('clearchecks-widget')?.remove()
    document.getElementById('account-registration-widget-iframe')?.remove()
    held.current = null
    setHosting(false)
    setBusy(false)
  }

  const disconnect = async () => {
    setBusy(true); setErr(null)
    try { await api.del('/company/screening'); reload() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      {/* The same head every other tab on this page prints. */}
      <div className="pagehead">
        <div>
          <h1>Background Checks</h1>
        </div>
      </div>
      {err && <div className="notice bad">{err}</div>}
      {/* Named, and said to be partial. The rest of the page is still true. */}
      {(data.problems || []).map((p) => (
        <div className="notice warn" key={p}>
          <div>{p}<div className="small">Everything else on this page is up to date.</div></div>
        </div>
      ))}

      {!data.connected
        ? <NotYet data={data} busy={busy} onConnect={connect} />
        : <Connected data={data} busy={busy} onDisconnect={disconnect} />}

      {/* 1060 and not a round 1000, for a reason that is entirely theirs. Their form is
          Tailwind: the card is max-w-lg (512px) until the frame reaches the lg breakpoint at
          1024px, where it becomes max-w-3xl (768px). Sitting just under it gave their form half
          the room and this dialog a wide grey border. The extra 36px over 1024 is for the frame's
          own scrollbar, which comes out of the width their layout then measures - at 1030 a
          scrollbar would drop it back to 512 and nobody would know why. */}
      {hosting && (
        <Modal title="Create An Account" width={1060} tall flush onClose={shut}>
          <div className="widgetframe" ref={host} />
        </Modal>
      )}

      {done && (
        <Modal title="You Are All Signed Up" width={560} onClose={() => setDone(false)}
          footer={<button type="button" className="primary" onClick={() => setDone(false)}>
            Close
          </button>}>
          <div className="stack">
            <div className="notice good">
              <div>
                <b>This company now has its own account with backgroundchecks.com.</b> You can
                order a background check from any driver&rsquo;s record.
              </div>
            </div>
            <p>
              They bill you directly for what you order, at their prices - you will find those,
              and their invoices, on this page. Your company&rsquo;s name is what appears on the
              paperwork each driver signs.
            </p>
          </div>
        </Modal>
      )}
    </div>
  )
}

// Scripts are loaded once per page and shared. Two copies of a widget on one document gives two
// modals, and the second is always the one that will not close.
const scripts = {}
function loadScript(src) {
  if (!src) return Promise.reject(new Error(
    'Signing up is not switched on for this installation yet.'))
  if (scripts[src]) return scripts[src]
  scripts[src] = new Promise((resolve, reject) => {
    const tag = document.createElement('script')
    tag.src = src
    tag.async = true
    tag.onload = resolve
    tag.onerror = () => {
      delete scripts[src]          // a failed load must not be remembered as a load
      reject(new Error('The sign-up form could not be loaded. Check the connection and try again.'))
    }
    document.head.appendChild(tag)
  })
  return scripts[src]
}

// ------------------------------------------------------------------------------------------------
// Before a company has an account
// ------------------------------------------------------------------------------------------------
function NotYet({ data, busy, onConnect }) {
  return (
    <>
      <div className="card qualcard">
        <div className="infotabs"><h3>You Run Your Own Background Checks</h3></div>
        <div className="panelbody">
        <p>
          TripProof does not sell background checks and takes no part of what they cost. Your
          company holds its own account with <b>backgroundchecks.com</b>, chooses what to order,
          and is billed by them directly at their prices.
        </p>
        <p>
          That is not an accounting preference. Under the Fair Credit Reporting Act the company
          obtaining a report about a job applicant has to be the company deciding whether to hire
          them. Your name belongs on the disclosure the driver signs, and your certification
          belongs on the file - not ours.
        </p>

        <h3 className="formsection">How It Works</h3>
        <ol className="howlist">
          <li>
            <b>You create an account</b> here, in one step. You agree their terms and give them
            payment details; nothing goes through TripProof.
          </li>
          <li>
            <b>You order a check from a driver&rsquo;s record</b>, choosing how deep to go from the
            reports your account carries.
          </li>
          <li>
            <b>The driver fills in their own details.</b> They are sent a link - by us and by
            backgroundchecks.com - and give their date of birth, Social Security number and
            signed authorisation to them. Not to you, and not to us.
          </li>
          <li>
            <b>The result lands on the driver&rsquo;s file</b> when it is ready, and counts towards
            the requirements that ask for it.
          </li>
        </ol>

        <h3 className="formsection">What It Costs</h3>
        <p>
          Whatever backgroundchecks.com charges you. Their reports start around $25 and rise with
          depth; add-ons such as a driving record, employment verification or a drug test are
          priced separately. You will see your own prices on this page once you are signed up, and
          their invoices with them.
        </p>

        {!data.cansignup && (
          <div className="notice warn">
            Signing up is not switched on for this installation yet. It needs the platform
            credentials from backgroundchecks.com before the button below can work.
          </div>
        )}

        <div className="formactions">
          <button type="button" className="primary big" disabled={busy || !data.cansignup}
            onClick={onConnect}>
            {busy ? <Loader2 size={16} className="spin" /> : <ShieldCheck size={16} />}
            {' '}Create An Account
          </button>
        </div>
        </div>
      </div>
    </>
  )
}

// ------------------------------------------------------------------------------------------------
// Once they have one
// ------------------------------------------------------------------------------------------------
function Connected({ data, busy, onDisconnect }) {
  const a = data.account || {}
  const bill = data.billing || {}
  const reports = data.skus?.reports || []
  const addons = data.skus?.addons || []
  const surcharges = data.skus?.surcharges || { count: 0 }
  return (
    <>
      <div className="notice good">
        <div>
          <b>This company has its own account with backgroundchecks.com.</b> Checks ordered from a
          driver&rsquo;s record go to it, and they invoice you directly.
        </div>
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>Account</h3></div>
        <div className="panelbody">
        <div className="kv">
          <dt>Company</dt><dd>{a.company_name || '-'}</dd>
          <dt>Contact</dt>
          <dd>{[a.first_name, a.last_name].filter(Boolean).join(' ') || '-'}</dd>
          <dt>Where</dt>
          <dd>{[a.city, a.state, a.zip].filter(Boolean).join(', ') || '-'}</dd>
          </div>
        </div>
      </div>

      {(data.teams || []).length > 0 && (
        <div className="card qualcard">
          <div className="infotabs"><h3>Teams</h3></div>
          <div className="panelbody">
          <table className="residencetable recordtable">
            <thead><tr><th>Team</th><th>Your role</th><th>Created</th></tr></thead>
            <tbody>
              {data.teams.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td>{t.pivot?.role || '-'}</td>
                  <td>{theirDate(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      <div className="card qualcard">
        <div className="infotabs"><h3>How You Pay Them</h3></div>
        <div className="panelbody">
        {bill.card_type || bill.account_cc4 ? (
          <div className="kv">
            <dt>Card</dt>
            <dd>{bill.card_type || 'Card'} ending {bill.account_cc4 || '----'}
              {bill.cc_month ? ` · expires ${bill.cc_month}/${bill.cc_year}` : ''}</dd>
            <dt>Billed to</dt>
            <dd>{[bill.first_name, bill.last_name].filter(Boolean).join(' ') || '-'}</dd>
            <dt>Address</dt>
            <dd>{[bill.address1, bill.city, bill.state, bill.zip]
              .filter(Boolean).join(', ') || '-'}</dd>
          </div>
        ) : (
          <p className="muted">No payment details are on file with them yet.</p>
        )}
        </div>
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>Invoices</h3></div>
        <div className="panelbody">
        {(data.invoices || []).length === 0 ? (
          <p className="muted">They have not invoiced this account yet.</p>
        ) : (
          <table className="residencetable recordtable">
            <thead>
              <tr><th>Invoice</th><th>Date</th><th>For</th><th>Status</th><th>Total</th><th /></tr>
            </thead>
            <tbody>
              {data.invoices.map((i) => (
                <tr key={i.id || i.public_invoice_id}>
                  <td className="mono">{i.public_invoice_id || '-'}</td>
                  <td>{theirDate(i.invoice_created_at)}</td>
                  {/* Who the report was for. Their invoices are one per order, so this is the
                      only thing that tells two identical totals apart. */}
                  <td className="small">{i.applicant_emails || '-'}</td>
                  <td className={i.status === 'paid' ? 'st-active' : 'st-ordered'}>
                    {i.status ? i.status[0].toUpperCase() + i.status.slice(1) : '-'}
                  </td>
                  <td><b>{money(i.total)}</b></td>
                  <td>
                    {/* api.open, not window.open: the token is a header on this application's
                        requests and not a cookie, so a plain navigation arrives signed out. It
                        fetches with the header and hands back a blob. */}
                    {i.public_invoice_id && (
                      <button type="button" onClick={() => api.open(
                        `/company/screening/invoices/${i.public_invoice_id}/pdf`)}>
                        <ExternalLink size={13} /> View
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        </div>
      </div>

      <div className="card qualcard">
        <div className="infotabs"><h3>What You Can Order</h3></div>
        <div className="panelbody">
        <p className="muted small">
          Your own prices, read from backgroundchecks.com. A report is the base search; add-ons are
          bought on top of it.
        </p>
        {reports.length === 0 ? <p className="muted">No reports are on this account.</p> : (
          <table className="residencetable recordtable lastisprose">
            <thead><tr><th>Report</th><th>Price</th><th>What it covers</th></tr></thead>
            <tbody>
              {reports.map((s) => (
                <tr key={s.sku}>
                  <td><b>{s.title}</b><div className="small muted mono">{s.sku}</div></td>
                  <td><b>{money(s.price)}</b></td>
                  <td className="small">{s.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {addons.length > 0 && (
          <>
            <h4 className="formsection">Add-ons</h4>
            <p className="muted small">Bought on top of a report, when you want them.</p>
            <table className="residencetable recordtable">
              <thead><tr><th>Add-on</th><th>Price</th></tr></thead>
              <tbody>
                {addons.map((s) => (
                  <tr key={s.sku}>
                    <td>{s.title}<span className="small muted mono"> · {s.sku}</span></td>
                    <td>{money(s.price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {surcharges.count > 0 && (
          <p className="muted small" style={{ marginTop: 12 }}>
            {/* Not a choice anybody makes - it follows from where the applicant has lived - so it
                is stated rather than listed. */}
            A further <b>{surcharges.count}</b> court surcharges may apply, from{' '}
            {money(surcharges.low)} to {money(surcharges.high)}. These are not chosen: some states
            and counties charge to be searched, and the fee follows the applicant&rsquo;s address
            history. backgroundchecks.com adds them to the invoice for that report.
          </p>
        )}
        </div>
      </div>

      <div className="formactions">
        <button type="button" className="danger" disabled={busy} onClick={onDisconnect}>
          <Unplug size={14} /> Disconnect This Account
        </button>
      </div>
      <p className="small muted">
        Disconnecting only stops TripProof holding the key. The account stays yours, and anything
        already ordered carries on.
      </p>
    </>
  )
}
