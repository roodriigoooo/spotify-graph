import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Panel, Bar, Readout, Marker } from './index'

describe('ascii kit (render)', () => {
  it('Panel shows its title and children', () => {
    render(<Panel title="ECHO · you ✕ sam">body text</Panel>)
    expect(screen.getByText(/ECHO/)).toBeInTheDocument()
    expect(screen.getByText('body text')).toBeInTheDocument()
  })

  it('Bar renders label, value, and a fill sized to the value', () => {
    const { container } = render(<Bar label="genre" value={0.62} />)
    expect(screen.getByText('genre')).toBeInTheDocument()
    expect(screen.getByText('0.62')).toBeInTheDocument()
    const fill = container.querySelector('.ascii-bar__fill') as HTMLElement
    expect(fill).toBeTruthy()
    expect(fill.style.width).toBe('62%')
  })

  it('Readout renders a dotted leader with the value', () => {
    render(<Readout label="match" value="73%" />)
    expect(screen.getByText('73%')).toBeInTheDocument()
  })

  it('Marker renders a pixel glyph (svg)', () => {
    const { container } = render(<Marker current intensity={1} />)
    expect(container.querySelector('svg')).toBeTruthy()
    expect(container.querySelectorAll('rect').length).toBeGreaterThan(0)
  })
})
