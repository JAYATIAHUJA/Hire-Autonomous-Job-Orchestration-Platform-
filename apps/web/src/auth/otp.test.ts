import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import {
  applyOtpBackspace,
  applyOtpInput,
  applyOtpPaste,
  codeOf,
  emptyCode,
  formatCountdown,
  isComplete,
  otpErrorMessage,
} from './otp'

const filled = (code: string) => code.padEnd(6, ' ').split('').map((c) => (c === ' ' ? '' : c))

describe('applyOtpInput', () => {
  it('fills a box and moves focus to the next one', () => {
    expect(applyOtpInput(emptyCode(), 0, '4')).toEqual({ digits: filled('4'), focus: 1 })
  })

  it('keeps focus on the last box', () => {
    expect(applyOtpInput(filled('12345'), 5, '6')).toEqual({ digits: filled('123456'), focus: 5 })
  })

  it('ignores non-digits', () => {
    expect(applyOtpInput(emptyCode(), 2, 'a')).toEqual({ digits: emptyCode(), focus: 2 })
  })

  it('overtyping a filled box keeps the new digit', () => {
    expect(applyOtpInput(filled('4'), 0, '47').digits[0]).toBe('7')
    expect(applyOtpInput(filled('4'), 0, '74').digits[0]).toBe('7')
    expect(applyOtpInput(filled('4'), 0, '44').digits[0]).toBe('4')
  })

  it('treats a long value as autofill', () => {
    expect(applyOtpInput(emptyCode(), 0, '123456')).toEqual({ digits: filled('123456'), focus: 5 })
  })
})

describe('applyOtpPaste', () => {
  it('spreads a pasted code across the boxes, dropping spaces and dashes', () => {
    expect(applyOtpPaste(emptyCode(), 0, ' 123-456 ')).toEqual({ digits: filled('123456'), focus: 5 })
  })

  it('fills from the focused box and drops what does not fit', () => {
    expect(applyOtpPaste(filled('12'), 2, '98765')).toEqual({ digits: filled('129876'), focus: 5 })
  })

  it('a paste with no digits changes nothing', () => {
    expect(applyOtpPaste(filled('1'), 1, 'abc')).toEqual({ digits: filled('1'), focus: 1 })
  })
})

describe('applyOtpBackspace', () => {
  it('clears the current box when it has a digit', () => {
    expect(applyOtpBackspace(filled('123'), 2)).toEqual({ digits: filled('12'), focus: 2 })
  })

  it('steps back and clears the previous box when the current one is empty', () => {
    expect(applyOtpBackspace(filled('12'), 2)).toEqual({ digits: filled('1'), focus: 1 })
  })

  it('stays on the first box', () => {
    expect(applyOtpBackspace(emptyCode(), 0)).toEqual({ digits: emptyCode(), focus: 0 })
  })
})

describe('code helpers', () => {
  it('is complete only with six digits', () => {
    expect(isComplete(filled('123456'))).toBe(true)
    expect(isComplete(filled('12345'))).toBe(false)
    expect(codeOf(filled('123456'))).toBe('123456')
  })

  it('formats the resend countdown', () => {
    expect(formatCountdown(30)).toBe('0:30')
    expect(formatCountdown(65)).toBe('1:05')
    expect(formatCountdown(-3)).toBe('0:00')
  })
})

describe('otpErrorMessage', () => {
  it('maps API errors to plain messages', () => {
    expect(otpErrorMessage(new ApiError('x', 429), 'verify')).toMatch(/Too many attempts/)
    expect(otpErrorMessage(new ApiError('x', 400), 'verify')).toMatch(/incorrect or has expired/)
    expect(otpErrorMessage(new ApiError('x', 422), 'send')).toBe('Enter a valid email address.')
    expect(otpErrorMessage(new ApiError('x', 503), 'send')).toMatch(/trouble/)
    expect(otpErrorMessage(new TypeError('Failed to fetch'), 'send')).toMatch(/Could not reach/)
  })
})
