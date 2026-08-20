import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Building2, MapPin, Users } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import SmartImage from '../components/SmartImage'
import CustomSelect from '../components/CustomSelect'
import { fetchMiceVenues } from '../services/api'
import '../styles/pages/Discovery.css'

const PAGE_SIZE = 12

function Meetings() {
  const { language, t } = useLanguage()
  const copy = t.discovery
  const [searchParams, setSearchParams] = useSearchParams()
  const destination = searchParams.get('destination') || 'all'
  const layout = searchParams.get('layout') || 'all'
  const minCapacity = searchParams.get('minCapacity') || ''
  const page = Math.max(1, Number(searchParams.get('page') || 1))
  const [payload, setPayload] = useState({ items: [], destinations: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    fetchMiceVenues({ destination, language, layout, minCapacity, page, pageSize: PAGE_SIZE })
      .then((data) => active && setPayload(data))
      .catch(() => active && setError(copy.errorText))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [copy.errorText, destination, language, layout, minCapacity, page, reloadToken])

  function updateParams(updates) {
    const next = new URLSearchParams(searchParams)
    Object.entries(updates).forEach(([key, value]) => {
      if (!value || value === 'all') next.delete(key)
      else next.set(key, String(value))
    })
    setSearchParams(next)
  }

  const totalPages = Math.max(1, Math.ceil(payload.total / PAGE_SIZE))

  return (
    <main className="discovery-page discovery-page--meetings">
      <section className="discovery-page__intro">
        <div className="discovery-page__container discovery-page__intro-inner">
          <div>
            <span className="discovery-page__eyebrow">{copy.meetingsEyebrow}</span>
            <h1>{copy.meetingsTitle}</h1>
            <p>{copy.meetingsDescription}</p>
          </div>
          <Link className="discovery-page__chat-link" to="/support">
            <Building2 size={17} /> {copy.contactPlanner}
          </Link>
        </div>
      </section>

      <div className="discovery-page__container discovery-page__body">
        <section className="discovery-page__toolbar discovery-page__toolbar--mice">
          <label>
            <span>{copy.destination}</span>
            <CustomSelect
              value={destination}
              options={[
                { value: 'all', label: copy.allDestinations },
                ...payload.destinations.map((item) => ({ value: item.id, label: item.name })),
              ]}
              onChange={(val) => updateParams({ destination: val, page: 1 })}
              aria-label={copy.destination}
            />
          </label>
          <label>
            <span>{copy.layout}</span>
            <CustomSelect
              value={layout}
              options={[
                { value: 'all', label: copy.allLayouts },
                ...Object.entries(copy.layoutLabels).map(([val, label]) => ({ value: val, label })),
              ]}
              onChange={(val) => updateParams({ layout: val, page: 1 })}
              aria-label={copy.layout}
            />
          </label>
          <label>
            <span>{copy.minCapacity}</span>
            <input
              min="1"
              max="10000"
              inputMode="numeric"
              type="number"
              value={minCapacity}
              placeholder={copy.capacityPlaceholder}
              onChange={(event) => updateParams({ minCapacity: event.target.value, page: 1 })}
            />
          </label>
          <div className="discovery-page__result-count"><strong>{payload.total}</strong><span>{copy.venueResults}</span></div>
        </section>

        {error && (
          <section className="discovery-page__state" role="alert">
            <h2>{copy.errorTitle}</h2>
            <p>{error}</p>
            <button type="button" onClick={() => setReloadToken((value) => value + 1)}>{copy.retry}</button>
          </section>
        )}
        {!error && loading && <div className="discovery-page__grid">{Array.from({ length: 6 }, (_, index) => <div className="discovery-card discovery-card--skeleton" key={index} />)}</div>}
        {!error && !loading && payload.items.length === 0 && <section className="discovery-page__state"><h2>{copy.emptyTitle}</h2><p>{copy.emptyText}</p></section>}

        {!error && !loading && payload.items.length > 0 && (
          <div className="discovery-page__grid">
            {payload.items.map((venue) => (
              <article className="discovery-card" key={venue.id}>
                <Link className="discovery-card__media" to={`/meetings/${venue.id}`}>
                  <SmartImage src={venue.image_url} alt={venue.name} variant="meeting" loading="lazy" />
                  <span className="discovery-card__badge">MICE</span>
                </Link>
                <div className="discovery-card__body">
                  <div className="discovery-card__location"><MapPin size={15} /> {venue.destination_name}</div>
                  <h2>{venue.name}</h2>
                  <p>{venue.subtitle || venue.summary || copy.noDescription}</p>
                  <div className="discovery-card__facts">
                    <span><Building2 size={15} /> {venue.room_count} {copy.rooms}</span>
                    {venue.max_capacity && <span><Users size={15} /> {venue.max_capacity} {copy.guests}</span>}
                  </div>
                  <Link className="discovery-card__link" to={`/meetings/${venue.id}`}>{copy.viewDetails}<ArrowRight size={16} /></Link>
                </div>
              </article>
            ))}
          </div>
        )}

        {!error && totalPages > 1 && (
          <nav className="discovery-page__pagination" aria-label={copy.pagination}>
            <button type="button" disabled={page <= 1} title={copy.previous} onClick={() => updateParams({ page: page - 1 })}><ArrowLeft size={17} /></button>
            <span>{page} / {totalPages}</span>
            <button type="button" disabled={page >= totalPages} title={copy.next} onClick={() => updateParams({ page: page + 1 })}><ArrowRight size={17} /></button>
          </nav>
        )}
      </div>
    </main>
  )
}

export default Meetings
