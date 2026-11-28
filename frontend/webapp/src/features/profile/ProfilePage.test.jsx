import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProfilePage } from './ProfilePage'
import { ToastProvider } from '@/components/ui/Toast'
import * as accounts from '@/api/accounts'
import { ApiError } from '@/api/errors'

const BASE_ME = {
  name: 'Pat Lee',
  email: 'pat@example.com',
  avatarColor: '#ff00ff',
  plansOwned: 1,
  plansJoined: 2,
  pendingEmail: '',
  emailReminders: true,
}

const logout = vi.fn().mockResolvedValue(undefined)

vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ logout }),
}))

vi.mock('@/api/accounts', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getMe: vi.fn().mockResolvedValue({
      name: 'Pat Lee',
      email: 'pat@example.com',
      avatarColor: '#ff00ff',
      plansOwned: 1,
      plansJoined: 2,
      pendingEmail: '',
      emailReminders: true,
    }),
    getReminderSettings: vi.fn().mockResolvedValue({ daysBefore: [3], email: true }),
    updateMe: vi.fn(),
    updateReminderSettings: vi.fn(),
    changePassword: vi.fn(),
    changeEmail: vi.fn(),
    resendEmailChange: vi.fn(),
    cancelEmailChange: vi.fn(),
    verifyEmail: vi.fn(),
    verifyEmailChange: vi.fn(),
  }
})

vi.mock('@/api/catalog', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getCategories: vi.fn().mockResolvedValue([]),
    getServiceNames: vi.fn().mockResolvedValue([]),
  }
})

beforeEach(() => {
  logout.mockClear()
  vi.mocked(accounts.getMe).mockResolvedValue(BASE_ME)
  vi.mocked(accounts.changeEmail).mockReset()
  vi.mocked(accounts.verifyEmail).mockReset()
  vi.mocked(accounts.verifyEmailChange).mockReset()
  vi.mocked(accounts.cancelEmailChange).mockReset()
  vi.mocked(accounts.resendEmailChange).mockReset()
  HTMLDialogElement.prototype.showModal = vi.fn(function showModal() {
    this.open = true
  })
  HTMLDialogElement.prototype.close = vi.fn(function close() {
    this.open = false
  })
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
  }
})

function wrap(ui) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ProfilePage account closure placement', () => {
  it('renders the closure section after catalog content', async () => {
    wrap(<ProfilePage />)
    const catalog = await screen.findByText(/categories and service names/i)
    const closeHeading = await screen.findByRole('heading', { name: /^close account$/i, level: 2 })
    expect(catalog.compareDocumentPosition(closeHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('button', { name: /close account…/i })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Pat Lee')).toBeInTheDocument())
  })
})

