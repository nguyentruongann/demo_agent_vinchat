import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Loader2, Send, Sparkles, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import {
  clearStoredMessages,
  getChatStreamStatus,
  loadStoredMessages,
  saveStoredMessages,
  streamChatMessage,
} from '../services/api'
import RichMessage from './RichMessage'
import StructuredMessage from './StructuredMessage'
import '../styles/components/ChatWidget.css'

export function openAiChat(promptText) {
  window.dispatchEvent(new CustomEvent('open-ai-chat', { detail: { prompt: promptText } }))
}

function ChatWidget() {
  const { language, t } = useLanguage()
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [quickInput, setQuickInput] = useState('')
  const [messages, setMessages] = useState(() => {
    const storedMessages = loadStoredMessages()
    return Array.isArray(storedMessages) && storedMessages.length > 0
      ? storedMessages
      : []
  })
  const [loading, setLoading] = useState(false)
  const [receivingTokens, setReceivingTokens] = useState(false)
  const [streamStage, setStreamStage] = useState('understanding')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const previousUserIdRef = useRef(undefined)
  const requestControllerRef = useRef(null)

  useEffect(() => {
    async function handleOpenAiChat(event) {
      setIsOpen(true)
      const prompt = event.detail?.prompt
      if (!prompt) return

      const userMsg = {
        id: `user-${Date.now()}`,
        sender: 'user',
        text: prompt,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      setMessages((prev) => [...prev, userMsg])
      await runStreamingResponse(prompt)
    }

    window.addEventListener('open-ai-chat', handleOpenAiChat)
    return () => window.removeEventListener('open-ai-chat', handleOpenAiChat)
  }, [language, t.chatError])

  useEffect(() => {
    if (isOpen && messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [messages, loading, isOpen])

  // The input is disabled while the assistant is answering. Once the response
  // finishes (or the widget is opened), restore keyboard focus automatically so
  // the user can keep typing without clicking the input again.
  useEffect(() => {
    if (!isOpen || loading) return undefined

    const frame = window.requestAnimationFrame(() => {
      inputRef.current?.focus({ preventScroll: true })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [isOpen, loading])

  // Frontend-generated error messages should follow the selected UI language.
  // Real chat history remains untouched.
  useEffect(() => {
    setMessages((current) => {
      let changed = false
      const next = current.map((message) => {
        const isLocalError = message.localizationKey === 'chatError'
          || String(message.id || '').startsWith('err-')
        if (!isLocalError) return message
        if (message.text === t.chatError && message.language === language) return message
        changed = true
        return {
          ...message,
          text: t.chatError,
          language,
          localizationKey: 'chatError',
        }
      })
      return changed ? next : current
    })
  }, [language, t.chatError])

  useEffect(() => {
    if (authLoading || user) return
    if (messages.length > 0) {
      saveStoredMessages(messages)
    }
  }, [authLoading, messages, user])

  useEffect(() => {
    if (authLoading) return

    const previousUserId = previousUserIdRef.current
    const nextUserId = user?.id || null
    previousUserIdRef.current = nextUserId

    // Authenticated chat content belongs in PostgreSQL, not shared browser
    // sessionStorage. Also clear visible widget state when identity changes so
    // another account on the same browser never inherits the previous user's UI.
    if (user) {
      clearStoredMessages()
      if (previousUserId === undefined || (previousUserId && previousUserId !== user.id)) {
        setMessages([])
      }
      return
    }

    if (previousUserId) {
      clearStoredMessages()
      setMessages([])
    }
  }, [authLoading, user?.id])

  function handleTriggerClick() {
    setIsOpen(true)
  }

  async function runStreamingResponse(prompt) {
    const controller = new AbortController()
    requestControllerRef.current = controller
    const assistantId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    const assistantTimestamp = new Date().toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    })
    let responseStarted = false

    setStreamStage('understanding')
    setReceivingTokens(false)
    setLoading(true)

    try {
      const response = await streamChatMessage(prompt, language, {
        signal: controller.signal,
        messageId: assistantId,
        timestamp: assistantTimestamp,
        onStatus: setStreamStage,
        onDelta: (_delta, fullText) => {
          if (!responseStarted) {
            responseStarted = true
            setReceivingTokens(true)
            setMessages((current) => [
              ...current,
              {
                id: assistantId,
                sender: 'assistant',
                text: fullText,
                timestamp: assistantTimestamp,
                language,
                sources: [],
                relatedHotels: [],
                isStreaming: true,
              },
            ])
            return
          }

          setMessages((current) => current.map((message) => (
            message.id === assistantId
              ? { ...message, text: fullText }
              : message
          )))
        },
        onReplace: (finalText) => {
          setMessages((current) => current.map((message) => (
            message.id === assistantId
              ? { ...message, text: finalText }
              : message
          )))
        },
      })

      setMessages((current) => {
        if (!responseStarted) return [...current, response]
        return current.map((message) => (
          message.id === assistantId
            ? { ...response, id: assistantId, timestamp: assistantTimestamp, isStreaming: false }
            : message
        ))
      })
    } catch (error) {
      if (error?.name === 'AbortError') return
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'assistant',
          text: t.chatError,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          language,
          localizationKey: 'chatError',
          errorDetail: error instanceof Error ? error.message : String(error),
        },
      ])
    } finally {
      if (responseStarted) {
        setMessages((current) => current.map((message) => (
          message.id === assistantId
            ? { ...message, isStreaming: false }
            : message
        )))
      }
      requestControllerRef.current = null
      setReceivingTokens(false)
      setLoading(false)
    }
  }

  async function handleSend(promptText) {
    const prompt = (promptText || quickInput).trim()
    if (!prompt || loading) return

    setQuickInput('')

    const userMsg = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: prompt,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages((prev) => [...prev, userMsg])
    await runStreamingResponse(prompt)
  }

  function handleQuickSend(event) {
    event.preventDefault()
    handleSend()
  }

  return (
    <div className="chat-widget">
      {!isOpen && (
        <button
          className="chat-widget__trigger"
          type="button"
          onClick={handleTriggerClick}
          title={t.navAiChat}
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
          <header className="chat-widget__header">
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
              aria-label={t.close}
              onClick={() => {
                requestControllerRef.current?.abort()
                setIsOpen(false)
              }}
            >
              <X className="chat-widget__close-icon" />
            </button>
          </header>

          <div className="chat-widget__body">
            {messages.length === 0 ? (
              <>
                <div className="chat-widget__welcome">
                  {t.chatWidgetWelcome}
                  <div className="chat-widget__topics">{t.chatWidgetTopics}</div>
                </div>

                <div className="chat-widget__chips">
                  <button
                    className="chat-widget__chip"
                    type="button"
                    onClick={() =>
                      handleSend(t.chatPromptPhuQuoc)
                    }
                  >
                    {t.chatWidgetChipPhuQuoc}
                  </button>
                  <button
                    className="chat-widget__chip"
                    type="button"
                    onClick={() =>
                      handleSend(t.chatPromptFamily)
                    }
                  >
                    {t.chatWidgetChipFamily}
                  </button>
                </div>
              </>
            ) : (
              <div className="chat-widget__thread">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`chat-widget__msg chat-widget__msg--${msg.sender}`}
                  >
                    <div className="chat-widget__msg-bubble">
                      {msg.sender === 'user' ? (
                        <RichMessage text={msg.text} isUser />
                      ) : (
                        <StructuredMessage
                          text={msg.text}
                          sources={msg.sources}
                          showActions={false}
                        />
                      )}
                      <span className="chat-widget__msg-time">{msg.timestamp}</span>
                    </div>
                  </div>
                ))}
                {loading && !receivingTokens && (
                  <div className="chat-widget__msg chat-widget__msg--assistant">
                    <div className="chat-widget__msg-bubble chat-widget__msg-bubble--loading">
                      <Loader2 className="chat-widget__spinner" />
                      <span>{getChatStreamStatus(streamStage, language)}</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          <form className="chat-widget__form" onSubmit={handleQuickSend}>
            <input
              ref={inputRef}
              className="chat-widget__input"
              type="text"
              placeholder={t.chatWidgetPlaceholder}
              value={quickInput}
              onChange={(event) => setQuickInput(event.target.value)}
              disabled={loading}
            />
            <button className="chat-widget__send" type="submit" disabled={loading}>
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
