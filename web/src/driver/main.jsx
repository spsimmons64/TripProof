// The TripProofDriver store app: the driver's app on its own, without the office application it is
// served beside on the web. Built by vite.app.config.js into dist-app, which Capacitor packages.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import ErrorBoundary from '../components/ErrorBoundary.jsx'
import DriverApp from './DriverApp.jsx'
import '../styles.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary><DriverApp /></ErrorBoundary>
  </StrictMode>,
)
