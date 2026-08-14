import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CalendarDays, Sparkles } from 'lucide-react'
import DestinationCard from '../components/DestinationCard'
import HeroSearch from '../components/HeroSearch'
import HotelCard from '../components/HotelCard'
import { useLanguage } from '../context/LanguageContext'
import { fetchDestinations, fetchHotels, fetchPromotions } from '../services/api'
import '../styles/pages/Home.css'

function Home() {
  const { language, t } = useLanguage()
  const [destinations, setDestinations] = useState([])
  const [hotels, setHotels] = useState([])
  const [offers, setOffers] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([
      fetchDestinations(),
      fetchHotels({ pageSize: 6 }),
      fetchPromotions({ status: 'active', pageSize: 3 }),
    ])
      .then(([destinationItems, hotelPayload, promotionPayload]) => {
        if (!active) return
        setDestinations(destinationItems)
        setHotels(hotelPayload.items || [])
        setOffers(promotionPayload.items || [])
        setError('')
      })
      .catch(() => active && setError(t.serverDataError))
    return () => { active = false }
  }, [language, t.serverDataError])

  useEffect(() => {
    const elements = document.querySelectorAll('.reveal-on-scroll')
    if (!('IntersectionObserver' in window)) {
      elements.forEach((element) => element.classList.add('is-revealed'))
      return undefined
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => entry.target.classList.toggle('is-revealed', entry.isIntersecting))
    }, { rootMargin: '0px 0px -30px 0px', threshold: 0.1 })
    elements.forEach((element) => observer.observe(element))
    return () => observer.disconnect()
  }, [destinations, hotels, offers])

  return (
    <main className="home-page">
      <HeroSearch destinations={destinations}>
        <div className="hero-search__booking-heading reveal-on-scroll">
          <span className="home-page__eyebrow">{t.portfoliosEyebrow}</span><h2>{t.destTitle}</h2><p>{t.destSubtitle}</p>
        </div>
      </HeroSearch>
      {error && <p className="home-page__data-error" role="alert">{error}</p>}
      <section className="home-page__section" id="featured-destinations">
        <div className="home-page__destinations-grid">
          {destinations.map((destination, index) => <div key={destination.id} className={`reveal-on-scroll reveal-delay-${(index % 4) + 1}`}><DestinationCard destination={destination} /></div>)}
        </div>
      </section>
      <section className="home-page__section home-page__ai-section">
        <div className="home-page__ai-banner reveal-on-scroll"><div className="home-page__ai-glow" /><div className="home-page__ai-content">
          <div className="home-page__ai-badge"><Sparkles /><span>{t.aiConciergeBadge}</span></div><h3>{t.aiBannerTitle}</h3><p>{t.aiBannerDesc}</p>
          <div className="home-page__ai-actions"><Link className="home-page__ai-primary" to="/chat"><Sparkles /><span>{t.startAiChat}</span></Link><Link className="home-page__ai-secondary" to="/support">{t.navSupport}</Link></div>
        </div></div>
      </section>
      <section className="home-page__section">
        <div className="home-page__split-heading reveal-on-scroll"><div><span className="home-page__eyebrow">{t.luxuryHospitality}</span><h2>{t.featuredHotels}</h2></div><Link className="home-page__view-all" to="/search"><span>{t.viewAllResorts}</span><ArrowRight /></Link></div>
        <div className="home-page__hotels-grid">{hotels.map((hotel, index) => <div key={hotel.id} className={`reveal-on-scroll reveal-delay-${(index % 3) + 1}`}><HotelCard hotel={hotel} /></div>)}</div>
      </section>
      <section className="home-page__offers-section"><div className="home-page__section home-page__offers-inner">
        <div className="home-page__section-heading home-page__section-heading--center reveal-on-scroll"><span className="home-page__eyebrow">{t.travelPackagesEyebrow}</span><h2>{t.offersTitle}</h2></div>
        <div className="home-page__combos-grid">{offers.map((offer, index) => <article className={`home-page__combo-card reveal-on-scroll reveal-delay-${(index % 3) + 1}`} key={offer.id}>
          {offer.image_url && <div className="home-page__combo-media"><img src={offer.image_url} alt={offer.title} /><span className="home-page__combo-tag">{offer.discount_text || t.navOffers}</span></div>}
          <div className="home-page__combo-body"><div><h4>{offer.title}</h4><p>{offer.summary}</p></div><div className="home-page__combo-footer">{offer.validity_to && <span><CalendarDays size={16} /> {offer.validity_to}</span>}<Link className="home-page__combo-link" to="/promotions">{t.viewDetails}</Link></div></div>
        </article>)}</div>
      </div></section>
    </main>
  )
}

export default Home
