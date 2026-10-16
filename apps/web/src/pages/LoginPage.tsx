import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { accountApi, USE_MOCKS } from '../api/account'
import { useAuth } from '../auth/AuthContext'
import { codeOf, DEFAULT_RESEND_SECONDS, emptyCode, formatCountdown, isComplete, otpErrorMessage } from '../auth/otp'
import OtpInput from '../components/OtpInput'
import Icon, { type IconName } from '../ui/Icon'
import { Alert } from '../ui/kit'

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

const VALUES: { icon: IconName; title: string; body: string }[] = [
  { icon: 'ghost', title: 'No ghost jobs', body: 'Every listing is scored for real hiring intent before it reaches you.' },
  { icon: 'code', title: 'Proof, not claims', body: 'Your profile is built from the code you actually shipped on GitHub.' },
  { icon: 'shield', title: 'Nothing sent without you', body: 'You approve every application. Each one gets a signed consent receipt.' },
]

export default function LoginPage() {
  const { setMe } = useAuth()
  const [params] = useSearchParams()
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

  return (
    <div className="auth-layout">
      <section>
        <span className="eyebrow">
          <span className="eyebrow-dot" aria-hidden="true" />
          For engineers and students in India
        </span>
        <h1 className="hero-title">
          Apply to real jobs.
          <br />
          <span className="serif accent-text">Skip the ghosts.</span>
        </h1>
        <p className="hero-lede">
          Hire deals you a daily deck of verified openings, backs your application with proof from your GitHub, and
          tracks every reply. Swipe right to apply, left to pass.
        </p>
        <ul className="value-list">
          {VALUES.map((v) => (
            <li key={v.title}>
              <span className="value-icon">
                <Icon name={v.icon} size={18} />
              </span>
              <span>
                <strong>{v.title}</strong>
                <span>{v.body}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <div className="card auth-card">
        {!sentTo ? (
          <>
            <h2>Sign in or create an account</h2>
            <p className="muted small" style={{ marginTop: 6 }}>
              Just your email: we send you a 6-digit code, no password. New here? Setup takes about three minutes.
            </p>
            <div style={{ height: 22 }} />
            <form onSubmit={onEmailSubmit} className="form" noValidate>
              <label className="field">
                <span className="field-label">Email address</span>
                <input
                  className="input"
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
              <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || !email.trim()}>
                {busy ? 'Sending code…' : 'Email me a sign-in code'}
              </button>
            </form>
          </>
        ) : (
          <form onSubmit={onCodeSubmit} className="form">
            <div>
              <h2>Check your inbox</h2>
              <p className="muted small" style={{ marginTop: 6 }} aria-live="polite">
                We sent a 6-digit code to <strong style={{ color: 'var(--ink)' }}>{sentTo}</strong>. It expires in 10
                minutes.
              </p>
            </div>
            <OtpInput
              digits={digits}
              onChange={onDigits}
              disabled={busy}
              invalid={Boolean(error)}
              describedBy={error ? 'auth-error' : undefined}
              autoFocus
            />
            <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || !isComplete(digits)}>
              {busy ? 'Checking…' : 'Verify and continue'}
            </button>
            <div className="row-between small">
              <button type="button" className="link-btn" disabled={busy || secondsLeft > 0} onClick={() => sendCode(sentTo)}>
                {secondsLeft > 0 ? `Resend in ${formatCountdown(secondsLeft)}` : 'Resend code'}
              </button>
              <button
                type="button"
                className="link-btn"
                onClick={() => {
                  setSentTo(null)
                  setError(null)
                }}
              >
                Use another email
              </button>
            </div>
          </form>
        )}

        {error && (
          <div style={{ marginTop: 16 }}>
            <Alert tone="error" id="auth-error">
              {error}
            </Alert>
          </div>
        )}

        {USE_MOCKS ? (
          <p className="dev-note">Mock mode: any email works and the code is 123456.</p>
        ) : (
          import.meta.env.DEV &&
          sentTo && (
            <p className="dev-note">
              Running locally? No email is sent. Your code is in the API log:
              <br />
              <code>docker logs hire-api-1 2&gt;&amp;1 | findstr "DEV login code"</code>
            </p>
          )
        )}

        <p className="hint" style={{ marginTop: 18 }}>
          Before we collect anything beyond your sign-in, we show you our{' '}
          <Link to="/privacy" className="text-link">
            privacy notice
          </Link>
          .
        </p>
      </div>
    </div>
  )
}
