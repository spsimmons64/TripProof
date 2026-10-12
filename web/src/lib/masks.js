// Format-as-you-type for US identifiers. Each takes whatever was typed or pasted and returns the
// formatted form, keeping only the digits that fit, so the field can never hold a malformed value.
const digits = (v, max) => String(v ?? '').replace(/\D/g, '').slice(0, max)

// (813) 555-0142. US area codes never start with 0 or 1, so a leading 1 (country code, typed or
// pasted) or 0 is dropped before the ten digits are taken.
export function formatPhone(v) {
  const d = String(v ?? '').replace(/\D/g, '').replace(/^[01]+/, '').slice(0, 10)
  if (d.length === 0) return ''
  if (d.length < 4) return `(${d}`
  if (d.length < 7) return `(${d.slice(0, 3)}) ${d.slice(3)}`
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
}

// 12-3456789
export function formatEin(v) {
  const d = digits(v, 9)
  return d.length > 2 ? `${d.slice(0, 2)}-${d.slice(2)}` : d
}

// 123-45-6789
export function formatSsn(v) {
  const d = digits(v, 9)
  if (d.length < 4) return d
  if (d.length < 6) return `${d.slice(0, 3)}-${d.slice(3)}`
  return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`
}

// 33602, or 33602-1234 once more than five digits are typed.
export function formatZip(v) {
  const d = digits(v, 9)
  return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d
}
