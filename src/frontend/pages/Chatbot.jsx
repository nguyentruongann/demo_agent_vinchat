import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Bot,
  Headphones,
  History,
  RotateCcw,
  Send,
  ShieldAlert,
  User,
} from 'lucide-react'
import ChatHistorySidebar from '../components/ChatHistorySidebar'
import HotelCard from '../components/HotelCard'
import RichMessage from '../components/RichMessage'
import StructuredMessage from '../components/StructuredMessage'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import {
  clearStoredMessages,
  fetchChatSessionMessages,
  fetchChatSessions,
  getChatSessionId,
  loadStoredMessages,
  saveStoredMessages,
  sendChatMessage,
  setChatSessionId,
  startNewChatSession,
} from '../services/api'
import '../styles/pages/Chatbot.css'

const CHAT_DRAFT_KEY = 'vinpearl_chat_draft_v2'

// Only frontend-generated/system messages should follow the current UI locale.
// Real user/assistant conversation history must stay in the language it was sent in.
const LOCAL_SYSTEM_MESSAGE_KEYS = {
  'msg-welcome': 'chatbotWelcome',
  'msg-reset': 'chatbotReset',
  'msg-logout': 'chatbotWelcome',
  'msg-empty-history': 'chatbotWelcome',
  'msg-login': 'chatbotWelcome',
}

function localSystemMessageKey(message) {
  if (message?.localizationKey) return message.localizationKey
  if (LOCAL_SYSTEM_MESSAGE_KEYS[message?.id]) return LOCAL_SYSTEM_MESSAGE_KEYS[message.id]
  if (message?.isError || String(message?.id || '').startsWith('error-')) return 'assistantUnavailable'
  if (String(message?.id || '').startsWith('err-')) return 'chatError'
  return null
}

function localizeSystemMessages(messages, translations, language) {
  let changed = false
  const nextMessages = messages.map((message) => {
    const localizationKey = localSystemMessageKey(message)
    if (!localizationKey || !translations[localizationKey]) return message

    const nextText = translations[localizationKey]
    if (
      message.text === nextText
      && message.language === language
      && message.localizationKey === localizationKey
    ) {
      return message
    }

    changed = true
    return {
      ...message,
      text: nextText,
      language,
      localizationKey,
    }
  })

  return changed ? nextMessages : messages
}

