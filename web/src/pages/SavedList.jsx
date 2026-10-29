import { useEffect, useState } from 'react'
import { Plus, Search } from 'lucide-react'
import { api } from '../lib/api.js'
import { date } from '../lib/format.js'
import { useLoad } from '../components/ui.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import { Phone } from '../components/Contact.jsx'
import { EntryDialog } from '../components/BookTrip.jsx'

// The company's saved passengers, or its saved locations: what Book A Trip and Edit Trip choose
// from. Searched, sorted and paged like every list; a row opens it to be put right or removed.
// Trips already booked keep the addresses they were booked with - this is the list, not history.
const COLUMNS = {
  passengers: [
    { id: 'name', label: 'Passenger', width: 260 },
    { id: 'dob', label: 'Date Of Birth', width: 150 },
    { id: 'phone', label: 'Telephone', width: 170 },
    { id: 'address', label: 'Address' },
  ],
  places: [
    { id: 'name', label: 'Location', width: 320 },
    { id: 'phone', label: 'Telephone', width: 170 },
    { id: 'address', label: 'Address' },
  ],
}

export default function SavedList({ kind }) {
  const passenger = kind === 'passengers'
  const g = useGridParams({ defaultSort: 'name', defaultDir: 'asc' })
  const [data, error, reload] = useLoad(() => api.get(`/${kind}?${g.query}${g.query.includes('page=') ? '' : '&page=1'}`), [kind, g.query])
  const [open, setOpen] = useState(null)        // {} new, or an entry
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])
  const noun = passenger ? 'Passenger' : 'Location'
  return (
    <div className="fill">
      <div className="pagehead">
        <h1>{passenger ? 'Passengers' : 'Locations'}</h1>
        <div className="row">
          <div className="searchbox"><Search size={14} /><input placeholder={`Search ${passenger ? 'Passengers' : 'Locations'}`}
            value={g.search} onChange={(e) => g.setSearch(e.target.value)} /></div>
          <button className="primary" onClick={() => setOpen({})}><Plus size={14} /> New {noun}</button>
        </div>
      </div>
      <DataGrid columns={COLUMNS[kind]} rows={data?.items} rowKey={(x) => x.recordid} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort} onRowClick={setOpen}
        pager={data && g.pager(data.total, passenger ? 'passenger' : 'location')}
        empty={g.search ? `No ${passenger ? 'passengers' : 'locations'} match ${g.search}.`
          : `No ${passenger ? 'passengers' : 'locations'} yet.`}
        cells={(x) => (passenger
          ? [<b>{x.name}</b>, x.dob ? date(x.dob) : '-', <Phone number={x.phone} />, x.full]
          : [<b>{x.name}</b>, <Phone number={x.phone} />, x.full])} />
      {open && (
        <EntryDialog kind={kind} entry={open.recordid ? open : null} onClose={() => setOpen(null)}
          onAdded={() => { setOpen(null); reload() }} onRemoved={() => { setOpen(null); reload() }} />
      )}
    </div>
  )
}
