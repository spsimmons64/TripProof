// How wide is this browser's scrollbar?
//
// A grid card scrolls its ROWS, not its headings, so the header sits outside the scrolling box.
// That costs the body a few pixels to its scrollbar which the header does not lose, and the two
// would sit out of step. The header carries a spacer cell of exactly this width to make up for it.
//
// Measured rather than guessed: it is about 15px on Chrome, 12 on Firefox with thin scrollbars, and
// 0 wherever the scrollbar floats over the content (macOS, most touch devices). Published as
// --sbw on :root, and re-measured if the window changes (a zoom changes it).
export function trackScrollbarWidth() {
  const measure = () => {
    const box = document.createElement('div')
    box.style.cssText = 'position:absolute;top:-9999px;width:100px;height:100px;overflow-y:scroll'
    document.body.appendChild(box)
    const width = box.offsetWidth - box.clientWidth
    box.remove()
    document.documentElement.style.setProperty('--sbw', `${width}px`)
  }
  measure()
  window.addEventListener('resize', measure)
}
