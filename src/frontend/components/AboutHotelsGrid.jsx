import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, ArrowUpRight, MapPin } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { fetchHotels } from '../services/api'
import '../styles/components/AboutHotelsGrid.css'

const FALLBACK_HOTEL_IMAGE = 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80'

export default function AboutHotelsGrid() {
  const { language, t } = useLanguage()
  const [hotels, setHotels] = useState([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    fetchHotels({ pageSize: 100 })
      .then((payload) => {
        if (!active) return
        setHotels(payload.items)
        setCurrentIndex(0)
      })
      .catch((requestError) => {
        if (!active) return
        setHotels([])
        setError(requestError instanceof Error ? requestError.message : String(requestError))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [language])

  if (loading) return <section className="vp-showcase-section" aria-busy="true">{t.loadingHotels}</section>
  if (error || hotels.length === 0) {
    return <section className="vp-showcase-section" role="status">{error ? t.hotelsLoadError : t.noHotels}</section>
  }

  const total = hotels.length
  const currentHotel = hotels[currentIndex]
  const imageUrl = currentHotel.images?.[0] || FALLBACK_HOTEL_IMAGE
  const description = currentHotel.summary || currentHotel.address || currentHotel.destination_name

  return (
    <section className="vp-showcase-section">
      <div className="vp-showcase-container">
        <h2 className="vp-showcase-main-title">{t.hotelsResorts}</h2>
        <div className="vp-showcase-card">
          <div className="vp-showcase-media">
            <img
              src={imageUrl}
              alt={currentHotel.name}
              className="vp-showcase-img"
              onError={(e) => {
                e.currentTarget.onerror = null
                e.currentTarget.src = FALLBACK_HOTEL_IMAGE
              }}
            />
            <span className="vp-showcase-badge"><MapPin size={13} />{currentHotel.destination_name}</span>
          </div>
          <div className="vp-showcase-info">
            <div className="vp-showcase-top-bar">
              <div className="vp-showcase-controls">
                <button type="button" className="vp-showcase-arrow-btn" onClick={() => setCurrentIndex((value) => value === 0 ? total - 1 : value - 1)} aria-label={t.previousResort}><ArrowLeft size={18} /></button>
                <span className="vp-showcase-counter">{currentIndex + 1} / {total}</span>
                <button type="button" className="vp-showcase-arrow-btn" onClick={() => setCurrentIndex((value) => value === total - 1 ? 0 : value + 1)} aria-label={t.nextResort}><ArrowRight size={18} /></button>
              </div>
            </div>
            <div className="vp-showcase-divider" />
            <div className="vp-showcase-content">
              <h3 className="vp-showcase-hotel-title">{currentHotel.name}</h3>
              <p className="vp-showcase-hotel-desc">{description}</p>
              <Link to={`/hotels/${currentHotel.id}`}>{t.viewDetails} <ArrowUpRight size={16} aria-hidden="true" /></Link>
            </div>
          </div>
        </div>
        <div className="vp-showcase-thumbs">
          {hotels.map((hotel, index) => (
            <button key={hotel.id} type="button" className={`vp-showcase-thumb-item ${index === currentIndex ? 'vp-showcase-thumb-item--active' : ''}`} onClick={() => setCurrentIndex(index)}>
              <img
                src={hotel.images?.[0] || FALLBACK_HOTEL_IMAGE}
                alt=""
                onError={(e) => {
                  e.currentTarget.onerror = null
                  e.currentTarget.src = FALLBACK_HOTEL_IMAGE
                }}
              />
              <span className="vp-showcase-thumb-title">{hotel.name}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
