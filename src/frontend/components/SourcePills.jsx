import { useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/StructuredMessage.css'

/**
 * SourcePills shows source citations as inline pills.
 * Displays up to `maxVisible` directly, with a "+N more" expander.
 */
export function SourcePills({ sources }) {
  const { t } = useLanguage()
  const [expanded, setExpanded] = useState(false)
  const maxVisible = 3

  if (!sources || sources.length === 0) return null

  const visible = expanded ? sources : sources.slice(0, maxVisible)
  const hiddenCount = sources.length - maxVisible
  const sourcesLabel = (t.aiSources || t.sourcesLabel || 'Nguồn').replace(/:$/, '')
  const moreLabel = t.moreSourcesCount
    ? t.moreSourcesCount.replace('{{count}}', hiddenCount)
    : 'nguồn khác'

  return (
    <div className="source-pills">
      <span className="source-pills__label">
        {sourcesLabel}
      </span>
      <div className="source-pills__list">
        {visible.map((source, idx) => {
          let label = source.source_file || sourcesLabel
          if (source.path) {
            try {
              const url = new URL(source.path)
              label = url.hostname.replace(/^www\./, '')
            } catch {
              // Keep source_file as label.
            }
          }

          if (source.path) {
            return (
              <a
                key={`src-${idx}`}
                className="source-pills__pill source-pills__pill--link"
                href={source.path}
                target="_blank"
                rel="noopener noreferrer"
                title={source.path}
              >
                <span>{label}</span>
                <ExternalLink className="source-pills__ext-icon" />
              </a>
            )
          }

          return (
            <span key={`src-${idx}`} className="source-pills__pill">
              {label}
            </span>
          )
        })}

        {!expanded && hiddenCount > 0 && (
          <button
            className="source-pills__more"
            type="button"
            onClick={() => setExpanded(true)}
          >
            +{hiddenCount} {moreLabel}
          </button>
        )}
      </div>
    </div>
  )
}

export default SourcePills
