import { useEffect, useRef, useState } from 'react'

export const VIDEO_SRC = '/videos/demo.mp4'

interface VideoModalProps {
  onClose: () => void
}

export default function VideoModal({ onClose }: VideoModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    dialogRef.current?.showModal()
  }, [])

  return (
    <dialog
      ref={dialogRef}
      className="video-modal"
      aria-label="视频演示"
      onClose={onClose}
      onClick={(e) => {
        // 点击遮罩时事件目标就是 dialog 自身，点击内容区则是子元素。
        if (e.target === e.currentTarget) dialogRef.current?.close()
      }}
    >
      <div className="video-modal-head">
        <h2>视频演示</h2>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => dialogRef.current?.close()}
        >
          关闭
        </button>
      </div>
      {failed ? (
        <p role="alert" className="video-modal-error">
          视频加载失败，请确认视频文件已正确挂载。
        </p>
      ) : (
        <video
          className="video-modal-player"
          src={VIDEO_SRC}
          controls
          preload="metadata"
          onError={() => setFailed(true)}
        />
      )}
    </dialog>
  )
}
