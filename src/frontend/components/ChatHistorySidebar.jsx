import {
  History,
  MessageSquare,
  Plus,
  X,
} from 'lucide-react'
import '../styles/components/ChatHistorySidebar.css'

const COPY = {
  en: {
    aria: 'Chat history',
    title: 'Chat history',
    close: 'Close history',
    newChat: 'New conversation',
    conversations: 'Conversations',
    loading: 'Loading history…',
    empty: 'No conversations yet.',
    messages: 'messages',
  },
  vi: {
    aria: 'Lịch sử chat',
    title: 'Lịch sử chat',
    close: 'Đóng lịch sử',
    newChat: 'Cuộc chat mới',
    conversations: 'Các cuộc trò chuyện',
    loading: 'Đang tải lịch sử…',
    empty: 'Chưa có cuộc trò chuyện nào.',
    messages: 'tin nhắn',
  },
  ko: {
    aria: '채팅 기록',
    title: '채팅 기록',
    close: '채팅 기록 닫기',
    newChat: '새 대화',
    conversations: '대화 목록',
    loading: '채팅 기록을 불러오는 중…',
    empty: '아직 대화가 없습니다.',
    messages: '메시지',
  },
  ja: {
    aria: 'チャット履歴',
    title: 'チャット履歴',
    close: '履歴を閉じる',
    newChat: '新しいチャット',
    conversations: '会話',
    loading: '履歴を読み込み中…',
    empty: 'まだ会話はありません。',
    messages: '件',
  },
  zh: {
    aria: '聊天记录',
    title: '聊天记录',
    close: '关闭聊天记录',
    newChat: '新对话',
    conversations: '对话',
    loading: '正在加载聊天记录…',
    empty: '暂无对话。',
    messages: '条消息',
  },
}

function formatSessionTime(value, language) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  if (sameDay) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const localeByLanguage = {
    vi: 'vi-VN',
    ko: 'ko-KR',
    ja: 'ja-JP',
    zh: 'zh-CN',
    en: 'en-US',
  }

  return date.toLocaleDateString(localeByLanguage[language] || 'en-US', {
    day: '2-digit',
    month: '2-digit',
  })
}

function ChatHistorySidebar({
  sessions,
  activeSessionId,
  loading,
  open,
  language,
  onClose,
  onNewConversation,
  onSelectSession,
}) {
  const copy = COPY[language] || COPY.en

  return (
    <aside
      className={`chat-history ${open ? 'chat-history--open' : ''}`}
      aria-label={copy.aria}
    >
      <div className="chat-history__mobile-head">
        <div className="chat-history__heading">
          <History className="chat-history__heading-icon" />
          <span>{copy.title}</span>
        </div>
        <button
          className="chat-history__close"
          type="button"
          aria-label={copy.close}
          onClick={onClose}
        >
          <X />
        </button>
      </div>

      <button className="chat-history__new" type="button" onClick={onNewConversation}>
        <Plus className="chat-history__new-icon" />
        <span>{copy.newChat}</span>
      </button>

      <div className="chat-history__section-title">{copy.conversations}</div>

      <div className="chat-history__list">
        {loading ? (
          <div className="chat-history__empty">{copy.loading}</div>
        ) : sessions.length === 0 ? (
          <div className="chat-history__empty">
            <MessageSquare className="chat-history__empty-icon" />
            <span>{copy.empty}</span>
          </div>
        ) : (
          sessions.map((session) => (
            <button
              className={`chat-history__item ${
                activeSessionId === session.id ? 'chat-history__item--active' : ''
              }`}
              key={session.id}
              type="button"
              onClick={() => onSelectSession(session.id)}
              title={session.title}
            >
              <MessageSquare className="chat-history__item-icon" />
              <span className="chat-history__item-copy">
                <span className="chat-history__item-title">{session.title}</span>
                <span className="chat-history__item-meta">
                  {formatSessionTime(session.last_activity_at || session.started_at, language)}
                  {session.message_count > 0 && (
                    <span>
                      {session.message_count} {copy.messages}
                    </span>
                  )}
                </span>
              </span>
            </button>
          ))
        )}
      </div>
    </aside>
  )
}

export default ChatHistorySidebar
