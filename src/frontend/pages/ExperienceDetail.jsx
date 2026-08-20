import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  CalendarRange,
  ExternalLink,
  MapPin,
  Ruler,
  Sparkles,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import SmartImage from '../components/SmartImage'
import { fetchAttractionById, fetchGolfCourseById } from '../services/api'
import '../styles/pages/Discovery.css'

function activityText(activity) {
  if (typeof activity === 'string') return activity
  if (!activity || typeof activity !== 'object') return ''
  return activity.text || activity.description || activity.title || activity.name || ''
}

function ExperienceDetail({ type }) {
  const params = useParams()
  const id = type === 'golf' ? params.courseId : params.attractionId
  const { language, t } = useLanguage()
  const copy = t.discovery
  const [item, setItem] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    const request = type === 'golf'
      ? fetchGolfCourseById(id, language)
      : fetchAttractionById(id, language)
    request
      .then((data) => {
        if (!active) return
        setItem(data)
        setError(data ? '' : copy.notFound)
      })
      .catch(() => active && setError(copy.errorText))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [copy.errorText, copy.notFound, id, language, type])

  if (loading || !item) {
    return (
      <main className="discovery-detail discovery-detail--state">
        {loading ? <div className="discovery-page__spinner" /> : <h1>{error}</h1>}
        {!loading && <Link to="/experiences"><ArrowLeft size={17} /> {copy.backToExperiences}</Link>}
      </main>
    )
  }

  const isGolf = type === 'golf'
  const title = isGolf ? item.name : item.title
  const sourceUrl = isGolf ? item.page_url : (item.source_url || item.detail_url)
  const description = item.full_text || item.description || item.summary
  const prompt = encodeURIComponent(`${copy.askAiPrompt}: ${title}, ${item.destination_name}`)

  return (
    <main className="discovery-detail">
      <div className="discovery-detail__container">
        <Link className="discovery-detail__back" to={isGolf ? '/experiences?view=golf' : '/experiences'}>
          <ArrowLeft size={17} /> {copy.backToExperiences}
        </Link>

        <section className="discovery-detail__hero">
          <SmartImage src={item.image_url} alt={title} variant={isGolf ? 'golf' : 'experience'} />
          <div className="discovery-detail__hero-content">
            <span>{isGolf ? copy.golfCourse : (copy.kindLabels[item.kind] || item.kind)}</span>
            <h1>{title}</h1>
            <p><MapPin size={17} /> {item.location_text || item.destination_name}</p>
          </div>
        </section>

        <div className="discovery-detail__actions">
          <Link to={`/chat?prompt=${prompt}`}><Sparkles size={17} /> {copy.askAi}</Link>
          {sourceUrl && (
            <a href={sourceUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={17} /> {copy.officialSource}
            </a>
          )}
        </div>

        <section className="discovery-detail__overview">
          <div>
            <span className="discovery-page__eyebrow">{copy.overview}</span>
            <h2>{item.section_title || title}</h2>
            <p>{description || copy.noDescription}</p>
          </div>
          <dl className="discovery-detail__facts">
            <div><dt>{copy.destination}</dt><dd>{item.destination_name}</dd></div>
            {!isGolf && item.duration_label && (
              <div><dt>{copy.duration}</dt><dd><CalendarRange size={16} /> {item.duration_label}</dd></div>
            )}
            {isGolf && item.holes && <div><dt>{copy.holes}</dt><dd>{item.holes}</dd></div>}
            {isGolf && item.par && <div><dt>Par</dt><dd>{item.par}</dd></div>}
            {isGolf && item.designer && <div><dt>{copy.designer}</dt><dd>{item.designer}</dd></div>}
            {isGolf && item.course_length && (
              <div><dt>{copy.courseLength}</dt><dd><Ruler size={16} /> {item.course_length}</dd></div>
            )}
          </dl>
        </section>

        {!isGolf && item.itinerary?.length > 0 && (
          <section className="discovery-detail__section">
            <div className="discovery-detail__section-heading">
              <span className="discovery-page__eyebrow">{copy.itinerary}</span>
              <h2>{copy.journeyPlan}</h2>
            </div>
            <div className="discovery-detail__timeline">
              {item.itinerary.map((day, index) => (
                <article key={`${day.day_number || index}-${day.heading || ''}`}>
                  <span>{copy.day} {day.day_number || index + 1}</span>
                  <div>
                    <h3>{day.heading || day.title || copy.itinerary}</h3>
                    {day.text && <p>{day.text}</p>}
                    {(day.activities || []).map((activity, activityIndex) => {
                      const text = activityText(activity)
                      return text ? <p key={activityIndex}>{text}</p> : null
                    })}
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        {isGolf && item.features?.length > 0 && (
          <section className="discovery-detail__section">
            <div className="discovery-detail__section-heading">
              <span className="discovery-page__eyebrow">{copy.features}</span>
              <h2>{copy.golfExperience}</h2>
            </div>
            <div className="discovery-detail__feature-grid">
              {item.features.map((feature) => (
                <article key={feature.id}>
                  <SmartImage src={feature.image_url} alt={feature.title} variant="golf" loading="lazy" />
                  <div>
                    <span>{feature.kind}</span>
                    <h3>{feature.title}</h3>
                    {feature.description && <p>{feature.description}</p>}
                    {feature.detail_url && (
                      <a href={feature.detail_url} target="_blank" rel="noreferrer">
                        {copy.viewSource} <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  )
}

export default ExperienceDetail
