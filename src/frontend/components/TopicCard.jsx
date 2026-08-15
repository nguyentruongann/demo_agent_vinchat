import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import Rail from './Rail'
import InlineMarkdown from './InlineMarkdown'
import '../styles/components/StructuredMessage.css'

/**
 * TopicCard — collapsible card with icon + title + subtitle header.
 * Body contains a Rail (timeline) and/or plain items.
 * First card is expanded by default.
 */
function TopicCard({ topic, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  const hasBody = Boolean(topic.stops?.length || topic.items?.length)

  return (
    <div className={`topic-card ${open ? 'topic-card--open' : ''}`}>
      <button
        className="topic-card__header"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="topic-card__icon">{topic.icon}</span>
        <div className="topic-card__titles">
          <span className="topic-card__title"><InlineMarkdown>{topic.title}</InlineMarkdown></span>
          {topic.subtitle && (
            <span className="topic-card__subtitle"><InlineMarkdown>{topic.subtitle}</InlineMarkdown></span>
          )}
        </div>
        <ChevronDown className={`topic-card__chevron ${open ? 'topic-card__chevron--open' : ''}`} />
      </button>

      {hasBody && (
        <div className="topic-card__body-wrap" aria-hidden={!open}>
          <div className="topic-card__body">
            {topic.stops && topic.stops.length > 0 && (
              <Rail stops={topic.stops} />
            )}
            {topic.items && topic.items.length > 0 && (
              <ul className="topic-card__items">
                {topic.items.map((item, idx) => (
                  <li key={idx} className="topic-card__item"><InlineMarkdown>{item}</InlineMarkdown></li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default TopicCard
