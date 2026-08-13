import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Send, Sparkles, X } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/ChatWidget.css'

function ChatWidget() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [quickInput, setQuickInput] = useState('')

  // Dragging state
  const [position, setPosition] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const isDraggingRef = useRef(false)
  const dragStartRef = useRef({ x: 0, y: 0 })
  const initialPosRef = useRef({ x: 0, y: 0 })
  const hasMovedRef = useRef(false)
  const widgetRef = useRef(null)

  const handleDragStart = (e) => {
    // Ignore right clicks
    if (e.type === 'mousedown' && e.button !== 0) return

    const clientX = e.touches ? e.touches[0].clientX : e.clientX
    const clientY = e.touches ? e.touches[0].clientY : e.clientY

    if (!widgetRef.current) return

    const rect = widgetRef.current.getBoundingClientRect()

    isDraggingRef.current = true
    hasMovedRef.current = false
    dragStartRef.current = { x: clientX, y: clientY }
    initialPosRef.current = { x: rect.left, y: rect.top }

    const onMove = (moveEvent) => {
      if (!isDraggingRef.current) return

      const curX = moveEvent.touches ? moveEvent.touches[0].clientX : moveEvent.clientX
      const curY = moveEvent.touches ? moveEvent.touches[0].clientY : moveEvent.clientY

      const deltaX = curX - dragStartRef.current.x
      const deltaY = curY - dragStartRef.current.y

      if (Math.abs(deltaX) > 4 || Math.abs(deltaY) > 4) {
        hasMovedRef.current = true
        setIsDragging(true)
      }

      if (!hasMovedRef.current) return

      let newX = initialPosRef.current.x + deltaX
      let newY = initialPosRef.current.y + deltaY

      const currentRect = widgetRef.current.getBoundingClientRect()
      const maxX = window.innerWidth - currentRect.width - 10
      const maxY = window.innerHeight - currentRect.height - 10
      newX = Math.max(10, Math.min(newX, maxX))
      newY = Math.max(10, Math.min(newY, maxY))

      setPosition({ x: newX, y: newY })
    }

    const onEnd = () => {
      isDraggingRef.current = false
      setIsDragging(false)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onEnd)
      window.removeEventListener('touchmove', onMove)
      window.removeEventListener('touchend', onEnd)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onEnd)
    window.addEventListener('touchmove', onMove)
    window.addEventListener('touchend', onEnd)
  }

  function openChat(prompt) {
    setIsOpen(false)
    navigate(`/chat?prompt=${encodeURIComponent(prompt)}`)
  }

  function handleTriggerClick() {
    if (hasMovedRef.current) return
    setIsOpen(true)
  }

  function handleQuickSend(event) {
    event.preventDefault()

    const prompt = quickInput.trim()
    if (!prompt) return

    setQuickInput('')
    openChat(prompt)
  }

  const dynamicStyle = position
    ? { left: `${position.x}px`, top: `${position.y}px`, right: 'auto', bottom: 'auto' }
    : {}

  return (
    <div
      ref={widgetRef}
      className={`chat-widget ${position ? 'chat-widget--custom-pos' : ''} ${
        isDragging ? 'chat-widget--dragging' : ''
      }`}
      style={dynamicStyle}
    >
      {!isOpen && (
        <button
          className="chat-widget__trigger"
          type="button"
          onMouseDown={handleDragStart}
          onTouchStart={handleDragStart}
          onClick={handleTriggerClick}
          title="Kéo để di chuyển"
        >
          <Sparkles className="chat-widget__trigger-icon" />
          <span className="chat-widget__trigger-label">{t.navAiChat}</span>
          <span className="chat-widget__status-dot" aria-hidden="true">
            <span className="chat-widget__status-ping" />
            <span className="chat-widget__status-core" />
          </span>
        </button>
      )}

      {isOpen && (
        <section className="chat-widget__panel" aria-label={t.navAiChat}>
          <header
            className="chat-widget__header chat-widget__header--draggable"
            onMouseDown={handleDragStart}
            onTouchStart={handleDragStart}
            title="Kéo để di chuyển"
          >
            <div className="chat-widget__identity">
              <div className="chat-widget__avatar">
                <Bot className="chat-widget__avatar-icon" />
              </div>
              <div>
                <h4 className="chat-widget__title">{t.chatWidgetTitle}</h4>
                <p className="chat-widget__online">
                  <span className="chat-widget__online-dot" />
                  {t.chatWidgetOnline}
                </p>
              </div>
            </div>

            <button
              className="chat-widget__close"
              type="button"
              aria-label="Close"
              onMouseDown={(e) => e.stopPropagation()}
              onTouchStart={(e) => e.stopPropagation()}
              onClick={() => setIsOpen(false)}
            >
              <X className="chat-widget__close-icon" />
            </button>
          </header>

          <div className="chat-widget__body">
            <div className="chat-widget__welcome">
              {t.chatWidgetWelcome}
              <div className="chat-widget__topics">
                {t.chatWidgetTopics}
              </div>
            </div>

            <div className="chat-widget__chips">
              <button
                className="chat-widget__chip"
                type="button"
                onClick={() =>
                  openChat(
                    'Recommend a 3-day luxury stay in Phu Quoc for 2 adults',
                  )
                }
              >
                {t.chatWidgetChipPhuQuoc}
              </button>
              <button
                className="chat-widget__chip"
                type="button"
                onClick={() =>
                  openChat('What are the child policies and extra bed fees?')
                }
              >
                {t.chatWidgetChipFamily}
              </button>
            </div>
          </div>

          <form className="chat-widget__form" onSubmit={handleQuickSend}>
            <input
              className="chat-widget__input"
              type="text"
              placeholder={t.chatWidgetPlaceholder}
              value={quickInput}
              onChange={(event) => setQuickInput(event.target.value)}
            />
            <button className="chat-widget__send" type="submit">
              <Send className="chat-widget__send-icon" />
            </button>
          </form>

          <button
            className="chat-widget__full-chat"
            type="button"
            onClick={() => {
              setIsOpen(false)
              navigate('/chat')
            }}
          >
            {t.chatWidgetOpenFull}
          </button>
        </section>
      )}
    </div>
  )
}

export default ChatWidget

