import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { accountApi, USE_MOCKS } from '../api/account'
import { useAuth } from '../auth/AuthContext'
import { HOME_PATH, safeNextPath } from '../auth/guard'
import { codeOf, DEFAULT_RESEND_SECONDS, emptyCode, formatCountdown, isComplete, otpErrorMessage } from '../auth/otp'
import OtpInput from '../components/OtpInput'

// Seconds left until `until` (epoch ms), ticking once a second.
function useSecondsLeft(until: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    setNow(Date.now())
    if (until <= Date.now()) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [until])
  return Math.max(0, Math.ceil((until - now) / 1000))
}

export default function LoginPage() {
  const { setMe } = useAuth()
  const [params] = useSearchParams()
  const next = safeNextPath(params.get('next'))
  const [email, setEmail] = useState('')
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [digits, setDigits] = useState(emptyCode)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(params.get('error') ? 'Sign-in was cancelled or failed. Try again.' : null)
  const [resendAt, setResendAt] = useState(0)
  const secondsLeft = useSecondsLeft(resendAt)
  const verifying = useRef(false)

  async function sendCode(target: string) {
    setBusy(true)
    setError(null)
    try {
      const res = await accountApi.sendOtp(target)
      setSentTo(target)
      setDigits(emptyCode())
      setResendAt(Date.now() + (res?.resend_after ?? DEFAULT_RESEND_SECONDS) * 1000)
    } catch (err) {
      setError(otpErrorMessage(err, 'send'))
    } finally {
      setBusy(false)
    }
  }

  async function verify(code: string) {
    if (!sentTo || verifying.current) return
    verifying.current = true
    setBusy(true)
    setError(null)
    try {
      // The route guard moves the user on as soon as the session is set.
      setMe(await accountApi.verifyOtp(sentTo, code))
    } catch (err) {
      setError(otpErrorMessage(err, 'verify'))
      setDigits(emptyCode())
    } finally {
      verifying.current = false
      setBusy(false)
    }
  }

  function onDigits(value: string[]) {
    setDigits(value)
    if (isComplete(value)) verify(codeOf(value))
  }

  function onEmailSubmit(e: FormEvent) {
    e.preventDefault()
    const target = email.trim()
    if (target) sendCode(target)
  }

  function onCodeSubmit(e: FormEvent) {
    e.preventDefault()
    if (isComplete(digits)) verify(codeOf(digits))
  }

  function oauth(provider: 'github' | 'google') {
    window.location.assign(accountApi.oauthStartUrl(provider, next ?? HOME_PATH))
  }

  return (
    <section className="auth-page">
      <h1>Sign in to Hire</h1>
      <p className="subtitle">
        One account for your proof-of-work profile, your deck and your applications. Before we collect anything beyond
        your sign-in, we show you our <Link to="/privacy" className="text-link">privacy notice</Link>.
      </p>

      <div className="card auth-card">
        {!sentTo ? (
          <>
            <div className="oauth-buttons">
              <button type="button" className="btn-oauth" onClick={() => oauth('github')}>
                Continue with GitHub
              </button>
              <button type="button" className="btn-oauth" onClick={() => oauth('google')}>
                Continue with Google
              </button>
            </div>
            <div className="divider" role="separator">
              <span>or use your email</span>
            </div>
            <form onSubmit={onEmailSubmit} className="connect-form auth-form" noValidate>
              <label>
                Email address
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  inputMode="email"
                  placeholder="you@example.com"
                  required
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? 'auth-error' : undefined}
                />
              </label>
              <button type="submit" disabled={busy || !email.trim()}>
                {busy ? 'Sending code…' : 'Email me a code'}
              </button>
            </form>
          </>
        ) : (
          <form onSubmit={onCodeSubmit} className="connect-form auth-form">
            <p className="otp-sent" aria-live="polite">
              We sent a 6-digit code to <strong>{sentTo}</strong>. It expires in 10 minutes.
            </p>
            <OtpInput
              digits={digits}
              onChange={onDigits}
              disabled={busy}
              invalid={Boolean(error)}
              describedBy={error ? 'auth-error' : undefined}
              autoFocus
            />
            <button type="submit" disabled={busy || !isComplete(digits)}>
              {busy ? 'Checking…' : 'Verify and continue'}
            </button>
            <div className="otp-actions">
              <button
                type="button"
                className="link-button"
                disabled={busy || secondsLeft > 0}
                onClick={() => sendCode(sentTo)}
              >
                {secondsLeft > 0 ? `Resend code in ${formatCountdown(secondsLeft)}` : 'Resend code'}
              </button>
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setSentTo(null)
                  setError(null)
                }}
              >
                Use a different email
              </button>
            </div>
          </form>
        )}

        <p id="auth-error" className="error auth-error" role="alert">
          {error}
        </p>
        {USE_MOCKS && <p className="hint">Mock mode: any email works, and the code is 123456.</p>}
      </div>
    </section>
  )
}
