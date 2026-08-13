import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  CheckCircle2,
  ChevronLeft,
  Clock,
  CreditCard,
  MapPin,
  Maximize2,
  ShieldAlert,
  Sparkles,
  Star,
  Users,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { fetchHotelById } from '../services/api'
import '../styles/pages/HotelDetail.css'

function HotelDetail() {
  const { hotelId, id } = useParams()
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [hotel, setHotel] = useState(null)
  const [selectedImg, setSelectedImg] = useState('')
  const [activeTab, setActiveTab] = useState('rooms')
  const [reservedRoom, setReservedRoom] = useState(null)
  const [bookingToast, setBookingToast] = useState(false)

  useEffect(() => {
    const selectedId = hotelId || id

    if (selectedId) {
      fetchHotelById(selectedId).then((data) => {
        if (data) {
          setHotel(data)
          setSelectedImg(data.images[0])
        }
      })
    }
  }, [hotelId, id])

  if (!hotel) {
    return (
      <main className="hotel-detail-page hotel-detail-page--loading">
        <div className="hotel-detail-page__loading">
          <div className="hotel-detail-page__spinner" />
          <p>{t.loadingResortDetails}</p>
        </div>
      </main>
    )
  }

  function handleBookRoom(room) {
    setReservedRoom(room)
    setBookingToast(true)
    window.setTimeout(() => setBookingToast(false), 4000)
  }

  function handlePlanItineraryWithAi() {
    const prompt = `${t.planItinerary}: ${hotel.name}, ${hotel.destination}`
    navigate(`/chat?prompt=${encodeURIComponent(prompt)}`)
  }

  return (
    <main className="hotel-detail-page">
      {bookingToast && reservedRoom && (
        <div className="hotel-detail-page__toast">
          <CheckCircle2 className="hotel-detail-page__toast-icon" />
          <div>
            <h5>{t.reservedSuccess}</h5>
            <p>
              {reservedRoom.name} -{' '}
              {new Intl.NumberFormat('vi-VN').format(reservedRoom.price)} {t.priceUnitNight}
            </p>
          </div>
        </div>
      )}

      <div className="hotel-detail-page__container">
        <Link className="hotel-detail-page__back-link" to="/search">
          <ChevronLeft className="hotel-detail-page__back-icon" />
          <span>{t.backToResorts}</span>
        </Link>

        <section className="hotel-detail-page__header">
          <div>
            <div className="hotel-detail-page__meta-row">
              <span className="hotel-detail-page__type">{hotel.type}</span>
              <div className="hotel-detail-page__rating">
                <Star className="hotel-detail-page__rating-icon" />
                <span>{hotel.rating}</span>
                <span>({hotel.reviewsCount} {t.reviews})</span>
              </div>
            </div>

            <h1 className="hotel-detail-page__title">{hotel.name}</h1>

            <p className="hotel-detail-page__location">
              <MapPin className="hotel-detail-page__location-icon" />
              <span>{hotel.location}</span>
            </p>
          </div>

          <button
            className="hotel-detail-page__ai-button"
            type="button"
            onClick={handlePlanItineraryWithAi}
          >
            <Sparkles className="hotel-detail-page__ai-icon" />
            <span>{t.planItinerary}</span>
          </button>
        </section>

        <section className="hotel-detail-page__gallery">
          <div className="hotel-detail-page__main-image">
            <img src={selectedImg} alt={hotel.name} />
          </div>

          <div className="hotel-detail-page__thumbnails">
            {hotel.images.map((image) => (
              <button
                className={`hotel-detail-page__thumbnail ${
                  selectedImg === image ? 'hotel-detail-page__thumbnail--active' : ''
                }`}
                key={image}
                type="button"
                onClick={() => setSelectedImg(image)}
              >
                <img src={image} alt="" />
              </button>
            ))}
          </div>
        </section>

        <nav className="hotel-detail-page__tabs" aria-label={t.overview}>
          <button
            className={`hotel-detail-page__tab ${
              activeTab === 'rooms' ? 'hotel-detail-page__tab--active' : ''
            }`}
            type="button"
            onClick={() => setActiveTab('rooms')}
          >
            {t.availableSuites} ({hotel.rooms.length})
          </button>
          <button
            className={`hotel-detail-page__tab ${
              activeTab === 'overview' ? 'hotel-detail-page__tab--active' : ''
            }`}
            type="button"
            onClick={() => setActiveTab('overview')}
          >
            {t.overview}
          </button>
          <button
            className={`hotel-detail-page__tab ${
              activeTab === 'policies' ? 'hotel-detail-page__tab--active' : ''
            }`}
            type="button"
            onClick={() => setActiveTab('policies')}
          >
            {t.policies}
          </button>
        </nav>

        {activeTab === 'rooms' && (
          <section className="hotel-detail-page__rooms">
            {hotel.rooms.map((room) => (
              <article className="hotel-detail-page__room" key={room.id}>
                <div className="hotel-detail-page__room-image">
                  <img src={room.image || hotel.images[0]} alt={room.name} />
                </div>

                <div className="hotel-detail-page__room-content">
                  <div>
                    <h3>{room.name}</h3>
                    <p>{room.description}</p>

                    <div className="hotel-detail-page__room-facts">
                      <span>
                        <Maximize2 className="hotel-detail-page__fact-icon" />
                        {room.size}
                      </span>
                      <span>
                        <Users className="hotel-detail-page__fact-icon" />
                        {room.guests}
                      </span>
                    </div>
                  </div>

                  <div className="hotel-detail-page__room-footer">
                    <div>
                      <span className="hotel-detail-page__room-price">
                        {new Intl.NumberFormat('vi-VN').format(room.price)}
                      </span>
                      <span className="hotel-detail-page__room-unit">{t.priceUnitNight}</span>
                    </div>

                    <button
                      className="hotel-detail-page__book-button"
                      type="button"
                      onClick={() => handleBookRoom(room)}
                    >
                      {t.selectRoom}
                    </button>
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
              <p>{hotel.description}</p>
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

        {activeTab === 'policies' && (
          <section className="hotel-detail-page__policies">
            <PolicyCard icon={Clock} title={t.checkInCheckOut}>
              {t.checkInLabel}: <strong>{hotel.policies.checkIn}</strong>
              <br />
              {t.checkOutLabel}: <strong>{hotel.policies.checkOut}</strong>
            </PolicyCard>
            <PolicyCard icon={Users} title={t.childrenPolicy}>
              {hotel.policies.children}
            </PolicyCard>
            <PolicyCard icon={ShieldAlert} title={t.cancellationPolicy}>
              {hotel.policies.cancellation}
            </PolicyCard>
            <PolicyCard icon={CreditCard} title={t.paymentMethods}>
              {hotel.policies.payment}
            </PolicyCard>
          </section>
        )}
      </div>
    </main>
  )
}

function PolicyCard({ icon: Icon, title, children }) {
  return (
    <article className="hotel-detail-page__policy">
      <div className="hotel-detail-page__policy-title">
        <Icon className="hotel-detail-page__policy-icon" />
        <span>{title}</span>
      </div>
      <p>{children}</p>
    </article>
  )
}

export default HotelDetail
