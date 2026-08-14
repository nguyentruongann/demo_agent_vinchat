import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/DestinationCard.css'

const FALLBACK_DEST_IMAGE = 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80'

function DestinationCard({ destination }) {
  const { t } = useLanguage()
  const imgSrc = destination.image_url || FALLBACK_DEST_IMAGE

  return (
    <Link className="destination-card" to={`/search?destination=${destination.id}`}>
      <img
        className="destination-card__image"
        src={imgSrc}
        alt={destination.name}
        onError={(e) => {
          e.currentTarget.onerror = null
          e.currentTarget.src = FALLBACK_DEST_IMAGE
        }}
      />
      <span className="destination-card__badge">{destination.property_count} {t.navHotels}</span>
      <div className="destination-card__content">
        <span className="destination-card__label">{destination.province || destination.country}</span>
        <h3 className="destination-card__title">{destination.name}</h3>
        {destination.description && <p className="destination-card__description">{destination.description}</p>}
        <div className="destination-card__action"><span>{t.exploreRetreats}</span><ChevronRight className="destination-card__action-icon" /></div>
      </div>
    </Link>
  )
}

export default DestinationCard
