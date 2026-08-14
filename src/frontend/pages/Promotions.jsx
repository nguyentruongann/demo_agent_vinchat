import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronDown,
  Gift,
  MapPin,
  RefreshCw,
  Search,
  Tag,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { fetchDestinations, fetchPromotions } from '../services/api'
import '../styles/pages/Promotions.css'

const INITIAL_PROMOTION_COUNT = 6

function PromotionSelect({ icon: Icon, value, options, label, onChange }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const selected = options.find((option) => option.id === value) || options[0]

  useEffect(() => {
    function closeOnOutsideClick(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsideClick)
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick)
  }, [])

  return (
    <div className={`promotions-select${open ? ' promotions-select--open' : ''}`} ref={rootRef}>
      <button
        type="button"
        className="promotions-select__trigger"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setOpen(false)
        }}
      >
        <Icon className="promotions-select__leading-icon" aria-hidden="true" />
        <span>{selected.label}</span>
        <ChevronDown className="promotions-select__chevron" aria-hidden="true" />
      </button>
      {open && (
        <div className="promotions-select__menu" role="listbox" aria-label={label}>
          {options.map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={option.id === value}
              className={option.id === value ? 'promotions-select__option is-selected' : 'promotions-select__option'}
              key={option.id}
              onClick={() => {
                onChange(option.id)
                setOpen(false)
              }}
            >
              <span>{option.label}</span>
              {option.id === value && <Check aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

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
  const [destinationOptions, setDestinationOptions] = useState([
    { id: 'all', label: t.allDestinations },
  ])
  const [destination, setDestination] = useState('all')
  const [status, setStatus] = useState('active')
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
        setDestinationOptions([
          { id: 'all', label: t.allDestinations },
          ...items.map((item) => ({ id: item.id, label: item.name })),
        ])
      })
      .catch(() => {
        if (active) setDestinationOptions([{ id: 'all', label: t.allDestinations }])
      })
    return () => {
      active = false
    }
  }, [language, t.allDestinations])

  const statusOptions = [
    { id: 'all', label: t.allStatuses },
    { id: 'active', label: t.statusActive },
    { id: 'upcoming', label: t.statusUpcoming },
    { id: 'expired', label: t.statusExpired },
  ]

  useEffect(() => {
    let active = true
    let refreshTimer
    if (loadedLanguageRef.current !== language || promotions.length === 0) {
      setLoading(true)
    }
    setError('')

    fetchPromotions({ destination, status, search })
      .then(({ items, translationFallback }) => {
        if (!active) return
        setPromotions(items)
        loadedLanguageRef.current = language
        if (translationFallback && language !== 'en') {
          refreshTimer = window.setTimeout(
            () => setRetryKey((value) => value + 1),
            5000,
          )
        }
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
      window.clearTimeout(refreshTimer)
    }
  }, [destination, status, search, retryKey, language])

  useEffect(() => {
    setShowAll(false)
  }, [destination, status, search])

  const visiblePromotions = showAll
    ? promotions
    : promotions.slice(0, INITIAL_PROMOTION_COUNT)

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
    <main className="promotions-page">
      <section className="promotions-page__hero">
        <div className="promotions-page__hero-content">
          <span className="promotions-page__eyebrow">
            <Gift aria-hidden="true" />
            {copy.eyebrow}
          </span>
          <h1>{copy.title}</h1>
          <p>{copy.description}</p>
        </div>
      </section>

      <div className="promotions-page__container">
        <section className="promotions-page__filters" aria-label={t.promotionFilters}>
          <form className="promotions-page__search" onSubmit={handleSearch}>
            <Search aria-hidden="true" />
            <input
              type="search"
              value={searchInput}
              placeholder={copy.search}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <button type="submit">{copy.submit}</button>
          </form>

          <PromotionSelect
            icon={MapPin}
            value={destination}
            options={destinationOptions}
            label={t.filterByDestination}
            onChange={setDestination}
          />

          <PromotionSelect
            icon={Tag}
            value={status}
            options={statusOptions}
            label={t.filterByStatus}
            onChange={setStatus}
          />
        </section>

        {loading ? (
          <section className="promotions-page__grid" aria-label={copy.loading}>
            {[1, 2, 3, 4, 5, 6].map((item) => (
              <div className="promotions-page__skeleton" key={item} />
            ))}
          </section>
        ) : error ? (
          <section className="promotions-page__state promotions-page__state--error">
            <RefreshCw aria-hidden="true" />
            <h2>{copy.errorTitle}</h2>
            <p>{copy.errorText}</p>
            <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
              {copy.retry}
            </button>
          </section>
        ) : promotions.length === 0 ? (
          <section className="promotions-page__state">
            <Gift aria-hidden="true" />
            <h2>{copy.emptyTitle}</h2>
            <p>{copy.emptyText}</p>
          </section>
        ) : (
          <>
            <section className="promotions-page__grid" aria-live="polite">
            {visiblePromotions.map((promotion) => {
              const fromDate = formatDate(promotion.validity_from, language)
              const toDate = formatDate(promotion.validity_to, language)
              return (
                <article className="promotion-card" key={promotion.id}>
                  <div className="promotion-card__visual">
                    <Gift aria-hidden="true" />
                    {promotion.image_url && (
                      <img
                        src={promotion.image_url}
                        alt=""
                        loading="lazy"
                        onError={(event) => {
                          event.currentTarget.hidden = true
                        }}
                      />
                    )}
                  </div>
                  <div className="promotion-card__body">
                    <div className="promotion-card__location">
                      <MapPin aria-hidden="true" />
                      <span>{getDestinations(promotion, translate)}</span>
                    </div>
                    <h2>{promotion.title}</h2>
                    {(fromDate || toDate) && (
                      <div className="promotion-card__validity">
                        <CalendarDays aria-hidden="true" />
                        <span>{copy.validity}: {fromDate || '—'} – {toDate || '—'}</span>
                      </div>
                    )}
                    <Link to={`/promotions/${promotion.id}`} className="promotion-card__action">
                      {copy.view}<ArrowUpRight aria-hidden="true" />
                    </Link>
                  </div>
                </article>
              )
            })}
            </section>
            {!showAll && promotions.length > INITIAL_PROMOTION_COUNT && (
              <div className="promotions-page__more">
                <button type="button" onClick={() => setShowAll(true)}>
                  {copy.viewMore}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  )
}

export default Promotions
