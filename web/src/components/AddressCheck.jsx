import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

// Under an address being booked: said in red when the map cannot find it, or finds it far from the
// company - a trip is timed from where its addresses are, so one in the wrong town is caught here
// rather than as a refusal at Save.
export default function AddressCheck({ address, label }) {
  const [problem, setProblem] = useState(null)
  useEffect(() => {
    setProblem(null)
    if (!address || !address.trim()) return undefined
    let dropped = false
    const wait = setTimeout(() => {
      api.get(`/address-check?${new URLSearchParams({ address: address.trim() })}`)
        .then((got) => { if (!dropped) setProblem(got.problem) }).catch(() => {})
    }, 700)
    return () => { dropped = true; clearTimeout(wait) }
  }, [address])
  if (!problem) return null
  return <div className="span-6 routeline pastclosing">The {label} address {problem} - check it.</div>
}
