import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Building2, ExternalLink, MapPin, Maximize2, Phone, Users } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import SmartImage from '../components/SmartImage'
import { fetchMiceVenueById } from '../services/api'
import '../styles/pages/Discovery.css'

function MeetingDetail() {
  const { venueId } = useParams()
  const { language, t } = useLanguage()
  const copy = t.discovery
  const [venue, setVenue] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    fetchMiceVenueById(venueId, language)
      .then((data) => {
        if (!active) return
        setVenue(data)
        setError(data ? '' : copy.notFound)
      })
      .catch(() => active && setError(copy.errorText))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [copy.errorText, copy.notFound, language, venueId])

  if (loading || !venue) {
    return (
      <main className="discovery-detail discovery-detail--state">
        {loading ? <div className="discovery-page__spinner" /> : <h1>{error}</h1>}
        {!loading && <Link to="/meetings"><ArrowLeft size={17} /> {copy.backToMeetings}</Link>}
      </main>
    )
  }

  return (
    <main className="discovery-detail">
      <div className="discovery-detail__container">
        <Link className="discovery-detail__back" to="/meetings"><ArrowLeft size={17} /> {copy.backToMeetings}</Link>
        <section className="discovery-detail__hero">
          <SmartImage src={venue.image_url} alt={venue.name} variant="meeting" />
          <div className="discovery-detail__hero-content">
            <span>MICE</span>
            <h1>{venue.name}</h1>
            <p><MapPin size={17} /> {venue.address || venue.destination_name}</p>
          </div>
        </section>

        <div className="discovery-detail__actions">
          <Link to="/support"><Building2 size={17} /> {copy.contactPlanner}</Link>
          {venue.phone && <a href={`tel:${venue.phone}`}><Phone size={17} /> {venue.phone}</a>}
          {venue.source_url && <a href={venue.source_url} target="_blank" rel="noreferrer"><ExternalLink size={17} /> {copy.officialSource}</a>}
        </div>

        <section className="discovery-detail__overview">
          <div>
            <span className="discovery-page__eyebrow">{copy.venueOverview}</span>
            <h2>{venue.subtitle || venue.name}</h2>
            <p>{venue.overview || venue.summary || copy.noDescription}</p>
          </div>
          <dl className="discovery-detail__facts">
            <div><dt>{copy.destination}</dt><dd>{venue.destination_name}</dd></div>
            <div><dt>{copy.rooms}</dt><dd>{venue.room_count}</dd></div>
            {venue.max_capacity && <div><dt>{copy.maxCapacity}</dt><dd><Users size={16} /> {venue.max_capacity}</dd></div>}
          </dl>
        </section>

        <section className="discovery-detail__section">
          <div className="discovery-detail__section-heading">
            <span className="discovery-page__eyebrow">{copy.venueSpaces}</span>
            <h2>{copy.roomsAndCapacity}</h2>
          </div>
          {venue.rooms.length === 0 ? (
            <div className="discovery-page__state"><p>{copy.noRooms}</p></div>
          ) : (
            <div className="discovery-detail__rooms">
              {venue.rooms.map((room) => (
                <article key={room.id}>
                  <SmartImage src={room.image_url} alt={room.name} variant="meeting" loading="lazy" />
                  <div className="discovery-detail__room-main">
                    <h3>{room.name}</h3>
                    {room.description && <p>{room.description}</p>}
                    <div className="discovery-card__facts">
                      {(room.area_sqm || room.area_raw) && <span><Maximize2 size={15} /> {room.area_sqm || room.area_raw} {room.area_sqm ? 'm²' : ''}</span>}
                      {room.ceiling_height_m && <span>{copy.ceiling}: {room.ceiling_height_m} m</span>}
                    </div>
                  </div>
                  {room.capacities.length > 0 && (
                    <div className="discovery-detail__capacity-list">
                      {room.capacities.map((capacity) => (
                        <div key={capacity.layout}>
                          <span>{copy.layoutLabels[capacity.layout] || capacity.layout}</span>
                          <strong>{capacity.pax}</strong>
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

export default MeetingDetail
