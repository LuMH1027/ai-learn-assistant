import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import FilePreview from './FilePreview.vue'
import { usePreviewStore } from '../stores/preview'
import type { FileLeafNode } from '../types/api'

function file(extension: string): FileLeafNode {
  return {
    id: `lesson${extension}`,
    name: `lesson${extension}`,
    path: `/courses/lesson${extension}`,
    type: 'file',
    extension,
    size: 128,
  }
}

function mountPreview(extension: string, content: string) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const preview = usePreviewStore()
  preview.activeFile = file(extension)
  preview.content = content
  return mount(FilePreview, { global: { plugins: [pinia] } })
}

describe('FilePreview', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('renders Markdown structure instead of showing its source syntax', () => {
    const wrapper = mountPreview('.md', [
      '# 进程调度',
      '',
      '- 先来先服务',
      '- 时间片轮转',
      '',
      '| 算法 | 特点 |',
      '| --- | --- |',
      '| RR | 公平 |',
      '',
      '```ts',
      'const quantum = 10',
      '```',
    ].join('\n'))

    expect(wrapper.get('.markdown-preview h1').text()).toBe('进程调度')
    expect(wrapper.findAll('.markdown-preview li')).toHaveLength(2)
    expect(wrapper.get('.markdown-preview table').text()).toContain('RR')
    expect(wrapper.get('.markdown-preview pre code').text()).toContain('const quantum = 10')
  })

  it('sanitizes unsafe HTML embedded in Markdown', () => {
    const wrapper = mountPreview(
      '.markdown',
      '# 安全内容\n\n<script>alert(1)</script><img src=x onerror="alert(2)">',
    )

    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.get('.markdown-preview img').attributes('onerror')).toBeUndefined()
  })

  it('keeps plain text in a preformatted element', () => {
    const wrapper = mountPreview('.txt', '# 这不是标题')

    expect(wrapper.find('.markdown-preview').exists()).toBe(false)
    expect(wrapper.get('pre').text()).toBe('# 这不是标题')
  })
})
