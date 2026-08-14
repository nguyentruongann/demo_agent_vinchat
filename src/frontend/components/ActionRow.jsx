import { Link } from 'react-router-dom'
import { Search, Headphones, BookmarkPlus, ArrowRight } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/StructuredMessage.css'

/**
 * ActionRow — contextual action buttons after an AI response.
 * Handles dynamic actions schema from backend JSON or defaults:
 * [ { label: "Đặt phòng ngay", style: "primary", action: "book" }, ... ]
 */
function ActionRow({ actions, onAction }) {
  const { t } = useLanguage()

  // Do not manufacture CTA buttons when the backend did not explicitly ask for one.
  // The chat UI must not show Book now / Contact concierge after every answer.
  const hiddenActions = new Set([
    'book',
    'book_now',
    'search',
    'contact',
    'support',
    'ticket',
    'ask_more',
  ])

  const activeActions = (Array.isArray(actions) ? actions : []).filter((item) => {
    const action = String(item?.action || '').toLowerCase()
    return !hiddenActions.has(action)
  })

  if (activeActions.length === 0) return null

  function getActionTarget(item) {
    const act = (item.action || '').toLowerCase()
    if (act === 'book' || act === 'book_now' || act === 'search') return '/search'
    if (act === 'contact' || act === 'support' || act === 'ticket') return '/support'
    if (act === 'save_itinerary' || act === 'save') return '/support'
    return '/search'
  }

  function getActionLabel(item) {
    const act = (item.action || '').toLowerCase()
    if (act === 'book' || act === 'book_now' || act === 'search') {
      return t.bookNowAction || t.bookNow || 'Đặt phòng ngay'
    }
    if (act === 'contact' || act === 'support' || act === 'ticket' || act === 'ask_more') {
      return t.contactConcierge || t.createTicket || 'Liên hệ tư vấn'
    }
    if (act === 'save_itinerary' || act === 'save') {
      return t.saveItinerary || 'Lưu lịch trình'
    }
    return item.label || t.continue || 'Tiếp tục'
  }

  function getActionIcon(item) {
    const act = (item.action || '').toLowerCase()
    if (act === 'book' || act === 'book_now' || act === 'search') return <Search className="action-row__btn-icon" />
    if (act === 'contact' || act === 'support' || act === 'ticket' || act === 'ask_more') return <Headphones className="action-row__btn-icon" />
    if (act === 'save_itinerary' || act === 'save') return <BookmarkPlus className="action-row__btn-icon" />
    return <ArrowRight className="action-row__btn-icon" />
  }

  function getBtnClass(style) {
    if (style === 'primary') return 'action-row__btn action-row__btn--primary'
    if (style === 'secondary') return 'action-row__btn action-row__btn--secondary'
    return 'action-row__btn action-row__btn--ghost'
  }

  return (
    <div className="action-row">
      {activeActions.map((item, idx) => {
        const target = getActionTarget(item)
        const btnClass = getBtnClass(item.style)
        const icon = getActionIcon(item)
        const label = getActionLabel(item)

        return (
          <Link
            key={`action-${idx}`}
            className={btnClass}
            to={target}
            onClick={() => onAction && onAction(item)}
          >
            {icon}
            <span>{label}</span>
          </Link>
        )
      })}
    </div>
  )
}

export default ActionRow
