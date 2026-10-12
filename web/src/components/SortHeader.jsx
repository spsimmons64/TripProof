import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'

// A clickable column header. Clicking the sorted column flips its direction; clicking another sorts
// by it (numbers start high-to-low, text A-Z, via `firstDir`). aria-sort tells screen readers.
export default function SortHeader({ id, label, sort, dir, onSort, numeric, firstDir, style, className }) {
  const active = sort === id
  const next = active ? (dir === 'asc' ? 'desc' : 'asc') : (firstDir || (numeric ? 'desc' : 'asc'))
  const Icon = !active ? ArrowUpDown : dir === 'asc' ? ArrowUp : ArrowDown
  return (
    <th className={[numeric && 'num', className].filter(Boolean).join(' ') || undefined} style={style}
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button type="button" className={`sorth${active ? ' on' : ''}`} onClick={() => onSort(id, next)}>
        {label}<Icon size={12} />
      </button>
    </th>
  )
}
