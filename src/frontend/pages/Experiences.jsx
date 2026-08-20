import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  CalendarRange,
  Flag,
  MapPin,
  Sparkles,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import SmartImage from '../components/SmartImage'
import CustomSelect from '../components/CustomSelect'
import { fetchAttractions, fetchGolfCourses } from '../services/api'
import '../styles/pages/Discovery.css'

const PAGE_SIZE = 12

function Experiences() {
  const { language, t } = useLanguage()
  const copy = t.discovery
  const [searchParams, setSearchParams] = useSearchParams()
  const view = searchParams.get('view') === 'golf' ? 'golf' : 'attractions'
  const destination = searchParams.get('destination') || 'all'
  const kind = searchParams.get('kind') || 'all'
  const page = Math.max(1, Number(searchParams.get('page') || 1))
  const [payload, setPayload] = useState({ items: [], destinations: [], kinds: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    const request = view === 'golf'
      ? fetchGolfCourses({ destination, language, page, pageSize: PAGE_SIZE })
      : fetchAttractions({ destination, kind, language, page, pageSize: PAGE_SIZE })
    request
      .then((data) => active && setPayload(data))
      .catch(() => active && setError(copy.errorText))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [copy.errorText, destination, kind, language, page, reloadToken, view])

  function updateParams(updates) {
    const next = new URLSearchParams(searchParams)
    Object.entries(updates).forEach(([key, value]) => {
      if (!value || value === 'all' || (key === 'view' && value === 'attractions')) {
        next.delete(key)
      } else {
        next.set(key, String(value))
      }
    })
    setSearchParams(next)
  }

  function changeView(nextView) {
    const next = new URLSearchParams()
    if (nextView === 'golf') next.set('view', 'golf')
    setSearchParams(next)
  }

  const totalPages = Math.max(1, Math.ceil(payload.total / PAGE_SIZE))

  return (
    <main className="discovery-page">
      <section className="discovery-page__intro">
        <div className="discovery-page__container discovery-page__intro-inner">
          <div>
            <span className="discovery-page__eyebrow">{copy.experiencesEyebrow}</span>
            <h1>{copy.experiencesTitle}</h1>
            <p>{copy.experiencesDescription}</p>
          </div>
          <Link className="discovery-page__chat-link" to="/chat">
            <Sparkles size={17} />
            <span>{copy.askAi}</span>
          </Link>
        </div>
      </section>

      <div className="discovery-page__container discovery-page__body">
        <div className="discovery-page__segmented" aria-label={copy.experiencesTitle}>
          <button
            className={view === 'attractions' ? 'is-active' : ''}
            type="button"
            onClick={() => changeView('attractions')}
          >
            <Sparkles size={17} /> {copy.attractionsTab}
          </button>
          <button
            className={view === 'golf' ? 'is-active' : ''}
            type="button"
            onClick={() => changeView('golf')}
          >
            <Flag size={17} /> {copy.golfTab}
          </button>
        </div>

        <section className="discovery-page__toolbar" aria-label={copy.filters}>
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
          {view === 'attractions' && (
            <label>
              <span>{copy.kind}</span>
              <CustomSelect
                value={kind}
                options={[
                  { value: 'all', label: copy.allKinds },
                  ...payload.kinds.map((item) => ({ value: item, label: copy.kindLabels[item] || item })),
                ]}
                onChange={(val) => updateParams({ kind: val, page: 1 })}
                aria-label={copy.kind}
              />
            </label>
          )}
          <div className="discovery-page__result-count">
            <strong>{payload.total}</strong>
            <span>{view === 'golf' ? copy.golfResults : copy.attractionResults}</span>
          </div>
        </section>

        {error && (
          <section className="discovery-page__state" role="alert">
            <h2>{copy.errorTitle}</h2>
            <p>{error}</p>
            <button type="button" onClick={() => setReloadToken((value) => value + 1)}>{copy.retry}</button>
          </section>
        )}

        {!error && loading && (
          <div className="discovery-page__grid" aria-label={copy.loading}>
            {Array.from({ length: 6 }, (_, index) => (
              <div className="discovery-card discovery-card--skeleton" key={index} />
            ))}
          </div>
        )}

        {!error && !loading && payload.items.length === 0 && (
          <section className="discovery-page__state">
            <h2>{copy.emptyTitle}</h2>
            <p>{copy.emptyText}</p>
          </section>
        )}

        {!error && !loading && payload.items.length > 0 && (
          <div className="discovery-page__grid">
            {payload.items.map((item) => {
              const isGolf = view === 'golf'
              const detailPath = isGolf
                ? `/experiences/golf/${item.id}`
                : `/experiences/attractions/${item.id}`
              return (
                <article className="discovery-card" key={item.id}>
                  <Link className="discovery-card__media" to={detailPath}>
                    <SmartImage
                      src={item.image_url}
                      alt={isGolf ? item.name : item.title}
                      variant={isGolf ? 'golf' : 'experience'}
                      loading="lazy"
                    />
                    <span className="discovery-card__badge">
                      {isGolf ? copy.golfCourse : (copy.kindLabels[item.kind] || item.kind)}
                    </span>
                  </Link>
                  <div className="discovery-card__body">
                    <div className="discovery-card__location">
                      <MapPin size={15} /> {item.destination_name}
                    </div>
                    <h2>{isGolf ? item.name : item.title}</h2>
                    <p>{item.summary || copy.noDescription}</p>
                    <div className="discovery-card__facts">
                      {!isGolf && item.duration_label && (
                        <span><CalendarRange size={15} /> {item.duration_label}</span>
                      )}
                      {isGolf && item.holes && <span>{item.holes} {copy.holes}</span>}
                      {isGolf && item.par && <span>Par {item.par}</span>}
                    </div>
                    <Link className="discovery-card__link" to={detailPath}>
                      {copy.viewDetails} <ArrowRight size={16} />
                    </Link>
                  </div>
                </article>
              )
            })}
          </div>
        )}

        {!error && totalPages > 1 && (
          <nav className="discovery-page__pagination" aria-label={copy.pagination}>
            <button
              type="button"
              disabled={page <= 1}
              title={copy.previous}
              onClick={() => updateParams({ page: page - 1 })}
            >
              <ArrowLeft size={17} />
            </button>
            <span>{page} / {totalPages}</span>
            <button
              type="button"
              disabled={page >= totalPages}
              title={copy.next}
              onClick={() => updateParams({ page: page + 1 })}
            >
              <ArrowRight size={17} />
            </button>
          </nav>
        )}
      </div>
    </main>
  )
}

export default Experiences
