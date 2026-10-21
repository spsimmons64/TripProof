// Every dialog wide enough for its own footer buttons.
//
// A footer button never wraps its words (styles.css). Where a dialog's set width cannot hold the
// row of them, the dialog grows to the width the row needs - up to the screen, never past it.
// Done once for the whole app, watching the page, because dialogs are built two ways (the shared
// Modal and a handful written by hand) and a footer gains and loses buttons as a dialog's state
// changes. A rule that had to be remembered in each dialog would be one somebody forgets.
function fit() {
  for (const box of document.querySelectorAll('.modal')) {
    const foot = box.querySelector(':scope > footer, :scope > form > footer, :scope > .modalfoot')
    if (!foot) continue
    box.style.minWidth = ''
    const short = foot.scrollWidth - foot.clientWidth
    if (short > 0) box.style.minWidth = `min(${box.offsetWidth + short + 2}px, calc(100vw - 32px))`
  }
}

export function fitDialogsToTheirButtons() {
  let queued = false
  const soon = () => {
    if (queued) return
    queued = true
    requestAnimationFrame(() => { queued = false; fit() })
  }
  new MutationObserver(soon).observe(document.body, { childList: true, subtree: true })
  window.addEventListener('resize', soon)
}
