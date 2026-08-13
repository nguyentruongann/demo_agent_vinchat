import {
  History,
  MessageSquare,
  Plus,
  X,
} from 'lucide-react'
import '../styles/components/ChatHistorySidebar.css'

function formatSessionTime(value, language) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  if (sameDay) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return date.toLocaleDateString(language === 'VI' ? 'vi-VN' : undefined, {
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
  const isVietnamese = language === 'VI'

  return (
    <aside className={`chat-history ${open ? 'chat-history--open' : ''}`} aria-label="Chat history">
      <div className="chat-history__mobile-head">
        <div className="chat-history__heading">
          <History className="chat-history__heading-icon" />
          <span>{isVietnamese ? 'Lịch sử chat' : 'Chat history'}</span>
        </div>
        <button
          className="chat-history__close"
          type="button"
          aria-label={isVietnamese ? 'Đóng lịch sử' : 'Close history'}
          onClick={onClose}
        >
          <X />
        </button>
      </div>

      <button className="chat-history__new" type="button" onClick={onNewConversation}>
        <Plus className="chat-history__new-icon" />
        <span>{isVietnamese ? 'Cuộc chat mới' : 'New conversation'}</span>
      </button>

      <div className="chat-history__section-title">
        {isVietnamese ? 'Các cuộc trò chuyện' : 'Conversations'}
      </div>

      <div className="chat-history__list">
        {loading ? (
          <div className="chat-history__empty">
            {isVietnamese ? 'Đang tải lịch sử…' : 'Loading history…'}
          </div>
        ) : sessions.length === 0 ? (
          <div className="chat-history__empty">
            <MessageSquare className="chat-history__empty-icon" />
            <span>{isVietnamese ? 'Chưa có cuộc trò chuyện nào.' : 'No conversations yet.'}</span>
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
                      {session.message_count} {isVietnamese ? 'tin nhắn' : 'messages'}
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
