// Printing what is on screen in a viewer.
//
// Two kinds of thing get read in this application and they print by different roads. A stored
// document is a file - a PDF or a photograph - and the browser already knows how to print one; it
// only needs to be handed the file rather than the page around it. A signed document has no file
// at all: it is rebuilt from the record every time it is read, so what prints is the same markup
// and the same stylesheet that were put on screen.
//
// Both go through a window of their own. Printing the page itself would print the dialog, the
// navigation and whatever is behind them, and a print stylesheet that hid all that would be a
// second description of the application's layout kept in step with the first by hand.

// How long to leave the hidden frame in the document. The print dialog is modal to the tab but
// not to this code, so the frame has to outlive the call that made it - a frame removed while
// somebody is still choosing a printer takes the document with it.
const KEEP = 60000

export function printFile(url, fallbackName) {
  if (!url) return
  const frame = document.createElement('iframe')
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;'
  frame.src = url
  frame.onload = () => {
    try {
      frame.contentWindow.focus()
      frame.contentWindow.print()
    } catch {
      // Some browsers refuse to print a frame they did not navigate themselves. Opening the file
      // in its own tab gets the reader to their own print button, which is worse than one click
      // and better than nothing happening.
      window.open(url, '_blank', 'noopener')
    }
    setTimeout(() => frame.remove(), KEEP)
  }
  frame.onerror = () => { frame.remove(); window.open(url, '_blank', 'noopener') }
  document.body.appendChild(frame)
  return fallbackName
}

export function printHtml(title, css, html) {
  const win = window.open('', '_blank', 'noopener,width=900,height=1000')
  if (!win) return false            // blocked; the caller says so rather than failing silently
  win.document.write(
    `<!doctype html><html><head><meta charset="utf-8"><title>${escapeText(title)}</title>`
    + `<style>${css || ''}</style></head><body>${html || ''}</body></html>`,
  )
  win.document.close()
  // The stylesheet and any images in it have to be in before the dialog opens, or the first page
  // prints unstyled and nobody can tell whether that is the document or a fault in it.
  win.onload = () => { win.focus(); win.print() }
  return true
}

function escapeText(s) {
  return String(s || '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
}

// An HTML document as something to read, never to run. Uploaded HTML can carry scripts, and a
// script running in this page's origin could read the signed-in session, so everything active is
// removed - scripts, frames, plugins, event handlers and javascript: links - before it is shown,
// and it is shown and printed only in frames that are not allowed to run scripts anyway.
export function inertHtml(text) {
  const doc = new DOMParser().parseFromString(text || '', 'text/html')
  doc.querySelectorAll('script, iframe, frame, frameset, object, embed, applet, base, meta[http-equiv]')
    .forEach((n) => n.remove())
  doc.querySelectorAll('*').forEach((n) => {
    for (const a of [...n.attributes]) {
      const v = (a.value || '').trim().toLowerCase()
      if (a.name.toLowerCase().startsWith('on')
          || (['href', 'src', 'action', 'formaction', 'xlink:href'].includes(a.name.toLowerCase())
              && (v.startsWith('javascript:') || v.startsWith('data:text/html')))) {
        n.removeAttribute(a.name)
      }
    }
  })
  return '<!doctype html>' + doc.documentElement.outerHTML
}

// Print an HTML document made inert by inertHtml: the same hidden-frame road as a file, with the
// frame forbidden to run scripts.
export function printInertHtml(html) {
  const frame = document.createElement('iframe')
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;'
  frame.setAttribute('sandbox', 'allow-same-origin allow-modals')
  frame.onload = () => {
    try { frame.contentWindow.focus(); frame.contentWindow.print() } catch { /* nothing else to try */ }
    setTimeout(() => frame.remove(), KEEP)
  }
  frame.srcdoc = html
  document.body.appendChild(frame)
}
