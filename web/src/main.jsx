import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { trackScrollbarWidth } from './lib/scrollbar.js'
import { fitDialogsToTheirButtons } from './lib/dialogwidth.js'
import './styles.css'

// Grid headers sit outside the scrolling rows and need to know the scrollbar's width.
trackScrollbarWidth()
// Dialogs widen to fit their footer buttons rather than wrap them.
fitDialogsToTheirButtons()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ErrorBoundary><App /></ErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
)
