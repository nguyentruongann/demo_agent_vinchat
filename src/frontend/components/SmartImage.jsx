import { useEffect, useState } from 'react'
import experiencePlaceholder from '../image/placeholders/experience.svg'
import golfPlaceholder from '../image/placeholders/golf.svg'
import hotelPlaceholder from '../image/placeholders/hotel.svg'
import meetingPlaceholder from '../image/placeholders/meeting.svg'
import promotionPlaceholder from '../image/uu-dai-khuyen-mai_1684378388.jpg.webp'

const PLACEHOLDERS = {
  experience: experiencePlaceholder,
  golf: golfPlaceholder,
  hotel: hotelPlaceholder,
  meeting: meetingPlaceholder,
  promotion: promotionPlaceholder,
}

/**
 * Image that always renders something: tries `src`, then each URL in
 * `fallbacks`, then a bundled themed placeholder. Covers both missing
 * (null/empty) and broken (404/403) image URLs coming from the API.
 */
function SmartImage({ src, alt = '', variant = 'hotel', fallbacks = [], ...imgProps }) {
  const chain = [src, ...fallbacks, PLACEHOLDERS[variant] || hotelPlaceholder].filter(Boolean)
  const [index, setIndex] = useState(0)

  useEffect(() => {
    setIndex(0)
  }, [src])

  if (chain.length === 0) return null

  return (
    <img
      src={chain[Math.min(index, chain.length - 1)]}
      alt={alt}
      onError={() => setIndex((current) => Math.min(current + 1, chain.length - 1))}
      {...imgProps}
    />
  )
}

export default SmartImage
