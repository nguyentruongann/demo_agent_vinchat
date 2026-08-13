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
import MarkdownContent from '../components/MarkdownContent'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import {
  fetchChatSessionMessages,
  fetchChatSessions,
  getChatSessionId,
  sendChatMessage,
  setChatSessionId,
  startNewChatSession,
} from '../services/api'
import '../styles/pages/Chatbot.css'

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

function Chatbot() {
  const { language, t } = useLanguage()
  const { user, loading: authLoading } = useAuth()
  const [searchParams] = useSearchParams()
  const initialPrompt = searchParams.get('prompt') || ''
  const handledPromptRef = useRef(null)
  const messagesContainerRef = useRef(null)
  const previousUserIdRef = useRef(undefined)

  function initialAssistantMessage(id = 'msg-welcome', text = t.chatbotWelcome) {
    return {
      id,
      sender: 'assistant',
      text,
      timestamp: displayTime(),
      language,
    }
  }

  const [messages, setMessages] = useState(() => [
    {
      id: 'msg-welcome',
      sender: 'assistant',
      text: t.chatbotWelcome,
      timestamp: displayTime(),
      language,
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(() => getChatSessionId())

  const suggestedPrompts = [
    {
      icon: '🏝',
      title: t.chatSuggestPhuQuoc,
      prompt:
        language === 'VI'
          ? 'Gợi ý gói nghỉ dưỡng 3 ngày 2 đêm tại VinTravel Grand Phú Quốc cho 2 người'
          : 'Suggest a 3D2N luxury stay in VinTravel Grand Phu Quoc for 2 adults',
    },
    {
      icon: '🎢',
      title: t.chatSuggestNhaTrang,
      prompt:
        language === 'VI'
          ? 'Tư vấn biệt thự biển Nha Trang kèm vé vui chơi VinWonders'
          : 'Recommend Nha Trang Ocean Villa with unlimited VinWonders park passes',
    },
    {
      icon: '👶',
      title: t.chatSuggestFamily,
      prompt:
        language === 'VI'
          ? 'Chính sách trẻ em và phụ thu giường phụ tại các resort VinTravel?'
          : 'What are the children policies and extra bed surcharges at VinTravel resorts?',
    },
    {
      icon: '⛳',
      title: t.chatSuggestHoiAn,
      prompt:
        language === 'VI'
          ? 'Tư vấn khu nghỉ dưỡng Hội An kết hợp chơi golf 18 lỗ'
          : 'Provide details on VinTravel Heritage Resort Hoi An 18-hole golf package',
    },
  ]

  useEffect(() => {
    const messagesContainer = messagesContainerRef.current
    if (!messagesContainer) return

    messagesContainer.scrollTo({
      top: messagesContainer.scrollHeight,
      behavior: messages.length > 1 ? 'smooth' : 'auto',
    })
  }, [messages, loading])

  useEffect(() => {
    if (authLoading) return undefined

    let cancelled = false

    async function syncConversationForAuthState() {
      const previousUserId = previousUserIdRef.current
      previousUserIdRef.current = user?.id || null

      if (!user) {
        setSessions([])
        setHistoryOpen(false)
        const currentId = getChatSessionId()
        setActiveSessionId(currentId)

        // On logout, immediately remove the previous account's visible messages.
        if (previousUserId) {
          setMessages([initialAssistantMessage('msg-logout')])
        }
        return
      }

      setHistoryLoading(true)
      try {
        const rows = await fetchChatSessions()
        if (cancelled) return
        setSessions(rows)

        const currentId = getChatSessionId()
        setActiveSessionId(currentId)
        const currentSessionExists = rows.some((item) => item.id === currentId)

        // Reload the active authenticated conversation after a browser refresh.
        if (currentSessionExists) {
          const payload = await fetchChatSessionMessages(currentId)
          if (cancelled) return
          const restored = (payload.messages || []).map(historyMessageToUi)
          setMessages(restored.length ? restored : [initialAssistantMessage('msg-empty-history')])
        } else if (previousUserId !== user.id) {
          // Login/register starts a fresh chat; older sessions remain in the sidebar.
          setMessages([initialAssistantMessage('msg-login')])
        }
      } catch (error) {
        if (!cancelled) console.error('Could not load chat history:', error)
      } finally {
        if (!cancelled) setHistoryLoading(false)
      }
    }

    syncConversationForAuthState()
    return () => {
      cancelled = true
    }
  }, [authLoading, user?.id])

  useEffect(() => {
    if (authLoading) return
    if (initialPrompt && handledPromptRef.current !== initialPrompt) {
      handledPromptRef.current = initialPrompt
      handleSendPrompt(initialPrompt)
    }
  }, [authLoading, initialPrompt])

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
      setMessages(restored.length ? restored : [initialAssistantMessage('msg-empty-history')])
      setHistoryOpen(false)
    } catch (error) {
      console.error('Could not load selected chat session:', error)
    } finally {
      setHistoryLoading(false)
    }
  }

  async function handleSendPrompt(promptText) {
    if (!promptText.trim() || loading) return

    const userMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      sender: 'user',
      text: promptText,
      timestamp: displayTime(),
      language,
    }

    setMessages((current) => [...current, userMessage])
    setInput('')
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
          text:
            language === 'VI'
              ? 'Không thể kết nối tới trợ lý lúc này. Vui lòng kiểm tra backend và thử lại.'
              : 'The assistant is unavailable right now. Please check the backend and try again.',
          timestamp: displayTime(),
          language,
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
    setMessages([
      initialAssistantMessage('msg-reset', t.chatbotReset),
    ])
  }

  return (
    <main className="chatbot-page">
      {user && historyOpen && (
        <button
          className="chatbot-page__history-backdrop"
          type="button"
          aria-label={language === 'VI' ? 'Đóng lịch sử chat' : 'Close chat history'}
          onClick={() => setHistoryOpen(false)}
        />
      )}

      <div className={`chatbot-page__shell ${user ? 'chatbot-page__shell--with-history' : 'chatbot-page__shell--solo'}`}>
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
                  <h1 className="chatbot-page__title">VinTravel AI Concierge</h1>
                  <span className="chatbot-page__live-badge">{t.liveAiBadge}</span>
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
                  <span>{language === 'VI' ? 'Lịch sử' : 'History'}</span>
                </button>
              )}
              <button
                className="chatbot-page__reset"
                type="button"
                title={t.resetConversation}
                onClick={startFreshConversation}
              >
                <RotateCcw className="chatbot-page__action-icon" />
                <span>{user ? (language === 'VI' ? 'Chat mới' : 'New chat') : t.clearChat}</span>
              </button>
              <Link className="chatbot-page__support-link" to="/support">
                <Headphones className="chatbot-page__action-icon" />
                <span>{t.createTicket}</span>
              </Link>
            </div>
          </section>

          <section className="chatbot-page__suggestions" aria-label="Suggested prompts">
            {suggestedPrompts.map((prompt) => (
              <button
                className="chatbot-page__suggestion"
                key={prompt.title}
                type="button"
                onClick={() => handleSendPrompt(prompt.prompt)}
              >
                <span className="chatbot-page__suggestion-icon">{prompt.icon}</span>
                <span className="chatbot-page__suggestion-title">{prompt.title}</span>
              </button>
            ))}
          </section>

          <section
            ref={messagesContainerRef}
            className="chatbot-page__messages"
            aria-label="Chat messages"
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
                    {message.sender === 'assistant' ? (
                      <MarkdownContent>{message.text}</MarkdownContent>
                    ) : (
                      <span className="chatbot-page__plain-text">{message.text}</span>
                    )}
                    <span className="chatbot-page__timestamp">{message.timestamp}</span>
                  </div>

                  {message.ticketId && (
                    <div className="chatbot-page__ticket" role="status">
                      <strong>{language === 'VI' ? 'Mã hỗ trợ' : 'Support ticket'}:</strong>{' '}
                      <span>{message.ticketId}</span>
                    </div>
                  )}

                  {message.sources && message.sources.length > 0 && (
                    <details className="chatbot-page__sources">
                      <summary>
                        {language === 'VI'
                          ? `${message.sources.length} nguồn tham khảo`
                          : `${message.sources.length} sources`}
                      </summary>
                      <ol>
                        {message.sources.map((source, index) => (
                          <li key={`${message.id}-${source.source_file}-${source.path}-${index}`}>
                            <div className="chatbot-page__source-title-row">
                              <span className="chatbot-page__source-title">{source.source_file}</span>
                              {source.category && (
                                <span className="chatbot-page__source-category">{source.category}</span>
                              )}
                            </div>
                            {source.path && /^https?:\/\//i.test(source.path) ? (
                              <a
                                className="chatbot-page__source-link"
                                href={source.path}
                                target="_blank"
                                rel="noreferrer noopener"
                              >
                                {language === 'VI' ? 'Mở nguồn tham khảo ↗' : 'Open source ↗'}
                              </a>
                            ) : source.path ? (
                              <code>{source.path}</code>
                            ) : null}
                            {typeof source.score === 'number' && (
                              <small>
                                {language === 'VI' ? 'Độ liên quan' : 'Relevance'}: {source.score.toFixed(4)}
                              </small>
                            )}
                          </li>
                        ))}
                      </ol>
                    </details>
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
              className="chatbot-page__input"
              type="text"
              placeholder={t.chatbotPlaceholder}
              value={input}
              disabled={loading}
              onChange={(event) => setInput(event.target.value)}
            />
            <button
              className="chatbot-page__send"
              type="submit"
              disabled={loading || !input.trim()}
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
