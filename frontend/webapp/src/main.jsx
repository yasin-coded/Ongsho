import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { installLiveDelay } from './dev/liveDelay'
import './index.css'
import App from './App.jsx'

installLiveDelay()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
