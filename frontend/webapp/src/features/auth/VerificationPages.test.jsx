import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from '@/api/errors'
import { RegisterPage } from './AuthPages'
import {
  EmailChangeVerifiedPage,
  RESEND_COOLDOWN_SECONDS,
  RegistrationCheckEmailPage,
  RegistrationVerifiedPage,
  VerifyEmailLinkPage,
} from './VerificationPages'

const register = vi.fn()
const verifyEmail = vi.fn()
const verifyEmailChange = vi.fn()
const resendVerification = vi.fn()
const endSession = vi.fn()

vi.mock('@/api/accounts', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    passwordRules: actual.passwordRules,
    register: (...args) => register(...args),
    verifyEmail: (...args) => verifyEmail(...args),
    verifyEmailChange: (...args) => verifyEmailChange(...args),
    resendVerification: (...args) => resendVerification(...args),
  }
})

vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ endSession }),
}))

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname + loc.search}</div>
}

function renderAt(url, client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/register/check-email" element={<RegistrationCheckEmailPage />} />
          <Route path="/verify-email" element={<VerifyEmailLinkPage />} />
          <Route path="/verify-email/confirm" element={<RegistrationVerifiedPage />} />
          <Route path="/email-change/confirm" element={<EmailChangeVerifiedPage />} />
          <Route path="/login" element={<h1>Log in page</h1>} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return client
}

const where = () => screen.getByTestId('where').textContent
const CHECK_EMAIL = { pathname: '/register/check-email', state: { email: 'pat@example.com' } }

beforeEach(() => {
  vi.clearAllMocks()
  register.mockImplementation(async ({ email }) => ({ email }))
  verifyEmail.mockResolvedValue({ verified: true })
  verifyEmailChange.mockResolvedValue({ email: 'new@example.com', verified: true })
  resendVerification.mockResolvedValue({ sent: true })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('registration journey', () => {
  it('navigates to the registration check-email page after sign-up', async () => {
    renderAt('/register')
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Pat Lee' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'pat@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct-horse-1' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'correct-horse-1' } })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByRole('heading', { name: /check your inbox/i })).toBeInTheDocument()
    expect(where()).toBe('/register/check-email')
    expect(screen.getByText('pat@example.com')).toBeInTheDocument()
  })

  it('moves an old ?email= check-email URL into history state and strips it from the URL', async () => {
    renderAt('/register/check-email?email=pat%40example.com')
    expect(await screen.findByText('pat@example.com')).toBeInTheDocument()
    expect(where()).toBe('/register/check-email')
    expect(screen.getByRole('button', { name: /resend verification email/i })).toBeInTheDocument()
  })

  it('without a known email (direct navigation) points to log in instead of offering resend', () => {
    renderAt('/register/check-email')
    expect(screen.getByRole('heading', { name: /check your inbox/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /resend/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /log in/i })).toHaveAttribute('href', '/login')
  })

  it('shows the server cooldown as a distinct number and disables resend until it ends', () => {
    vi.useFakeTimers()
    renderAt(CHECK_EMAIL)
    const button = screen.getByRole('button', { name: /resend verification email/i })
    expect(button).toBeDisabled()
    const timer = screen.getByRole('timer', { name: `Resend available in ${RESEND_COOLDOWN_SECONDS} seconds` })
    expect(timer.querySelector('.t-countdown')).toHaveTextContent(String(RESEND_COOLDOWN_SECONDS))

    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByRole('timer').querySelector('.t-countdown')).toHaveTextContent(String(RESEND_COOLDOWN_SECONDS - 1))
    fireEvent.click(button)
    expect(resendVerification).not.toHaveBeenCalled()

    for (let i = 1; i < RESEND_COOLDOWN_SECONDS; i += 1) act(() => vi.advanceTimersByTime(1000))
    expect(button).toBeEnabled()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
  })

  it('resends to the signed-up address and restarts the cooldown', async () => {
    vi.useFakeTimers()
    renderAt(CHECK_EMAIL)
    for (let i = 0; i < RESEND_COOLDOWN_SECONDS; i += 1) act(() => vi.advanceTimersByTime(1000))
    const button = screen.getByRole('button', { name: /resend verification email/i })
    fireEvent.click(button)
    fireEvent.click(button)
    vi.useRealTimers()

    expect(await screen.findByRole('status')).toHaveTextContent(/new link is on its way to pat@example.com/i)
    expect(resendVerification).toHaveBeenCalledTimes(1)
    expect(resendVerification).toHaveBeenCalledWith({ email: 'pat@example.com' })
    expect(screen.getByRole('timer', { name: `Resend available in ${RESEND_COOLDOWN_SECONDS} seconds` })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /resend verification email/i })).toBeDisabled()
  })

  it('uses the server Retry-After when resend is throttled', async () => {
    vi.useFakeTimers()
    resendVerification.mockRejectedValue(new ApiError('Request was throttled.', { status: 429, code: 'throttled', retryAfter: 1800 }))
    renderAt(CHECK_EMAIL)
    for (let i = 0; i < RESEND_COOLDOWN_SECONDS; i += 1) act(() => vi.advanceTimersByTime(1000))
    fireEvent.click(screen.getByRole('button', { name: /resend verification email/i }))
    vi.useRealTimers()

    expect(await screen.findByRole('alert')).toHaveTextContent(/throttled/i)
    const timer = screen.getByRole('timer', { name: 'Resend available in 1800 seconds' })
    expect(timer.querySelector('.t-countdown')).toHaveTextContent('30:00')
    expect(timer).toHaveTextContent(/minutes/)
    expect(screen.getByRole('button', { name: /resend verification email/i })).toBeDisabled()
  })

  it('has no "I verified" shortcut and never calls a verify endpoint while waiting', () => {
    renderAt(CHECK_EMAIL)
    expect(screen.queryByRole('button', { name: /verified/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /verified/i })).not.toBeInTheDocument()
    expect(verifyEmail).not.toHaveBeenCalled()
    expect(verifyEmailChange).not.toHaveBeenCalled()
  })

  it('routes a registration link to the registration endpoint only', async () => {
    renderAt('/verify-email?token=reg-token')
    await waitFor(() => expect(verifyEmail).toHaveBeenCalledWith({ token: 'reg-token' }))
    expect(verifyEmail).toHaveBeenCalledTimes(1)
    expect(verifyEmailChange).not.toHaveBeenCalled()
    expect(where()).toBe('/verify-email/confirm?token=reg-token')
  })

  it('shows the registration success page and its Log in button opens login', async () => {
    renderAt('/verify-email/confirm?token=reg-token')
    expect(await screen.findByRole('heading', { name: 'Email verified!' })).toBeInTheDocument()
    expect(screen.getByText(/email address has been verified/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /resend/i })).not.toBeInTheDocument()
    expect(endSession).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('link', { name: /^log in$/i }))
    expect(await screen.findByRole('heading', { name: 'Log in page' })).toBeInTheDocument()
  })

  it('does not show success for an invalid or expired registration link', async () => {
    verifyEmail.mockRejectedValue(new ApiError('Invalid or expired verification link.', { code: 'invalid_token' }))
    renderAt('/verify-email/confirm?token=bad')
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/i)
    expect(screen.queryByRole('heading', { name: 'Email verified!' })).not.toBeInTheDocument()
  })

  it('treats a registration confirm URL without a token as an error, without calling the API', () => {
    renderAt('/verify-email/confirm')
    expect(screen.getByRole('alert')).toHaveTextContent(/incomplete/i)
    expect(verifyEmail).not.toHaveBeenCalled()
  })

  it('redirects the old ?email= waiting URL to the check-email page', async () => {
    renderAt('/verify-email?email=signup%40example.com')
    expect(await screen.findByRole('heading', { name: /check your inbox/i })).toBeInTheDocument()
    expect(where()).toBe('/register/check-email')
    expect(screen.getByText('signup@example.com')).toBeInTheDocument()
  })
})

