import { Fragment } from 'react'
import '../styles/components/InlineMarkdown.css'

// Lightweight, safe inline markdown renderer for assistant-generated text.
// Supported without dangerouslySetInnerHTML:
// - **bold** / __bold__
// - *emphasis* / _emphasis_
// - `inline code`
// - [label](https://example.com)
// - [label] (https://example.com)  <-- tolerant of common LLM spacing
// - bare http(s) URLs
//
// Markdown links are intentionally limited to http/https so generated text
// cannot create javascript:, data:, or other unsafe navigation schemes.
const INLINE_TOKEN_RE = /(\[[^\]\n]+\]\s*\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<>"']+|\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\*[^*\n]+\*|_[^_\n]+_)/gi
const MARKDOWN_LINK_RE = /^\[([^\]\n]+)\]\s*\((https?:\/\/[^\s)]+)\)$/i

function trimUrlPunctuation(rawUrl) {
  let url = rawUrl
  let trailing = ''

  // Sentence punctuation is commonly attached to a bare URL by the LLM.
  // Keep it outside the clickable anchor.
  while (/[.,;:!?]$/.test(url)) {
    trailing = url.slice(-1) + trailing
    url = url.slice(0, -1)
  }

  // Only remove a closing parenthesis when there are more closing than opening
  // parentheses in the URL. This preserves valid URLs containing balanced ().
  while (url.endsWith(')')) {
    const openCount = (url.match(/\(/g) || []).length
    const closeCount = (url.match(/\)/g) || []).length
    if (closeCount <= openCount) break
    trailing = ')' + trailing
    url = url.slice(0, -1)
  }

  return { url, trailing }
}

function isSafeHttpUrl(value) {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

function InlineAnchor({ href, children, title }) {
  if (!isSafeHttpUrl(href)) return <>{children}</>

  return (
    <a
      className="inline-md__link"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={title || href}
    >
      <span className="inline-md__link-label">{children}</span>
      <span className="inline-md__link-external" aria-hidden="true">↗</span>
    </a>
  )
}

function InlineMarkdown({ children }) {
  const value = String(children ?? '')
  const parts = value.split(INLINE_TOKEN_RE)

  return parts.map((part, index) => {
    if (!part) return null
    const key = `inline-md-${index}`

    const markdownLink = part.match(MARKDOWN_LINK_RE)
    if (markdownLink) {
      const [, label, href] = markdownLink
      return (
        <InlineAnchor key={key} href={href} title={href}>
          {label}
        </InlineAnchor>
      )
    }

    if (/^https?:\/\//i.test(part)) {
      const { url, trailing } = trimUrlPunctuation(part)
      return (
        <Fragment key={key}>
          <InlineAnchor href={url}>{url}</InlineAnchor>
          {trailing}
        </Fragment>
      )
    }

    if (
      (part.startsWith('**') && part.endsWith('**')) ||
      (part.startsWith('__') && part.endsWith('__'))
    ) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }

    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={key}>{part.slice(1, -1)}</code>
    }

    if (
      (part.startsWith('*') && part.endsWith('*')) ||
      (part.startsWith('_') && part.endsWith('_'))
    ) {
      return <em key={key}>{part.slice(1, -1)}</em>
    }

    return <Fragment key={key}>{part}</Fragment>
  })
}

export default InlineMarkdown
