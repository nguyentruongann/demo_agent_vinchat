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
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import AboutHotelsGrid from '../components/AboutHotelsGrid'
import aboutData from '../../data_crawl/About/vinpearl_about.json'
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
  const { language } = useLanguage()
  const isVi = language === 'VI'

  const headlineText = isVi ? VI_TRANSLATIONS.headline : aboutData.headline
  const introText = isVi ? VI_TRANSLATIONS.introduction : aboutData.introduction

  return (
    <div className="about-page">
      {/* Top Header Breadcrumb */}
      <section className="about-breadcrumb-bar">
        <div className="about-container">
          <nav className="about-breadcrumb">
            <Link to="/">{isVi ? 'Trang chủ' : 'Home'}</Link>
            <ChevronRight className="about-breadcrumb__sep" />
            <span className="about-breadcrumb__current">
              {isVi ? 'Giới thiệu về Vinpearl' : 'About Vinpearl'}
            </span>
          </nav>
        </div>
      </section>

      {/* Hero Section */}
      <section className="about-hero">
        <div className="about-hero__bg">
          <img
            src="https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=1920&q=80"
            alt="Vinpearl Hero"
          />
          <div className="about-hero__overlay" />
        </div>

        <div className="about-container about-hero__content">
          <div className="about-hero__badge">
            <Award className="about-hero__badge-icon" />
            <span>{isVi ? 'Thương hiệu du lịch hàng đầu Việt Nam từ 2003' : 'Vietnam Premier Hospitality Pioneer Since 2003'}</span>
          </div>

          <h1 className="about-hero__title">{headlineText}</h1>
          <p className="about-hero__intro">{introText}</p>

          <div className="about-hero__stats">
            <div className="about-stat-card">
              <div className="about-stat-card__number">2003</div>
              <div className="about-stat-card__label">
                {isVi ? 'Năm thành lập' : 'Founding Year'}
              </div>
            </div>
            <div className="about-stat-card">
              <div className="about-stat-card__number">3</div>
              <div className="about-stat-card__label">
                {isVi ? 'Phức hợp du lịch độc đáo' : 'Destination Complexes'}
              </div>
            </div>
            <div className="about-stat-card">
              <div className="about-stat-card__number">9+</div>
              <div className="about-stat-card__label">
                {isVi ? 'Resort & Khách sạn 5 sao' : 'Luxury Hotels & Resorts'}
              </div>
            </div>
            <div className="about-stat-card">
              <div className="about-stat-card__number">5★</div>
              <div className="about-stat-card__label">
                {isVi ? 'Dịch vụ tiêu chuẩn quốc tế' : 'World-Class Hospitality'}
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
              {isVi ? 'Trải nghiệm đỉnh cao' : 'Signature Offerings'}
            </span>
            <h2>{isVi ? 'Gói Sản phẩm & Dịch vụ Đặc sắc' : 'Signature Product Packages'}</h2>
            <p>
              {isVi
                ? 'Những gói trải nghiệm nghỉ dưỡng được thiết kế riêng đáp ứng mọi nhu cầu của du khách.'
                : 'Curated experience packages tailored to elevate your luxury getaway.'}
            </p>
          </div>

          <div className="about-packages-grid">
            {aboutData.signature_product_packages.map((pkg, idx) => {
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
                      `${isVi ? 'Tư vấn gói' : 'Inquire package'}: ${pkg.name}`,
                    )}`}
                    className="about-package-card__btn"
                  >
                    <Sparkles className="about-package-card__btn-icon" />
                    <span>{isVi ? 'Tư vấn với AI' : 'Inquire with AI'}</span>
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
              {isVi ? 'Hội họp & Sự kiện' : 'Meetings & Celebrations'}
            </span>
            <h2>{isVi ? 'Trung tâm Hội nghị & MICE Đẳng cấp' : 'MICE & Event Venues'}</h2>
          </div>

          <div className="about-mice-grid">
            {/* Almaz Card */}
            {aboutData.mice.map((item) => (
              <div key={item.name} className="about-mice-card">
                <div className="about-mice-card__header">
                  <Briefcase className="about-mice-card__icon" />
                  <div>
                    <span className="about-mice-card__tag">MICE & Entertainment</span>
                    <h3>{item.name}</h3>
                  </div>
                </div>
                <p>
                  {isVi && VI_TRANSLATIONS.mice[item.name]
                    ? VI_TRANSLATIONS.mice[item.name]
                    : item.description}
                </p>
                <Link to="/support" className="about-mice-card__action">
                  <span>{isVi ? 'Liên hệ đặt sự kiện' : 'Book MICE Event'}</span>
                  <ChevronRight size={16} />
                </Link>
              </div>
            ))}

            {/* Convention Centers Card */}
            {aboutData.meeting_and_events.map((item) => (
              <div key={item.name} className="about-mice-card">
                <div className="about-mice-card__header">
                  <Building2 className="about-mice-card__icon" />
                  <div>
                    <span className="about-mice-card__tag">Convention & Gala</span>
                    <h3>{item.name}</h3>
                  </div>
                </div>
                <p>
                  {isVi && VI_TRANSLATIONS.mice[item.name]
                    ? VI_TRANSLATIONS.mice[item.name]
                    : item.description}
                </p>
                <Link to="/support" className="about-mice-card__action">
                  <span>{isVi ? 'Yêu cầu báo giá hội nghị' : 'Request Event Quote'}</span>
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
                <h2>{isVi ? 'Thông tin Doanh nghiệp & Pháp lý' : 'Corporate & Legal Information'}</h2>
                <p>{aboutData.company_info.account_holder}</p>
              </div>
            </div>

            <div className="about-company-grid">
              <div className="about-company-item">
                <MapPin className="about-company-item__icon" />
                <div>
                  <strong>{isVi ? 'Địa chỉ trụ sở' : 'Registered Address'}</strong>
                  <p>{aboutData.company_info.address}</p>
                </div>
              </div>

              <div className="about-company-item">
                <Phone className="about-company-item__icon" />
                <div>
                  <strong>{isVi ? 'Tổng đài chăm sóc khách hàng' : 'Hotline'}</strong>
                  <p>{aboutData.company_info.hotline}</p>
                </div>
              </div>

              <div className="about-company-item">
                <CreditCard className="about-company-item__icon" />
                <div>
                  <strong>{isVi ? 'Thông tin chuyển khoản' : 'Bank Account Details'}</strong>
                  <p>
                    {isVi ? 'Số TK' : 'Account'}: <strong>{aboutData.company_info.bank_account}</strong>
                  </p>
                  <p>{aboutData.company_info.bank}</p>
                </div>
              </div>

              <div className="about-company-item">
                <Building2 className="about-company-item__icon" />
                <div>
                  <strong>{isVi ? 'Đăng ký kinh doanh' : 'Business Registration'}</strong>
                  <p>{aboutData.company_info.business_registration}</p>
                  <p>
                    {isVi ? 'Nơi cấp' : 'Issued by'}: {aboutData.company_info.issued_by}
                  </p>
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
            <h2>
              {isVi
                ? 'Bạn cần tư vấn chi tiết về Vinpearl?'
                : 'Need Custom Vinpearl Recommendations?'}
            </h2>
            <p>
              {isVi
                ? 'Hỏi trợ lý VinTravel AI Concierge để nhận tư vấn lịch trình 3N2Đ, bảng giá phòng và ưu đãi mới nhất.'
                : 'Ask VinTravel AI Concierge for personalized 3D2N itineraries, suite availability, and special rates.'}
            </p>
            <div className="about-ai-cta__actions">
              <Link to="/chat" className="about-ai-cta__primary">
                <Sparkles size={18} />
                <span>{isVi ? 'Trò chuyện với AI' : 'Chat with AI Concierge'}</span>
              </Link>
              <Link to="/search" className="about-ai-cta__secondary">
                <Search size={18} />
                <span>{isVi ? 'Xem tất cả Resort' : 'Browse All Resorts'}</span>
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
