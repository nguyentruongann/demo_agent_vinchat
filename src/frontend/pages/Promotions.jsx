import { useEffect, useMemo, useRef, useState } from 'react'
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
import { fetchPromotions } from '../services/api'
import '../styles/pages/Promotions.css'

const DESTINATIONS = [
  { id: 'all', en: 'All destinations', vi: 'Tất cả điểm đến' },
  { id: 'nha-trang', en: 'Nha Trang', vi: 'Nha Trang' },
  { id: 'phu-quoc', en: 'Phu Quoc', vi: 'Phú Quốc' },
  { id: 'hoi-an', en: 'Hoi An', vi: 'Hội An' },
  { id: 'ha-noi', en: 'Hanoi', vi: 'Hà Nội' },
  { id: 'hai-phong', en: 'Hai Phong', vi: 'Hải Phòng' },
]

const STATUS_OPTIONS = [
  { id: 'all', en: 'All statuses', vi: 'Tất cả trạng thái' },
  { id: 'active', en: 'Active', vi: 'Đang áp dụng' },
  { id: 'upcoming', en: 'Upcoming', vi: 'Sắp diễn ra' },
  { id: 'expired', en: 'Expired', vi: 'Đã kết thúc' },
]

const INITIAL_PROMOTION_COUNT = 6

function PromotionSelect({ icon: Icon, value, options, isVi, label, onChange }) {
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
        <span>{isVi ? selected.vi : selected.en}</span>
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
              <span>{isVi ? option.vi : option.en}</span>
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
  return new Intl.DateTimeFormat(language === 'VI' ? 'vi-VN' : 'en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function getDestinations(promotion, language) {
  if (promotion.is_nationwide) {
    return language === 'VI' ? 'Toàn quốc' : 'Nationwide'
  }
  if (!Array.isArray(promotion.destinations) || promotion.destinations.length === 0) {
    return language === 'VI' ? 'Nhiều điểm đến' : 'Multiple destinations'
  }
  return promotion.destinations
    .map((item) => (typeof item === 'string' ? item : item.name || item.id))
    .filter(Boolean)
    .join(', ')
}

function Promotions() {
  const { language } = useLanguage()
  const isVi = language === 'VI'
  const [promotions, setPromotions] = useState([])
  const [destination, setDestination] = useState('all')
  const [status, setStatus] = useState('active')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')

    fetchPromotions({ destination, status, search })
      .then(({ items }) => {
        if (active) setPromotions(items)
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
  }, [destination, status, search, retryKey])

  useEffect(() => {
    setShowAll(false)
  }, [destination, status, search])

  const visiblePromotions = showAll
    ? promotions
    : promotions.slice(0, INITIAL_PROMOTION_COUNT)

  const copy = useMemo(
    () =>
      isVi
        ? {
            eyebrow: 'Ưu đãi tuyển chọn',
            title: 'Đặc quyền cho hành trình đáng nhớ',
            description: 'Khám phá ưu đãi nghỉ dưỡng và trải nghiệm tại các điểm đến Vinpearl.',
            search: 'Tìm theo tên hoặc nội dung ưu đãi',
            submit: 'Tìm kiếm',
            loading: 'Đang tải ưu đãi...',
            emptyTitle: 'Chưa có ưu đãi phù hợp',
            emptyText: 'Hãy thử đổi điểm đến, trạng thái hoặc từ khóa tìm kiếm.',
            errorTitle: 'Không thể tải ưu đãi',
            errorText: 'API Promotions chưa sẵn sàng hoặc backend chưa kết nối database.',
            retry: 'Thử lại',
            view: 'Xem ưu đãi',
            viewMore: 'Xem thêm ưu đãi',
            validity: 'Hạn áp dụng',
            noSummary: 'Thông tin chi tiết sẽ được cập nhật trong thời gian sớm nhất.',
          }
        : {
            eyebrow: 'Curated offers',
            title: 'Privileges for remarkable journeys',
            description: 'Discover resort and experience offers across Vinpearl destinations.',
            search: 'Search promotion title or content',
            submit: 'Search',
            loading: 'Loading promotions...',
            emptyTitle: 'No matching promotions',
            emptyText: 'Try another destination, status, or search term.',
            errorTitle: 'Unable to load promotions',
            errorText: 'The Promotions API is unavailable or the backend is not connected to the database.',
            retry: 'Try again',
            view: 'View offer',
            viewMore: 'View more offers',
            validity: 'Valid period',
            noSummary: 'More details will be available soon.',
          },
    [isVi],
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
        <section className="promotions-page__filters" aria-label="Promotion filters">
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
            options={DESTINATIONS}
            isVi={isVi}
            label={isVi ? 'Lọc theo điểm đến' : 'Filter by destination'}
            onChange={setDestination}
          />

          <PromotionSelect
            icon={Tag}
            value={status}
            options={STATUS_OPTIONS}
            isVi={isVi}
            label={isVi ? 'Lọc theo trạng thái' : 'Filter by status'}
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
                      <span>{getDestinations(promotion, language)}</span>
                    </div>
                    <h2>{promotion.title}</h2>
                    {(fromDate || toDate) && (
                      <div className="promotion-card__validity">
                        <CalendarDays aria-hidden="true" />
                        <span>{copy.validity}: {fromDate || '—'} – {toDate || '—'}</span>
                      </div>
                    )}
                    {promotion.booking_url ? (
                      <a href={promotion.booking_url} target="_blank" rel="noreferrer">
                        {copy.view}<ArrowUpRight aria-hidden="true" />
                      </a>
                    ) : (
                      <span className="promotion-card__action promotion-card__action--disabled" aria-disabled="true">
                        {copy.view}<ArrowUpRight aria-hidden="true" />
                      </span>
                    )}
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
