import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LoginPage } from './AuthPages'
import { RegistrationCheckEmailPage } from './VerificationPages'
import { ApiError } from '@/api/errors'

const login = vi.fn()

vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ login }),
}))

function wrap(ui) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={ui} />
          <Route path="/register/check-email" element={<RegistrationCheckEmailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function submit(email) {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret-pass-1' } })
  fireEvent.click(screen.getByRole('button', { name: /log in/i }))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LoginPage', () => {
  it('links an unverified account to the registration check-email page', async () => {
    login.mockRejectedValue(new ApiError('Verify your email before signing in.', { status: 403, code: 'email_not_verified' }))
    wrap(<LoginPage />)
    submit('pat@example.com')
    const link = await screen.findByRole('link', { name: /send a new verification email/i })
    expect(link).toHaveAttribute('href', '/register/check-email')
    fireEvent.click(link)
    expect(await screen.findByRole('heading', { name: /check your inbox/i })).toBeInTheDocument()
    expect(screen.getByText('pat@example.com')).toBeInTheDocument()
  })

  it('does not offer the verification link for wrong credentials', async () => {
    login.mockRejectedValue(new ApiError('Invalid email or password.', { status: 401, code: 'invalid_credentials' }))
    wrap(<LoginPage />)
    submit('pat@example.com')
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid email or password/i)
    expect(screen.queryByRole('link', { name: /send a new verification email/i })).not.toBeInTheDocument()
  })
})
