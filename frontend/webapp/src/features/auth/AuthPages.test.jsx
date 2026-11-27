import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { VerifyEmailPage } from './AuthPages'
import { ApiError } from '@/api/errors'

const verifyEmail = vi.fn()
const verifyEmailChange = vi.fn()
const resendVerification = vi.fn()
const endSession = vi.fn()

vi.mock('@/api/accounts', () => ({
  verifyEmail: (...args) => verifyEmail(...args),
  verifyEmailChange: (...args) => verifyEmailChange(...args),
  resendVerification: (...args) => resendVerification(...args),
}))

vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ endSession }),
}))

function wrap(ui, initialEntries) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  verifyEmail.mockResolvedValue({ verified: true })
  verifyEmailChange.mockResolvedValue({ email: 'new@example.com', verified: true })
  resendVerification.mockResolvedValue({ sent: true })
})

describe('VerifyEmailPage', () => {
  it('calls verifyEmailChange when type is email-change', async () => {
    wrap(<VerifyEmailPage />, ['/verify-email?type=email-change&token=abc123'])
    await waitFor(() => expect(verifyEmailChange).toHaveBeenCalledWith({ token: 'abc123' }))
    expect(verifyEmail).not.toHaveBeenCalled()
  })

  it('calls verifyEmail for registration links', async () => {
    wrap(<VerifyEmailPage />, ['/verify-email?token=reg-token'])
    await waitFor(() => expect(verifyEmail).toHaveBeenCalledWith({ token: 'reg-token' }))
    expect(verifyEmailChange).not.toHaveBeenCalled()
  })

  it('shows email-change success copy and login action', async () => {
    wrap(<VerifyEmailPage />, ['/verify-email?type=email-change&token=ok'])
    expect(await screen.findByRole('heading', { name: /email address updated successfully/i })).toBeInTheDocument()
    expect(screen.getByText(/new@example.com/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^log in$/i })).toHaveAttribute('href', '/login')
    expect(screen.queryByRole('button', { name: /resend/i })).not.toBeInTheDocument()
  })

  it('clears client session after successful email-change verification', async () => {
    wrap(<VerifyEmailPage />, ['/verify-email?type=email-change&token=ok'])
    await screen.findByRole('heading', { name: /email address updated successfully/i })
    expect(endSession).toHaveBeenCalledTimes(1)
  })

  it('shows mapped error for stale email-change links', async () => {
    verifyEmailChange.mockRejectedValue(
      new ApiError('stale', { code: 'email_change_stale', status: 400 }),
    )
    wrap(<VerifyEmailPage />, ['/verify-email?type=email-change&token=stale'])
    expect(await screen.findByRole('alert')).toHaveTextContent(/no longer valid/i)
  })

  it('keeps registration resend UI when only email param is present', () => {
    wrap(<VerifyEmailPage />, ['/verify-email?email=signup%40example.com'])
    expect(screen.getByRole('button', { name: /resend/i })).toBeInTheDocument()
    expect(verifyEmail).not.toHaveBeenCalled()
    expect(verifyEmailChange).not.toHaveBeenCalled()
  })
})