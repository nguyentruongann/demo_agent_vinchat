import InlineMarkdown from './InlineMarkdown'
import '../styles/components/StructuredMessage.css'

/**
 * ContextStrip — small teal-soft pill showing location/distance info.
 * Sits below the lead text, above topic cards.
 */
function ContextStrip({ context }) {
  if (!context) return null

  return (
    <div className="context-strip">
      <span className="context-strip__icon">{context.icon}</span>
      <span className="context-strip__text"><InlineMarkdown>{context.text}</InlineMarkdown></span>
    </div>
  )
}

export default ContextStrip
