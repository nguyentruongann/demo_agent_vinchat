import { Link } from 'react-router-dom'
import { ArrowRight, BedDouble, CheckCircle2, MapPin, Sparkles, Users } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { openAiChat } from './ChatWidget'
import SmartImage from './SmartImage'
import '../styles/components/HotelCard.css'

const FALLBACK_HOTEL_IMAGE = 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80'

function HotelCard({ hotel }) {
  const { t } = useLanguage()
  const price = hotel.price_from == null
    ? null
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: hotel.currency || 'USD', maximumFractionDigits: 0 }).format(hotel.price_from)

  function handleAskAi(event) {
    event.preventDefault()
    openAiChat(`${t.askAiAboutThis}: ${hotel.name}`)
  }

  const imgSrc = hotel.images?.[0] || FALLBACK_HOTEL_IMAGE

  return (
    <article className="hotel-card">
      <div className="hotel-card__media">
        <SmartImage
          className="hotel-card__image"
          src={imgSrc}
          alt={hotel.name}
          variant="hotel"
        />
        <div className="hotel-card__media-overlay" />
        <div className="hotel-card__type-badge">{hotel.kind || t.property}</div>
        <div className="hotel-card__rating-badge"><BedDouble size={13} /><span>{hotel.room_count} {t.rooms}</span></div>
        <div className="hotel-card__location-overlay"><MapPin className="hotel-card__location-icon" /><span>{hotel.address || hotel.destination_name}</span></div>
      </div>
      <div className="hotel-card__body">
        <div>
          <h3 className="hotel-card__title">{hotel.name}</h3>
          {hotel.summary && <p className="hotel-card__description">{hotel.summary}</p>}
          <div className="hotel-card__amenities">
            {hotel.amenities.slice(0, 3).map((amenity) => <span className="hotel-card__amenity" key={amenity}><CheckCircle2 className="hotel-card__amenity-icon" /><span>{amenity}</span></span>)}
            {hotel.max_guests && <span className="hotel-card__amenity"><Users className="hotel-card__amenity-icon" /><span>{t.upToGuests.replace('{{count}}', hotel.max_guests)}</span></span>}
          </div>
        </div>
        <div className="hotel-card__footer">
          <div className="hotel-card__price-row"><div><span className="hotel-card__price-label">{price ? t.startingFrom : t.officialRate}</span><span className="hotel-card__price-value">{price || t.contactProperty}</span></div><button className="hotel-card__ask-ai" type="button" onClick={handleAskAi}><Sparkles className="hotel-card__ask-ai-icon" /><span>{t.navAiChat}</span></button></div>
          <Link className="hotel-card__details-link" to={`/hotels/${hotel.id}`}><span>{t.viewDetails}</span><ArrowRight className="hotel-card__details-icon" /></Link>
        </div>
      </div>
    </article>
  )
}

export default HotelCard
