import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Award,
  Building2,
  Calendar,
  Clock3,
  Compass,
  MapPin,
  Search,
  Sparkles,
  Users,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/HeroSearch.css'

function HeroSearch({ children, destinations = [] }) {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [destination, setDestination] = useState('all')
  const [checkIn, setCheckIn] = useState('2026-08-10')
  const [checkOut, setCheckOut] = useState('2026-08-13')
  const [guests, setGuests] = useState('2 Adults')
  const [maxPrice] = useState('400')

  function handleSearch(event) {
    event.preventDefault()

    const params = new URLSearchParams()
    if (destination !== 'all') params.append('destination', destination)
    if (maxPrice) params.append('maxPrice', maxPrice)

    navigate(`/search?${params.toString()}`)
  }

  function handleAskAi() {
    const destName =
      destinations.find((item) => item.id === destination)?.name || t.vietnam
    const budget = t.maximumPerNight.replace('{{price}}', `$${maxPrice}`)
    const prompt = `${t.planItinerary}: ${destName}, ${guests}, ${budget}`

    navigate(`/chat?prompt=${encodeURIComponent(prompt)}`)
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
              <select
                className="hero-search__control"
                id="hero-destination"
                value={destination}
                onChange={(event) => setDestination(event.target.value)}
              >
                <option value="all">{t.allDestinations}</option>
                {destinations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
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

            <div className="hero-search__field">
              <label className="hero-search__label" htmlFor="hero-guests">
                <Users className="hero-search__label-icon" />
                <span>{t.searchGuests}</span>
              </label>
              <select
                className="hero-search__control"
                id="hero-guests"
                value={guests}
                onChange={(event) => setGuests(event.target.value)}
              >
                <option value="2 Adults">{t.adults2}</option>
                <option value="2 Adults, 1 Child">{t.adults2Child1}</option>
                <option value="2 Adults, 2 Children">{t.adults2Children2}</option>
                <option value="4 Adults (Villa)">{t.adults4Villa}</option>
                <option value="6 Adults (Estate)">{t.adults6Estate}</option>
              </select>
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
