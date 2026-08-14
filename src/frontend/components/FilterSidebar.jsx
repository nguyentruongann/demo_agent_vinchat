import { Filter, RotateCcw } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/FilterSidebar.css'

function FilterSidebar({
  selectedDest,
  setSelectedDest,
  selectedType,
  setSelectedType,
  maxPrice,
  setMaxPrice,
  resetFilters,
  destinations = [],
}) {
  const { t } = useLanguage()
  const propertyTypes = ['all', 'resort', 'hotel']

  return (
    <aside className="filter-sidebar">
      <div className="filter-sidebar__header">
        <div className="filter-sidebar__title">
          <Filter className="filter-sidebar__title-icon" />
          <span>{t.filterTitle}</span>
        </div>
        <button
          className="filter-sidebar__reset"
          type="button"
          onClick={resetFilters}
        >
          <RotateCcw className="filter-sidebar__reset-icon" />
          <span>{t.reset}</span>
        </button>
      </div>

      <div className="filter-sidebar__group">
        <label className="filter-sidebar__label" htmlFor="destination-filter">
          {t.searchDest}
        </label>
        <select
          className="filter-sidebar__select"
          id="destination-filter"
          value={selectedDest}
          onChange={(event) => setSelectedDest(event.target.value)}
        >
          <option value="all">{t.allDestinations}</option>
          {destinations.map((destination) => (
            <option key={destination.id} value={destination.id}>
              {destination.name}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-sidebar__group">
        <span className="filter-sidebar__label">{t.accType}</span>
        <div className="filter-sidebar__radio-list">
          {propertyTypes.map((type) => (
            <label
              className={`filter-sidebar__radio ${
                selectedType === type ? 'filter-sidebar__radio--active' : ''
              }`}
              key={type}
            >
              <input
                className="filter-sidebar__radio-input"
                type="radio"
                name="propertyType"
                checked={selectedType === type}
                onChange={() => setSelectedType(type)}
              />
              <span>{type === 'all' ? t.allTypes : t[type]}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="filter-sidebar__group filter-sidebar__group--price">
        <div className="filter-sidebar__price-header">
          <label className="filter-sidebar__label" htmlFor="price-filter">
            {t.priceRange}
          </label>
          <span className="filter-sidebar__price-value">
            ${maxPrice} USD
          </span>
        </div>
        <input
          className="filter-sidebar__range"
          id="price-filter"
          type="range"
          min="50"
          max="500"
          step="10"
          value={maxPrice}
          onChange={(event) => setMaxPrice(Number(event.target.value))}
        />
        <div className="filter-sidebar__range-labels">
          <span>$50</span>
          <span>$500</span>
        </div>
      </div>
    </aside>
  )
}

export default FilterSidebar
