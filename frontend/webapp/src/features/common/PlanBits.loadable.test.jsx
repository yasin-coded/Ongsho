import React from 'react'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Loadable } from './PlanBits'

describe('Loadable skeleton vs stale data', () => {
  it('shows skeleton only on first pending load without cached data', () => {
    const skeleton = <div data-testid="layout-skeleton">Loading layout</div>
    const { rerender } = render(
      <Loadable query={{ isPending: true, data: undefined, isError: false }} skeleton={skeleton}>
        {(data) => <div data-testid="live">{data.ok}</div>}
      </Loadable>,
    )
    expect(screen.getByTestId('layout-skeleton')).toBeInTheDocument()
    expect(screen.queryByTestId('live')).not.toBeInTheDocument()

    rerender(
      <Loadable query={{ isPending: true, data: { ok: 'cached' }, isError: false }} skeleton={skeleton}>
        {(data) => <div data-testid="live">{data.ok}</div>}
      </Loadable>,
    )
    expect(screen.queryByTestId('layout-skeleton')).not.toBeInTheDocument()
    expect(screen.getByTestId('live')).toHaveTextContent('cached')
  })
})