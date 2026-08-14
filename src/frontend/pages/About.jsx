import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Building2,
  Award,
  Phone,
  MapPin,
  CreditCard,
  ShieldCheck,
  Sparkles,
  ChevronRight,
  Users,
  Trophy,
  HeartPulse,
  Briefcase,
  Search,
  RefreshCcw,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import AboutHotelsGrid from '../components/AboutHotelsGrid'
import aboutDataFallback from '../../data_crawl/About/vinpearl_about.json'
import { fetchAboutInfo } from '../services/api'
import '../styles/pages/About.css'

const VI_TRANSLATIONS = {
  headline: 'Trải nghiệm nghỉ dưỡng mang đậm bản sắc Việt Nam độc đáo',
  introduction:
    "Vinpearl là thương hiệu dịch vụ du lịch nghỉ dưỡng – giải trí lớn nhất Việt Nam với chuỗi resort, khách sạn, trung tâm hội nghị, nhà hàng và spa cao cấp tại các điểm đến hàng đầu. Tiên phong từ năm 2003, Vinpearl sở hữu 3 phức hợp du lịch quy mô hàng đầu Việt Nam, mang đến cho du khách những hành trình nghỉ dưỡng đáng nhớ và cá nhân hóa độc đáo.",
  packages: {
    'Family Beach Resorts':
      'Trải nghiệm & tận hưởng kỳ nghỉ tại thiên đường nghỉ dưỡng gia đình tại các bãi biển hàng đầu Việt Nam.',
    'Golf Stay & Play':
      'Nghỉ dưỡng & trải nghiệm đánh golf đỉnh cao giữa thiên nhiên nguyên sơ tại các sân golf tốt nhất khu vực Châu Á - Thái Bình Dương.',
    'Wellness & Retreat':
      'Thư giãn & tái tạo thân - tâm - trí với các liệu trình wellness tinh tế, nâng tầm khi hòa quyện cùng thiên nhiên, văn hóa & lịch sử Việt Nam.',
  },
  mice: {
    Almaz:
      'Trải nghiệm hội họp đẳng cấp kết hợp nghỉ dưỡng 5 sao và giải trí đỉnh cao. Cam kết mang tới sự thành công cho sự kiện với sự chuyên nghiệp và lòng hiếu khách Việt Nam.',
    'Vinpearl Convention Centers':
      'Chuỗi trung tâm hội nghị kiến trúc hiện đại, trang thiết bị tiên tiến và không gian đa năng cho các sự kiện sang trọng, đáp ứng quy mô lên tới hàng ngàn khách.',
  },
}

