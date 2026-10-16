import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './auth/AuthContext'
import { RouteGuard } from './auth/RouteGuard'
import ConnectPage from './pages/ConnectPage'
import JobsPage from './pages/JobsPage'
import LoginPage from './pages/LoginPage'
import OnboardingPage from './pages/OnboardingPage'
import PipelinePage from './pages/PipelinePage'
import PrivacyPage from './pages/PrivacyPage'
import ProfilePage from './pages/ProfilePage'
import SwipePage from './pages/SwipePage'
import { registerServiceWorker } from './registerSW'
import './index.css'

registerServiceWorker()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<App />}>
            <Route path="login" element={<RouteGuard route="login"><LoginPage /></RouteGuard>} />
            <Route path="privacy" element={<PrivacyPage />} />
            <Route path="onboarding" element={<RouteGuard route="onboarding"><OnboardingPage /></RouteGuard>} />
            <Route element={<RouteGuard route="app" />}>
              <Route index element={<ConnectPage />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route path="profile/:profileId" element={<ProfilePage />} />
              <Route path="swipe" element={<SwipePage />} />
              <Route path="pipeline" element={<PipelinePage />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
