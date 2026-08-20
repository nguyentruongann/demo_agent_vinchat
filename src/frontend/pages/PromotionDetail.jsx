import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  CalendarDays,
  Check,
  ChevronRight,
  Clipboard,
  ExternalLink,
  FileText,
  Gift,
  HelpCircle,
  Info,
  MapPin,
  Phone,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  Tag,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import SmartImage from '../components/SmartImage'
import { fetchPromotionById } from '../services/api'
import '../styles/pages/PromotionDetail.css'

const DATE_LOCALES = {
  en: 'en-GB',
  vi: 'vi-VN',
  ko: 'ko-KR',
  ja: 'ja-JP',
  zh: 'zh-CN',
}

function normalizeText(value) {
  return String(value || '').trim()
}

function formatDate(value, language) {
  if (!value) return ''
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(DATE_LOCALES[language] || 'en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function PlainText({ children }) {
  const text = normalizeText(children)
  if (!text) return null
  return <p className="promotion-prose">{text}</p>
}

function StructuredBlock({ block, promotionTitle }) {
  const payload = block.payload || {}

  if (block.block_type === 'heading') {
    const heading = normalizeText(payload.text || block.caption)
    if (!heading || heading.toLocaleLowerCase() === normalizeText(promotionTitle).toLocaleLowerCase()) {
      return null
    }
    return <h3 className="promotion-structured-heading">{heading}</h3>
  }

  if (block.block_type === 'bullet_list' || block.block_type === 'list') {
    const items = Array.isArray(payload.items) ? payload.items.filter(Boolean) : []
    if (items.length === 0) return null
    return (
      <div className="promotion-structured-list">
        {block.caption && <h4>{block.caption}</h4>}
        <ul>
          {items.map((item, index) => <li key={`${block.id}-${index}`}>{String(item)}</li>)}
        </ul>
      </div>
    )
  }

  if (block.block_type === 'table') {
    const rows = Array.isArray(payload.rows)
      ? payload.rows.filter((row) => Array.isArray(row) && row.some((cell) => normalizeText(cell)))
      : []
    if (rows.length === 0) return null
    const columnCount = Math.max(...rows.map((row) => row.length))
    const header = rows[0]
    const body = rows.slice(1)

    return (
      <figure className="promotion-table-figure">
        {block.caption && <figcaption>{block.caption}</figcaption>}
        <div className="promotion-table-scroll" tabIndex="0">
          <table>
            <thead>
              <tr>
                {Array.from({ length: columnCount }, (_, index) => (
                  <th key={`${block.id}-head-${index}`} scope="col">
                    {normalizeText(header[index]) || '—'}
                  </th>
                ))}
              </tr>
            </thead>
            {body.length > 0 && (
              <tbody>
                {body.map((row, rowIndex) => (
                  <tr key={`${block.id}-row-${rowIndex}`}>
                    {Array.from({ length: columnCount }, (_, cellIndex) => (
                      <td key={`${block.id}-${rowIndex}-${cellIndex}`}>
                        {normalizeText(row[cellIndex]) || '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            )}
          </table>
        </div>
      </figure>
    )
  }

  return null
}

function TextList({ items, ordered = false }) {
  if (!Array.isArray(items) || items.length === 0) return null
  const List = ordered ? 'ol' : 'ul'
  return (
    <List className={ordered ? 'promotion-numbered-list' : 'promotion-bullet-list'}>
      {items.map((item) => <li key={item.id}>{item.text}</li>)}
    </List>
  )
}

export default function PromotionDetail() {
  const { promotionId } = useParams()
  const { language, t, translate } = useLanguage()
  const [promo, setPromo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [copiedCode, setCopiedCode] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')

    fetchPromotionById(promotionId)
      .then((data) => {
        if (!active) return
        if (!data) setError('not_found')
        else setPromo(data)
      })
      .catch(() => {
        if (active) setError('api_error')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [promotionId, language])

  const visibleSections = useMemo(() => {
    const sections = Array.isArray(promo?.sections) ? promo.sections : []
    const hasTables = promo?.blocks?.some((block) => block.block_type === 'table')
    return sections.filter((section) => {
      const content = normalizeText(section.content)
      if (!content) return false
      return !(hasTables && content.includes(' | '))
    })
  }, [promo])

  const validityText = useMemo(() => {
    if (!promo) return ''
    const from = formatDate(promo.validity_from || promo.booking_from || promo.stay_from, language)
    const to = formatDate(promo.validity_to || promo.booking_to || promo.stay_to, language)
    if (from && to) return `${from} – ${to}`
    if (to) return `${t.validUntil}: ${to}`
    if (from) return `${t.startsFrom}: ${from}`
    return ''
  }, [language, promo, t.startsFrom, t.validUntil])

  const destinationText = useMemo(() => {
    if (!promo) return ''
    if (promo.is_nationwide) return translate('promotions.nationwide')
    return (promo.destinations || []).map((destination) => destination.name).filter(Boolean).join(', ')
  }, [promo, translate])

  async function copyPromotionCode(code) {
    try {
      await navigator.clipboard.writeText(code)
      setCopiedCode(code)
      window.setTimeout(() => setCopiedCode(''), 1800)
    } catch {
      setCopiedCode('')
    }
  }

  function retry() {
    setLoading(true)
    setError('')
    fetchPromotionById(promotionId)
      .then((data) => {
        if (!data) setError('not_found')
        else setPromo(data)
      })
      .catch(() => setError('api_error'))
      .finally(() => setLoading(false))
  }

  if (loading) {
    return (
      <div className="promotion-detail-state" aria-busy="true" aria-label={t.loadingPromotion}>
        <div className="promotion-detail-skeleton promotion-detail-skeleton--wide" />
        <div className="promotion-detail-skeleton-grid">
          <div className="promotion-detail-skeleton" />
          <div className="promotion-detail-skeleton" />
        </div>
      </div>
    )
  }

  if (error || !promo) {
    const notFound = error === 'not_found'
    return (
      <div className="promotion-detail-error" role="alert">
        <span className="promotion-detail-error__icon"><Info /></span>
        <h1>{notFound ? t.promotionNotFound : t.promotionLoadError}</h1>
        <p>{notFound ? t.promotionNotFoundDesc : t.promotionLoadErrorDesc}</p>
        {notFound ? (
          <Link to="/promotions" className="promotion-primary-action">{t.viewOtherPromotions}</Link>
        ) : (
          <button type="button" onClick={retry} className="promotion-primary-action">
            <RefreshCcw size={17} /> {t.tryAgain}
          </button>
        )}
      </div>
    )
  }

  const statusLabel = promo.status === 'upcoming'
    ? t.statusUpcoming
    : promo.status === 'expired'
      ? t.statusExpired
      : t.statusActive
  const hasStructuredContent = (promo.blocks?.length || 0) + visibleSections.length > 0

  return (
    <div className="promotion-detail-page">
      <nav className="promotion-breadcrumb" aria-label={t.breadcrumb}>
        <div className="promotion-container">
          <Link to="/">{t.home}</Link>
          <ChevronRight aria-hidden="true" />
          <Link to="/promotions">{t.promotionsLabel}</Link>
          <ChevronRight aria-hidden="true" />
          <span title={promo.title}>{promo.title}</span>
        </div>
      </nav>

      <header className="promotion-detail-hero">
        <div className="promotion-container promotion-detail-hero__grid">
          <div className="promotion-detail-hero__content">
            <div className="promotion-detail-badges">
              <span className={`promotion-status promotion-status--${promo.status}`}>{statusLabel}</span>
              {promo.discount_text && <span className="promotion-discount"><Tag />{promo.discount_text}</span>}
            </div>
            <h1>{promo.title}</h1>
            {promo.summary && <p className="promotion-detail-hero__summary">{promo.summary}</p>}
            <div className="promotion-detail-meta">
              {validityText && (
                <div><CalendarDays aria-hidden="true" /><span><strong>{t.validityLabel}</strong>{validityText}</span></div>
              )}
              {destinationText && (
                <div><MapPin aria-hidden="true" /><span><strong>{t.appliesAt}</strong>{destinationText}</span></div>
              )}
            </div>
            <div className="promotion-detail-hero__actions">
              {promo.booking_url && (
                <a href={promo.booking_url} target="_blank" rel="noreferrer" className="promotion-primary-action">
                  <Sparkles size={18} /> {t.bookNow} <ExternalLink size={15} />
                </a>
              )}
              <Link to="/promotions" className="promotion-secondary-action">{t.backToPromotions}</Link>
            </div>
          </div>

          <div className="promotion-detail-hero__visual">
            <SmartImage src={promo.image_url} alt="" variant="promotion" />
          </div>
        </div>
      </header>

      <div className="promotion-container promotion-detail-layout">
        <div className="promotion-detail-content">
          {promo.benefits?.length > 0 && (
            <section className="promotion-content-card promotion-benefits-section">
              <div className="promotion-section-heading">
                <span><Gift /></span>
                <div><p>{t.offerHighlights}</p><h2>{t.benefitsIncluded}</h2></div>
              </div>
              <div className="promotion-benefits-grid">
                {promo.benefits.map((benefit) => (
                  <article key={benefit.id} className="promotion-benefit-card">
                    <span className="promotion-benefit-card__check"><Check /></span>
                    <div>
                      <h3>{benefit.benefit_type.replaceAll('_', ' ')}</h3>
                      <p>{benefit.description || [benefit.value, benefit.unit].filter(Boolean).join(' ')}</p>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}

          {visibleSections.length > 0 && (
            <section className="promotion-content-card">
              <div className="promotion-section-heading">
                <span><FileText /></span>
                <div><p>{t.promotionOverview}</p><h2>{t.programDetails}</h2></div>
              </div>
              <div className="promotion-sections">
                {visibleSections.map((section) => (
                  <article key={section.id} className="promotion-copy-section">
                    {section.heading && <h3>{section.heading}</h3>}
                    <PlainText>{section.content}</PlainText>
                  </article>
                ))}
              </div>
            </section>
          )}

          {promo.blocks?.length > 0 && (
            <section className="promotion-content-card">
              <div className="promotion-section-heading">
                <span><Info /></span>
                <div><p>{t.structuredInformation}</p><h2>{t.offerDetails}</h2></div>
              </div>
              <div className="promotion-structured-content">
                {promo.blocks.map((block) => (
                  <StructuredBlock key={block.id} block={block} promotionTitle={promo.title} />
                ))}
              </div>
            </section>
          )}

          {!hasStructuredContent && promo.content && (
            <section className="promotion-content-card">
              <div className="promotion-section-heading">
                <span><FileText /></span>
                <div><p>{t.promotionOverview}</p><h2>{t.programDetails}</h2></div>
              </div>
              <PlainText>{promo.content}</PlainText>
            </section>
          )}

          {promo.steps?.length > 0 && (
            <section className="promotion-content-card">
              <div className="promotion-section-heading">
                <span><ShieldCheck /></span>
                <div><p>{t.howToUse}</p><h2>{t.redemptionSteps}</h2></div>
              </div>
              <TextList items={promo.steps} ordered />
            </section>
          )}

          {(promo.terms?.length > 0 || promo.combination_rules?.length > 0) && (
            <section className="promotion-content-card promotion-policy-card">
              <details open>
                <summary><FileText />{t.termsAndConditions}</summary>
                <div className="promotion-policy-card__body">
                  <TextList items={promo.terms} />
                  {promo.combination_rules?.length > 0 && (
                    <>
                      <h3>{t.combinationRules}</h3>
                      <TextList items={promo.combination_rules} />
                    </>
                  )}
                </div>
              </details>
            </section>
          )}
        </div>

        <aside className="promotion-detail-sidebar" aria-label={t.bookingAndSupport}>
          <div className="promotion-sidebar-sticky">
            {promo.codes?.length > 0 && (
              <section className="promotion-sidebar-card promotion-code-card">
                <div className="promotion-sidebar-card__heading">
                  <span><Tag /></span>
                  <div><p>{t.saveOffer}</p><h2>{t.promoCode}</h2></div>
                </div>
                <div className="promotion-codes">
                  {promo.codes.map((code) => (
                    <article key={code.id} className="promotion-code-item">
                      <button type="button" onClick={() => copyPromotionCode(code.code)} aria-label={`${t.copyCode} ${code.code}`}>
                        <span>{code.code}</span>
                        {copiedCode === code.code ? <Check /> : <Clipboard />}
                      </button>
                      {code.description && <p>{code.description}</p>}
                      {code.validity && <small><CalendarDays />{code.validity}</small>}
                      {code.conditions?.length > 0 && (
                        <ul>{code.conditions.map((condition, index) => <li key={`${code.id}-${index}`}>{condition}</li>)}</ul>
                      )}
                    </article>
                  ))}
                </div>
                <p className="promotion-copy-feedback" aria-live="polite">
                  {copiedCode ? t.codeCopied : ''}
                </p>
              </section>
            )}

            <section className="promotion-sidebar-card promotion-booking-card">
              <span className="promotion-booking-card__icon"><Sparkles /></span>
              <p>{t.readyForTrip}</p>
              <h2>{t.bookOfferDirectly}</h2>
              {validityText && <small><CalendarDays />{validityText}</small>}
              {promo.booking_url ? (
                <a href={promo.booking_url} target="_blank" rel="noreferrer" className="promotion-primary-action">
                  {t.bookNow} <ExternalLink size={15} />
                </a>
              ) : (
                <Link to="/support" className="promotion-primary-action">{t.contactSupport}</Link>
              )}
              {promo.terms_url && (
                <a href={promo.terms_url} target="_blank" rel="noreferrer" className="promotion-text-link">
                  <FileText />{t.readDetailedRules}<ExternalLink />
                </a>
              )}
            </section>

            {promo.contacts?.length > 0 && (
              <section className="promotion-sidebar-card promotion-contact-card">
                <h2><Phone />{t.supportContact}</h2>
                <TextList items={promo.contacts} />
              </section>
            )}

            <Link to="/support" className="promotion-support-link">
              <HelpCircle />
              <span><strong>{t.needMoreAdvice}</strong><small>{t.sendSupportRequest}</small></span>
              <ChevronRight />
            </Link>
          </div>
        </aside>
      </div>
    </div>
  )
}
