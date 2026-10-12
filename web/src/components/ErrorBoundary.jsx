import { Component } from 'react'

// Catches a crash anywhere below it and shows what went wrong instead of a blank page, so the
// error can be read, reported and fixed. "Try again" re-renders from scratch.
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('TripProof crashed:', error, info?.componentStack)
    this.setState({ stack: info?.componentStack })
  }

  render() {
    const { error, stack } = this.state
    if (!error) return this.props.children
    return (
      <div className="crash">
        <div className="card">
          <h1>Something went wrong</h1>
          <pre>{String(error?.message || error)}{'\n'}{(error?.stack || '').split('\n').slice(1, 6).join('\n')}{stack ? `\n\nComponent:${stack.split('\n').slice(0, 6).join('\n')}` : ''}</pre>
          <button className="primary" onClick={() => window.location.reload()}>Try again</button>
        </div>
      </div>
    )
  }
}
