import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from 'react'
import { applyOtpBackspace, applyOtpInput, applyOtpPaste, OTP_LENGTH, type OtpEdit } from '../auth/otp'

type Props = {
  digits: string[]
  onChange: (digits: string[]) => void
  disabled?: boolean
  invalid?: boolean
  describedBy?: string
  autoFocus?: boolean
}

// Six single-digit boxes in one fieldset. Typing advances, Backspace steps back,
// arrows move, and a pasted or autofilled code fills every box.
export default function OtpInput({ digits, onChange, disabled, invalid, describedBy, autoFocus }: Props) {
  const refs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (autoFocus) refs.current[0]?.focus()
  }, [autoFocus])

  function apply(edit: OtpEdit) {
    onChange(edit.digits)
    refs.current[edit.focus]?.focus()
  }

  function onKeyDown(index: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Backspace') {
      e.preventDefault()
      apply(applyOtpBackspace(digits, index))
    } else if (e.key === 'ArrowLeft' && index > 0) {
      e.preventDefault()
      refs.current[index - 1]?.focus()
    } else if (e.key === 'ArrowRight' && index < OTP_LENGTH - 1) {
      e.preventDefault()
      refs.current[index + 1]?.focus()
    }
  }

  function onPaste(index: number, e: ClipboardEvent<HTMLInputElement>) {
    e.preventDefault()
    apply(applyOtpPaste(digits, index, e.clipboardData.getData('text')))
  }

  return (
    <fieldset className="otp-fieldset" disabled={disabled}>
      <legend>6-digit code</legend>
      <div className="otp-boxes">
        {digits.map((digit, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el
            }}
            className="otp-box"
            value={digit}
            inputMode="numeric"
            pattern="[0-9]*"
            autoComplete={i === 0 ? 'one-time-code' : 'off'}
            aria-label={`Digit ${i + 1} of ${OTP_LENGTH}`}
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
            onFocus={(e) => e.currentTarget.select()}
            onChange={(e) => apply(applyOtpInput(digits, i, e.currentTarget.value))}
            onKeyDown={(e) => onKeyDown(i, e)}
            onPaste={(e) => onPaste(i, e)}
          />
        ))}
      </div>
    </fieldset>
  )
}
