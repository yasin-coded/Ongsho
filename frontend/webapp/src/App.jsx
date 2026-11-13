import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router'
import { ToastProvider } from '@/components/ui/Toast'
import { forceMockMode } from '@/api/modes'
import { router } from './routes'

const liveApi = !forceMockMode()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: liveApi,
      refetchOnReconnect: liveApi,
      retry: (count, err) => (err?.status === 0 || !err?.status) && count < 1,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  )
}
