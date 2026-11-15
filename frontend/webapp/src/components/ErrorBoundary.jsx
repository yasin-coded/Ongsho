import { Component } from 'react'
import { Button } from '@/components/ui/Button'

export class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error) {
    if (import.meta.env.DEV) {
      console.error('UI error boundary caught an error')
    }
    void error
  }

  render() {
    if (this.state.error) {
      return (
        <div className="grid min-h-[40vh] place-items-center p-8 text-center" role="alert">
          <div className="grid max-w-md gap-4">
            <h1 className="t-card">Something went wrong</h1>
            <p className="t-muted">This screen could not be loaded. Reload the page to try again.</p>
            <Button type="button" onClick={() => window.location.reload()}>
              Reload
            </Button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}