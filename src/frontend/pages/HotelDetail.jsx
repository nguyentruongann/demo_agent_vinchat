import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, ChevronLeft, Clock, ExternalLink, MapPin, Maximize2, Sparkles, Users, Utensils } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import SmartImage from '../components/SmartImage'
import { fetchHotelById } from '../services/api'
import '../styles/pages/HotelDetail.css'

function formatPrice(amount, currency, fallback) {
  if (amount == null) return fallback
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: 0,
  }).format(amount)
}

function localizedCopy(language, viText, enText) {
  return language === 'vi' ? viText : enText
}

function RoomPrice({ room, t, language }) {
  if (room.price == null) {
    const unavailable = t.roomPriceUnavailable
      || localizedCopy(language, 'Gi\u00e1 ch\u01b0a c\u00f4ng b\u1ed1', 'Rate unavailable')
    const hint = t.roomPriceUnavailableHint
      || localizedCopy(
        language,
        'Xem gi\u00e1 theo ng\u00e0y tr\u00ean trang \u0111\u1eb7t ph\u00f2ng ch\u00ednh th\u1ee9c.',
        'Check date-based rates on the official booking page.',
      )

    return (
      <div className="hotel-detail-page__price-unavailable">
        <span className="hotel-detail-page__room-price hotel-detail-page__room-price--unavailable">
          {unavailable}
        </span>
        <small>{hint}</small>
      </div>
    )
  }

  return (
    <div>
      <span className="hotel-detail-page__room-price">
        {formatPrice(room.price, room.currency, t.contactProperty)}
      </span>
      <span className="hotel-detail-page__room-unit"> {t.perNightShort}</span>
    </div>
  )
}

