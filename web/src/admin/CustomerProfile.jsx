import { useState } from 'react'
import { ExternalLink, FileText, Rocket } from 'lucide-react'
import { launchAccount } from '../lib/launch.js'
import { api } from '../lib/api.js'
import { Modal, clean, useForm } from './common.jsx'
import { EinInput, PhoneInput, ZipInput } from '../components/MaskedInput.jsx'
import { Badge } from '../components/ui.jsx'
import { tzDate, money } from '../lib/format.js'
import DataGrid from '../components/DataGrid.jsx'

export const US_STATES = ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY',
  'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI',
  'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY']

const FIELDS = ['name', 'address1', 'address2', 'city', 'county', 'state', 'zip', 'phone', 'fax',
  'email', 'supportemail', 'billingemail', 'ein', 'adminname', 'adminemail', 'medicaidid', 'npi']

// The customer profile form, for both "New customer" and "Edit". The account number is assigned by
// the server when a customer is created and is never part of the form. With `detailsLink` (opened
// from the grid) the footer offers Launch, into the customer's own portal; `readOnly` (support staff) shows the
// profile without letting it be saved.
export default function CustomerProfileForm({ account, onClose, onSaved, detailsLink, readOnly }) {
  const editing = !!account
  const f = useForm({ ...Object.fromEntries(FIELDS.map((k) => [k, account?.[k] ?? (k === 'state' ? 'FL' : '')])), status: account?.status || 'active' },
    async (v) => {
      // Going inactive signs every one of the customer's users out, so it is confirmed first.
      if (editing && account.status !== 'inactive' && v.status === 'inactive' &&
          !confirm(`Make ${account.name} inactive? Every user is signed out and cannot sign in until it is made active again.`)) return
      const body = clean(v)
      onSaved(editing ? await api.patch(`/admin/accounts/${account.recordid}`, body) : await api.post('/admin/accounts', body))
    })
  const v = f.values
  // Existing customers get two tabs; a new customer has no billing yet, so just the form.
  const [tab, setTab] = useState('account')
  return (
    <Modal width={editing ? 880 : 780} title={editing ? `${account.name} · Account #${account.accountnumber}` : 'New customer'} onClose={onClose}
      footer={<>
        {detailsLink && editing && (
          <button type="button" className="launch" onClick={() => launchAccount(account.recordid)} title="Open this customer’s portal in a new tab">
            <Rocket size={14} /> Launch
          </button>
        )}
        <button onClick={onClose}>{readOnly ? 'Close' : 'Cancel'}</button>
        {!readOnly && <button className="primary" onClick={f.onSubmit} disabled={f.busy}>{editing ? 'Save' : 'Create and send invitation'}</button>}
      </>}>
      {editing && (
        <div className="tabs dlgtabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === 'account'} className={tab === 'account' ? 'on' : ''} onClick={() => setTab('account')}>Account information</button>
          <button type="button" role="tab" aria-selected={tab === 'billing'} className={tab === 'billing' ? 'on' : ''} onClick={() => setTab('billing')}>Billing information</button>
        </div>
      )}
      {/* One fixed-height panel for both tabs, so the dialog never changes height when switching. */}
      <div className={editing ? 'dlgpanel' : undefined}>
      {tab === 'billing' ? <BillingTab account={account} /> : <>
      <fieldset className="plain" disabled={readOnly}>
      <form className="profilesections" onSubmit={f.onSubmit}>
        <section>
          <h3 className="formsection">Demographics</h3>
          <div className="profileform">
            <label className="field span-5">Company name *<input required value={v.name} onChange={f.set('name')} /></label>
            <label className="field span-1">Status
              <select value={v.status} onChange={f.set('status')}>
                {/* Setup is set by the online signup, never chosen here; it shows only while an account is in it. */}
                {account?.status === 'setup' && <option value="setup" disabled>Setup</option>}
                <option value="active">Active</option><option value="inactive">Inactive</option>
              </select>
            </label>
            <label className="field span-6">Address line 1<input value={v.address1} onChange={f.set('address1')} autoComplete="address-line1" /></label>
            <label className="field span-6">Address line 2<input value={v.address2} onChange={f.set('address2')} autoComplete="address-line2" /></label>
            <label className="field span-2">City<input value={v.city} onChange={f.set('city')} autoComplete="address-level2" /></label>
            <label className="field span-1">County<input value={v.county} onChange={f.set('county')} /></label>
            <label className="field span-1">State
              <select value={v.state} onChange={f.set('state')}>{US_STATES.map((s) => <option key={s}>{s}</option>)}</select>
            </label>
            <label className="field span-2">ZIP<ZipInput value={v.zip} onChange={f.set('zip')} /></label>
            <label className="field span-3">Telephone<PhoneInput value={v.phone} onChange={f.set('phone')} /></label>
            <label className="field span-3">Fax<PhoneInput value={v.fax} onChange={f.set('fax')} autoComplete="off" /></label>
          </div>
        </section>
        <section>
          <h3 className="formsection">Identifiers</h3>
          <div className="profileform">
            <label className="field span-2">EIN<EinInput value={v.ein} onChange={f.set('ein')} /></label>
            <label className="field span-2">Medicaid ID<input value={v.medicaidid} onChange={f.set('medicaidid')} /></label>
            <label className="field span-2">NPI<input value={v.npi} onChange={f.set('npi')} inputMode="numeric" /></label>
          </div>
        </section>
        <section>
          <h3 className="formsection">Email Addresses</h3>
          <div className="profileform">
            <label className="field span-2">General<input type="email" value={v.email || ''} onChange={f.set('email')} /></label>
            <label className="field span-2">Support<input type="email" value={v.supportemail || ''} onChange={f.set('supportemail')} /></label>
            <label className="field span-2">Billing<input type="email" value={v.billingemail || ''} onChange={f.set('billingemail')} /></label>
          </div>
        </section>
        <section>
          <h3 className="formsection">Administrator</h3>
          <div className="profileform">
            <label className="field span-3">Admin name *<input required value={v.adminname} onChange={f.set('adminname')} /></label>
            <label className="field span-3">Admin email *<input type="email" required value={v.adminemail} onChange={f.set('adminemail')} /></label>
          </div>
        </section>
      </form>
      </fieldset>
      </>}
      </div>
      {f.error && <div className="error">{f.error}</div>}
    </Modal>
  )
}

