import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const stylesheetPath = resolve(process.cwd(), 'src/styles.css')
const stylesheet = existsSync(stylesheetPath)
  ? readFileSync(stylesheetPath, 'utf8')
  : ''

describe('workspace visual contract', () => {
  it('declares the approved percentage layout and viewport sizing', () => {
    expect(stylesheet).toContain('--sidebar-share: 22%')
    expect(stylesheet).toContain('--preview-share: 31%')
    expect(stylesheet).toContain('height: 100dvh')
    expect(stylesheet).toContain('grid-template-columns')
  })

  it('supports compact, mobile, focus and reduced-motion states', () => {
    expect(stylesheet).toContain('.sidebar-compact')
    expect(stylesheet).toContain('@media (max-width: 60rem)')
    expect(stylesheet).toContain('@media (prefers-reduced-motion: reduce)')
    expect(stylesheet).toContain(':focus-visible')
    expect(stylesheet).toContain('min-height: 44px')
  })

  it('uses the approved quiet palette without gradients', () => {
    expect(stylesheet.toLowerCase()).toContain('#e8ecef')
    expect(stylesheet).not.toMatch(/gradient\s*\(/i)
  })
})