function HotelDetail() {
  const { hotelId } = useParams()
  const { language, t } = useLanguage()
  const navigate = useNavigate()
  const [hotel, setHotel] = useState(null)
  const [selectedImg, setSelectedImg] = useState('')
  const [activeTab, setActiveTab] = useState('rooms')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    fetchHotelById(hotelId)
      .then((data) => {
        if (!active) return
        setHotel(data)
        setSelectedImg(data?.images?.[0] || '')
        setError(data ? '' : t.hotelNotFound)
      })
      .catch(() => active && setError(t.hotelLoadError))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [hotelId, language, t.hotelLoadError, t.hotelNotFound])

  if (loading) {
    return (
      <main className="hotel-detail-page hotel-detail-page--loading">
        <div className="hotel-detail-page__loading">
          <div className="hotel-detail-page__spinner" />
          <p>{t.loadingResortDetails}</p>
        </div>
      </main>
    )
  }

  if (!hotel) {
    return (
      <main className="hotel-detail-page hotel-detail-page--loading">
        <div className="hotel-detail-page__loading">
          <p role="alert">{error}</p>
          <Link to="/search">{t.backToResorts}</Link>
        </div>
      </main>
    )
  }

  const handlePlan = () => navigate(`/chat?prompt=${encodeURIComponent(`${t.planItinerary}: ${hotel.name}, ${hotel.destination_name}`)}`)
  const allRoomsMissingPrice = hotel.rooms.length > 0 && hotel.rooms.every((room) => room.price == null)
  const priceNoticeTitle = t.roomPriceNoticeTitle
    || localizedCopy(language, 'Gi\u00e1 ph\u00f2ng ch\u01b0a c\u00f3 trong d\u1eef li\u1ec7u', 'Room rates are not available in the dataset')
  const priceNoticeText = t.roomPriceNoticeText
    || localizedCopy(
      language,
      'Ngu\u1ed3n hi\u1ec7n t\u1ea1i kh\u00f4ng c\u00f4ng b\u1ed1 gi\u00e1 c\u1ed1 \u0111\u1ecbnh cho c\u00e1c h\u1ea1ng ph\u00f2ng n\u00e0y. B\u1ea5m xem gi\u00e1 \u0111\u1ec3 ki\u1ec3m tra theo ng\u00e0y tr\u00ean trang Vinpearl.',
      'The current source does not publish fixed rates for these room types. Check rates by date on Vinpearl.',
    )
  const checkRateLabel = t.checkRoomRate
    || localizedCopy(language, 'Xem gi\u00e1 / \u0111\u1eb7t ph\u00f2ng', 'Check rates / book')

  return (
    <main className="hotel-detail-page">
      <div className="hotel-detail-page__container">
        <Link className="hotel-detail-page__back-link" to="/search">
          <ChevronLeft className="hotel-detail-page__back-icon" />
          <span>{t.backToResorts}</span>
        </Link>

        <section className="hotel-detail-page__header">
          <div>
            <div className="hotel-detail-page__meta-row">
              <span className="hotel-detail-page__type">{hotel.kind}</span>
              <span>{hotel.room_count} {t.rooms}</span>
            </div>
            <h1 className="hotel-detail-page__title">{hotel.name}</h1>
            <p className="hotel-detail-page__location">
              <MapPin className="hotel-detail-page__location-icon" />
              <span>{hotel.address || hotel.destination_name}</span>
            </p>
          </div>
          <button className="hotel-detail-page__ai-button" type="button" onClick={handlePlan}>
            <Sparkles className="hotel-detail-page__ai-icon" />
            <span>{t.planItinerary}</span>
          </button>
        </section>

        <section className="hotel-detail-page__gallery">
          <div className="hotel-detail-page__main-image">
            <SmartImage src={selectedImg} alt={hotel.name} variant="hotel" />
          </div>
          <div className="hotel-detail-page__thumbnails">
            {hotel.images.map((image) => (
              <button
                className={`hotel-detail-page__thumbnail ${selectedImg === image ? 'hotel-detail-page__thumbnail--active' : ''}`}
                key={image}
                type="button"
                onClick={() => setSelectedImg(image)}
              >
                <SmartImage src={image} alt="" variant="hotel" loading="lazy" />
              </button>
            ))}
          </div>
        </section>

        <nav className="hotel-detail-page__tabs" aria-label={t.overview}>
          <button className={`hotel-detail-page__tab ${activeTab === 'rooms' ? 'hotel-detail-page__tab--active' : ''}`} type="button" onClick={() => setActiveTab('rooms')}>{t.availableSuites} ({hotel.rooms.length})</button>
          <button className={`hotel-detail-page__tab ${activeTab === 'overview' ? 'hotel-detail-page__tab--active' : ''}`} type="button" onClick={() => setActiveTab('overview')}>{t.overview}</button>
          <button className={`hotel-detail-page__tab ${activeTab === 'dining' ? 'hotel-detail-page__tab--active' : ''}`} type="button" onClick={() => setActiveTab('dining')}>{t.dining} ({hotel.dining.length})</button>
        </nav>

        {activeTab === 'rooms' && (
          <section className="hotel-detail-page__rooms">
            {allRoomsMissingPrice && (
              <div className="hotel-detail-page__price-notice" role="status">
                <strong>{priceNoticeTitle}</strong>
                <span>{priceNoticeText}</span>
              </div>
            )}
            {hotel.rooms.map((room) => (
              <article className="hotel-detail-page__room" key={room.id}>
                <div className="hotel-detail-page__room-image">
                  <SmartImage src={room.image_url} alt={room.name} variant="hotel" loading="lazy" />
                </div>
                <div className="hotel-detail-page__room-content">
                  <div>
                    <h3>{room.name}</h3>
                    {room.description && <p>{room.description}</p>}
                    <div className="hotel-detail-page__room-facts">
                      {room.area_sqm && <span><Maximize2 className="hotel-detail-page__fact-icon" />{room.area_sqm} m2</span>}
                      {room.guest_count && <span><Users className="hotel-detail-page__fact-icon" />{room.guest_count} {t.guestsLabel}</span>}
                    </div>
                  </div>
                  <div className="hotel-detail-page__room-footer">
                    <RoomPrice room={room} t={t} language={language} />
                    {room.booking_url && (
                      <a className="hotel-detail-page__book-button" href={room.booking_url} target="_blank" rel="noreferrer">
                        {room.price == null ? checkRateLabel : t.selectRoom} <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </section>
        )}

        {activeTab === 'overview' && (
          <section className="hotel-detail-page__overview">
            <article className="hotel-detail-page__panel">
              <h3>{t.aboutPrefix} {hotel.name}</h3>
              <p>{hotel.summary || hotel.address}</p>
              {hotel.source_url && (
                <a href={hotel.source_url} target="_blank" rel="noreferrer">
                  {t.officialPropertyPage} <ExternalLink size={14} />
                </a>
              )}
            </article>
            <article className="hotel-detail-page__panel">
              <h3>{t.resortAmenitiesTitle}</h3>
              <div className="hotel-detail-page__amenities">
                {hotel.amenities.map((amenity) => (
                  <div className="hotel-detail-page__amenity" key={amenity}>
                    <CheckCircle2 className="hotel-detail-page__amenity-icon" />
                    <span>{amenity}</span>
                  </div>
                ))}
              </div>
            </article>
          </section>
        )}

        {activeTab === 'dining' && (
          <section className="hotel-detail-page__rooms">
            {hotel.dining.length ? hotel.dining.map((item) => (
              <article className="hotel-detail-page__room" key={item.id}>
                <div className="hotel-detail-page__room-image"><SmartImage src={item.image_url} alt={item.name} variant="hotel" loading="lazy" /></div>
                <div className="hotel-detail-page__room-content">
                  <div>
                    <h3><Utensils size={18} /> {item.name}</h3>
                    {item.description && <p>{item.description}</p>}
                    {item.hours && <p><Clock size={15} /> {item.hours}</p>}
                    {item.contact && <p>{item.contact}</p>}
                  </div>
                </div>
              </article>
            )) : <p>{t.noDiningData}</p>}
          </section>
        )}
      </div>
    </main>
  )
}

export default HotelDetail
