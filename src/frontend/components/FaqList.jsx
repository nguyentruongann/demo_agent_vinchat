import { useState, useId } from 'react'
import { ChevronDown } from 'lucide-react'

/**
 * Accordion FAQ list component.
 * @param {{ items: import('../types').FaqItem[], emptyText?: string }} props
 */
export default function FaqList({ items, emptyText = 'No FAQs found.' }) {
  const [openId, setOpenId] = useState(null)
  const baseId = useId()

  if (!items || items.length === 0) {
    return (
      <div className="faq-list__empty">
        <p>{emptyText}</p>
      </div>
    )
  }

  const toggle = (id) => {
    setOpenId((prev) => (prev === id ? null : id))
  }

  return (
    <div className="faq-list" role="list">
      {items.map((item, idx) => {
        const isOpen = openId === item.id
        const panelId = `${baseId}-panel-${idx}`
        const triggerId = `${baseId}-trigger-${idx}`

        return (
          <div
            key={item.id}
            className={`faq-list__item${isOpen ? ' faq-list__item--open' : ''}`}
            role="listitem"
          >
            <button
              id={triggerId}
              className="faq-list__trigger"
              type="button"
              onClick={() => toggle(item.id)}
              aria-expanded={isOpen}
              aria-controls={panelId}
            >
              <span className="faq-list__question">{item.question}</span>
              <ChevronDown
                className={`faq-list__chevron${isOpen ? ' faq-list__chevron--open' : ''}`}
                size={18}
                aria-hidden="true"
              />
            </button>
            <div
              id={panelId}
              className="faq-list__panel"
              role="region"
              aria-labelledby={triggerId}
              hidden={!isOpen}
            >
              <div className="faq-list__answer">{item.answer}</div>
              {item.category && (
                <span className="faq-list__category-tag">{item.category}</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
