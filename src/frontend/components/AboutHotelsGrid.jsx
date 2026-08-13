import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, ArrowUpRight, MapPin } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import aboutData from '../../data_crawl/About/vinpearl_about.json'
import { HOTEL_IMAGES } from '../data/mediaAssets'
import '../styles/components/AboutHotelsGrid.css'

const HOTEL_DESTINATIONS = {
  'VinHolidays Fiesta Phu Quoc': { key: 'phu-quoc', name: 'Phú Quốc' },
  'Vinpearl Wonderworld Phu Quoc': { key: 'phu-quoc', name: 'Phú Quốc' },
  'Vinpearl Resort & Spa Phu Quoc': { key: 'phu-quoc', name: 'Phú Quốc' },
  'Vinpearl Resort & Spa Nha Trang Bay': { key: 'nha-trang', name: 'Nha Trang' },
  'Vinpearl Resort Nha Trang': { key: 'nha-trang', name: 'Nha Trang' },
  'Vinpearl Luxury Nha Trang': { key: 'nha-trang', name: 'Nha Trang' },
  'Vinpearl Beachfront Nha Trang': { key: 'nha-trang', name: 'Nha Trang' },
  'Vinpearl Resort & Golf Nam Hoi An': { key: 'hoi-an', name: 'Nam Hội An' },
  'Vinpearl Resort & Spa Ha Long': { key: 'ha-long', name: 'Hạ Long' },
}

const VI_HOTELS_DESC = {
  'VinHolidays Fiesta Phu Quoc':
    'Located at the heart of the Grand World Complex and adjacent to Vinpearl Phu Quoc Cluster, Vinholidays Fiesta Phu Quoc inherits a 5-star ecosystem with diverse entertainment and shopping, which bring the majority of Vietnamese people closer to their dream vacation at one of the most beautiful destinations in the country.',
  'Vinpearl Wonderworld Phu Quoc':
    'Vinpearl Wonderworld Phu Quoc features exclusively villas that focus on the privacy of all guests, and intimate touch with nature, from lush gardens to private, expansive beaches. The resort is also within a close vicinity with an international-standard golf course in the midst of an old-growth forest, which brings a unique experience to any visitor.',
  'Vinpearl Resort & Spa Phu Quoc':
    'Welcoming guests with its bright red tiles, Indochine-style architecture, and an outdoor swimming pool of nearly 5,000m2, Vinpearl Resort & Spa Phu Quoc offers a fun-filled journey with typical natural flavors of the pearl island. Must-try experiences here include savoring a seafood buffet with magnificent sunset views at Pepper Restaurant by the sea, enjoying a unique Balinese massage at spa huts above the lake, and conquering thousands of entertainment experiences at VinWonders right nearby.',
  'Vinpearl Resort & Spa Nha Trang Bay':
    'On the "paradise island" of Hon Tre, Vinpearl Resort & Spa Nha Trang Bay is always eye catching with its white bow-shaped architecture and distinctive pure vibe. Located behind the colorful bougainvillea roads, Vinpearl Resort & Spa Nha Trang Bay welcomes guests with a beautiful private beach, a large outdoor swimming pool and tailor-made services for a relaxing family vacation.',
  'Vinpearl Resort Nha Trang':
    'Vinpearl Resort Nha Trang is a peaceful haven for those who love to relax and take care of health, a place to restore energy, a place to mark milestones of happiness and success, such as a dream wedding or a classy meeting.',
  'Vinpearl Luxury Nha Trang':
    'A serene oasis away from the hustle and bustle of city life, Vinpearl Luxury Nha Trang is a heaven for bespoke guests, amidst tropical gardens, expansive coast line and 84 villas embodying exclusivity and rejuvenation. An ideal space to reconnect and cherish every single moment with loved ones, be it a cozy family reunion or a romantic getaway.',
  'Vinpearl Beachfront Nha Trang':
    'Vinpearl Beachfront Nha Trang features sea-view hotel apartments showcasing not only the comfort and convenience Vinpearl is famous for, but full and convenient access to the sunny beach of Nha Trang Bay. This is a new, luxury destination where guests will enjoy a busy shopping center, luxurious restaurants, an outdoor swimming pool with panoramic ocean views, and first-class meeting spaces.',
  'Vinpearl Resort & Golf Nam Hoi An':
    'Vinpearl Resort & Golf Nam Hoi An is the perfect destination for a family vacation with cultural experiences and edutainment products exclusively for children, and also ideal for MICE or reward tourism thanks to its excellent service and a system of superior meeting rooms to cater for events of up to 600 guests.',
  'Vinpearl Resort & Spa Ha Long':
    'As the first & only resort in the North of Vietnam built entirely on the sea, Vinpearl Resort & Spa Ha Long makes an unforgettable impression with 3 private beaches, green premises and an outdoor swimming pool of up to 1,200m2.',
}

