import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  CalendarDays,
  Gift,
  MapPin,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import SmartImage from '../components/SmartImage'
import { fetchDestinations, fetchPromotions } from '../services/api'
import promoBanner from '../image/uu-dai-khuyen-mai_1684378388.jpg.webp'
import '../styles/pages/Promotions.css'

const INITIAL_PROMOTION_COUNT = 8

function formatDate(value, language) {
  if (!value) return null
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  const locales = { en: 'en-GB', vi: 'vi-VN', ko: 'ko-KR', ja: 'ja-JP', zh: 'zh-CN' }
  return new Intl.DateTimeFormat(locales[language] || 'en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function getDestinations(promotion, translate) {
  if (promotion.is_nationwide) {
    return translate('promotions.nationwide')
  }
  if (!Array.isArray(promotion.destinations) || promotion.destinations.length === 0) {
    return translate('promotions.multipleDestinations')
  }
  return promotion.destinations
    .map((item) => (typeof item === 'string' ? item : item.name || item.id))
    .filter(Boolean)
    .join(', ')
}

function Promotions() {
  const { language, t, translate } = useLanguage()
  const [promotions, setPromotions] = useState([])
  const [destinationsList, setDestinationsList] = useState([])
  const [selectedDestination, setSelectedDestination] = useState('all')
  const [status] = useState('active')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const [showAll, setShowAll] = useState(false)
  const loadedLanguageRef = useRef(null)

  useEffect(() => {
    let active = true
    fetchDestinations()
      .then((items) => {
        if (!active) return
        setDestinationsList(items)
      })
      .catch(() => {
        if (active) setDestinationsList([])
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    if (loadedLanguageRef.current !== language || promotions.length === 0) {
      setLoading(true)
    }
    setError('')

    fetchPromotions({ destination: selectedDestination, status, search })
      .then(({ items }) => {
        if (!active) return
        setPromotions(items)
        loadedLanguageRef.current = language
      })
      .catch((requestError) => {
        if (!active) return
        setPromotions([])
        setError(requestError instanceof Error ? requestError.message : String(requestError))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [selectedDestination, status, search, retryKey, language])

  // Featured promotions (top 3 for Section 1)
  const mainFeatured = promotions[0]
  const sideFeatured = promotions.slice(1, 3)

  // Section 2 list
  const visiblePromotions = showAll ? promotions : promotions.slice(0, INITIAL_PROMOTION_COUNT)

  const copy = Object.fromEntries(
    ['eyebrow', 'title', 'description', 'search', 'submit', 'loading', 'emptyTitle',
      'emptyText', 'errorTitle', 'errorText', 'retry', 'view', 'viewMore', 'validity']
      .map((key) => [key, translate(`promotions.${key}`)]),
  )

  function handleSearch(event) {
    event.preventDefault()
    setSearch(searchInput.trim())
  }

  return (
    <main className="promotions-v2">
      <div className="promotions-v2__container">
        {/* ==================================================================
            SECTION 1: "Ưu đãi nổi bật"
            ================================================================== */}
        <section className="promo-featured-section">
          <h2 className="promo-section-title">
            {t.featuredPromotions || 'Ưu đãi nổi bật'}
          </h2>

          {loading ? (
            <div className="promo-featured__skeleton-grid">
              <div className="promo-skeleton promo-skeleton--large" />
              <div className="promo-skeleton-stack">
                <div className="promo-skeleton promo-skeleton--small" />
                <div className="promo-skeleton promo-skeleton--small" />
              </div>
            </div>
          ) : (
            <>
              <div className="promo-featured__grid">
                {/* Left Column: 60% Width, 1 Large Card */}
                <article className="promo-featured__card promo-featured__card--main">
                  <SmartImage
                    src={mainFeatured?.image_url || promoBanner}
                    alt={mainFeatured?.title || copy.title}
                    variant="promotion"
                    className="promo-featured__card-img"
                  />
                  <div className="promo-featured__overlay" />
                  <div className="promo-featured__card-content">
                    <span className="promo-featured__badge">
                      <Sparkles size={14} />
                      {mainFeatured?.discount_text || 'Hot Offer'}
                    </span>
                    <h3>{mainFeatured?.title || copy.title}</h3>
                    {mainFeatured?.summary && (
                      <p>{mainFeatured.summary}</p>
                    )}
                    <Link
                      to={mainFeatured ? `/promotions/${mainFeatured.id}` : '#'}
                      className="promo-featured__btn"
                    >
                      <span>{copy.view || 'Xem thêm'}</span>
                      <ArrowUpRight size={17} />
                    </Link>
                  </div>
                </article>

                {/* Right Column: 40% Width, 2 Small Stacked Cards (No CTA button) */}
                <div className="promo-featured__side-grid">
                  {sideFeatured.length > 0 ? (
                    sideFeatured.map((item) => (
                      <article className="promo-featured__card promo-featured__card--small" key={item.id}>
                        <SmartImage
                          src={item.image_url || promoBanner}
                          alt={item.title}
                          variant="promotion"
                          className="promo-featured__card-img"
                        />
                        <div className="promo-featured__overlay" />
                        <div className="promo-featured__card-content">
                          <span className="promo-featured__sub-badge">
                            {item.discount_text || 'Exclusive'}
                          </span>
                          <h4>{item.title}</h4>
                        </div>
                        <Link to={`/promotions/${item.id}`} className="promo-featured__card-overlay-link" aria-label={item.title} />
                      </article>
                    ))
                  ) : (
                    <>
                      <article className="promo-featured__card promo-featured__card--small">
                        <img src={promoBanner} alt="" className="promo-featured__card-img" />
                        <div className="promo-featured__overlay" />
                        <div className="promo-featured__card-content">
                          <span className="promo-featured__sub-badge">Special</span>
                          <h4>Ưu đãi kỳ nghỉ đẳng cấp Vinpearl</h4>
                        </div>
                      </article>
                      <article className="promo-featured__card promo-featured__card--small">
                        <img src={promoBanner} alt="" className="promo-featured__card-img" />
                        <div className="promo-featured__overlay" />
                        <div className="promo-featured__card-content">
                          <span className="promo-featured__sub-badge">Limited</span>
                          <h4>Tận hưởng trọn vẹn dịch vụ 5 sao</h4>
                        </div>
                      </article>
                    </>
                  )}
                </div>
              </div>

              {/* Pagination Dots (Carousel Indicator) */}
              <div className="promo-featured__pagination" aria-hidden="true">
                <span className="promo-dot promo-dot--active" />
                <span className="promo-dot" />
                <span className="promo-dot" />
              </div>
            </>
          )}
        </section>

        {/* ==================================================================
            SECTION 2: "Ưu đãi theo điểm đến"
            ================================================================== */}
        <section className="promo-dest-section">
          <div className="promo-dest-header">
            <h2 className="promo-section-title">
              {t.offersByDestination || 'Ưu đãi theo điểm đến'}
            </h2>

            <form className="promo-search-bar" onSubmit={handleSearch}>
              <Search size={16} />
              <input
                type="search"
                value={searchInput}
                placeholder={copy.search}
                onChange={(e) => setSearchInput(e.target.value)}
              />
              <button type="submit">{copy.submit || 'Tìm'}</button>
            </form>
          </div>

          {/* Filter Pills (Rounded Pills with Scroll Horizontal) */}
          <div className="promo-pills-bar">
            <button
              type="button"
              className={`promo-pill ${selectedDestination === 'all' ? 'is-active' : ''}`}
              onClick={() => setSelectedDestination('all')}
            >
              {t.allDestinations || 'Tất cả'}
            </button>
            {destinationsList.map((dest) => (
              <button
                type="button"
                key={dest.id}
                className={`promo-pill ${selectedDestination === dest.id ? 'is-active' : ''}`}
                onClick={() => setSelectedDestination(dest.id)}
              >
                {dest.name}
              </button>
            ))}
          </div>

          {/* Destination Cards Grid */}
          {loading ? (
            <div className="promo-dest__grid">
              {[1, 2, 3, 4].map((i) => (
                <div className="promo-skeleton promo-skeleton--card" key={i} />
              ))}
            </div>
          ) : error ? (
            <div className="promo-state promo-state--error">
              <RefreshCw size={24} />
              <p>{copy.errorText}</p>
              <button type="button" onClick={() => setRetryKey((v) => v + 1)}>
                {copy.retry}
              </button>
            </div>
          ) : visiblePromotions.length === 0 ? (
            <div className="promo-state">
              <Gift size={28} />
              <p>{copy.emptyText}</p>
            </div>
          ) : (
            <>
              <div className="promo-dest__grid">
                {visiblePromotions.map((item) => {
                  const fromDate = formatDate(item.validity_from, language)
                  const toDate = formatDate(item.validity_to, language)
                  return (
                    <article className="promo-dest__card" key={item.id}>
                      <div className="promo-dest__card-media">
                        <SmartImage
                          src={item.image_url}
                          alt={item.title}
                          variant="promotion"
                        />
                        {item.discount_text && (
                          <span className="promo-dest__tag">{item.discount_text}</span>
                        )}
                      </div>
                      <div className="promo-dest__card-body">
                        <div className="promo-dest__card-loc">
                          <MapPin size={14} />
                          <span>{getDestinations(item, translate)}</span>
                        </div>
                        <h3>{item.title}</h3>
                        {(fromDate || toDate) && (
                          <div className="promo-dest__card-date">
                            <CalendarDays size={14} />
                            <span>{fromDate || '—'} – {toDate || '—'}</span>
                          </div>
                        )}
                        <Link to={`/promotions/${item.id}`} className="promo-dest__card-link">
                          <span>{copy.view || 'Xem chi tiết'}</span>
                          <ArrowUpRight size={15} />
                        </Link>
                      </div>
                    </article>
                  )
                })}
              </div>

              {!showAll && promotions.length > INITIAL_PROMOTION_COUNT && (
                <div className="promo-dest__more">
                  <button type="button" onClick={() => setShowAll(true)}>
                    {copy.viewMore || 'Xem thêm ưu đãi'}
                  </button>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  )
}

export default Promotions
