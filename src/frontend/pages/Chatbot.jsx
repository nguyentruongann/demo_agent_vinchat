import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowDown,
  Bot,
  Calendar,
  Check,
  Compass,
  Copy,
  Headphones,
  History,
  MapPin,
  Plus,
  Send,
  ShieldAlert,
  Sparkles,
  Square,
  User,
  Users,
  Wallet,
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
  setChatSessionId,
  startNewChatSession,
  streamChatMessage,
} from '../services/api'
import '../styles/pages/Chatbot.css'

const CHAT_DRAFT_KEY = 'vinpearl_chat_draft_v2'
const STREAM_STATUS_INDEX = {
  understanding: 0,
  searching: 1,
  evaluating: 1,
  composing: 2,
  verifying: 3,
  finalizing: 3,
}

const UI_COPY = {
  vi: {
    assistant: 'Trợ lý du lịch AI',
    online: 'Sẵn sàng hỗ trợ',
    history: 'Lịch sử',
    newChat: 'Chat mới',
    newChatAria: 'Bắt đầu cuộc trò chuyện mới',
    support: 'Hỗ trợ',
    closeHistory: 'Đóng lịch sử chat',
    copy: 'Sao chép câu trả lời',
    copied: 'Đã sao chép',
    scrollBottom: 'Về tin nhắn mới nhất',
    send: 'Gửi tin nhắn',
    stop: 'Dừng trả lời',
    keyboardHint: 'Enter để gửi · Shift + Enter để xuống dòng',
    disclaimer: 'Vinpearl AI có thể mắc lỗi. Hãy kiểm tra lại thông tin quan trọng trước khi đặt dịch vụ.',
    thinkingMessages: [
      'Trợ lý đang tiếp nhận thông tin của bạn...',
      'Đang xử lý và tìm thông tin phù hợp...',
      'Đang tổng hợp câu trả lời cho bạn...',
      'Sắp xong rồi, đợi mình một chút nhé...',
    ],
    suggestionsTitle: 'Bạn muốn bắt đầu từ đâu?',
    suggestionsSubtitle: 'Chọn một gợi ý hoặc đặt câu hỏi theo cách của bạn.',
    prompts: [
      {
        icon: 'compass',
        eyebrow: 'Khám phá',
        title: 'Chọn điểm đến phù hợp',
        text: 'Gợi ý điểm đến Vinpearl phù hợp cho gia đình có trẻ nhỏ',
      },
      {
        icon: 'calendar',
        eyebrow: 'Lịch trình',
        title: 'Lên kế hoạch 3N2Đ',
        text: 'Lên lịch trình 3 ngày 2 đêm ở Phú Quốc cho gia đình',
      },
      {
        icon: 'wallet',
        eyebrow: 'Ngân sách',
        title: 'Ước tính chi phí chuyến đi',
        text: 'Ước tính chi phí chuyến đi 3 ngày 2 đêm ở Nha Trang cho 2 người',
      },
      {
        icon: 'family',
        eyebrow: 'Gia đình',
        title: 'Hỏi chính sách trẻ em',
        text: 'Tư vấn chính sách trẻ em khi lưu trú tại Vinpearl',
      },
    ],
  },
  en: {
    assistant: 'AI travel concierge',
    online: 'Ready to help',
    history: 'History',
    newChat: 'New chat',
    newChatAria: 'Start a new conversation',
    support: 'Support',
    closeHistory: 'Close chat history',
    copy: 'Copy response',
    copied: 'Copied',
    scrollBottom: 'Jump to latest message',
    send: 'Send message',
    stop: 'Stop response',
    keyboardHint: 'Enter to send · Shift + Enter for a new line',
    disclaimer: 'Vinpearl AI can make mistakes. Check important details before booking.',
    thinkingMessages: [
      'The assistant is receiving your request...',
      'Finding the most relevant information...',
      'Putting your answer together...',
      'Almost there — just a moment...',
    ],
    suggestionsTitle: 'Where would you like to start?',
    suggestionsSubtitle: 'Pick a suggestion or ask in your own words.',
    prompts: [
      { icon: 'compass', eyebrow: 'Explore', title: 'Choose a destination', text: 'Recommend a Vinpearl destination for a family with young children' },
      { icon: 'calendar', eyebrow: 'Itinerary', title: 'Plan a 3D2N trip', text: 'Plan a 3-day 2-night family itinerary in Phu Quoc' },
      { icon: 'wallet', eyebrow: 'Budget', title: 'Estimate trip cost', text: 'Estimate a 3-day 2-night Nha Trang trip for two people' },
      { icon: 'family', eyebrow: 'Family', title: 'Child policies', text: 'Explain Vinpearl child policies for hotel stays' },
    ],
  },
  ko: {
    assistant: 'AI 여행 컨시어지',
    online: '도움드릴 준비가 되었습니다',
    history: '기록',
    newChat: '새 채팅',
    newChatAria: '새 대화 시작',
    support: '지원',
    closeHistory: '채팅 기록 닫기',
    copy: '답변 복사',
    copied: '복사됨',
    scrollBottom: '최신 메시지로 이동',
    send: '메시지 보내기',
    stop: '응답 중지',
    keyboardHint: 'Enter 전송 · Shift + Enter 줄바꿈',
    disclaimer: 'Vinpearl AI는 실수할 수 있습니다. 예약 전 중요한 정보를 확인하세요.',
    thinkingMessages: [
      '요청 내용을 확인하고 있어요...',
      '가장 관련성 높은 정보를 찾고 있어요...',
      '답변을 정리하고 있어요...',
      '거의 다 됐어요. 잠시만 기다려 주세요...',
    ],
    suggestionsTitle: '무엇부터 시작할까요?',
    suggestionsSubtitle: '추천 항목을 선택하거나 자유롭게 질문하세요.',
    prompts: [
      { icon: 'compass', eyebrow: '탐색', title: '여행지 추천', text: '어린 자녀가 있는 가족에게 적합한 Vinpearl 여행지를 추천해 주세요' },
      { icon: 'calendar', eyebrow: '일정', title: '3일 2박 일정', text: '푸꾸옥 가족 여행 3일 2박 일정을 짜 주세요' },
      { icon: 'wallet', eyebrow: '예산', title: '여행 비용 예상', text: '2인 나트랑 3일 2박 여행 비용을 예상해 주세요' },
      { icon: 'family', eyebrow: '가족', title: '아동 정책', text: 'Vinpearl 숙박 시 아동 정책을 알려 주세요' },
    ],
  },
  ja: {
    assistant: 'AIトラベルコンシェルジュ',
    online: 'ご案内できます',
    history: '履歴',
    newChat: '新規チャット',
    newChatAria: '新しい会話を開始',
    support: 'サポート',
    closeHistory: 'チャット履歴を閉じる',
    copy: '回答をコピー',
    copied: 'コピーしました',
    scrollBottom: '最新メッセージへ',
    send: 'メッセージを送信',
    stop: '回答を停止',
    keyboardHint: 'Enterで送信 · Shift + Enterで改行',
    disclaimer: 'Vinpearl AIは誤る場合があります。予約前に重要な情報をご確認ください。',
    thinkingMessages: [
      'ご質問を受け付けています...',
      '関連する情報を確認しています...',
      '回答をまとめています...',
      'もう少しです。少々お待ちください...',
    ],
    suggestionsTitle: '何から始めますか？',
    suggestionsSubtitle: '候補を選ぶか、自由に質問してください。',
    prompts: [
      { icon: 'compass', eyebrow: '探す', title: '旅行先を選ぶ', text: '小さな子ども連れの家族におすすめのVinpearl旅行先を教えてください' },
      { icon: 'calendar', eyebrow: '旅程', title: '3日2泊プラン', text: 'フーコックの家族旅行3日2泊の旅程を作ってください' },
      { icon: 'wallet', eyebrow: '予算', title: '旅行費用を試算', text: '2人でニャチャン3日2泊旅行の費用を見積もってください' },
      { icon: 'family', eyebrow: '家族', title: '子ども料金・規定', text: 'Vinpearl宿泊時の子ども向け規定を教えてください' },
    ],
  },
  zh: {
    assistant: 'AI 旅行礼宾助手',
    online: '随时为您服务',
    history: '记录',
    newChat: '新对话',
    newChatAria: '开始新对话',
    support: '客服',
    closeHistory: '关闭聊天记录',
    copy: '复制回答',
    copied: '已复制',
    scrollBottom: '回到最新消息',
    send: '发送消息',
    stop: '停止回答',
    keyboardHint: 'Enter 发送 · Shift + Enter 换行',
    disclaimer: 'Vinpearl AI 可能会出错。预订前请核对重要信息。',
    thinkingMessages: [
      '正在接收您的问题...',
      '正在查找最相关的信息...',
      '正在整理回答...',
      '马上就好，请稍等一下...',
    ],
    suggestionsTitle: '想从哪里开始？',
    suggestionsSubtitle: '选择一个建议，或直接输入您的问题。',
    prompts: [
      { icon: 'compass', eyebrow: '探索', title: '选择目的地', text: '推荐适合带幼儿家庭的 Vinpearl 目的地' },
      { icon: 'calendar', eyebrow: '行程', title: '规划3天2晚', text: '规划富国岛家庭3天2晚行程' },
      { icon: 'wallet', eyebrow: '预算', title: '估算旅行费用', text: '估算两人芽庄3天2晚旅行费用' },
      { icon: 'family', eyebrow: '家庭', title: '儿童政策', text: '介绍入住 Vinpearl 时的儿童政策' },
    ],
  },
}

