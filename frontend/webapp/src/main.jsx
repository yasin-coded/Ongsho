import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { installLiveDelay } from './dev/liveDelay'
import './index.css'

const App = lazy(() => import('./App.jsx'))

installLiveDelay()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Suspense fallback={null}>
      <App />
    </Suspense>
  </StrictMode>,
)