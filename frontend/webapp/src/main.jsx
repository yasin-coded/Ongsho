import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { installLiveDelay } from './dev/liveDelay'
import './index.css'
import App from './AppLazy.jsx'

installLiveDelay()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Suspense fallback={null}>
      <App />
    </Suspense>
  </StrictMode>,
)