import { Fragment } from 'react'

// Lightweight, safe inline markdown renderer for assistant-generated text.
// It intentionally supports only presentation tokens that can be rendered
// without injecting HTML: bold, emphasis and inline code.
const INLINE_MARKDOWN_RE = /(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`)/g

function InlineMarkdown({ children }) {
  const value = String(children ?? '')
  const parts = value.split(INLINE_MARKDOWN_RE)

  return parts.map((part, index) => {
    if (!part) return null
    const key = `inline-md-${index}`

    if (
      (part.startsWith('**') && part.endsWith('**')) ||
      (part.startsWith('__') && part.endsWith('__'))
    ) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }

    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={key}>{part.slice(1, -1)}</code>
    }

    return <Fragment key={key}>{part}</Fragment>
  })
}

export default InlineMarkdown
