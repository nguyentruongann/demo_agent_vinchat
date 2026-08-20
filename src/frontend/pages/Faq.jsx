import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  RefreshCcw,
  Search,
  X,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { fetchFaqs } from '../services/api'
import FaqList from '../components/FaqList'
import '../styles/pages/Faq.css'

const DEBOUNCE_MS = 300
const PAGE_SIZE = 20

function Skeleton() {
  return (
    <div className="faq-skeleton" aria-busy="true">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="faq-skeleton__item" />
      ))}
    </div>
  )
}

export default function Faq() {
  const { t } = useLanguage()
  const [searchParams, setSearchParams] = useSearchParams()

  // URL state
  const urlQ = searchParams.get('q') || ''
  const urlCategory = searchParams.get('category') || ''
  const urlPage = Number(searchParams.get('page')) || 1

  // Local state
  const [inputValue, setInputValue] = useState(urlQ)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const debounceRef = useRef(null)

  // ── URL updater (doesn't reset page on search change) ───
  const updateParams = useCallback(
    (updates) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        for (const [key, value] of Object.entries(updates)) {
          if (value) {
            next.set(key, value)
          } else {
            next.delete(key)
          }
        }
        // Reset page to 1 on filter/search change
        if ('q' in updates || 'category' in updates) {
          next.delete('page')
        }
        return next
      }, { replace: true })
    },
    [setSearchParams],
  )

  // ── Fetch ──────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const result = await fetchFaqs({
        q: urlQ || undefined,
        category: urlCategory || undefined,
        page: urlPage,
        pageSize: PAGE_SIZE,
      })
      setData(result)
    } catch (err) {
      console.error('Failed to fetch FAQs:', err)
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [urlQ, urlCategory, urlPage])

  useEffect(() => {
    loadData()
  }, [loadData])

  // ── Debounced search ───────────────────────────────────────
  const handleSearchInput = (e) => {
    const value = e.target.value
    setInputValue(value)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      updateParams({ q: value.trim() })
    }, DEBOUNCE_MS)
  }

  const clearSearch = () => {
    setInputValue('')
    clearTimeout(debounceRef.current)
    updateParams({ q: '' })
  }

  // ── Category filter ────────────────────────────────────────
  const handleCategory = (cat) => {
    updateParams({ category: cat === urlCategory ? '' : cat })
  }

  // ── Pagination ─────────────────────────────────────────────
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0
  const canPrev = urlPage > 1
  const canNext = urlPage < totalPages

  const goPage = (p) => {
    updateParams({ page: String(p) })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // ── Categories with "All" ──────────────────────────────────
  const categories = useMemo(() => {
    if (!data?.categories) return []
    return data.categories
  }, [data])

  const allCount = useMemo(() => {
    if (!categories.length) return 0
    return categories.reduce((sum, c) => sum + c.count, 0)
  }, [categories])

  return (
    <div className="faq-page">
      {/* Breadcrumb */}
      <section className="faq-breadcrumb-bar">
        <div className="faq-container">
          <nav className="faq-breadcrumb" aria-label={t.breadcrumb || 'Breadcrumb'}>
            <Link to="/">{t.home || 'Home'}</Link>
            <ChevronRight className="faq-breadcrumb__sep" />
            <span className="faq-breadcrumb__current">
              {t.faqTitle || 'FAQs'}
            </span>
          </nav>
        </div>
      </section>

      {/* Hero */}
      <section className="faq-hero">
        <div className="faq-container">
          <span className="faq-hero__badge">
            <HelpCircle size={16} />
            <span>{t.faqBadge || 'Knowledge Center'}</span>
          </span>
          <h1>{t.faqHeading || 'Frequently Asked Questions'}</h1>
          <p>{t.faqSubheading || 'Find answers about our resorts, booking policies, and travel services.'}</p>
        </div>
      </section>

      {/* Search Bar (floating) */}
      <div className="faq-container">
        <div className="faq-search-bar">
          <Search className="faq-search-bar__icon" aria-hidden="true" />
          <input
            className="faq-search-bar__input"
            type="search"
            placeholder={t.faqSearchPlaceholder || 'Search questions and answers...'}
            value={inputValue}
            onChange={handleSearchInput}
            aria-label={t.faqSearchPlaceholder || 'Search questions and answers'}
          />
          {inputValue && (
            <button
              className="faq-search-bar__clear"
              onClick={clearSearch}
              type="button"
              aria-label={t.faqClearSearch || 'Clear search'}
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="faq-container faq-main">
        {/* Mobile Chips */}
        <div className="faq-chips">
          <button
            className={`faq-chip${!urlCategory ? ' faq-chip--active' : ''}`}
            onClick={() => handleCategory('')}
            type="button"
          >
            {t.faqAllCategories || 'All'} ({allCount})
          </button>
          {categories.map((cat) => (
            <button
              key={cat.name}
              className={`faq-chip${urlCategory === cat.name ? ' faq-chip--active' : ''}`}
              onClick={() => handleCategory(cat.name)}
              type="button"
            >
              {cat.name} ({cat.count})
            </button>
          ))}
        </div>

        <div className="faq-layout">
          {/* Desktop Sidebar */}
          <aside className="faq-sidebar">
            <h3 className="faq-sidebar__title">
              {t.faqCategories || 'Categories'}
            </h3>
            <div className="faq-sidebar__list">
              <button
                className={`faq-sidebar__item${!urlCategory ? ' faq-sidebar__item--active' : ''}`}
                onClick={() => handleCategory('')}
                type="button"
              >
                <span>{t.faqAllCategories || 'All'}</span>
                <span className="faq-sidebar__count">{allCount}</span>
              </button>
              {categories.map((cat) => (
                <button
                  key={cat.name}
                  className={`faq-sidebar__item${urlCategory === cat.name ? ' faq-sidebar__item--active' : ''}`}
                  onClick={() => handleCategory(cat.name)}
                  type="button"
                >
                  <span>{cat.name}</span>
                  <span className="faq-sidebar__count">{cat.count}</span>
                </button>
              ))}
            </div>
          </aside>

          {/* FAQ Content */}
          <div className="faq-content">
            {loading ? (
              <Skeleton />
            ) : error ? (
              <div className="faq-error">
                <h3 className="faq-error__title">
                  {t.faqErrorTitle || 'Unable to load FAQs'}
                </h3>
                <p className="faq-error__text">
                  {t.faqErrorText || 'Please check the connection and try again.'}
                </p>
                <button className="faq-error__btn" onClick={loadData} type="button">
                  <RefreshCcw size={14} />
                  <span>{t.tryAgain || 'Try again'}</span>
                </button>
              </div>
            ) : (
              <>
                <FaqList
                  items={data?.items || []}
                  emptyText={t.faqEmpty || 'No matching questions found. Try a different search or category.'}
                />

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="faq-pagination">
                    <button
                      className="faq-pagination__btn"
                      onClick={() => goPage(urlPage - 1)}
                      disabled={!canPrev}
                      type="button"
                      aria-label={t.faqPrevPage || 'Previous page'}
                    >
                      <ChevronLeft size={16} />
                      <span>{t.faqPrev || 'Previous'}</span>
                    </button>
                    <span className="faq-pagination__info">
                      {urlPage} / {totalPages}
                    </span>
                    <button
                      className="faq-pagination__btn"
                      onClick={() => goPage(urlPage + 1)}
                      disabled={!canNext}
                      type="button"
                      aria-label={t.faqNextPage || 'Next page'}
                    >
                      <span>{t.faqNext || 'Next'}</span>
                      <ChevronRight size={16} />
                    </button>
                  </div>
                )}

                {/* Result count */}
                {data && (
                  <p style={{ textAlign: 'center', color: '#94a3b8', fontSize: '13px', marginTop: '16px' }}>
                    {data.total} {t.faqResultCount || 'questions found'}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