describe('email-change journey', () => {
  it('routes an email-change link to the email-change endpoint only', async () => {
    renderAt('/verify-email?type=email-change&token=abc123')
    await waitFor(() => expect(verifyEmailChange).toHaveBeenCalledWith({ token: 'abc123' }))
    expect(verifyEmailChange).toHaveBeenCalledTimes(1)
    expect(verifyEmail).not.toHaveBeenCalled()
    expect(where()).toBe('/email-change/confirm?token=abc123')
  })

  it('shows the separate success page with a Log in button that opens login', async () => {
    renderAt('/email-change/confirm?token=ok')
    expect(await screen.findByRole('heading', { name: 'Your new email has been verified!' })).toBeInTheDocument()
    expect(screen.getByText(/can now log in using your new email address/i)).toBeInTheDocument()
    expect(screen.getByText('new@example.com')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Email verified!' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: /^log in$/i }))
    expect(await screen.findByRole('heading', { name: 'Log in page' })).toBeInTheDocument()
  })

  it('ends the session and clears the query cache after success', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    client.setQueryData(['me'], { email: 'old@example.com' })
    renderAt('/email-change/confirm?token=ok', client)
    await screen.findByRole('heading', { name: 'Your new email has been verified!' })
    expect(endSession).toHaveBeenCalledTimes(1)
    expect(client.getQueryData(['me'])).toBeUndefined()
  })

  it.each([
    ['invalid_token', /invalid or has already been used/i],
    ['expired_token', /expired/i],
    ['email_change_stale', /no longer valid/i],
    ['email_taken', /already in use/i],
    ['account_inactive', /not active/i],
  ])('does not show success or end the session for %s', async (code, message) => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    client.setQueryData(['me'], { email: 'old@example.com' })
    verifyEmailChange.mockRejectedValue(new ApiError('nope', { code, status: 400 }))
    renderAt('/email-change/confirm?token=bad', client)
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('heading', { name: /could not verify your new email/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /has been verified/i })).not.toBeInTheDocument()
    expect(endSession).not.toHaveBeenCalled()
    expect(client.getQueryData(['me'])).toEqual({ email: 'old@example.com' })
  })

  it.each([
    ['throttled', new ApiError('Request was throttled.', { code: 'throttled', status: 429, retryAfter: 30 })],
    ['network', new ApiError('Could not reach Ongsho.', { status: 0 })],
  ])('keeps the session on %s errors', async (_, err) => {
    verifyEmailChange.mockRejectedValue(err)
    renderAt('/email-change/confirm?token=bad')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /has been verified/i })).not.toBeInTheDocument()
    expect(endSession).not.toHaveBeenCalled()
  })

  it('never falls through to registration for unknown link types', () => {
    renderAt('/verify-email?type=something-else&token=abc')
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(verifyEmail).not.toHaveBeenCalled()
    expect(verifyEmailChange).not.toHaveBeenCalled()
  })
})