const SUGGESTION_ICONS = {
  compass: Compass,
  calendar: Calendar,
  wallet: Wallet,
  family: Users,
}

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
    // Chat still works when storage is unavailable.
  }
}

function clearStoredDraft() {
  try {
    sessionStorage.removeItem(CHAT_DRAFT_KEY)
  } catch {
    // Ignore storage failures.
  }
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
  const requestControllerRef = useRef(null)
  const [copiedMessageId, setCopiedMessageId] = useState(null)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const [thinkingMessageIndex, setThinkingMessageIndex] = useState(0)

  const copy = UI_COPY[language] || UI_COPY.en

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
  const [receivingTokens, setReceivingTokens] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(() => getChatSessionId())
  const [conversationReady, setConversationReady] = useState(false)

  const showStarters = useMemo(
    () => !loading && !messages.some((message) => message.sender === 'user'),
    [loading, messages],
  )

  function scrollToBottom(behavior = 'smooth') {
    const messagesContainer = messagesContainerRef.current
    if (!messagesContainer) return
    messagesContainer.scrollTo({
      top: messagesContainer.scrollHeight,
      behavior,
    })
    setShowScrollDown(false)
  }

  useEffect(() => {
    if (showScrollDown) return
    scrollToBottom(messages.length > 1 ? 'smooth' : 'auto')
  }, [messages, loading])

  useEffect(() => {
    const textarea = inputRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 148)}px`
  }, [input])

  // Restore focus after a response so the conversation can continue immediately.
  useEffect(() => {
    if (loading || !conversationReady) return undefined

    const frame = window.requestAnimationFrame(() => {
      inputRef.current?.focus({ preventScroll: true })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [loading, conversationReady])

  // Keep only local/system UI messages synchronized with the selected language.
  useEffect(() => {
    setMessages((current) => localizeSystemMessages(current, t, language))
  }, [language, t.chatbotWelcome, t.chatbotReset, t.assistantUnavailable, t.chatError])

  // Guest chats may be restored from sessionStorage. Authenticated chats are
  // restored from PostgreSQL instead, preventing cross-account browser leakage.
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
          setMessages(restored.length ? restored : [createSystemMessage('msg-empty-history')])
          clearStoredMessages()
        } else if (previousUserId === null) {
          // The user has just logged in during this SPA session. Keep a guest
          // conversation visible; the backend can claim it on the next message.
          setActiveSessionId(currentSessionId)
        } else {
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
      setMessages(restored.length ? restored : [createSystemMessage('msg-empty-history')])
      clearStoredMessages()
      setHistoryOpen(false)
      setShowScrollDown(false)
    } catch (error) {
      console.error('Could not load selected chat session:', error)
    } finally {
      setHistoryLoading(false)
    }
  }

  async function handleSendPrompt(promptText) {
    if (!promptText.trim() || loading || !conversationReady) return

    const cleanPrompt = promptText.trim()
    const userMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      sender: 'user',
      text: cleanPrompt,
      timestamp: displayTime(),
      language,
    }

    setShowScrollDown(false)
    setMessages((current) => [...current, userMessage])
    setInput('')
    clearStoredDraft()
    setThinkingMessageIndex(0)
    setReceivingTokens(false)
    setLoading(true)

    const controller = new AbortController()
    requestControllerRef.current = controller
    const assistantId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    const assistantTimestamp = displayTime()
    let responseStarted = false

    try {
      const aiResponse = await streamChatMessage(cleanPrompt, language, {
        signal: controller.signal,
        messageId: assistantId,
        timestamp: assistantTimestamp,
        onStatus: (stage) => {
          setThinkingMessageIndex(STREAM_STATUS_INDEX[stage] ?? 0)
        },
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
        if (!responseStarted) return [...current, aiResponse]
        return current.map((message) => (
          message.id === assistantId
            ? { ...aiResponse, id: assistantId, timestamp: assistantTimestamp, isStreaming: false }
            : message
        ))
      })
      if (aiResponse.sessionId) {
        setActiveSessionId(aiResponse.sessionId)
      }
      if (user) await refreshSessions()
    } catch (error) {
      if (error?.name === 'AbortError') return
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

  function stopResponse() {
    requestControllerRef.current?.abort()
  }

  function handleFormSubmit(event) {
    event.preventDefault()
    handleSendPrompt(input)
  }

  function handleComposerKeyDown(event) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent?.isComposing) return
    event.preventDefault()
    handleSendPrompt(input)
  }

  function handleMessagesScroll(event) {
    const node = event.currentTarget
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight
    setShowScrollDown(distanceFromBottom > 140)
  }

  async function handleCopyMessage(message) {
    if (!message?.text) return
    try {
      await navigator.clipboard.writeText(message.text)
      setCopiedMessageId(message.id)
      window.setTimeout(() => {
        setCopiedMessageId((current) => (current === message.id ? null : current))
      }, 1600)
    } catch (error) {
      console.warn('Could not copy chat message:', error)
    }
  }

  function startFreshConversation() {
    if (loading) {
      stopResponse()
    }
    const sessionId = startNewChatSession()
    setActiveSessionId(sessionId)
    setHistoryOpen(false)
    clearStoredDraft()
    setInput('')
    setShowScrollDown(false)
    setMessages([createSystemMessage('msg-reset', 'chatbotReset')])
  }

  return (
    <div className="chatbot-page">
      {user && historyOpen && (
        <button
          className="chatbot-page__history-backdrop"
          type="button"
          aria-label={copy.closeHistory}
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

        <section className="chatbot-page__container" aria-label={copy.assistant}>
          <header className="chatbot-page__header">
            <div className="chatbot-page__identity">
              <div className="chatbot-page__avatar chatbot-page__avatar--brand" aria-hidden="true">
                <Sparkles className="chatbot-page__avatar-icon chatbot-page__avatar-icon--large" />
              </div>
              <div className="chatbot-page__identity-copy">
                <div className="chatbot-page__title-row">
                  <h1 className="chatbot-page__title">Vinpearl AI</h1>
                  <span className="chatbot-page__status">
                    <span className="chatbot-page__status-dot" />
                    {copy.online}
                  </span>
                </div>
                <p className="chatbot-page__subtitle">{copy.assistant} · {t.chatbotSubtitle}</p>
              </div>
            </div>

            <div className="chatbot-page__header-actions">
              {user && (
                <button
                  className="chatbot-page__header-button chatbot-page__history-toggle"
                  type="button"
                  onClick={() => setHistoryOpen(true)}
                >
                  <History className="chatbot-page__action-icon" />
                  <span>{copy.history}</span>
                </button>
              )}
              <button
                className="chatbot-page__header-button"
                type="button"
                aria-label={copy.newChatAria}
                title={t.resetConversation}
                onClick={startFreshConversation}
              >
                <Plus className="chatbot-page__action-icon" />
                <span>{copy.newChat}</span>
              </button>
              <Link className="chatbot-page__header-button chatbot-page__support-link" to="/support">
                <Headphones className="chatbot-page__action-icon" />
                <span>{copy.support}</span>
              </Link>
            </div>
          </header>

          <div className="chatbot-page__conversation">
            <section
              ref={messagesContainerRef}
              className="chatbot-page__messages"
              aria-label={t.chatMessages}
              aria-live="polite"
              onScroll={handleMessagesScroll}
            >
              <div className="chatbot-page__messages-inner">
                {messages.map((message) => (
                  <article
                    className={`chatbot-page__message-row ${
                      message.sender === 'user' ? 'chatbot-page__message-row--user' : ''
                    }`}
                    key={message.id}
                  >
                    <div
                      className={`chatbot-page__avatar chatbot-page__avatar--message ${
                        message.sender === 'user'
                          ? 'chatbot-page__avatar--user'
                          : 'chatbot-page__avatar--assistant'
                      }`}
                      aria-hidden="true"
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
                      </div>

                      <div className={`chatbot-page__message-meta ${message.sender === 'user' ? 'chatbot-page__message-meta--user' : ''}`}>
                        <span className="chatbot-page__timestamp">{message.timestamp}</span>
                        {message.sender === 'assistant' && !message.isError && (
                          <button
                            className="chatbot-page__message-action"
                            type="button"
                            aria-label={copiedMessageId === message.id ? copy.copied : copy.copy}
                            title={copiedMessageId === message.id ? copy.copied : copy.copy}
                            onClick={() => handleCopyMessage(message)}
                          >
                            {copiedMessageId === message.id ? <Check /> : <Copy />}
                            <span>{copiedMessageId === message.id ? copy.copied : copy.copy}</span>
                          </button>
                        )}
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

                {showStarters && (
                  <section className="chatbot-page__starter" aria-labelledby="chat-starter-title">
                    <div className="chatbot-page__starter-heading">
                      <div>
                        <h2 id="chat-starter-title">{copy.suggestionsTitle}</h2>
                        <p>{copy.suggestionsSubtitle}</p>
                      </div>
                      <MapPin className="chatbot-page__starter-heading-icon" aria-hidden="true" />
                    </div>
                    <div className="chatbot-page__suggestions">
                      {copy.prompts.map((prompt) => {
                        const SuggestionIcon = SUGGESTION_ICONS[prompt.icon] || Compass
                        return (
                          <button
                            className="chatbot-page__suggestion"
                            type="button"
                            key={prompt.title}
                            onClick={() => handleSendPrompt(prompt.text)}
                          >
                            <span className="chatbot-page__suggestion-topline">
                              <span className="chatbot-page__suggestion-icon-wrap">
                                <SuggestionIcon className="chatbot-page__suggestion-icon" />
                              </span>
                              <span className="chatbot-page__suggestion-eyebrow">{prompt.eyebrow}</span>
                            </span>
                            <span className="chatbot-page__suggestion-title">{prompt.title}</span>
                            <span className="chatbot-page__suggestion-arrow">→</span>
                          </button>
                        )
                      })}
                    </div>
                  </section>
                )}

                {loading && !receivingTokens && (
                  <article
                    className="chatbot-page__typing"
                    role="status"
                    aria-live="polite"
                    aria-atomic="true"
                  >
                    <div className="chatbot-page__avatar chatbot-page__avatar--message chatbot-page__avatar--assistant" aria-hidden="true">
                      <Bot className="chatbot-page__avatar-icon" />
                    </div>
                    <div className="chatbot-page__typing-bubble">
                      <span className="chatbot-page__typing-dots" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </span>
                      <span
                        key={thinkingMessageIndex}
                        className="chatbot-page__typing-text"
                      >
                        {copy.thinkingMessages?.[thinkingMessageIndex] || t.chatbotThinking}
                      </span>
                    </div>
                  </article>
                )}
              </div>
            </section>

            {showScrollDown && (
              <button
                className="chatbot-page__scroll-down"
                type="button"
                aria-label={copy.scrollBottom}
                title={copy.scrollBottom}
                onClick={() => scrollToBottom('smooth')}
              >
                <ArrowDown />
              </button>
            )}

            <div className="chatbot-page__composer-area">
              <form className="chatbot-page__form" onSubmit={handleFormSubmit}>
                <textarea
                  ref={inputRef}
                  className="chatbot-page__input"
                  rows="1"
                  placeholder={t.chatbotPlaceholder}
                  value={input}
                  disabled={!conversationReady}
                  aria-label={t.chatbotPlaceholder}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                />
                {loading ? (
                  <button
                    className="chatbot-page__send chatbot-page__send--stop"
                    type="button"
                    aria-label={copy.stop}
                    title={copy.stop}
                    onClick={stopResponse}
                  >
                    <Square className="chatbot-page__send-icon chatbot-page__stop-icon" />
                  </button>
                ) : (
                  <button
                    className="chatbot-page__send"
                    type="submit"
                    aria-label={copy.send}
                    title={copy.send}
                    disabled={!conversationReady || !input.trim()}
                  >
                    <Send className="chatbot-page__send-icon" />
                  </button>
                )}
              </form>

              <div className="chatbot-page__composer-meta">
                <span className="chatbot-page__keyboard-hint">{copy.keyboardHint}</span>
                <span className="chatbot-page__disclaimer">{copy.disclaimer}</span>
              </div>
            </div>
          </div>

          <div className="chatbot-page__escalation">
            <ShieldAlert className="chatbot-page__escalation-icon" />
            <span>{t.chatbotEscalation}</span>
            <Link to="/support">{t.chatbotSubmitTicket}</Link>
          </div>
        </section>
      </div>
    </div>
  )
}

export default Chatbot
