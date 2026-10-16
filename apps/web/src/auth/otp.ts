import { ApiError } from '../api/client'

// Pure state for the 6-box code input, kept apart from the component so the
// typing, paste and backspace rules can be unit tested.

export const OTP_LENGTH = 6
export const DEFAULT_RESEND_SECONDS = 30

export type OtpEdit = { digits: string[]; focus: number }

export const emptyCode = (): string[] => Array<string>(OTP_LENGTH).fill('')

const clampIndex = (i: number) => Math.max(0, Math.min(OTP_LENGTH - 1, i))

// Pasting (or autofilling) into box `index`: digits fill boxes from `index`
// onwards, anything that is not a digit is dropped.
export function applyOtpPaste(digits: string[], index: number, text: string): OtpEdit {
  const next = [...digits]
  const chars = text.replace(/\D/g, '').slice(0, OTP_LENGTH - index).split('')
  chars.forEach((c, offset) => {
    next[index + offset] = c
  })
  return { digits: next, focus: clampIndex(index + chars.length) }
}

// The new value of box `index` after a keystroke. One digit fills the box and
// moves on. A box that already held a digit reports old + new ("47" after
// typing 7 over 4), so keep the new one. Longer values are autofill: treat as
// a paste. Non-digits are ignored.
export function applyOtpInput(digits: string[], index: number, value: string): OtpEdit {
  const incoming = value.replace(/\D/g, '')
  if (!incoming) return { digits: [...digits], focus: index }
  if (incoming.length === 2 && digits[index]) {
    const typed = incoming[0] === digits[index] ? incoming[1] : incoming[0]
    const next = [...digits]
    next[index] = typed
    return { digits: next, focus: clampIndex(index + 1) }
  }
  return applyOtpPaste(digits, index, incoming)
}

// Backspace in box `index`: clear it, or step back and clear the previous box
// when it is already empty.
export function applyOtpBackspace(digits: string[], index: number): OtpEdit {
  const next = [...digits]
  if (next[index]) {
    next[index] = ''
    return { digits: next, focus: index }
  }
  const prev = clampIndex(index - 1)
  next[prev] = ''
  return { digits: next, focus: prev }
}

export const codeOf = (digits: string[]) => digits.join('')

export const isComplete = (digits: string[]) => digits.length === OTP_LENGTH && digits.every((d) => /^\d$/.test(d))

export function otpErrorMessage(err: unknown, phase: 'send' | 'verify'): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return 'Too many attempts. Wait a few minutes, then request a new code.'
    if (phase === 'verify' && [400, 401, 403, 422].includes(err.status)) {
      return 'That code is incorrect or has expired. Check the latest email, or request a new code.'
    }
    if (phase === 'send' && err.status === 422) return 'Enter a valid email address.'
    if (err.status >= 500) return 'Hire is having trouble right now. Try again in a moment.'
    return err.message
  }
  return 'Could not reach Hire. Check your connection and try again.'
}

export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
