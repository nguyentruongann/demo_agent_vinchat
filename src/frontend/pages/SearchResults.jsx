import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Building2, SearchX, Sparkles } from 'lucide-react'
import FilterSidebar from '../components/FilterSidebar'
import HotelCard from '../components/HotelCard'
import { useLanguage } from '../context/LanguageContext'
import { DESTINATIONS } from '../data/mockData'
import { fetchHotels } from '../services/api'
import '../styles/pages/SearchResults.css'

function SearchResults() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [destFilter, setDestFilter] = useState(
    searchParams.get('destination') || 'all',
  )
  const [typeFilter, setTypeFilter] = useState(searchParams.get('type') || 'all')
  const [maxPrice, setMaxPrice] = useState(
    searchParams.get('maxPrice') ? Number(searchParams.get('maxPrice')) : 25000000,
  )
  const [hotels, setHotels] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let isMounted = true
    setLoading(true)

    fetchHotels({
      destination: destFilter,
      type: typeFilter,
      maxPrice,
    }).then((data) => {
      if (isMounted) {
        setHotels(data)
        setLoading(false)
      }
    })

    return () => {
      isMounted = false
    }
  }, [destFilter, typeFilter, maxPrice])

  function handleReset() {
    setDestFilter('all')
    setTypeFilter('all')
    setMaxPrice(25000000)
    setSearchParams({})
  }

  const selectedDestObj = DESTINATIONS.find((item) => item.id === destFilter)

  return (
    <main className="search-results-page">
      <div className="search-results-page__container">
        <section className="search-results-page__heading">
          <div className="search-results-page__eyebrow">
            <Building2 className="search-results-page__eyebrow-icon" />
            <span>{t.portfolioEyebrow}</span>
          </div>
          <h1>
            {selectedDestObj
              ? `${selectedDestObj.name} ${t.searchHeadingSuffix}`
              : t.navHotels}
          </h1>
          <p>
            {t.foundPrefix}{' '}
            <span className="search-results-page__count">{hotels.length}</span>{' '}
            {t.searchFoundText}
          </p>
        </section>

        <section className="search-results-page__layout">
          <aside className="search-results-page__sidebar">
            <FilterSidebar
              selectedDest={destFilter}
              setSelectedDest={setDestFilter}
              selectedType={typeFilter}
              setSelectedType={setTypeFilter}
              maxPrice={maxPrice}
              setMaxPrice={setMaxPrice}
              resetFilters={handleReset}
            />
          </aside>

          <div className="search-results-page__content">
            {loading ? (
              <div className="search-results-page__grid">
                {[1, 2, 3, 4].map((item) => (
                  <div className="search-results-page__skeleton" key={item} />
                ))}
              </div>
            ) : hotels.length > 0 ? (
              <div className="search-results-page__grid">
                {hotels.map((hotel) => (
                  <HotelCard key={hotel.id} hotel={hotel} />
                ))}
              </div>
            ) : (
              <div className="search-results-page__empty">
                <div className="search-results-page__empty-icon">
                  <SearchX />
                </div>
                <h3>{t.noMatchesTitle}</h3>
                <p>{t.noMatchesDesc}</p>
                <button
                  className="search-results-page__empty-button"
                  type="button"
                  onClick={() =>
                    navigate(
                      '/chat?prompt=Can%20you%20help%20me%20find%20a%20resort%20within%20my%20custom%20budget%3F',
                    )
                  }
                >
                  <Sparkles className="search-results-page__empty-button-icon" />
                  <span>{t.askAiCustomRecommendation}</span>
                </button>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}

export default SearchResults