function displayTime(value) {
  const date = value ? new Date(value) : new Date()
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function historyMessageToUi(message) {
  return {
    id: `history-${message.id}`,
    sender: message.role === 'user' ? 'user' : 'assistant',
    text: message.content,
    timestamp: displayTime(message.created_at),
    language: message.language || 'unknown',
    route: message.route,
    ticketId: message.ticket_id,
    sources: [],
    relatedHotels: [],
  }
}

function loadStoredDraft() {
  try {
    return sessionStorage.getItem(CHAT_DRAFT_KEY) || ''
  } catch {
    return ''
  }
}

function saveStoredDraft(value) {
  try {
    sessionStorage.setItem(CHAT_DRAFT_KEY, value)
  } catch {
    // Ignore storage failures; chat still works without draft persistence.
  }
}

function clearStoredDraft() {
  try {
    sessionStorage.removeItem(CHAT_DRAFT_KEY)
  } catch {
    // Ignore storage failures.
  }
}

function historyButtonLabel(language) {
  return {
    en: 'History',
    vi: 'Lịch sử',
    ko: '기록',
    ja: '履歴',
    zh: '记录',
  }[language] || 'History'
}

function newChatLabel(language) {
  return {
    en: 'New chat',
    vi: 'Chat mới',
    ko: '새 채팅',
    ja: '新しいチャット',
    zh: '新对话',
  }[language] || 'New chat'
}

function closeHistoryLabel(language) {
  return {
    en: 'Close chat history',
    vi: 'Đóng lịch sử chat',
    ko: '채팅 기록 닫기',
    ja: 'チャット履歴を閉じる',
    zh: '关闭聊天记录',
  }[language] || 'Close chat history'
}

function Chatbot() {
  const { language, t } = useLanguage()
  const { user, loading: authLoading } = useAuth()
  const [searchParams] = useSearchParams()
  const initialPrompt = searchParams.get('prompt') || ''
  const handledPromptRef = useRef(null)
  const messagesContainerRef = useRef(null)
  const inputRef = useRef(null)
  const previousUserIdRef = useRef(undefined)

  function createSystemMessage(id, localizationKey = 'chatbotWelcome') {
    return {
      id,
      sender: 'assistant',
      text: t[localizationKey] || t.chatbotWelcome,
      timestamp: displayTime(),
      language,
      localizationKey,
    }
  }

  const [messages, setMessages] = useState(() => {
    const storedMessages = loadStoredMessages()
    if (Array.isArray(storedMessages) && storedMessages.length > 0) {
      return storedMessages
    }
    return [createSystemMessage('msg-welcome')]
  })
  const [input, setInput] = useState(() => loadStoredDraft())
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(() => getChatSessionId())
  const [conversationReady, setConversationReady] = useState(false)

  useEffect(() => {
    const messagesContainer = messagesContainerRef.current
    if (!messagesContainer) return

    messagesContainer.scrollTo({
      top: messagesContainer.scrollHeight,
      behavior: messages.length > 1 ? 'smooth' : 'auto',
    })
  }, [messages, loading])

  // While the assistant is responding, the input is intentionally disabled.
  // Restore focus as soon as it becomes available again so users can continue
  // the conversation without an extra mouse click.
  useEffect(() => {
    if (loading || !conversationReady) return undefined

    const frame = window.requestAnimationFrame(() => {
      inputRef.current?.focus({ preventScroll: true })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [loading, conversationReady])

  // Keep only local/system UI messages synchronized with the selected language.
  // This also upgrades old sessionStorage messages created before localizationKey existed.
  useEffect(() => {
    setMessages((current) => localizeSystemMessages(current, t, language))
  }, [language, t.chatbotWelcome, t.chatbotReset, t.assistantUnavailable, t.chatError])

  // Guest chats may be restored from sessionStorage. Authenticated chats are
  // restored from PostgreSQL instead, which prevents account A's visible chat
  // content from leaking into account B on a shared browser.
  useEffect(() => {
    if (authLoading) return
    if (!user) saveStoredMessages(messages)
  }, [authLoading, messages, user])

  useEffect(() => {
    saveStoredDraft(input)
  }, [input])

  useEffect(() => {
    if (authLoading) return undefined

    let cancelled = false
    setConversationReady(false)

    async function syncConversationForAuthState() {
      const previousUserId = previousUserIdRef.current
      const nextUserId = user?.id || null
      previousUserIdRef.current = nextUserId

      if (!user) {
        setSessions([])
        setHistoryOpen(false)

        if (previousUserId) {
          // Logging out must never leave the previous account's session ID or
          // messages active for the next person using this browser.
          clearStoredMessages()
          clearStoredDraft()
          const freshSessionId = startNewChatSession()
          setActiveSessionId(freshSessionId)
          setMessages([createSystemMessage('msg-logout')])
          setInput('')
        } else {
          setActiveSessionId(getChatSessionId())
        }

        if (!cancelled) setConversationReady(true)
        return
      }

      setHistoryLoading(true)
      try {
        const rows = await fetchChatSessions()
        if (cancelled) return
        setSessions(rows)

        const currentSessionId = getChatSessionId()
        const currentSessionExists = rows.some((item) => item.id === currentSessionId)

        if (currentSessionExists) {
          const payload = await fetchChatSessionMessages(currentSessionId)
          if (cancelled) return
          const restored = (payload.messages || []).map(historyMessageToUi)
          setActiveSessionId(currentSessionId)
          setMessages(
            restored.length
              ? restored
              : [createSystemMessage('msg-empty-history')],
          )
          clearStoredMessages()
        } else if (previousUserId === null) {
          // The user has just logged in during this SPA session. Keep a guest
          // conversation visible; the next message will let the backend claim
          // that anonymous session for this authenticated user.
          setActiveSessionId(currentSessionId)
        } else {
          // First authenticated load with an unknown/stale session, or a direct
          // account switch: rotate IDs to avoid a 403 against another user's chat.
          clearStoredMessages()
          const freshSessionId = startNewChatSession()
          setActiveSessionId(freshSessionId)
          setMessages([createSystemMessage('msg-login')])
        }
      } catch (error) {
        if (!cancelled) console.error('Could not load chat history:', error)
      } finally {
        if (!cancelled) {
          setHistoryLoading(false)
          setConversationReady(true)
        }
      }
    }

    syncConversationForAuthState()
    return () => {
      cancelled = true
    }
  }, [authLoading, user?.id])

  useEffect(() => {
    if (!conversationReady) return

    const promptAlreadyInHistory = messages.some(
      (message) => message.sender === 'user' && message.text === initialPrompt,
    )

    if (
      initialPrompt
      && handledPromptRef.current !== initialPrompt
      && !promptAlreadyInHistory
    ) {
      handledPromptRef.current = initialPrompt
      handleSendPrompt(initialPrompt)
    }
  }, [conversationReady, initialPrompt, messages])

  async function refreshSessions() {
    if (!user) return
    try {
      const rows = await fetchChatSessions()
      setSessions(rows)
    } catch (error) {
      console.error('Could not refresh chat history:', error)
    }
  }

  async function loadHistorySession(sessionId) {
    if (!user || loading || historyLoading) return

    setHistoryLoading(true)
    try {
      const payload = await fetchChatSessionMessages(sessionId)
      const restored = (payload.messages || []).map(historyMessageToUi)
      setChatSessionId(sessionId)
      setActiveSessionId(sessionId)
      setMessages(
        restored.length
          ? restored
          : [createSystemMessage('msg-empty-history')],
      )
      clearStoredMessages()
      setHistoryOpen(false)
    } catch (error) {
      console.error('Could not load selected chat session:', error)
    } finally {
      setHistoryLoading(false)
    }
  }

  async function handleSendPrompt(promptText) {
    if (!promptText.trim() || loading || !conversationReady) return

    const userMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      sender: 'user',
      text: promptText,
      timestamp: displayTime(),
      language,
    }

    setMessages((current) => [...current, userMessage])
    setInput('')
    clearStoredDraft()
    setLoading(true)

    try {
      const aiResponse = await sendChatMessage(promptText, language)
      setMessages((current) => [...current, aiResponse])
      if (aiResponse.sessionId) {
        setActiveSessionId(aiResponse.sessionId)
      }
      if (user) await refreshSessions()
    } catch (error) {
      console.error('Chat request failed:', error)
      setMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          sender: 'assistant',
          text: t.assistantUnavailable,
          timestamp: displayTime(),
          language,
          localizationKey: 'assistantUnavailable',
          isError: true,
          errorDetail: error instanceof Error ? error.message : String(error),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function handleFormSubmit(event) {
    event.preventDefault()
    handleSendPrompt(input)
  }

  function startFreshConversation() {
    if (loading) return
    const sessionId = startNewChatSession()
    setActiveSessionId(sessionId)
    setHistoryOpen(false)
    clearStoredDraft()
    setInput('')
    setMessages([createSystemMessage('msg-reset', 'chatbotReset')])
  }

  return (
    <main className="chatbot-page">
      {user && historyOpen && (
        <button
          className="chatbot-page__history-backdrop"
          type="button"
          aria-label={closeHistoryLabel(language)}
          onClick={() => setHistoryOpen(false)}
        />
      )}

      <div
        className={`chatbot-page__shell ${
          user ? 'chatbot-page__shell--with-history' : 'chatbot-page__shell--solo'
        }`}
      >
        {user && (
          <ChatHistorySidebar
            sessions={sessions}
            activeSessionId={activeSessionId}
            loading={historyLoading}
            open={historyOpen}
            language={language}
            onClose={() => setHistoryOpen(false)}
            onNewConversation={startFreshConversation}
            onSelectSession={loadHistorySession}
          />
        )}

        <div className="chatbot-page__container">
          <section className="chatbot-page__header">
            <div className="chatbot-page__identity">
              <div className="chatbot-page__avatar chatbot-page__avatar--brand">
                <Bot className="chatbot-page__avatar-icon chatbot-page__avatar-icon--large" />
              </div>
              <div>
                <div className="chatbot-page__title-row">
                  <h1 className="chatbot-page__title">VinTravel AI</h1>
                </div>
                <p className="chatbot-page__subtitle">{t.chatbotSubtitle}</p>
              </div>
            </div>

            <div className="chatbot-page__header-actions">
              {user && (
                <button
                  className="chatbot-page__history-toggle"
                  type="button"
                  onClick={() => setHistoryOpen(true)}
                >
                  <History className="chatbot-page__action-icon" />
                  <span>{historyButtonLabel(language)}</span>
                </button>
              )}
              <button
                className="chatbot-page__reset"
                type="button"
                title={t.resetConversation}
                onClick={startFreshConversation}
              >
                <RotateCcw className="chatbot-page__action-icon" />
                <span>{user ? newChatLabel(language) : t.clearChat}</span>
              </button>
              <Link className="chatbot-page__support-link" to="/support">
                <Headphones className="chatbot-page__action-icon" />
                <span>{t.createTicket}</span>
              </Link>
            </div>
          </section>

          <section
            ref={messagesContainerRef}
            className="chatbot-page__messages"
            aria-label={t.chatMessages}
          >
            {messages.map((message) => (
              <article
                className={`chatbot-page__message-row ${
                  message.sender === 'user' ? 'chatbot-page__message-row--user' : ''
                }`}
                key={message.id}
              >
                <div
                  className={`chatbot-page__avatar ${
                    message.sender === 'user'
                      ? 'chatbot-page__avatar--user'
                      : 'chatbot-page__avatar--assistant'
                  }`}
                >
                  {message.sender === 'user' ? (
                    <User className="chatbot-page__avatar-icon" />
                  ) : (
                    <Bot className="chatbot-page__avatar-icon" />
                  )}
                </div>

                <div className="chatbot-page__message-content">
                  <div
                    className={`chatbot-page__bubble ${
                      message.sender === 'user'
                        ? 'chatbot-page__bubble--user'
                        : message.isError
                          ? 'chatbot-page__bubble--error'
                          : 'chatbot-page__bubble--assistant'
                    }`}
                  >
                    {message.sender === 'user' || message.isError ? (
                      <RichMessage text={message.text} isUser={message.sender === 'user'} />
                    ) : (
                      <StructuredMessage text={message.text} sources={message.sources} />
                    )}
                    <span className="chatbot-page__timestamp">{message.timestamp}</span>
                  </div>

                  {message.ticketId && (
                    <div className="chatbot-page__ticket" role="status">
                      <strong>{t.supportTicket}:</strong>{' '}
                      <span>{message.ticketId}</span>
                    </div>
                  )}

                  {message.relatedHotels && message.relatedHotels.length > 0 && (
                    <div className="chatbot-page__related-hotels">
                      {message.relatedHotels.map((hotel, index) => (
                        <HotelCard key={`${message.id}-${hotel.id}-${index}`} hotel={hotel} />
                      ))}
                    </div>
                  )}
                </div>
              </article>
            ))}

            {loading && (
              <article className="chatbot-page__typing">
                <div className="chatbot-page__avatar chatbot-page__avatar--assistant">
                  <Bot className="chatbot-page__avatar-icon" />
                </div>
                <div className="chatbot-page__typing-bubble">
                  <span className="chatbot-page__typing-dot" />
                  <span>{t.chatbotThinking}</span>
                </div>
              </article>
            )}
          </section>

          <form className="chatbot-page__form" onSubmit={handleFormSubmit}>
            <input
              ref={inputRef}
              className="chatbot-page__input"
              type="text"
              placeholder={t.chatbotPlaceholder}
              value={input}
              disabled={loading || !conversationReady}
              onChange={(event) => setInput(event.target.value)}
            />
            <button
              className="chatbot-page__send"
              type="submit"
              disabled={loading || !conversationReady || !input.trim()}
            >
              <Send className="chatbot-page__send-icon" />
            </button>
          </form>

          <div className="chatbot-page__escalation">
            <p>
              <ShieldAlert className="chatbot-page__escalation-icon" />
              <span>{t.chatbotEscalation}</span>
              <Link to="/support">{t.chatbotSubmitTicket}</Link>
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}

export default Chatbot
