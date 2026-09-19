import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import VideoModal, { VIDEO_SRC } from '../components/VideoModal'

function dialog(): HTMLDialogElement {
  return document.querySelector('dialog') as HTMLDialogElement
}

describe('VideoModal', () => {
  it('opens as a modal dialog and renders the player', () => {
    render(<VideoModal onClose={vi.fn()} />)

    expect(dialog()).toHaveAttribute('open')
    expect(dialog()).toHaveAttribute('aria-label', '视频演示')
    const player = dialog().querySelector('video') as HTMLVideoElement
    expect(player).toHaveAttribute('src', VIDEO_SRC)
    expect(player).toHaveAttribute('controls')
    expect(player).toHaveAttribute('preload', 'metadata')
  })

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<VideoModal onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: '关闭' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when the backdrop is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<VideoModal onClose={onClose} />)

    await user.click(dialog())

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('stays open when the dialog content is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<VideoModal onClose={onClose} />)

    await user.click(screen.getByRole('heading', { name: '视频演示' }))

    expect(onClose).not.toHaveBeenCalled()
  })

  it('shows a failure message instead of the player when the video errors', () => {
    render(<VideoModal onClose={vi.fn()} />)

    fireEvent.error(dialog().querySelector('video') as HTMLVideoElement)

    expect(screen.getByRole('alert')).toHaveTextContent('视频加载失败')
    expect(dialog().querySelector('video')).not.toBeInTheDocument()
  })
})