export default function AboutHotelsGrid() {
  const { language } = useLanguage()
  const isVi = language === 'VI'
  const [currentIndex, setCurrentIndex] = useState(0)

  const hotels = aboutData.hotels_and_resorts
  const total = hotels.length

  const handlePrev = () => {
    setCurrentIndex((prev) => (prev === 0 ? total - 1 : prev - 1))
  }

  const handleNext = () => {
    setCurrentIndex((prev) => (prev === total - 1 ? 0 : prev + 1))
  }

  const currentHotel = hotels[currentIndex]
  const imgUrl = HOTEL_IMAGES[currentHotel.name] || HOTEL_IMAGES['VinHolidays Fiesta Phu Quoc']
  const destInfo = HOTEL_DESTINATIONS[currentHotel.name] || { name: 'Việt Nam' }
  const description =
    isVi && VI_HOTELS_DESC[currentHotel.name]
      ? VI_HOTELS_DESC[currentHotel.name]
      : currentHotel.description

  return (
    <section className="vp-showcase-section">
      <div className="vp-showcase-container">
        {/* Main Section Title */}
        <h2 className="vp-showcase-main-title">Hotels & Resorts</h2>

        {/* 2-Column Split Showcase Box */}
        <div className="vp-showcase-card">
          {/* Left Column: Hero Image */}
          <div className="vp-showcase-media">
            <img
              src={imgUrl}
              alt={currentHotel.name}
              key={currentHotel.name}
              className="vp-showcase-img"
            />
            <span className="vp-showcase-badge">
              <MapPin size={13} className="vp-showcase-badge-icon" />
              {destInfo.name}
            </span>
          </div>

          {/* Right Column: Controls, Counter, Title & Description */}
          <div className="vp-showcase-info">
            {/* Top Counter & Arrows Bar */}
            <div className="vp-showcase-top-bar">
              <div className="vp-showcase-controls">
                <button
                  type="button"
                  className="vp-showcase-arrow-btn"
                  onClick={handlePrev}
                  aria-label="Previous resort"
                >
                  <ArrowLeft size={18} />
                </button>

                <span className="vp-showcase-counter">
                  {currentIndex + 1} / {total}
                </span>

                <button
                  type="button"
                  className="vp-showcase-arrow-btn"
                  onClick={handleNext}
                  aria-label="Next resort"
                >
                  <ArrowRight size={18} />
                </button>
              </div>
            </div>

            <div className="vp-showcase-divider" />

            {/* Hotel Title & Paragraph Content */}
            <div className="vp-showcase-content">
              <h3 className="vp-showcase-hotel-title">{currentHotel.name}</h3>
              <p className="vp-showcase-hotel-desc">{description}</p>
            </div>

          </div>
        </div>

        {/* Bottom Thumbnail Strip */}
        <div className="vp-showcase-thumbs">
          {hotels.map((h, idx) => (
            <button
              key={h.name}
              type="button"
              className={`vp-showcase-thumb-item ${
                idx === currentIndex ? 'vp-showcase-thumb-item--active' : ''
              }`}
              onClick={() => setCurrentIndex(idx)}
            >
              <img src={HOTEL_IMAGES[h.name]} alt={h.name} />
              <span className="vp-showcase-thumb-title">{h.name}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
