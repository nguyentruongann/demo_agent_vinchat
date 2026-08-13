import { Fragment } from 'react'

const INLINE_TOKEN = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<]+)/g

function trimTrailingPunctuation(url) {
  return url.replace(/[.,;:!?]+$/, '')
}

function renderInline(text, keyPrefix = 'inline') {
  const value = String(text ?? '')
  const parts = value.split(INLINE_TOKEN)

  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`

    if (!part) return null

    if ((part.startsWith('**') && part.endsWith('**')) || (part.startsWith('__') && part.endsWith('__'))) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }

    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={key}>{part.slice(1, -1)}</code>
    }

    const markdownLink = part.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/)
    if (markdownLink) {
      return (
        <a key={key} href={markdownLink[2]} target="_blank" rel="noreferrer noopener">
          {markdownLink[1]}
        </a>
      )
    }

    if (/^https?:\/\//.test(part)) {
      const url = trimTrailingPunctuation(part)
      const trailing = part.slice(url.length)
      return (
        <Fragment key={key}>
          <a href={url} target="_blank" rel="noreferrer noopener">
            {url}
          </a>
          {trailing}
        </Fragment>
      )
    }

    return <Fragment key={key}>{part}</Fragment>
  })
}

function flushParagraph(blocks, paragraphLines, blockIndex) {
  if (!paragraphLines.length) return blockIndex

  blocks.push(
    <p key={`paragraph-${blockIndex}`}>
      {paragraphLines.map((line, index) => (
        <Fragment key={`paragraph-${blockIndex}-line-${index}`}>
          {index > 0 && <br />}
          {renderInline(line, `paragraph-${blockIndex}-${index}`)}
        </Fragment>
      ))}
    </p>,
  )

  paragraphLines.length = 0
  return blockIndex + 1
}

function flushList(blocks, listItems, ordered, blockIndex) {
  if (!listItems.length) return blockIndex

  const ListTag = ordered ? 'ol' : 'ul'
  blocks.push(
    <ListTag key={`list-${blockIndex}`}>
      {listItems.map((item, index) => (
        <li key={`list-${blockIndex}-${index}`}>
          {renderInline(item, `list-${blockIndex}-${index}`)}
        </li>
      ))}
    </ListTag>,
  )

  listItems.length = 0
  return blockIndex + 1
}

function MarkdownContent({ children, className = '' }) {
  const text = String(children ?? '').replace(/\r\n?/g, '\n')
  const lines = text.split('\n')
  const blocks = []
  const paragraphLines = []
  const listItems = []
  let listOrdered = false
  let inCodeBlock = false
  let codeLanguage = ''
  let codeLines = []
  let blockIndex = 0

  const closeParagraph = () => {
    blockIndex = flushParagraph(blocks, paragraphLines, blockIndex)
  }

  const closeList = () => {
    blockIndex = flushList(blocks, listItems, listOrdered, blockIndex)
  }

  const closeCodeBlock = () => {
    if (!inCodeBlock && !codeLines.length) return

    blocks.push(
      <pre key={`code-${blockIndex}`}>
        <code data-language={codeLanguage || undefined}>{codeLines.join('\n')}</code>
      </pre>,
    )
    blockIndex += 1
    codeLines = []
    codeLanguage = ''
    inCodeBlock = false
  }

  lines.forEach((rawLine) => {
    const line = rawLine.replace(/\s+$/, '')

    const fence = line.match(/^```\s*([^\s`]*)\s*$/)
    if (fence) {
      if (inCodeBlock) {
        closeCodeBlock()
      } else {
        closeParagraph()
        closeList()
        inCodeBlock = true
        codeLanguage = fence[1] || ''
      }
      return
    }

    if (inCodeBlock) {
      codeLines.push(rawLine)
      return
    }

    if (!line.trim()) {
      closeParagraph()
      closeList()
      return
    }

    if (/^\s*(---+|___+|\*\*\*+)\s*$/.test(line)) {
      closeParagraph()
      closeList()
      blocks.push(<hr key={`hr-${blockIndex}`} />)
      blockIndex += 1
      return
    }

    const heading = line.match(/^\s*(#{1,4})\s+(.+)$/)
    if (heading) {
      closeParagraph()
      closeList()
      const level = Math.min(Math.max(heading[1].length, 3), 6)
      const HeadingTag = `h${level}`
      blocks.push(
        <HeadingTag key={`heading-${blockIndex}`}>
          {renderInline(heading[2], `heading-${blockIndex}`)}
        </HeadingTag>,
      )
      blockIndex += 1
      return
    }

    const unorderedItem = line.match(/^\s*[-*+]\s+(.+)$/)
    const orderedItem = line.match(/^\s*\d+[.)]\s+(.+)$/)
    if (unorderedItem || orderedItem) {
      closeParagraph()
      const nextOrdered = Boolean(orderedItem)
      if (listItems.length && nextOrdered !== listOrdered) {
        closeList()
      }
      listOrdered = nextOrdered
      listItems.push((orderedItem || unorderedItem)[1])
      return
    }

    const quote = line.match(/^\s*>\s?(.*)$/)
    if (quote) {
      closeParagraph()
      closeList()
      blocks.push(
        <blockquote key={`quote-${blockIndex}`}>
          {renderInline(quote[1], `quote-${blockIndex}`)}
        </blockquote>,
      )
      blockIndex += 1
      return
    }

    closeList()
    paragraphLines.push(line)
  })

  closeParagraph()
  closeList()
  if (inCodeBlock || codeLines.length) closeCodeBlock()

  return <div className={`chatbot-markdown ${className}`.trim()}>{blocks}</div>
}

export default MarkdownContent
