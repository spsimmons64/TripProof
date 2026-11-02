import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Download, Loader2 } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, money } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { EmailInput } from '../components/MaskedInput.jsx'

// A passenger paying an invoice, with no login. The company's page asks for the invoice number and
// ZIP on the paper; a link or QR code comes straight to the invoice. Paying happens on the
// processor's own page, so a card number is never typed here.
export default function PayPortal() {
  const { accountnumber, token } = useParams()
  return (
    <main className="payportal">
      {token ? <Invoice token={token} /> : <Find accountnumber={accountnumber} />}
    </main>
  )
}

function Find({ accountnumber }) {
  const navigate = useNavigate()
  const [company, error] = useLoad(() => api.get(`/pay/account/${accountnumber}`), [accountnumber])
  const [invoice, setInvoice] = useState('')
  const [zip, setZip] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  if (!company) return <Loading error={error && 'We could not find this company.'} page />
  const find = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      const got = await api.post(`/pay/account/${accountnumber}/find`, { invoice: Number(invoice), zip })
      navigate(`/pay/${accountnumber}/${got.token}`)
    } catch (x) { setErr(x.message); setBusy(false) }
  }
  return (
    <form className="card payform stack" onSubmit={find}>
      <h1>{company.name}</h1>
      <h2>Pay An Invoice</h2>
      {err && <div className="notice bad">{err}</div>}
      <label className="field">Invoice Number
        <input inputMode="numeric" value={invoice} onChange={(e) => setInvoice(e.target.value.replace(/\D/g, ''))} autoFocus />
      </label>
      <label className="field">Billing ZIP Code
        <input inputMode="numeric" maxLength={5} value={zip} onChange={(e) => setZip(e.target.value.replace(/\D/g, ''))} />
      </label>
      <button type="submit" className="primary" disabled={busy || !invoice || zip.length !== 5}>
        {busy ? <Loader2 size={15} className="spin" /> : 'Find Invoice'}
      </button>
      {company.phone && <p className="muted">Questions? Call {company.phone}.</p>}
    </form>
  )
}

function Invoice({ token }) {
  const [params, setParams] = useSearchParams()
  const session = params.get('session')
  const [nonce, setNonce] = useState(0)
  const [inv, error] = useLoad(() => api.get(`/pay/invoice/${token}`), [token, nonce])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [email, setEmail] = useState('')       // required where none is on file: for the receipt
  // Back from the payment page: the processor is asked, never the address bar.
  useEffect(() => {
    if (!session) return
    api.post(`/pay/invoice/${token}/confirm/${session}`, {})
      .catch((e) => setErr(e.message))
      .finally(() => { setParams({}, { replace: true }); setNonce((n) => n + 1) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session])
  if (!inv) return <Loading error={error && 'We could not find that invoice.'} page />
  const pay = async () => {
    setBusy(true); setErr(null)
    try { window.location.href = (await api.post(`/pay/invoice/${token}/checkout`, { email })).url }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  const paid = inv.balance <= 0
  return (
    <div className="card payform stack">
      <h1>{inv.company}</h1>
      <h2>Invoice {inv.number}</h2>
      {err && <div className="notice bad">{err}</div>}
      {paid && <div className="notice good">Paid In Full. Thank You.</div>}
      {inv.replaced && !paid && <div className="notice bad">This invoice was replaced. Call {inv.company}{inv.phone ? ` at ${inv.phone}` : ''}.</div>}
      <div className="kv">
        <dt>Bill To</dt><dd>{inv.billto}</dd>
        <dt>Issued</dt><dd>{date(inv.issuedon)}</dd>
        <dt>Total</dt><dd>{money(inv.amount)}</dd>
        <dt>Balance Due</dt><dd><b>{money(inv.balance)}</b></dd>
      </div>
      {inv.canpay && inv.needsemail && (
        <label className="field">Email Address *
          <EmailInput value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
      )}
      {inv.canpay && (
        <button type="button" className="primary paybutton" disabled={busy || (inv.needsemail && !email.trim())} onClick={pay}>
          {busy ? <Loader2 size={15} className="spin" /> : `Pay ${money(inv.balance)}`}
        </button>
      )}
      {!inv.canpay && !paid && !inv.replaced && <p className="muted">To pay this invoice, call {inv.company}{inv.phone ? ` at ${inv.phone}` : ''}.</p>}
      <button type="button" onClick={() => api.download(`/pay/invoice/${token}/pdf`, `invoice-${inv.number}.pdf`)}><Download size={13} /> Download Invoice</button>
      {inv.phone && inv.canpay && <p className="muted">Questions? Call {inv.phone}.</p>}
    </div>
  )
}

// The pretend card processor, for testing only: it stands where Stripe's page will. Any card is
// accepted, nothing is charged, and the server refuses all of this unless it is switched on.
export function SimulatedCheckout() {
  const { accountnumber, token } = useParams()
  const navigate = useNavigate()
  const [inv, error] = useLoad(() => api.get(`/pay/invoice/${token}`), [token])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const back = `/pay/${accountnumber}/${token}`
  if (!inv) return <main className="payportal"><Loading error={error} page /></main>
  const pay = async () => {
    setBusy(true); setErr(null)
    try { await api.post(`/pay/invoice/${token}/simulate`, {}); navigate(back) }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <main className="payportal">
      <div className="card payform stack">
        <div className="notice warn">Test Mode: Simulated Card Processor. No Money Moves.</div>
        <h1>{inv.company}</h1>
        <h2>Invoice {inv.number}: {money(inv.balance)}</h2>
        {err && <div className="notice bad">{err}</div>}
        <label className="field">Card Number<input defaultValue="4242 4242 4242 4242" /></label>
        <div className="row simcard">
          <label className="field">Expires<input defaultValue="12/30" /></label>
          <label className="field">CVC<input defaultValue="123" /></label>
        </div>
        <button type="button" className="primary paybutton" disabled={busy} onClick={pay}>
          {busy ? <Loader2 size={15} className="spin" /> : `Pay ${money(inv.balance)}`}
        </button>
        <button type="button" disabled={busy} onClick={() => setErr('Your card was declined. Nothing was charged.')}>Simulate A Declined Card</button>
        <button type="button" disabled={busy} onClick={() => navigate(back)}>Cancel</button>
      </div>
    </main>
  )
}
