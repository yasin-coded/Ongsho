import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AccountCloseSection, CloseAccountModal } from './CloseAccountModal'
import { ApiError } from '@/api/http'
import { ACCOUNT_CLOSE_ERROR_MESSAGES } from '@/lib/accountCloseErrors'
import { ToastProvider } from '@/components/ui/Toast'

const closeAccount = vi.fn()
const endSession = vi.fn()
const navigate = vi.fn()

vi.mock('@/api/accounts', () => ({
  closeAccount: (...args) => closeAccount(...args),
}))

vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ endSession }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useNavigate: () => navigate,
  }
})

beforeEach(() => {
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

async function submitClose(user, password = 'pass12345') {
  await user.type(screen.getByLabelText(/current password/i), password)
  await user.click(screen.getByRole('button', { name: /^close account$/i }))
}

describe('AccountCloseSection', () => {
  beforeEach(() => {
    closeAccount.mockReset()
    endSession.mockReset()
    navigate.mockReset()
  })

  it('renders the account closure section', () => {
    wrap(<AccountCloseSection />)
    expect(screen.getByRole('heading', { name: /close account/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /close account…/i })).toBeInTheDocument()
  })

  it('opens and closes the confirmation dialog without calling the API', async () => {
    const user = userEvent.setup()
    wrap(<AccountCloseSection />)
    await user.click(screen.getByRole('button', { name: /close account…/i }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^cancel$/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(closeAccount).not.toHaveBeenCalled()
  })
})

describe('CloseAccountModal', () => {
  beforeEach(() => {
    closeAccount.mockReset()
    endSession.mockReset()
    navigate.mockReset()
  })

  it('rejects empty password client-side', async () => {
    const user = userEvent.setup()
    wrap(<CloseAccountModal open onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: /^close account$/i }))
    expect(closeAccount).not.toHaveBeenCalled()
    expect(await screen.findByText(/enter your password/i)).toBeInTheDocument()
  })

  it('sends password on success and clears session without logout', async () => {
    const user = userEvent.setup()
    closeAccount.mockResolvedValue({ closed: true })
    const onClose = vi.fn()
    wrap(<CloseAccountModal open onClose={onClose} />)
    await user.type(screen.getByLabelText(/current password/i), 'pass12345')
    await user.click(screen.getByRole('button', { name: /^close account$/i }))
    await waitFor(() => expect(closeAccount).toHaveBeenCalledWith({ password: 'pass12345' }))
    expect(closeAccount.mock.calls[0][0]).not.toHaveProperty('userId')
    expect(endSession).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalled()
    expect(navigate).toHaveBeenCalledWith('/login?reason=account-closed', { replace: true })
  })

  it('shows mapped field error for invalid_password', async () => {
    const user = userEvent.setup()
    closeAccount.mockRejectedValue(
      new ApiError(ACCOUNT_CLOSE_ERROR_MESSAGES.invalid_password, {
        status: 400,
        code: 'invalid_password',
        fields: { password: ACCOUNT_CLOSE_ERROR_MESSAGES.invalid_password },
      }),
    )
    wrap(<CloseAccountModal open onClose={() => {}} />)
    await submitClose(user)
    expect(await screen.findByText(ACCOUNT_CLOSE_ERROR_MESSAGES.invalid_password)).toBeInTheDocument()
    expect(endSession).not.toHaveBeenCalled()
  })

  it('shows mapped message for lockout', async () => {
    const user = userEvent.setup()
    closeAccount.mockRejectedValue(
      new ApiError(ACCOUNT_CLOSE_ERROR_MESSAGES.locked, { status: 429, code: 'locked' }),
    )
    wrap(<CloseAccountModal open onClose={() => {}} />)
    await submitClose(user)
    await waitFor(() => expect(closeAccount).toHaveBeenCalled())
    expect(await screen.findByText(ACCOUNT_CLOSE_ERROR_MESSAGES.locked)).toBeInTheDocument()
    expect(endSession).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it.each([
    ['staff_cannot_close', 403],
    ['account_already_closed', 409],
    ['pending_ownership_transfer', 409],
    ['owned_plans_remain', 409],
    ['active_membership', 409],
    ['tombstone_collision', 409],
  ])('shows mapped blocker toast for %s', async (code, status) => {
    const user = userEvent.setup()
    const message = ACCOUNT_CLOSE_ERROR_MESSAGES[code]
    closeAccount.mockRejectedValue(new ApiError(message, { status, code }))
    wrap(<CloseAccountModal open onClose={() => {}} />)
    await submitClose(user)
    await waitFor(() => expect(closeAccount).toHaveBeenCalled())
    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(endSession).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('shows connection error toast without clearing session', async () => {
    const user = userEvent.setup()
    closeAccount.mockRejectedValue(
      new ApiError('Could not reach Ongsho. Check your connection and try again.', { status: 0 }),
    )
    wrap(<CloseAccountModal open onClose={() => {}} />)
    await submitClose(user)
    expect(await screen.findByText(/could not reach ongsho/i)).toBeInTheDocument()
    expect(endSession).not.toHaveBeenCalled()
  })

  it('shows generic server failure toast without success redirect', async () => {
    const user = userEvent.setup()
    closeAccount.mockRejectedValue(new ApiError('Something went wrong. Try again.', { status: 500, code: 'server_error' }))
    wrap(<CloseAccountModal open onClose={() => {}} />)
    await submitClose(user)
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
    expect(endSession).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('prevents duplicate submission while busy', async () => {
    const user = userEvent.setup()
    let resolve
    closeAccount.mockReturnValue(new Promise((r) => { resolve = r }))
    wrap(<CloseAccountModal open onClose={() => {}} />)
    await user.type(screen.getByLabelText(/current password/i), 'pass12345')
    const submit = screen.getByRole('button', { name: /^close account$/i })
    await user.click(submit)
    await user.click(submit)
    expect(closeAccount).toHaveBeenCalledTimes(1)
    resolve({ closed: true })
  })
})