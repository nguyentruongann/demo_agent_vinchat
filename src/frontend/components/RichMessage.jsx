import { useState } from 'react'
import { ExternalLink, ImageIcon, Link2, X } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/RichMessage.css'

/**
 * Image extensions that should render as inline previews.
 */
const IMAGE_EXTENSIONS = /\.(jpg|jpeg|png|gif|webp|svg|bmp|avif)(\?[^\s]*)?$/i

/**
 * Split a text string into an array of segments:
 * each segment is either plain text or a URL token.
 */
function tokenize(text) {
  if (!text) return []

  // Match http(s) URLs, including paths & query strings.
  const urlRegex = /(https?:\/\/[^\s<>"')\]},]+)/gi
  const parts = []
  let lastIndex = 0
  let match

  while ((match = urlRegex.exec(text)) !== null) {
    // Push preceding plain text.
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, match.index) })
    }

    let url = match[1]
    // Strip trailing punctuation that is almost never part of a real URL.
    url = url.replace(/[.,;:!?)]+$/, '')

    const isImage = IMAGE_EXTENSIONS.test(url)
    parts.push({ type: isImage ? 'image' : 'url', value: url })
    lastIndex = match.index + match[0].length
  }

  // Trailing plain text.
  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) })
  }

  return parts
}

function InlineImage({ src }) {
  const { t } = useLanguage()
  const [lightbox, setLightbox] = useState(false)
  const [error, setError] = useState(false)

  if (error) {
    return (
      <a
        className="rich-msg__link"
        href={src}
        target="_blank"
        rel="noopener noreferrer"
      >
        <ImageIcon className="rich-msg__link-icon" />
        <span className="rich-msg__link-text">{src}</span>
        <ExternalLink className="rich-msg__external-icon" />
      </a>
    )
  }

  return (
    <>
      <span className="rich-msg__image-wrap" onClick={() => setLightbox(true)}>
        <img
          className="rich-msg__image"
          src={src}
          alt=""
          loading="lazy"
          onError={() => setError(true)}
        />
        <span className="rich-msg__image-overlay">
          <ImageIcon className="rich-msg__image-overlay-icon" />
        </span>
      </span>

      {lightbox && (
        <div className="rich-msg__lightbox" onClick={() => setLightbox(false)}>
          <button
            className="rich-msg__lightbox-close"
            type="button"
            aria-label={t.close}
            onClick={(e) => {
              e.stopPropagation()
              setLightbox(false)
            }}
          >
            <X className="rich-msg__lightbox-close-icon" />
          </button>
          <img className="rich-msg__lightbox-img" src={src} alt="" />
        </div>
      )}
    </>
  )
}

function InlineLink({ href }) {
  // Decide a human-friendly label: hostname + short path.
  let label
  try {
    const parsed = new URL(href)
    const pathSegments = parsed.pathname
      .split('/')
      .filter(Boolean)
      .slice(-2)
      .join('/')
    label = parsed.hostname + (pathSegments ? `/${pathSegments}` : '')
  } catch {
    label = href
  }

  return (
    <a
      className="rich-msg__link"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={href}
    >
      <Link2 className="rich-msg__link-icon" />
      <span className="rich-msg__link-text">{label}</span>
      <ExternalLink className="rich-msg__external-icon" />
    </a>
  )
}

/**
 * Renders chat message text with:
 * - URLs rendered as clickable link chips
 * - Image URLs rendered as inline previews with lightbox
 * - Plain text preserved with whitespace (pre-wrap)
 *
 * @param {{ text: string, isUser?: boolean }} props
 */
function RichMessage({ text, isUser }) {
  // User messages are rendered as-is (no parsing).
  if (isUser || !text) {
    return <p className="rich-msg__text">{text}</p>
  }

  const tokens = tokenize(text)

  // If there are no URLs at all, render as plain text (fast path).
  if (tokens.length === 1 && tokens[0].type === 'text') {
    return <p className="rich-msg__text">{text}</p>
  }

  return (
    <div className="rich-msg">
      {tokens.map((token, index) => {
        if (token.type === 'image') {
          return <InlineImage key={`img-${index}`} src={token.value} />
        }
        if (token.type === 'url') {
          return <InlineLink key={`url-${index}`} href={token.value} />
        }
        // Plain text segment — preserve whitespace.
        return (
          <span key={`txt-${index}`} className="rich-msg__text">
            {token.value}
          </span>
        )
      })}
    </div>
  )
}

/**
 * Renders a compact list of source links.
 *
 * @param {{ sources: Array<{source_file: string, path?: string, category?: string}>, language?: string }} props
 */
export function SourceChips({ sources, language }) {
  const { t } = useLanguage()
  if (!sources || sources.length === 0) return null

  return (
    <div className="rich-msg__sources">
      <span className="rich-msg__sources-label">
        📎 {t.sourcesLabel}
      </span>
      <div className="rich-msg__sources-list">
        {sources.map((source, index) => (
          <SourceChip key={`src-${index}`} source={source} />
        ))}
      </div>
    </div>
  )
}

function SourceChip({ source }) {
  if (source.path) {
    return (
      <a
        className="rich-msg__source-chip rich-msg__source-chip--link"
        href={source.path}
        target="_blank"
        rel="noopener noreferrer"
        title={source.path}
      >
        <Link2 className="rich-msg__source-icon" />
        <span>{source.source_file}</span>
        <ExternalLink className="rich-msg__source-external" />
      </a>
    )
  }

  return (
    <span className="rich-msg__source-chip">
      <span>{source.source_file}</span>
    </span>
  )
}

export default RichMessage
