const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const num = new Intl.NumberFormat('en-US')

export const money = (v) => usd.format(Number(v || 0))
export const money0 = (v) => usd0.format(Number(v || 0))
export const count = (v) => num.format(Number(v || 0))

// Business dates/times come from the API as local wall-clock strings; show them as-is rather than
// letting the browser shift them through its own time zone.
export const date = (v) => {
  if (!v) return '-'
  const [y, m, d] = String(v).slice(0, 10).split('-')
  return `${m}/${d}/${y}`
}
export const datetime = (v) => {
  if (!v) return '-'
  const s = String(v).replace('T', ' ')
  const [dpart, tpart = ''] = s.split(' ')
  const [hh, mm] = tpart.split(':')
  if (hh === undefined || (hh === '00' && mm === '00')) return date(dpart)
  const h = Number(hh)
  return `${date(dpart)} ${((h + 11) % 12) + 1}:${mm} ${h < 12 ? 'AM' : 'PM'}`
}
// The clock part on its own, for a board where every row is the same day and repeating the date
// in every cell says nothing. A business time like the rest of these, so it is read off the stored
// wall clock and never shifted into a time zone.
export const time = (v) => {
  if (!v) return '-'
  const [hh, mm] = String(v).replace('T', ' ').split(' ')[1]?.split(':') || []
  if (hh === undefined) return '-'
  const h = Number(hh)
  return `${((h + 11) % 12) + 1}:${mm} ${h < 12 ? 'AM' : 'PM'}`
}
// Coverage windows are half-open [start, end). An end at midnight means "good through the day
// before", which is how people read an expiry - show that, not the exclusive instant.
export const through = (v) => {
  if (!v) return 'no end'
  const s = String(v).replace('T', ' ')
  const [dpart, tpart = '00:00'] = s.split(' ')
  if (!tpart.startsWith('00:00')) return `until ${datetime(v)}`
  const d = new Date(`${dpart}T12:00:00`)
  d.setDate(d.getDate() - 1)
  return `through ${date(d.toISOString())}`
}
export const bytes = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`)

// ---- Timestamps in the signed-in user's time zone ------------------------------------------------
// Housekeeping stamps from the API (created, sign-ins, activity, publishing, invoices…) are UTC with
// no zone marker. These read them as UTC and show them in the user's own time zone (users.timezone,
// else their account's), daylight saving handled. App sets the zone once the user is known.
//
// Business times - trip pickups, credential issue/expiry - are the operator's local wall clock and
// are NOT timestamps: show those with date()/datetime() above, never these. Date-only values pass
// through unchanged, so they can't shift a day.
let zone = 'America/New_York'
let fmtTime, fmtDay
const build = () => {
  fmtTime = new Intl.DateTimeFormat('en-US', { timeZone: zone, month: '2-digit', day: '2-digit', year: 'numeric', hour: 'numeric', minute: '2-digit' })
  fmtDay = new Intl.DateTimeFormat('en-US', { timeZone: zone, month: '2-digit', day: '2-digit', year: 'numeric' })
}
build()
export const setDisplayTimeZone = (tz) => {
  if (!tz || tz === zone) return
  try { new Intl.DateTimeFormat('en-US', { timeZone: tz }); zone = tz; build() } catch { /* unknown zone: keep the last good one */ }
}
export const displayTimeZone = () => zone
const hasTime = (v) => /\d{2}:\d{2}/.test(String(v))
const asUTC = (v) => {
  const s = String(v).replace(' ', 'T')
  return new Date(/([zZ]|[+-]\d{2}:?\d{2})$/.test(s) ? s : `${s}Z`)
}
export const tzDateTime = (v) => (!v ? '-' : !hasTime(v) ? date(v) : fmtTime.format(asUTC(v)).replace(',', ''))
export const tzDate = (v) => (!v ? '-' : !hasTime(v) ? date(v) : fmtDay.format(asUTC(v)))
