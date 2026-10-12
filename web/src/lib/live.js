import { useEffect, useRef } from 'react'
import { api } from './api.js'

// Learning that something changed.
//
// The server keeps a feed of changes - see api/app/events.py - and every entry in it says only
// which thing changed. So the client's job is never to apply an event; it is to go and ask again
// through the endpoints it already uses, which already decide what this user may see.
//
// Two ways of noticing, in the order they matter:
//
//   Coming back to the tab. This is the real workflow - send a driver a link to sign, go and do
//   something else, come back. Whatever happened while you were away is picked up the moment you
//   look, which is the only moment it matters.
//
//   Asking, while you are waiting on something. Only on the screen that is waiting, only while it
//   is waiting, and only for the subject it is waiting on.
//
// Both go through one endpoint, and the client's question - what changed since this cursor - is the
// same question a stream or a socket would answer later. Nothing above this line has to change when
// the transport does.

// Refetch when the tab is looked at again, and when the connection comes back.
export function useRefreshOnFocus(reload, enabled = true) {
  const latest = useRef(reload)
  latest.current = reload
  useEffect(() => {
    if (!enabled) return undefined
    const again = () => { if (document.visibilityState === 'visible') latest.current?.() }
    window.addEventListener('focus', again)
    window.addEventListener('online', again)
    document.addEventListener('visibilitychange', again)
    return () => {
      window.removeEventListener('focus', again)
      window.removeEventListener('online', again)
      document.removeEventListener('visibilitychange', again)
    }
  }, [enabled])
}

// Ask what has changed about one subject, every `seconds`, while `watching` is true. The cursor
// starts at the end of the feed, so a screen only ever hears about what happens after it opened.
export function useWatch(subject, subjectid, reload, { watching = true, seconds = 20 } = {}) {
  const latest = useRef(reload)
  latest.current = reload
  const cursor = useRef(null)

  useEffect(() => {
    if (!watching) return undefined
    let live = true
    let timer = null

    const ask = async () => {
      try {
        const query = new URLSearchParams()
        if (subject) query.set('subject', subject)
        if (subjectid && subjectid !== 'all') query.set('subjectid', subjectid)
        if (cursor.current !== null) query.set('since', String(cursor.current))
        const r = await api.get(`/events?${query}`)
        if (!live) return
        const first = cursor.current === null
        cursor.current = r.cursor
        // Nothing is applied from the feed - it only says it is worth asking again.
        if (!first && r.events?.length) latest.current?.()
      } catch {
        // A feed that cannot be reached is not an error worth showing: the page is still correct,
        // it is just no longer being told when it stops being.
      }
      if (live) timer = setTimeout(ask, seconds * 1000)
    }
    ask()
    return () => { live = false; if (timer) clearTimeout(timer) }
  }, [subject, subjectid, watching, seconds])
}
