import { useMemo, useState } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { CardElement, Elements, useElements, useStripe } from '@stripe/react-stripe-js'
import { AlertTriangle, CreditCard, ExternalLink, FileText, Info } from 'lucide-react'
import { api } from '../lib/api.js'
import { money, tzDate } from '../lib/format.js'
import { Badge, Loading, Tile, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import { useUser } from '../App.jsx'

const cardLabel = (c) => `${(c.brand || 'card').toUpperCase()} •••• ${c.last4}`

// Plan, subscription status, the card on file and the invoice history. `hold` - the account is on a
// billing hold, and this is the only page its users can reach until they pay.
export default function Billing({ hold }) {
  const user = useUser()
  const [data, error, reload] = useLoad(() => api.get('/billing'))
  const [changing, setChanging] = useState(false)
  const [message, setMessage] = useState(null)
  const stripePromise = useMemo(() => (data?.stripe ? loadStripe(data.stripe) : null), [data?.stripe])
  if (!data) return <Loading error={error} />

  const { plan, subscription: sub, card, nextplan, invoices } = data
  const due = sub && ['past_due', 'unpaid'].includes(sub.status)
  const canChange = !user.launched && !!data.stripe
  const statusSub = !sub ? 'No subscription yet'
    : sub.status === 'trialing' ? `Free trial ends ${tzDate(sub.trialend)}`
    : due ? (sub.nextattempt ? `Next retry ${tzDate(sub.nextattempt)}` : 'Payment overdue')
    : sub.status === 'canceled' ? `Ended ${tzDate(sub.canceledon)}`
    : sub.cancelatperiodend ? `Ends ${tzDate(sub.currentperiodend)}`
    : `Next bill ${tzDate(sub.currentperiodend)}`
  const planChanges = plan && nextplan && nextplan.name !== plan.name

  return (
    <div className="stack">
      <div className="pagehead"><h1>Billing</h1></div>

      {message && <div className={`notice ${message.bad ? 'bad' : 'good'}`}>{message.bad ? <AlertTriangle size={16} /> : <Info size={16} />}<div>{message.text}</div></div>}
      {data.hold ? (
        <div className="notice bad"><AlertTriangle size={16} /><div>
          <b>Your subscription has lapsed</b>, so your TripProof account is paused. Update your payment card to
          reactivate it - you’ll be charged {plan ? money(nextplan && !nextplan.contact ? nextplan.monthlyprice : plan.monthlyprice) : 'your plan’s price'} now
          and your records are exactly as you left them.
          {!canChange && ' Only your account owner or admin can do this.'}
        </div></div>
      ) : due && (
        <div className="notice bad"><AlertTriangle size={16} /><div>
          <b>Your last payment didn’t go through</b>{sub.lastpaymenterror ? ` - ${sub.lastpaymenterror.replace(/\.$/, '')}` : ''}. We’ll retry the card
          {sub.nextattempt ? ` on ${tzDate(sub.nextattempt)}` : ''}; update it now to pay the balance and avoid interruption.
        </div></div>
      )}

      <div className="grid cols-3">
        <Tile className="fill-teal" label="Plan" value={plan ? plan.name : '-'}
          sub={plan ? `${money(sub?.monthlyprice ?? plan.monthlyprice)}/month · ${sub?.fleetsize ?? plan.fleetsize} vehicles` : ''} />
        <Tile className={due || data.hold ? 'fill-orange' : 'fill-light'} label="Status"
          value={sub ? <Badge state={sub.status} /> : '-'} sub={statusSub} />
        <div className="card tile">
          <div className="label">Payment card</div>
          <div className="value cardvalue"><CreditCard size={22} /> {card ? cardLabel(card) : 'None on file'}</div>
          <div className="sub">{card?.exp ? `Expires ${card.exp}` : ''}</div>
          {canChange && <button className={due || data.hold ? 'primary' : ''} style={{ marginTop: 10 }} onClick={() => setChanging(true)}>
            {due || data.hold ? 'Update card and pay now' : 'Update card'}</button>}
        </div>
      </div>

      {planChanges && (
        <div className={`notice ${nextplan.contact ? 'warn' : 'info'}`}><Info size={16} /><div>
          You have <b>{data.billablefleet} vehicles</b> on file.{' '}
          {nextplan.contact
            ? <>That’s past our listed plans - you’ll stay on {plan.name} until we contact you with pricing for your fleet.</>
            : <>Your next bill will be on the <b>{nextplan.name}</b> plan ({money(nextplan.monthlyprice)}/month). Plans follow your fleet size and are checked before each bill.</>}
        </div></div>
      )}
      {!planChanges && plan && (
        <p className="muted small" style={{ margin: 0 }}>Plans are priced by fleet size and checked against the vehicles on file before each bill. You have {data.billablefleet} vehicles on file.</p>
      )}

      <div className="card gridcard" style={{ flex: 'none' }}>
        <div className="tablewrap"><table>
          <thead><tr><th>Date</th><th>Invoice</th><th>Period</th><th className="num">Amount</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {invoices.length === 0 && <tr><td colSpan={6} className="muted">No invoices yet{sub?.status === 'trialing' ? ` - your first bill is on ${tzDate(sub.trialend)}` : ''}.</td></tr>}
            {invoices.map((i) => (
              <tr key={i.number || i.invoicedon}>
                <td>{tzDate(i.invoicedon)}</td>
                <td>{i.number || '-'}</td>
                <td>{i.periodstart ? `${tzDate(i.periodstart)} - ${tzDate(i.periodend)}` : '-'}</td>
                <td className="num">{money(i.status === 'paid' ? i.amountpaid : i.amountdue)}</td>
                <td><Badge state={i.status} />{i.status === 'open' && i.failuremessage && <div className="small muted">{i.failuremessage}</div>}</td>
                <td className="num nowrap">
                  {i.hostedurl && <a href={i.hostedurl} target="_blank" rel="noreferrer" className="iconlink"><ExternalLink size={13} /> View</a>}
                  {i.pdfurl && <a href={i.pdfurl} target="_blank" rel="noreferrer" className="iconlink"><FileText size={13} /> PDF</a>}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>
      {hold && <p className="muted small">Questions about your bill? Contact TripProof support.</p>}

      {changing && stripePromise && (
        <Elements stripe={stripePromise}>
          <CardForm charge={due || data.hold} onClose={() => setChanging(false)}
            onDone={(r) => {
              setChanging(false)
              setMessage({ text: r.message, bad: !!r.paymentfailed })
              // Paid off a hold: the rest of the portal opens again.
              if (hold && !r.hold) window.location.assign('/')
              else reload()
            }} />
        </Elements>
      )}
    </div>
  )
}

function CardForm({ charge, onClose, onDone }) {
  const stripe = useStripe()
  const elements = useElements()
  const user = useUser()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    if (!stripe || !elements) return
    setBusy(true); setError(null)
    try {
      const { clientsecret } = await api.post('/billing/card/intent')
      const res = await stripe.confirmCardSetup(clientsecret, {
        payment_method: { card: elements.getElement(CardElement), billing_details: { name: user.name, email: user.email } },
      })
      if (res.error) throw new Error(res.error.message)
      onDone(await api.post('/billing/card'))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }
  return (
    <Modal width={520} title="Update payment card" onClose={onClose}
      footer={<><button onClick={onClose}>Cancel</button>
        <button className="primary" onClick={submit} disabled={busy || !stripe}>{busy ? 'Saving…' : charge ? 'Save card and pay' : 'Save card'}</button></>}>
      <form onSubmit={submit} className="stack">
        <p className="muted" style={{ margin: 0 }}>
          {charge ? 'The new card becomes your default and is charged the balance due right away.' : 'The new card becomes your default for future bills.'}
          {' '}Card details go straight to Stripe - TripProof never sees the full number.
        </p>
        <div className="cardbox"><CardElement options={{ hidePostalCode: true, style: { base: { fontSize: '16px', color: '#13272b', '::placeholder': { color: '#74858a' } } } }} /></div>
        {error && <div className="error">{error}</div>}
      </form>
    </Modal>
  )
}
