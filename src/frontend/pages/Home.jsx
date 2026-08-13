import { Link } from 'react-router-dom'
import { ArrowRight, Check, Sparkles } from 'lucide-react'
import DestinationCard from '../components/DestinationCard'
import HeroSearch from '../components/HeroSearch'
import HotelCard from '../components/HotelCard'
import { useLanguage } from '../context/LanguageContext'
import { COMBOS, DESTINATIONS, HOTELS } from '../data/mockData'
import '../styles/pages/Home.css'

const VI_COMBO_COPY = {
  'combo-1': {
    title: 'Gói 3N2Đ: Vé bay + biệt thự biển + golf chuẩn quốc tế',
    tag: 'Bán chạy',
    duration: '3 ngày / 2 đêm',
    includes: [
      'Vé máy bay khứ hồi',
      'Biệt thự biển riêng',
      '1 vòng golf 18 lỗ',
      'Buffet sáng hằng ngày',
      'Đưa đón sân bay nhanh',
    ],
  },
  'combo-2': {
    title: 'Kỳ nghỉ gia đình: 3N2Đ trọn gói + VinWonders không giới hạn',
    tag: 'Gia đình yêu thích',
    duration: '3 ngày / 2 đêm',
    includes: [
      'Biệt thự biển 2 phòng ngủ',
      'Ẩm thực trọn gói 3 bữa/ngày',
      'Vé VinWonders không giới hạn',
      'Vé cáp treo',
    ],
  },
  'combo-3': {
    title: 'Nghỉ dưỡng di sản & wellness: 2N1Đ villa + Akoya Spa',
    tag: 'Ưu đãi wellness',
    duration: '2 ngày / 1 đêm',
    includes: [
      'Garden Villa Suite',
      'Massage Akoya 60 phút',
      'Bữa tối organic tại nông trại',
      'Xe đưa đón phố cổ',
    ],
  },
}

function Home() {
  const { language, t } = useLanguage()
  const featuredHotels = HOTELS.filter((hotel) => hotel.featured)

  return (
    <main className="home-page">
      <HeroSearch />

      <section className="home-page__section">
        <div className="home-page__section-heading home-page__section-heading--center">
          <span className="home-page__eyebrow">{t.portfoliosEyebrow}</span>
          <h2>{t.destTitle}</h2>
          <p>{t.destSubtitle}</p>
        </div>

        <div className="home-page__destinations-grid">
          {DESTINATIONS.map((destination) => (
            <DestinationCard key={destination.id} destination={destination} />
          ))}
        </div>
      </section>

      <section className="home-page__section home-page__ai-section">
        <div className="home-page__ai-banner">
          <div className="home-page__ai-glow" />
          <div className="home-page__ai-content">
            <div className="home-page__ai-badge">
              <Sparkles className="home-page__ai-badge-icon" />
              <span>{t.aiConciergeBadge}</span>
            </div>

            <h3>{t.aiBannerTitle}</h3>
            <p>"{t.aiBannerDesc}"</p>

            <div className="home-page__ai-actions">
              <Link className="home-page__ai-primary" to="/chat">
                <Sparkles className="home-page__button-icon" />
                <span>{t.startAiChat}</span>
              </Link>
              <Link className="home-page__ai-secondary" to="/support">
                {t.navSupport}
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="home-page__section">
        <div className="home-page__split-heading">
          <div>
            <span className="home-page__eyebrow">{t.luxuryHospitality}</span>
            <h2>{t.featuredHotels}</h2>
          </div>

          <Link className="home-page__view-all" to="/search">
            <span>{t.viewAllResorts}</span>
            <ArrowRight className="home-page__view-all-icon" />
          </Link>
        </div>

        <div className="home-page__hotels-grid">
          {featuredHotels.map((hotel) => (
            <HotelCard key={hotel.id} hotel={hotel} />
          ))}
        </div>
      </section>

      <section className="home-page__offers-section">
        <div className="home-page__section home-page__offers-inner">
          <div className="home-page__section-heading home-page__section-heading--center">
            <span className="home-page__eyebrow">{t.travelPackagesEyebrow}</span>
            <h2>{t.offersTitle}</h2>
          </div>

          <div className="home-page__combos-grid">
            {COMBOS.map((combo) => {
              const localizedCombo =
                language === 'VI' ? VI_COMBO_COPY[combo.id] : null
              const title = localizedCombo?.title || combo.title
              const tag = localizedCombo?.tag || combo.tag
              const duration = localizedCombo?.duration || combo.duration
              const includes = localizedCombo?.includes || combo.includes

              return (
                <article className="home-page__combo-card" key={combo.id}>
                  <div className="home-page__combo-media">
                    <img src={combo.image} alt={title} />
                    <span className="home-page__combo-tag">{tag}</span>
                    <span className="home-page__combo-duration">{duration}</span>
                  </div>

                  <div className="home-page__combo-body">
                    <div>
                      <h4>{title}</h4>
                      <ul className="home-page__combo-includes">
                        {includes.map((item) => (
                          <li key={item}>
                            <Check className="home-page__combo-check" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="home-page__combo-footer">
                      <div>
                        <span className="home-page__combo-original">
                          {new Intl.NumberFormat('vi-VN').format(combo.originalPrice)} VND
                        </span>
                        <span className="home-page__combo-price">
                          {new Intl.NumberFormat('vi-VN').format(combo.offerPrice)} VND
                        </span>
                      </div>

                      <Link
                        className="home-page__combo-link"
                        to={`/chat?prompt=${encodeURIComponent(
                          `${t.bookWithAi}: ${title}`,
                        )}`}
                      >
                        {t.bookWithAi}
                      </Link>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        </div>
      </section>
    </main>
  )
}

export default Home
