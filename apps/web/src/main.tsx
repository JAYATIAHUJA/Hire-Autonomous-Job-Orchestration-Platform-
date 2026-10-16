import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import App from './App'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { RouteGuard } from './auth/RouteGuard'
import HomePage from './pages/HomePage'
import JobsPage from './pages/JobsPage'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import MyProfilePage from './pages/MyProfilePage'
import OnboardingPage from './pages/OnboardingPage'
import PipelinePage from './pages/PipelinePage'
import PrivacyPage from './pages/PrivacyPage'
import ProfilePage from './pages/ProfilePage'
import SwipePage from './pages/SwipePage'
import { registerServiceWorker } from './registerSW'
import { Loading } from './ui/kit'
import './index.css'

registerServiceWorker()

// "/": the website for visitors, the dashboard for signed-in users.
function IndexGate() {
  const { auth } = useAuth()
  if (auth.status === 'loading') return <Loading label="Loading…" />
  if (auth.status === 'anonymous') return <LandingPage />
  return (
    <RouteGuard route="app">
      <HomePage />
    </RouteGuard>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<App />}>
            <Route path="login" element={<RouteGuard route="login"><LoginPage /></RouteGuard>} />
            <Route path="privacy" element={<PrivacyPage />} />
            <Route index element={<IndexGate />} />
            <Route path="onboarding" element={<RouteGuard route="onboarding"><OnboardingPage /></RouteGuard>} />
            <Route element={<RouteGuard route="app" />}>
              <Route path="swipe" element={<SwipePage />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route path="pipeline" element={<PipelinePage />} />
              <Route path="profile" element={<MyProfilePage />} />
              <Route path="profile/:profileId" element={<ProfilePage />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
