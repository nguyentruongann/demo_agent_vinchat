import { useMemo } from 'react'
import parseStructuredMessage from '../services/parseStructuredMessage'
import ContextStrip from './ContextStrip'
import TopicCard from './TopicCard'
import SourcePills from './SourcePills'
import ActionRow from './ActionRow'
import RichMessage from './RichMessage'
import InlineMarkdown from './InlineMarkdown'
import '../styles/components/StructuredMessage.css'

/**
 * StructuredMessage — top-level renderer for assistant AI messages.
 *
 * Parses raw text or structured JSON from backend Gemini output.
 * Renders TopicCards, Rail timelines, ContextStrips, SourcePills,
 * and ActionRows seamlessly.
 */
function StructuredMessage({ text, sources, isUser, onAction, showActions = true }) {
  // User messages are always plain
  if (isUser) {
    return <RichMessage text={text} isUser />
  }

  const parsed = useMemo(() => parseStructuredMessage(text), [text])

  // Merge RAG sources with JSON inline sources
  const mergedSources = useMemo(() => {
    if (sources && sources.length > 0) return sources
    if (parsed.sources && parsed.sources.length > 0) {
      return parsed.sources.map((s) => ({
        source_file: s.domain || 'vinpearl.com',
        path: s.domain ? (s.domain.startsWith('http') ? s.domain : `https://${s.domain}`) : null,
      }))
    }
    return []
  }, [sources, parsed.sources])

  // Fail-safe: if parsing produced no topic structure, always render the full raw
  // answer. A detected lead must never suppress the rest of plainText.
  if (parsed.plainText && parsed.topics.length === 0) {
    return (
      <div className="structured-msg structured-msg--plain">
        <RichMessage text={parsed.plainText || text} isUser={false} />
        {mergedSources && mergedSources.length > 0 && <SourcePills sources={mergedSources} />}
        {showActions && <ActionRow actions={parsed.actions} onAction={onAction} />}
      </div>
    )
  }

  return (
    <div className="structured-msg">
      {/* Lead paragraph */}
      {parsed.lead && (
        <p className="structured-msg__lead"><InlineMarkdown>{parsed.lead}</InlineMarkdown></p>
      )}

      {/* Context strip (location/distance) */}
      <ContextStrip context={parsed.context} />

      {/* Topic cards */}
      {parsed.topics.length > 0 && (
        <div className="structured-msg__topics">
          {parsed.topics.map((topic, idx) => (
            <TopicCard
              key={`topic-${idx}`}
              topic={topic}
              defaultOpen={idx === 0}
            />
          ))}
        </div>
      )}

      {/* Source pills */}
      {mergedSources && mergedSources.length > 0 && (
        <SourcePills sources={mergedSources} />
      )}

      {/* Action row */}
      {showActions && <ActionRow actions={parsed.actions} onAction={onAction} />}
    </div>
  )
}

export default StructuredMessage
