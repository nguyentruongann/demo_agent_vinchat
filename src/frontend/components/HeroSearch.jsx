import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Calendar,
  MapPin,
  Search,
  Sparkles,
  Users,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { DESTINATIONS } from '../data/mockData'
import '../styles/components/HeroSearch.css'

function HeroSearch() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [destination, setDestination] = useState('all')
  const [checkIn, setCheckIn] = useState('2026-08-10')
  const [checkOut, setCheckOut] = useState('2026-08-13')
  const [guests, setGuests] = useState('2 Adults')
  const [maxPrice, setMaxPrice] = useState('20000000')

  function handleSearch(event) {
    event.preventDefault()

    const params = new URLSearchParams()
    if (destination !== 'all') params.append('destination', destination)
    if (maxPrice) params.append('maxPrice', maxPrice)

    navigate(`/search?${params.toString()}`)
  }

  function handleAskAi() {
    const destName =
      DESTINATIONS.find((item) => item.id === destination)?.name || 'Vietnam'
    const budget = (Number(maxPrice) / 1000000).toFixed(0)
    const prompt = `${t.planItinerary}: ${destName}, ${guests}, ${budget}M VND`

    navigate(`/chat?prompt=${encodeURIComponent(prompt)}`)
  }

  return (
    <section className="hero-search">
      <div className="hero-search__background" />
      <div className="hero-search__overlay" />
      <div className="hero-search__watermark">
        BEYOND
        <br />
        HORIZON
      </div>

      <div className="hero-search__content">
        <div className="hero-search__badge">
          <Sparkles className="hero-search__badge-icon" />
          <span>{t.heroBadge}</span>
        </div>

        <h1 className="hero-search__title">
          {t.heroTitleBefore} <span>{t.heroTitleAccent}</span> {t.heroTitleAfter}
        </h1>
        <p className="hero-search__subtitle">{t.heroSubtitleCustom}</p>

        <div className="hero-search__search-panel">
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
                {DESTINATIONS.map((item) => (
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

          <div className="hero-search__ai-row">
            <span>{t.heroAiHelp}</span>
            <button
              className="hero-search__ai-button"
              type="button"
              onClick={handleAskAi}
            >
              <Sparkles className="hero-search__ai-icon" />
              <span>{t.btnAskAi}</span>
            </button>
          </div>
        </div>

        <div className="hero-search__metrics">
          <div className="hero-search__metric">
            <span className="hero-search__metric-value">12</span>
            <span className="hero-search__metric-label">{t.resortsVillas}</span>
          </div>
          <div className="hero-search__metric">
            <span className="hero-search__metric-value hero-search__metric-value--gold">
              5-Star
            </span>
            <span className="hero-search__metric-label">{t.luxuryRating}</span>
          </div>
          <div className="hero-search__metric">
            <span className="hero-search__metric-value">24h</span>
            <span className="hero-search__metric-label">{t.aiSupport}</span>
          </div>
        </div>
      </div>
    </section>
  )
}

export default HeroSearch
