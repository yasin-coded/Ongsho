import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProfilePage } from './ProfilePage'
import { ToastProvider } from '@/components/ui/Toast'

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