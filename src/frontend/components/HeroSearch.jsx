import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Award,
  Building2,
  Calendar,
  ChevronDown,
  Clock3,
  Compass,
  MapPin,
  Minus,
  Plus,
  Search,
  Users,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import CustomSelect from './CustomSelect'
import '../styles/components/HeroSearch.css'

function HeroSearch({ children, destinations = [] }) {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [destination, setDestination] = useState('all')
  const [checkIn, setCheckIn] = useState('2026-08-10')
  const [checkOut, setCheckOut] = useState('2026-08-13')

  // Vinpearl Room & Guest Counter Popover State
  const [roomsCount, setRoomsCount] = useState(1)
  const [adultsCount, setAdultsCount] = useState(2)
  const [childrenCount, setChildrenCount] = useState(0)
  const [infantsCount, setInfantsCount] = useState(0)
  const [guestPickerOpen, setGuestPickerOpen] = useState(false)
  const guestPickerRef = useRef(null)
  const [maxPrice] = useState('400')

  useEffect(() => {
    function handleClickOutside(event) {
      if (guestPickerRef.current && !guestPickerRef.current.contains(event.target)) {
        setGuestPickerOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function getGuestSummaryText() {
    let summary = `${roomsCount} phòng, ${adultsCount} người lớn`
    if (childrenCount > 0) summary += `, ${childrenCount} trẻ em`
    if (infantsCount > 0) summary += `, ${infantsCount} em bé`
    return summary
  }

  function handleSearch(event) {
    event.preventDefault()

    const params = new URLSearchParams()
    if (destination !== 'all') params.append('destination', destination)
    if (maxPrice) params.append('maxPrice', maxPrice)

    navigate(`/search?${params.toString()}`)
  }

  return (
    <>
      <section className="hero-search">
        <video
          className="hero-search__background"
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          aria-hidden="true"
        >
          <source
            src="https://statics.vinpearl.com/Banner%20WEB%20.mp4"
            type="video/mp4"
          />
        </video>
        <div className="hero-search__overlay" />

        <div className="hero-search__content">
          <div className="hero-search__intro">

            <h1 className="hero-search__title">
              {t.heroTitleBefore} <span>{t.heroTitleAccent}</span>{' '}
              {t.heroTitleAfter}
            </h1>
            <p className="hero-search__subtitle">{t.heroSubtitleCustom}</p>

            <div className="hero-search__hero-actions">
              <a className="hero-search__discover" href="#featured-destinations">
                <Compass aria-hidden="true" />
                <span>{t.exploreRetreats}</span>
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="hero-search__booking-area">
        {children}
        <div className="hero-search__search-panel reveal-on-scroll" id="hero-booking-search">
          <form className="hero-search__form" onSubmit={handleSearch}>
            <div className="hero-search__field">
              <label className="hero-search__label" htmlFor="hero-destination">
                <MapPin className="hero-search__label-icon" />
                <span>{t.searchDest}</span>
              </label>
              <CustomSelect
                id="hero-destination"
                value={destination}
                options={[
                  { value: 'all', label: t.allDestinations },
                  ...destinations.map((item) => ({ value: item.id, label: item.name })),
                ]}
                onChange={(val) => setDestination(val)}
                aria-label={t.searchDest}
              />
            </div>

            <div className="hero-search__field">
              <label className="hero-search__label" htmlFor="hero-check-in">
                <Calendar className="hero-search__label-icon" />
                <span>{t.searchCheckIn}</span>
              </label>
              <input
                className="hero-search__control"
                id="hero-check-in"
                type="date"
                value={checkIn}
                onChange={(event) => setCheckIn(event.target.value)}
              />
            </div>

            <div className="hero-search__field">
              <label className="hero-search__label" htmlFor="hero-check-out">
                <Calendar className="hero-search__label-icon" />
                <span>{t.searchCheckOut}</span>
              </label>
              <input
                className="hero-search__control"
                id="hero-check-out"
                type="date"
                value={checkOut}
                onChange={(event) => setCheckOut(event.target.value)}
              />
            </div>

            <div className="hero-search__field" ref={guestPickerRef}>
              <label className="hero-search__label" htmlFor="hero-guests">
                <Users className="hero-search__label-icon" />
                <span>{t.searchGuests || 'SỐ KHÁCH'}</span>
              </label>

              <button
                type="button"
                className="hero-search__guest-trigger"
                id="hero-guests"
                onClick={() => setGuestPickerOpen((open) => !open)}
                aria-expanded={guestPickerOpen}
              >
                <span className="hero-search__guest-trigger-text">{getGuestSummaryText()}</span>
                <ChevronDown className={`hero-search__guest-chevron ${guestPickerOpen ? 'is-open' : ''}`} />
              </button>

              {guestPickerOpen && (
                <div className="hero-search__guest-popover">
                  {/* Row 1: Số phòng */}
                  <div className="hero-search__popover-row">
                    <span className="hero-search__popover-label">Số phòng</span>
                    <div className="hero-search__counter">
                      <button
                        type="button"
                        className="hero-search__counter-btn"
                        disabled={roomsCount <= 1}
                        onClick={() => setRoomsCount((r) => Math.max(1, r - 1))}
                        aria-label="Giảm số phòng"
                      >
                        <Minus size={14} />
                      </button>
                      <span className="hero-search__counter-val">{roomsCount}</span>
                      <button
                        type="button"
                        className="hero-search__counter-btn"
                        disabled={roomsCount >= 5}
                        onClick={() => setRoomsCount((r) => Math.min(5, r + 1))}
                        aria-label="Tăng số phòng"
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                  </div>

                  <div className="hero-search__popover-divider" />

                  {/* Title: Phòng 1 */}
                  <div className="hero-search__popover-subtitle">
                    Phòng 1
                  </div>

                  {/* Row 2: Grid 3 cột */}
                  <div className="hero-search__popover-grid">
                    {/* Người lớn */}
                    <div className="hero-search__popover-col">
                      <span className="hero-search__popover-sublabel">Người lớn</span>
                      <div className="hero-search__counter">
                        <button
                          type="button"
                          className="hero-search__counter-btn"
                          disabled={adultsCount <= 1}
                          onClick={() => setAdultsCount((a) => Math.max(1, a - 1))}
                          aria-label="Giảm người lớn"
                        >
                          <Minus size={14} />
                        </button>
                        <span className="hero-search__counter-val">{adultsCount}</span>
                        <button
                          type="button"
                          className="hero-search__counter-btn"
                          disabled={adultsCount >= 10}
                          onClick={() => setAdultsCount((a) => Math.min(10, a + 1))}
                          aria-label="Tăng người lớn"
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                    </div>

                    {/* Trẻ em */}
                    <div className="hero-search__popover-col">
                      <span className="hero-search__popover-sublabel">Trẻ em</span>
                      <div className="hero-search__counter">
                        <button
                          type="button"
                          className="hero-search__counter-btn"
                          disabled={childrenCount <= 0}
                          onClick={() => setChildrenCount((c) => Math.max(0, c - 1))}
                          aria-label="Giảm trẻ em"
                        >
                          <Minus size={14} />
                        </button>
                        <span className="hero-search__counter-val">{childrenCount}</span>
                        <button
                          type="button"
                          className="hero-search__counter-btn"
                          disabled={childrenCount >= 6}
                          onClick={() => setChildrenCount((c) => Math.min(6, c + 1))}
                          aria-label="Tăng trẻ em"
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                    </div>

                    {/* Em bé */}
                    <div className="hero-search__popover-col">
                      <span className="hero-search__popover-sublabel">Em bé</span>
                      <div className="hero-search__counter">
                        <button
                          type="button"
                          className="hero-search__counter-btn"
                          disabled={infantsCount <= 0}
                          onClick={() => setInfantsCount((i) => Math.max(0, i - 1))}
                          aria-label="Giảm em bé"
                        >
                          <Minus size={14} />
                        </button>
                        <span className="hero-search__counter-val">{infantsCount}</span>
                        <button
                          type="button"
                          className="hero-search__counter-btn"
                          disabled={infantsCount >= 4}
                          onClick={() => setInfantsCount((i) => Math.min(4, i + 1))}
                          aria-label="Tăng em bé"
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="hero-search__popover-divider" />

                  {/* Note */}
                  <div className="hero-search__popover-note">
                    *Em bé: Dưới 4 tuổi / Trẻ em: Từ 4 - dưới 12 tuổi
                  </div>

                  {/* Button */}
                  <button
                    type="button"
                    className="hero-search__popover-apply"
                    onClick={() => setGuestPickerOpen(false)}
                  >
                    Áp dụng
                  </button>
                </div>
              )}
            </div>

            <button className="hero-search__submit" type="submit">
              <Search className="hero-search__submit-icon" />
              <span>{t.btnSearch}</span>
            </button>
          </form>
        </div>
      </section>

      <section className="hero-search__metrics" aria-label={t.vinpearlHighlights}>
        <div className="hero-search__metrics-inner reveal-on-scroll">
          <div className="hero-search__metric">
            <Building2 className="hero-search__metric-icon" aria-hidden="true" />
            <div>
              <span className="hero-search__metric-value">12</span>
              <span className="hero-search__metric-label">{t.resortsVillas}</span>
            </div>
          </div>
          <div className="hero-search__metric">
            <Award className="hero-search__metric-icon" aria-hidden="true" />
            <div>
              <span className="hero-search__metric-value">{t.fiveStar}</span>
              <span className="hero-search__metric-label">{t.luxuryRating}</span>
            </div>
          </div>
          <div className="hero-search__metric">
            <Clock3 className="hero-search__metric-icon" aria-hidden="true" />
            <div>
              <span className="hero-search__metric-value">24h</span>
              <span className="hero-search__metric-label">{t.aiSupport}</span>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}

export default HeroSearch
