// A time-zone picker: the US zones by their everyday names first, then every other IANA zone.
// `inheritLabel` adds a blank choice meaning "use the account's time zone" (customer users).
export const US_ZONES = [
  ['America/New_York', 'Eastern'],
  ['America/Chicago', 'Central'],
  ['America/Denver', 'Mountain'],
  ['America/Phoenix', 'Arizona (no DST)'],
  ['America/Los_Angeles', 'Pacific'],
  ['America/Anchorage', 'Alaska'],
  ['Pacific/Honolulu', 'Hawaii'],
  ['America/Puerto_Rico', 'Puerto Rico'],
]
const US = new Map(US_ZONES)
const OTHERS = (() => {
  try { return Intl.supportedValuesOf('timeZone').filter((z) => !US.has(z)) } catch { return [] }
})()

// "Eastern" for the US zones, the IANA name otherwise.
export const zoneLabel = (tz) => (tz ? US.get(tz) || tz.replace(/_/g, ' ') : '')

export default function TimeZoneSelect({ value, onChange, inheritLabel, disabled }) {
  return (
    <select value={value || ''} onChange={onChange} disabled={disabled}>
      {inheritLabel && <option value="">{inheritLabel}</option>}
      <optgroup label="United States">
        {US_ZONES.map(([z, label]) => <option key={z} value={z}>{label} - {z.replace(/_/g, ' ')}</option>)}
      </optgroup>
      {OTHERS.length > 0 && (
        <optgroup label="Other">
          {OTHERS.map((z) => <option key={z} value={z}>{z.replace(/_/g, ' ')}</option>)}
        </optgroup>
      )}
    </select>
  )
}
