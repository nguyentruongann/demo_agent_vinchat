/**
 * parseStructuredMessage(text)
 *
 * Extracts structured data from the AI's markdown-ish answer text.
 * Returns an object that StructuredMessage.jsx can render as TopicCards,
 * Rails, ContextStrips, etc.
 *
 * If the text is too short or unstructured, returns { plainText } so the
 * caller can fall back to plain rendering.
 */

// ── helpers ──────────────────────────────────────────────────────────────────

const TIME_RANGE_RE = /(\d{1,2}[:.]\d{2})\s*[–—-]\s*(\d{1,2}[:.]\d{2})/
const TIME_SINGLE_RE = /^(\d{1,2}[:.]\d{2})\b/
const BOLD_HEADING_RE = /^\*\*(.+?)\*\*\s*[:：]?\s*$/
const NUMBERED_HEADING_RE = /^(?:#{1,4}\s+)?(?:\d+[.)]\s*)?(?:\*\*)?(.+?)(?:\*\*)?\s*[:：]?\s*$/
const BULLET_RE = /^[\s]*[•●◆▸▹►–—*-]\s+/
const LOCATION_RE = /(?:cách|gần|nằm\s+(?:tại|ở|trên)|located|distance|khoảng\s+cách|km\s+từ)/i
const EMOJI_RE = /^(\p{Emoji_Presentation}|\p{Extended_Pictographic})\s*/u

const TOPIC_ICONS = [
  { pattern: /golf/i, icon: '⛳' },
  { pattern: /spa|wellness|massage/i, icon: '💆' },
  { pattern: /biển|beach|ocean|bãi\s*cát/i, icon: '🏖️' },
  { pattern: /ăn|dining|nhà\s*hàng|restaurant|buffet|hải\s*sản|seafood/i, icon: '🍽️' },
  { pattern: /vui\s*chơi|park|vinwonders|trò\s*chơi|game|safari/i, icon: '🎢' },
  { pattern: /trẻ\s*em|child|kid|family|gia\s*đình/i, icon: '👶' },
  { pattern: /villa|biệt\s*thự|phòng|room|suite/i, icon: '🏨' },
  { pattern: /bảo\s*tàng|museum|teddy|gấu/i, icon: '🧸' },
  { pattern: /show|biểu\s*diễn|sunset|concert|nhạc/i, icon: '🎭' },
  { pattern: /ngày\s*\d|day\s*\d|lịch\s*trình|itinerary/i, icon: '📋' },
  { pattern: /giá|price|budget|ngân\s*sách|cost|chi\s*phí/i, icon: '💰' },
  { pattern: /check.?in|nhận\s*phòng/i, icon: '🔑' },
  { pattern: /check.?out|trả\s*phòng/i, icon: '🚪' },
  { pattern: /chính\s*sách|policy|quy\s*định|regulation/i, icon: '📜' },
  { pattern: /cáp\s*treo|cable\s*car/i, icon: '🚡' },
  { pattern: /grand\s*world|phố|street|town/i, icon: '🏘️' },
]

function guessTopicIcon(title) {
  for (const { pattern, icon } of TOPIC_ICONS) {
    if (pattern.test(title)) return icon
  }
  return '📌'
}

function getImplicitTopicTitle(text) {
  const value = String(text || '')
  if (/[ぁ-んァ-ン]/u.test(value)) return '主な情報'
  if (/[가-힣]/u.test(value)) return '주요 정보'
  if (/[\u4e00-\u9fff]/u.test(value)) return '主要信息'

  const normalized = value.toLowerCase()
  if (/[ăâđêôơưàáạảãèéẹẻẽìíịỉĩòóọỏõùúụủũỳýỵỷỹ]/iu.test(value) ||
      /\b(tại|ở|có|thông tin|nhu cầu|bạn|khách sạn|dịch vụ|ẩm thực|vui chơi)\b/iu.test(normalized)) {
    return 'Thông tin nổi bật'
  }
  return 'Highlights'
}

function stripMarkdownBold(str) {
  return str.replace(/\*\*(.+?)\*\*/g, '$1').trim()
}

function extractLeadingEmoji(str) {
  const m = str.match(EMOJI_RE)
  if (m) return { icon: m[0].trim(), rest: str.slice(m[0].length).trim() }
  return { icon: null, rest: str }
}

function cleanBulletText(line) {
  return line.replace(BULLET_RE, '').trim()
}

function isBullet(line) {
  return BULLET_RE.test(line)
}

function isHeadingLine(line) {
  const trimmed = line.trim()
  if (!trimmed) return null

  // **Bold heading**
  const boldMatch = trimmed.match(BOLD_HEADING_RE)
  if (boldMatch) return stripMarkdownBold(boldMatch[1])

  // ### Markdown heading or numbered heading (but only if short-ish)
  if (/^#{1,4}\s+/.test(trimmed) || /^\d+[.)]\s+/.test(trimmed)) {
    const numMatch = trimmed.match(NUMBERED_HEADING_RE)
    if (numMatch && numMatch[1].length < 120) {
      return stripMarkdownBold(numMatch[1])
    }
  }

  return null
}

function parseTimeFromLine(text) {
  const rangeMatch = text.match(TIME_RANGE_RE)
  if (rangeMatch) return rangeMatch[0]
  const singleMatch = text.match(TIME_SINGLE_RE)
  if (singleMatch) return singleMatch[0]
  return null
}

function sanitizeTypos(obj) {
  if (typeof obj === 'string') {
    return obj
      .replace(/\bQor\s+định\b/gi, 'Quy định')
      .replace(/\bQor\s+dinh\b/gi, 'Quy định')
      .replace(/\bQor\b/gi, 'Quy')
  }
  if (Array.isArray(obj)) {
    return obj.map(sanitizeTypos)
  }
  if (obj && typeof obj === 'object') {
    const res = {}
    for (const key of Object.keys(obj)) {
      res[key] = sanitizeTypos(obj[key])
    }
    return res
  }
  return obj
}

function normalizeTopics(rawTopics, sourceText) {
  if (!Array.isArray(rawTopics)) return []

  const topics = rawTopics
    .filter((topic) => topic && typeof topic === 'object')
    .map((topic) => ({
      icon: topic.icon || guessTopicIcon(String(topic.title || '')),
      title: String(topic.title || '').trim(),
      subtitle: String(topic.subtitle || '').trim(),
      stops: Array.isArray(topic.stops) ? topic.stops.filter(Boolean) : [],
      items: Array.isArray(topic.items)
        ? topic.items.map((item) => String(item || '').trim()).filter(Boolean)
        : [],
    }))
    .filter((topic) => topic.title || topic.stops.length || topic.items.length)

  if (!topics.length) return []

  // Gemini sometimes formats a short list as consecutive bold lines:
  //   **Tên khách hàng**
  //   **Số booking**
  //   **Loại thanh toán**
  // The old parser treated every bold line as a new card heading, producing three
  // empty accordion bodies rendered as "—". If *all* parsed topics are header-only,
  // they are semantically a list, so collapse them into one visible list card.
  if (topics.every((topic) => !topic.stops.length && !topic.items.length)) {
    const items = topics.map((topic) => topic.title).filter(Boolean)
    if (!items.length) return []
    return [{
      icon: '📌',
      title: getImplicitTopicTitle(sourceText),
      subtitle: `${items.length} mục`,
      stops: [],
      items,
    }]
  }

  for (const topic of topics) {
    if (topic.subtitle) continue
    const parts = []
    if (topic.stops.length) parts.push(`${topic.stops.length} hoạt động`)
    if (topic.items.length && !topic.stops.length) parts.push(`${topic.items.length} mục`)
    topic.subtitle = parts.join(' · ')
  }
  return topics
}

// ── main parser ──────────────────────────────────────────────────────────────

export function parseStructuredMessage(text) {
  if (!text || typeof text !== 'string') {
    return { plainText: text || '', lead: '', context: null, topics: [], sources: [], actions: [] }
  }

  // ── 0. Check if input is structured JSON (from backend Gemini output) ──
  try {
    let cleanText = text.trim()
    if (cleanText.startsWith('```')) {
      cleanText = cleanText.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim()
    }
    if ((cleanText.startsWith('{') && cleanText.endsWith('}')) || (cleanText.startsWith('[') && cleanText.endsWith(']'))) {
      const rawObj = JSON.parse(cleanText)
      if (rawObj && typeof rawObj === 'object' && !Array.isArray(rawObj)) {
        const obj = sanitizeTypos(rawObj)
        const topics = normalizeTopics(obj.topics, text)
        return {
          lead: obj.lead || '',
          context: obj.context && typeof obj.context === 'object' ? obj.context : null,
          topics,
          sources: Array.isArray(obj.sources) ? obj.sources : [],
          actions: Array.isArray(obj.actions) ? obj.actions : [],
          plainText: topics.length ? '' : (obj.lead || text),
        }
      }
    }
  } catch {
    // Not valid JSON, proceed to markdown regex parsing
  }

  const lines = text.split('\n')

  // Too short — just return as plain text
  if (lines.length < 3 && text.length < 200) {
    return { plainText: text, lead: text, context: null, topics: [], sources: [], actions: [] }
  }

  let lead = ''
  let context = null
  const topics = []
  let currentTopic = null
  let leadDone = false

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i]
    const trimmed = raw.trim()

    // Skip empty lines
    if (!trimmed) continue

    // ── Extract lead (first 1–2 non-heading, non-bullet sentences) ──
    if (!leadDone) {
      const heading = isHeadingLine(trimmed)
      if (!heading && !isBullet(trimmed)) {
        const cleaned = trimmed
        if (lead) {
          lead += ' ' + cleaned
          leadDone = true // 2 sentences max for lead
        } else {
          lead = cleaned
          // If this looks like a complete intro (has period/exclamation), mark done
          if (/[.!?]$/.test(cleaned) && cleaned.length > 40) {
            leadDone = true
          }
        }
        continue
      } else {
        leadDone = true
      }
    }

    // ── Detect context strip (location / distance info) ──
    // A bullet can itself describe a place (e.g. "- The Venice ... nằm bên sông").
    // Do not consume such bullets as a context strip, otherwise the place silently
    // disappears from the list. ContextStrip is reserved for standalone prose.
    if (!context && !isBullet(trimmed) && LOCATION_RE.test(trimmed)) {
      const cleaned = trimmed
      if (stripMarkdownBold(cleaned).length < 150) {
        context = { icon: '📍', text: cleaned }
        continue
      }
    }

    // ── Detect topic headings ──
    const headingTitle = isHeadingLine(trimmed)
    if (headingTitle) {
      // Finish previous topic
      if (currentTopic) {
        topics.push(currentTopic)
      }
      const { icon: emojiIcon, rest: titleWithoutEmoji } = extractLeadingEmoji(headingTitle)
      const icon = emojiIcon || guessTopicIcon(headingTitle)
      currentTopic = {
        icon,
        title: titleWithoutEmoji || headingTitle,
        subtitle: '',
        stops: [],
        items: [],
      }
      continue
    }

    // ── Process bullet / content lines under a topic ──
    if (currentTopic) {
      const bulletText = isBullet(trimmed) ? cleanBulletText(trimmed) : trimmed
      const parsingText = stripMarkdownBold(bulletText)
      const time = parseTimeFromLine(parsingText)

      if (time) {
        // It's a timeline stop. Use markdown-free text for structural parsing;
        // normal non-timeline content keeps its inline markdown for rendering.
        const afterTime = parsingText.replace(TIME_RANGE_RE, '').replace(TIME_SINGLE_RE, '').trim()
        const colonIdx = afterTime.indexOf(':')
        let name, desc
        if (colonIdx > 0 && colonIdx < 60) {
          name = afterTime.slice(0, colonIdx).replace(/^[–—-]\s*/, '').trim()
          desc = afterTime.slice(colonIdx + 1).trim()
        } else {
          const parts = afterTime.replace(/^[–—-]\s*/, '').split(/[.!]/, 2)
          name = parts[0]?.trim() || afterTime.replace(/^[–—-]\s*/, '').trim()
          desc = parts[1]?.trim() || ''
        }
        currentTopic.stops.push({ time, name, desc })
      } else if (isBullet(trimmed)) {
        currentTopic.items.push(bulletText)
      } else {
        // Non-bullet text under a topic — append as description item
        currentTopic.items.push(bulletText)
      }
      continue
    }

    // ── Standalone bullet without a topic — create an implicit one ──
    // Broad discovery answers often come back as an intro followed directly by
    // bullets, without markdown headings. Previously only timed bullets were kept,
    // so normal place/service bullets were dropped from the rendered response.
    if (isBullet(trimmed)) {
      const displayText = cleanBulletText(trimmed)
      const parsingText = stripMarkdownBold(displayText)
      const time = parseTimeFromLine(parsingText)

      if (!currentTopic) {
        currentTopic = {
          icon: time ? '📋' : '📌',
          title: time ? 'Lịch trình' : getImplicitTopicTitle(text),
          subtitle: '',
          stops: [],
          items: [],
        }
      }

      if (time) {
        const afterTime = parsingText.replace(TIME_RANGE_RE, '').replace(TIME_SINGLE_RE, '').trim()
        const name = afterTime.replace(/^[–—-]\s*/, '').trim()
        currentTopic.stops.push({ time, name, desc: '' })
      } else if (displayText) {
        currentTopic.items.push(displayText)
      }
      continue
    }
  }

  // Push last topic
  if (currentTopic) {
    topics.push(currentTopic)
  }

  const normalizedTopics = normalizeTopics(topics, text)

  // If we got nothing useful, return plainText fallback
  if (!normalizedTopics.length && !lead) {
    return { plainText: text, lead: text, context: null, topics: [] }
  }

  return sanitizeTypos({
    lead: lead || '',
    context,
    topics: normalizedTopics,
    plainText: normalizedTopics.length === 0 ? text : '',
  })
}

export default parseStructuredMessage