export default function About() {
  const { language, t } = useLanguage()
  const isVi = language === 'vi'

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const loadData = async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await fetchAboutInfo()
      setData(res)
    } catch (err) {
      console.error('Failed to fetch about info:', err)
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Derived data with fallback
  const org = data?.org || {
    headline: aboutDataFallback.headline,
    introduction: aboutDataFallback.introduction,
    address: aboutDataFallback.company_info.address,
    hotline: aboutDataFallback.company_info.hotline,
    account_holder: aboutDataFallback.company_info.account_holder,
    bank_account: aboutDataFallback.company_info.bank_account,
    bank: aboutDataFallback.company_info.bank,
    business_registration: aboutDataFallback.company_info.business_registration,
    issued_by: aboutDataFallback.company_info.issued_by,
  }

  const packages = data?.highlights?.packages || aboutDataFallback.signature_product_packages
  const mice = data?.highlights?.mice || aboutDataFallback.mice
  const meetingEvents = data?.highlights?.meeting_events || aboutDataFallback.meeting_and_events

  const headlineText = isVi ? VI_TRANSLATIONS.headline : org.headline
  const introText = isVi ? VI_TRANSLATIONS.introduction : org.introduction

  if (loading) {
    return (
      <div className="about-page" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: '#c9a45c', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <RefreshCcw className="animate-spin" size={20} />
          <span>Đang tải thông tin...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="about-page">
      {error && (
        <div style={{ background: '#fee2e2', color: '#991b1b', padding: '10px', textAlign: 'center', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '10px' }}>
          <span>Không thể tải dữ liệu mới nhất. Đang hiển thị bản lưu tạm.</span>
          <button onClick={loadData} style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '4px 10px', border: '1px solid #991b1b', borderRadius: '4px', background: 'transparent', color: '#991b1b', cursor: 'pointer' }}>
            <RefreshCcw size={14} /> Thử lại
          </button>
        </div>
      )}

      {/* Top Header Breadcrumb */}
      <section className="about-breadcrumb-bar">
        <div className="about-container">
          <nav className="about-breadcrumb">
            <Link to="/">{t.aboutHome}</Link>
            <ChevronRight className="about-breadcrumb__sep" />
            <span className="about-breadcrumb__current">
              {t.aboutVinpearl}
            </span>
          </nav>
        </div>
      </section>

      {/* Hero Section */}
      <section className="about-hero">
        <div className="about-hero__bg">
          <img
            src="https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=1920&q=80"
            alt={t.aboutHeroAlt}
          />
          <div className="about-hero__overlay" />
        </div>

        <div className="about-container about-hero__content">
          <div className="about-hero__badge">
            <Award className="about-hero__badge-icon" />
            <span>{t.aboutPioneer}</span>
          </div>

          <h1 className="about-hero__title">{headlineText}</h1>
          <p className="about-hero__intro">{introText}</p>

          <div className="about-hero__stats">
            <div className="about-stat-card">
              <div className="about-stat-card__number">2003</div>
              <div className="about-stat-card__label">
                {t.foundingYear}
              </div>
            </div>
            <div className="about-stat-card">
              <div className="about-stat-card__number">3</div>
              <div className="about-stat-card__label">
                {t.destinationComplexes}
              </div>
            </div>
            <div className="about-stat-card">
              <div className="about-stat-card__number">9+</div>
              <div className="about-stat-card__label">
                {t.luxuryHotelsResorts}
              </div>
            </div>
            <div className="about-stat-card">
              <div className="about-stat-card__number">5★</div>
              <div className="about-stat-card__label">
                {t.worldClassHospitality}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content Area */}
      <main className="about-container about-main">
        {/* Official Vinpearl Showcase Section */}
        <AboutHotelsGrid />

        {/* Signature Product Packages */}
        <section className="about-section about-packages-section">
          <div className="about-section__header">
            <span className="about-section__eyebrow">
              {t.signatureOfferings}
            </span>
            <h2>{t.signatureProductPackages}</h2>
            <p>{t.signaturePackagesDescription}</p>
          </div>

          <div className="about-packages-grid">
            {packages.map((pkg, idx) => {
              const desc =
                isVi && VI_TRANSLATIONS.packages[pkg.name]
                  ? VI_TRANSLATIONS.packages[pkg.name]
                  : pkg.description

              let IconComp = Users
              let bgGradient = 'linear-gradient(135deg, #0b2e3d 0%, #1e4e63 100%)'

              if (idx === 1) {
                IconComp = Trophy
                bgGradient = 'linear-gradient(135deg, #1b382b 0%, #2e5c47 100%)'
              } else if (idx === 2) {
                IconComp = HeartPulse
                bgGradient = 'linear-gradient(135deg, #3d1c2a 0%, #632d45 100%)'
              }

              return (
                <div key={pkg.name} className="about-package-card" style={{ background: bgGradient }}>
                  <div className="about-package-card__icon-wrap">
                    <IconComp className="about-package-card__icon" />
                  </div>
                  <h3>{pkg.name}</h3>
                  <p>{desc}</p>
                  <Link
                    to={`/chat?prompt=${encodeURIComponent(
                      `${t.inquirePackage}: ${pkg.name}`,
                    )}`}
                    className="about-package-card__btn"
                  >
                    <Sparkles className="about-package-card__btn-icon" />
                    <span>{t.inquireWithAi}</span>
                  </Link>
                </div>
              )
            })}
          </div>
        </section>

        {/* MICE & Events Section */}
        <section className="about-section about-mice-section">
          <div className="about-section__header">
            <span className="about-section__eyebrow">
              {t.meetingsCelebrations}
            </span>
            <h2>{t.miceEventVenues}</h2>
          </div>

          <div className="about-mice-grid">
            {/* Almaz Card */}
            {mice.map((item) => (
              <div key={item.name} className="about-mice-card">
                <div className="about-mice-card__header">
                  <Briefcase className="about-mice-card__icon" />
                  <div>
                    <span className="about-mice-card__tag">{t.miceEntertainment}</span>
                    <h3>{item.name}</h3>
                  </div>
                </div>
                <p>
                  {isVi && VI_TRANSLATIONS.mice[item.name]
                    ? VI_TRANSLATIONS.mice[item.name]
                    : item.description}
                </p>
                <Link to="/support" className="about-mice-card__action">
                  <span>{t.bookMiceEvent}</span>
                  <ChevronRight size={16} />
                </Link>
              </div>
            ))}

            {/* Convention Centers Card */}
            {meetingEvents.map((item) => (
              <div key={item.name} className="about-mice-card">
                <div className="about-mice-card__header">
                  <Building2 className="about-mice-card__icon" />
                  <div>
                    <span className="about-mice-card__tag">{t.conventionGala}</span>
                    <h3>{item.name}</h3>
                  </div>
                </div>
                <p>
                  {isVi && VI_TRANSLATIONS.mice[item.name]
                    ? VI_TRANSLATIONS.mice[item.name]
                    : item.description}
                </p>
                <Link to="/support" className="about-mice-card__action">
                  <span>{t.requestEventQuote}</span>
                  <ChevronRight size={16} />
                </Link>
              </div>
            ))}
          </div>
        </section>

        {/* Company Legal Information */}
        <section className="about-section about-company-section">
          <div className="about-company-box">
            <div className="about-company-box__title-row">
              <ShieldCheck className="about-company-box__shield" />
              <div>
                <h2>{t.corporateLegalInfo}</h2>
                <p>{org.account_holder}</p>
              </div>
            </div>

            <div className="about-company-grid">
              <div className="about-company-item">
                <MapPin className="about-company-item__icon" />
                <div>
                  <strong>{t.registeredAddress}</strong>
                  <p>{org.address}</p>
                </div>
              </div>

              <div className="about-company-item">
                <Phone className="about-company-item__icon" />
                <div>
                  <strong>{t.hotline}</strong>
                  <p>{org.hotline}</p>
                </div>
              </div>

              {org.bank_account && org.account_holder && org.bank && (
                <div className="about-company-item">
                  <CreditCard className="about-company-item__icon" />
                  <div>
                    <strong>{t.bankAccountDetails}</strong>
                    <p>
                      {t.account}: <strong>{org.bank_account}</strong>
                    </p>
                    <p>{org.bank}</p>
                  </div>
                </div>
              )}

              <div className="about-company-item">
                <Building2 className="about-company-item__icon" />
                <div>
                  <strong>{t.businessRegistration}</strong>
                  <p>{org.business_registration}</p>
                  {org.issued_by && (
                    <p>
                      {t.issuedBy}: {org.issued_by}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* AI Travel Assistance Banner */}
        <section className="about-ai-cta">
          <div className="about-ai-cta__inner">
            <div className="about-ai-cta__sparkle">
              <Sparkles size={28} />
            </div>
            <h2>{t.customRecommendations}</h2>
            <p>{t.customRecommendationsDesc}</p>
            <div className="about-ai-cta__actions">
              <Link to="/chat" className="about-ai-cta__primary">
                <Sparkles size={18} />
                <span>{t.chatWithAi}</span>
              </Link>
              <Link to="/search" className="about-ai-cta__secondary">
                <Search size={18} />
                <span>{t.browseAllResorts}</span>
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