const INVOICE_COLUMNS = [
  { id: 'date', label: 'Date', width: 105 },
  { id: 'number', label: 'Invoice' },
  { id: 'period', label: 'Period', width: 190 },
  { id: 'amount', label: 'Amount', width: 100, numeric: true },
  { id: 'status', label: 'Status', width: 190 },
  { id: 'links', srLabel: 'Links', width: 70, className: 'actions' },
]

// Read-only: what Stripe last reported for this customer, and every invoice (the transaction
// history). Changes happen in Stripe, or by the customer on their Billing page, and come back
// through the webhook.
function BillingTab({ account }) {
  const s = account.subscription
  // Stripe's next retry is on the open invoice; the subscription only has it after a failure event.
  const retry = s?.nextattempt || account.invoices.find((i) => i.status === 'open' && i.nextattempt)?.nextattempt
  const next = !s ? '-' : s.status === 'trialing' ? `Trial ends ${tzDate(s.trialend)}`
    : ['past_due', 'unpaid'].includes(s.status) ? (retry ? `Next retry ${tzDate(retry)}` : 'Overdue')
    : s.status === 'canceled' ? `Ended ${tzDate(s.canceledon)}` : s.cancelatperiodend ? `Ends ${tzDate(s.currentperiodend)}`
    : `Next bill ${tzDate(s.currentperiodend)}`
  const paid = account.invoices.filter((i) => i.status === 'paid').reduce((t, i) => t + Number(i.amountpaid), 0)
  return (
    <div className="billtab">
      <section>
        <h3 className="formsection">Billing
          {account.stripedashboard && <a className="iconlink" href={account.stripedashboard} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Open in Stripe</a>}
        </h3>
        {account.holdreason === 'billing' && <div className="notice bad" style={{ marginBottom: 10 }}>On a billing hold - the subscription lapsed. It lifts automatically when the customer pays.</div>}
        {!s && !account.stripecustomerid ? <p className="muted">No billing yet - this customer was set up by staff, not through the online application.</p> : (
          <div className="billcols">
            <dl className="kv billkv">
              <dt>Subscription</dt><dd>{s ? <><Badge state={s.status} /> <span className="muted small">{next}</span></> : 'None'}</dd>
              <dt>Price</dt><dd>{s ? `${money(s.monthlyprice)}/month · ${s.fleetsize} vehicles` : '-'}</dd>
              <dt>Started</dt><dd>{s ? tzDate(s.startedon) : '-'}</dd>
            </dl>
            <dl className="kv billkv">
              <dt>Card</dt><dd>{account.cardlast4 ? `${(account.cardbrand || '').toUpperCase()} •••• ${account.cardlast4} (exp ${account.cardexp})` : '-'}</dd>
              <dt>Last payment</dt><dd>{s?.lastpaidon ? `${money(s.lastpaidamount)} on ${tzDate(s.lastpaidon)}` : '-'}</dd>
              <dt>Total paid</dt><dd>{money(paid)}</dd>
              {s?.lastpaymenterror && <><dt>Last failure</dt><dd className="bad">{s.lastpaymenterror}</dd></>}
            </dl>
          </div>
        )}
      </section>
      <section className="billhistory">
        <h3 className="formsection">Transaction history</h3>
        <DataGrid columns={INVOICE_COLUMNS} rows={account.invoices} rowKey={(i) => i.stripeinvoiceid}
          empty="No invoices yet."
          cells={(i) => [
            tzDate(i.invoicedon),
            i.number || '-',
            i.periodstart ? `${tzDate(i.periodstart)} - ${tzDate(i.periodend)}` : '-',
            money(i.status === 'paid' ? i.amountpaid : i.amountdue),
            <><Badge state={i.status} />{i.status !== 'paid' && i.failuremessage &&
              <span className="rownote bad" title={i.failuremessage}>{i.attemptcount > 1 ? `${i.attemptcount} attempts · ` : ''}{i.failuremessage.replace(/\.$/, '')}</span>}</>,
            <span className="nowrap">
              {i.hostedurl && <a href={i.hostedurl} target="_blank" rel="noreferrer" title="View invoice" className="iconlink"><ExternalLink size={14} /></a>}
              {i.pdfurl && <a href={i.pdfurl} target="_blank" rel="noreferrer" title="Download PDF" className="iconlink"><FileText size={14} /></a>}
            </span>,
          ]} />
      </section>
    </div>
  )
}
