import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  CheckCircle2,
  MapPin,
  Sparkles,
  Star,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/HotelCard.css'

function HotelCard({ hotel }) {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const formattedPrice = new Intl.NumberFormat('vi-VN').format(hotel.price)

  function handleAskAi(event) {
    event.preventDefault()
    event.stopPropagation()

    const prompt = `${t.askAiAboutThis}: ${hotel.name}`
    navigate(`/chat?prompt=${encodeURIComponent(prompt)}`)
  }

  return (
    <article className="hotel-card">
      <div className="hotel-card__media">
        <img
          className="hotel-card__image"
          src={hotel.images[0]}
          alt={hotel.name}
        />
        <div className="hotel-card__media-overlay" />

        <div className="hotel-card__type-badge">{hotel.type}</div>

        <div className="hotel-card__rating-badge">
          <Star className="hotel-card__rating-icon" />
          <span>{hotel.rating}</span>
          <span className="hotel-card__reviews">({hotel.reviewsCount})</span>
        </div>

        <div className="hotel-card__location-overlay">
          <MapPin className="hotel-card__location-icon" />
          <span>{hotel.location}</span>
        </div>
      </div>

      <div className="hotel-card__body">
        <div>
          <h3 className="hotel-card__title">{hotel.name}</h3>
          <p className="hotel-card__description">"{hotel.description}"</p>

          <div className="hotel-card__amenities">
            {hotel.amenities.slice(0, 3).map((amenity) => (
              <span className="hotel-card__amenity" key={amenity}>
                <CheckCircle2 className="hotel-card__amenity-icon" />
                <span>{amenity}</span>
              </span>
            ))}
            {hotel.amenities.length > 3 && (
              <span className="hotel-card__amenity-more">
                +{hotel.amenities.length - 3}
              </span>
            )}
          </div>
        </div>

        <div className="hotel-card__footer">
          <div className="hotel-card__price-row">
            <div>
              <span className="hotel-card__price-label">{t.startingFrom}</span>
              <span className="hotel-card__price-value">{formattedPrice}</span>
              <span className="hotel-card__price-unit">{t.priceUnitNight}</span>
            </div>
            <button
              className="hotel-card__ask-ai"
              type="button"
              onClick={handleAskAi}
            >
              <Sparkles className="hotel-card__ask-ai-icon" />
              <span>{t.navAiChat}</span>
            </button>
          </div>

          <Link className="hotel-card__details-link" to={`/hotels/${hotel.id}`}>
            <span>{t.viewDetails}</span>
            <ArrowRight className="hotel-card__details-icon" />
          </Link>
        </div>
      </div>
    </article>
  )
}

export default HotelCard
