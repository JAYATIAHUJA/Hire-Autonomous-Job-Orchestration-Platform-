import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import App from './App'
import ConnectPage from './pages/ConnectPage'
import JobsPage from './pages/JobsPage'
import PipelinePage from './pages/PipelinePage'
import ProfilePage from './pages/ProfilePage'
import SwipePage from './pages/SwipePage'
import { registerServiceWorker } from './registerSW'
import './index.css'

registerServiceWorker()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<ConnectPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="profile/:profileId" element={<ProfilePage />} />
          <Route path="swipe" element={<SwipePage />} />
          <Route path="pipeline" element={<PipelinePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