describe('ProfilePage email change', () => {
  const lockedEmail = () => screen.findByLabelText('Email')

  async function openChangeForm() {
    fireEvent.click(await screen.findByRole('button', { name: 'Change email' }))
    return screen.getByRole('form', { name: 'Change email' })
  }

  function fillAndSubmit(form, email = 'new@example.com', password = 'secret-pass-1') {
    fireEvent.change(within(form).getByLabelText('New email address'), { target: { value: email } })
    fireEvent.change(within(form).getByLabelText('Current password'), { target: { value: password } })
    fireEvent.click(within(form).getByRole('button', { name: /send verification link/i }))
  }

  it('shows the current email in a locked, read-only field', async () => {
    wrap(<ProfilePage />)
    const field = await lockedEmail()
    expect(field).toHaveValue('pat@example.com')
    expect(field).toHaveAttribute('readonly')
    expect(screen.queryByRole('form', { name: 'Change email' })).not.toBeInTheDocument()
  })

  it('reveals new-email and password fields when Change email is clicked', async () => {
    wrap(<ProfilePage />)
    const form = await openChangeForm()
    expect(within(form).getByLabelText('New email address')).toHaveValue('')
    expect(within(form).getByLabelText('Current password')).toHaveValue('')
  })

  it('shows the pending box only after the server accepts the request, keeping the old email', async () => {
    const pendingMe = { ...BASE_ME, pendingEmail: 'new@example.com' }
    vi.mocked(accounts.changeEmail).mockImplementation(async () => {
      vi.mocked(accounts.getMe).mockResolvedValue(pendingMe)
      return pendingMe
    })
    wrap(<ProfilePage />)
    const form = await openChangeForm()
    fillAndSubmit(form, '  New@Example.com ')

    const box = await screen.findByText('Waiting to verify new@example.com')
    expect(accounts.changeEmail).toHaveBeenCalledWith({ email: 'new@example.com', password: 'secret-pass-1' })
    const status = box.closest('[role="status"]')
    expect(status).toHaveTextContent(/stays active for login until the new address is verified/i)
    expect(await lockedEmail()).toHaveValue('pat@example.com')
    expect(screen.queryByRole('form', { name: 'Change email' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change email' })).not.toBeInTheDocument()
    expect(accounts.verifyEmail).not.toHaveBeenCalled()
    expect(accounts.verifyEmailChange).not.toHaveBeenCalled()
  })

  it('does not show a pending state when the request fails, and clears the password', async () => {
    vi.mocked(accounts.changeEmail).mockRejectedValue(
      new ApiError('The password is not correct.', { status: 400, code: 'invalid_password', fields: { password: 'The password is not correct.' } }),
    )
    wrap(<ProfilePage />)
    const form = await openChangeForm()
    fillAndSubmit(form, 'new@example.com', 'wrong-pass-1')

    expect(await within(form).findByText('The password is not correct.')).toBeInTheDocument()
    expect(within(form).getByLabelText('Current password')).toHaveValue('')
    expect(screen.queryByText(/waiting to verify/i)).not.toBeInTheDocument()
    expect(await lockedEmail()).toHaveValue('pat@example.com')
  })

  it('validates locally without calling the API', async () => {
    wrap(<ProfilePage />)
    const form = await openChangeForm()
    fillAndSubmit(form, 'pat@example.com', '')
    expect(within(form).getByText('That is already your email.')).toBeInTheDocument()
    expect(accounts.changeEmail).not.toHaveBeenCalled()
  })

  it('keeps showing the old email as the login email while a change is pending', async () => {
    vi.mocked(accounts.getMe).mockResolvedValue({ ...BASE_ME, pendingEmail: 'new@example.com' })
    wrap(<ProfilePage />)
    expect(await screen.findByText('Waiting to verify new@example.com')).toBeInTheDocument()
    const field = await lockedEmail()
    expect(field).toHaveValue('pat@example.com')
    expect(screen.getByText('You log in with this address.')).toBeInTheDocument()
  })

  it('removes the pending box when the change is cancelled', async () => {
    vi.mocked(accounts.getMe).mockResolvedValue({ ...BASE_ME, pendingEmail: 'new@example.com' })
    vi.mocked(accounts.cancelEmailChange).mockImplementation(async () => {
      vi.mocked(accounts.getMe).mockResolvedValue(BASE_ME)
      return BASE_ME
    })
    wrap(<ProfilePage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel change' }))
    expect(await screen.findByRole('button', { name: 'Change email' })).toBeInTheDocument()
    expect(screen.queryByText(/waiting to verify/i)).not.toBeInTheDocument()
  })

  it('starts the resend cooldown when the change request succeeds', async () => {
    const pendingMe = { ...BASE_ME, pendingEmail: 'new@example.com' }
    vi.mocked(accounts.changeEmail).mockImplementation(async () => {
      vi.mocked(accounts.getMe).mockResolvedValue(pendingMe)
      return pendingMe
    })
    wrap(<ProfilePage />)
    fillAndSubmit(await openChangeForm())
    expect(await screen.findByRole('timer', { name: 'Resend available in 60 seconds' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resend' })).toBeDisabled()
    expect(screen.getByText('Waiting to verify new@example.com')).toBeInTheDocument()
  })

  it('resends once, then shows the countdown and keeps the pending state', async () => {
    vi.mocked(accounts.getMe).mockResolvedValue({ ...BASE_ME, pendingEmail: 'new@example.com' })
    vi.mocked(accounts.resendEmailChange).mockResolvedValue({ sent: true })
    wrap(<ProfilePage />)
    const button = await screen.findByRole('button', { name: 'Resend' })
    expect(button).toBeEnabled()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()

    fireEvent.click(button)
    fireEvent.click(button)
    expect(await screen.findByText('Sent again to new@example.com.')).toBeInTheDocument()
    expect(accounts.resendEmailChange).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('timer', { name: 'Resend available in 60 seconds' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resend' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Resend' }))
    expect(accounts.resendEmailChange).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Waiting to verify new@example.com')).toBeInTheDocument()
    expect(await lockedEmail()).toHaveValue('pat@example.com')
  })

  it('uses the server Retry-After when resend is throttled', async () => {
    vi.mocked(accounts.getMe).mockResolvedValue({ ...BASE_ME, pendingEmail: 'new@example.com' })
    vi.mocked(accounts.resendEmailChange).mockRejectedValue(
      new ApiError('Request was throttled.', { status: 429, code: 'throttled', retryAfter: 120 }),
    )
    wrap(<ProfilePage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resend' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/throttled/i)
    const timer = screen.getByRole('timer', { name: 'Resend available in 120 seconds' })
    expect(timer.querySelector('.t-countdown')).toHaveTextContent('2:00')
    expect(screen.getByRole('button', { name: 'Resend' })).toBeDisabled()
    expect(screen.getByText('Waiting to verify new@example.com')).toBeInTheDocument()
  })

  it('refreshes the profile when the server says nothing is pending any more', async () => {
    vi.mocked(accounts.getMe).mockResolvedValue({ ...BASE_ME, pendingEmail: 'new@example.com' })
    vi.mocked(accounts.resendEmailChange).mockImplementation(async () => {
      vi.mocked(accounts.getMe).mockResolvedValue(BASE_ME)
      throw new ApiError('No pending email change.', { status: 400, code: 'nothing_pending' })
    })
    wrap(<ProfilePage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resend' }))
    expect(await screen.findByRole('button', { name: 'Change email' })).toBeInTheDocument()
    expect(screen.queryByText(/waiting to verify/i)).not.toBeInTheDocument()
  })

  it('after verification and a fresh login, shows the new email locked with no pending box', async () => {
    vi.mocked(accounts.getMe).mockResolvedValue({ ...BASE_ME, email: 'new@example.com', pendingEmail: '' })
    wrap(<ProfilePage />)
    const field = await lockedEmail()
    await waitFor(() => expect(field).toHaveValue('new@example.com'))
    expect(field).toHaveAttribute('readonly')
    expect(screen.queryByText(/waiting to verify/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change email' })).toBeInTheDocument()
  })
})