import { formatEin, formatPhone, formatSsn, formatZip } from '../lib/masks.js'

// Inputs that format as you type. onChange receives an event-like { target: { value } } carrying the
// formatted value, so they drop into the same handlers as a plain <input>.
function Masked({ format, value, onChange, ...rest }) {
  return (
    <input {...rest} value={format(value)} inputMode="numeric"
      onChange={(e) => onChange({ target: { value: format(e.target.value) } })} />
  )
}

// Free text is stored the way it is filed: upper case throughout, except an email address, which is
// lower case. Both transform as you type, so what is stored is what is shown.
function Cased({ cased, as: Tag = 'input', value, onChange, ...rest }) {
  return (
    <Tag {...rest} value={cased(value ?? '')}
      onChange={(e) => onChange({ target: { value: cased(e.target.value) } })} />
  )
}

export const UpperInput = (props) => <Cased cased={(v) => String(v).toUpperCase()} {...props} />
export const UpperArea = (props) => <Cased as="textarea" rows={4} cased={(v) => String(v).toUpperCase()} {...props} />
export const EmailInput = (props) => (
  <Cased type="email" autoComplete="email" cased={(v) => String(v).toLowerCase()} {...props} />
)

export const PhoneInput = (props) => <Masked type="tel" autoComplete="tel" maxLength={14} format={formatPhone} {...props} />
export const EinInput = (props) => <Masked maxLength={10} format={formatEin} {...props} />
export const SsnInput = (props) => <Masked maxLength={11} autoComplete="off" format={formatSsn} {...props} />
export const ZipInput = (props) => <Masked maxLength={10} autoComplete="postal-code" format={formatZip} {...props} />
