import { Link } from 'react-router-dom'
import {
  Mail,
  MapPin,
  Phone,
  Facebook,
  Youtube,
  Instagram
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/Footer.css'

const VINPEARL_LOGO_URL =
  'https://statics.vinpearl.com/files/images/new-homepage/vp-logo-blue.svg'
const QR_CODE_URL = 'https://statics.vinpearl.com/QR-code.png' // fallback URL
const APP_STORE_URL = 'https://statics.vinpearl.com/app-store.svg'
const GOOGLE_PLAY_URL = 'https://statics.vinpearl.com/google-play.svg'
const BCT_URL = 'https://statics.vinpearl.com/bocongthuong.png'

function Footer() {
  const { t } = useLanguage()

  return (
    <footer className="footer">
      <div className="footer__container">
        <div className="footer__grid">
          {/* Column 1: Brand & Contact */}
          <section className="footer__brand-column">
            <div className="footer__brand">
              <img className="footer__brand-logo" src={VINPEARL_LOGO_URL} alt="Vinpearl" />
            </div>
            
            <div className="footer__section">
              <div className="footer__contact-item">
                <MapPin className="footer__contact-icon" />
                <span>Đảo Hòn Tre, Phường Vĩnh Nguyên, Tỉnh Khánh Hòa, Việt Nam</span>
              </div>
              <div className="footer__contact-item">
                <Mail className="footer__contact-icon" />
                <a href="mailto:callcenter@vinpearl.com">callcenter@vinpearl.com</a>
              </div>
              <div className="footer__contact-item">
                <Phone className="footer__contact-icon" />
                <a href="tel:1900232389">1900 23 23 89 (nhánh 3)</a>
              </div>
            </div>

            <div className="footer__info-block">
              <p>Chủ tài khoản:</p>
              <p>Công ty cổ phần Vinpearl</p>
              <p>Tài khoản ngân hàng số: 9124412488166 (VND)</p>
              <p>Ngân hàng thương mại cổ phần Kỹ Thương Việt Nam (Techcombank) - Hội sở</p>
            </div>

            <div className="footer__info-block">
              <p>Số ĐKKD:</p>
              <p>4200456848. ĐK lần đầu 26/7/2006.</p>
              <p>ĐK thay đổi tại từng thời điểm</p>
              <p>Nơi cấp: Sở Kế hoạch và Đầu tư tỉnh Khánh Hòa</p>
            </div>

           
          </section>

          {/* Column 2: About & Destinations */}
          <section className="footer__column">
            <div className="footer__section">
              <h4 className="footer__heading">{t.vpAboutVinpearl}</h4>
              <ul className="footer__list">
                <li><Link className="footer__link" to="/about">{t.vpAboutUs}</Link></li>
                <li><Link className="footer__link" to="/">{t.vpContact}</Link></li>
                <li><Link className="footer__link" to="/">{t.vpCareers}</Link></li>
                <li><Link className="footer__link" to="/">{t.vpFAQ}</Link></li>
                <li><Link className="footer__link" to="/">{t.vpSitemap}</Link></li>
              </ul>
            </div>

            <div className="footer__section">
              <h4 className="footer__heading">{t.destTitle}</h4>
              <ul className="footer__list">
                <li><Link className="footer__link" to="/search?destination=hoi-an">Nam Hội An</Link></li>
                <li><Link className="footer__link" to="/search?destination=nha-trang">Nha Trang</Link></li>
                <li><Link className="footer__link" to="/search?destination=phu-quoc">Phú Quốc</Link></li>
              </ul>
            </div>
          </section>

          {/* Column 3: Terms & Tags */}
          <section className="footer__column">
            <div className="footer__section">
              <h4 className="footer__heading">{t.vpTermsAndConditions}</h4>
              <ul className="footer__list">
                <li><Link className="footer__link" to="/regulations?doc=ab8c79e6ba880330">{t.vpTermsGeneral}</Link></li>
                <li><Link className="footer__link" to="/regulations?doc=dc59dc5ab26beb6c">{t.vpTermsRegulations}</Link></li>
                <li><Link className="footer__link" to="/regulations?doc=51b47a823a328173">{t.vpTermsBooking}</Link></li>
                <li><Link className="footer__link" to="/regulations?doc=8b462f7c7f84c886">{t.vpTermsDispute}</Link></li>
                <li><Link className="footer__link" to="/regulations?doc=e85231023643cc90">{t.vpTermsPrivacy}</Link></li>
                <li><Link className="footer__link" to="/regulations?doc=fc50fe230088e326">{t.vpTermsTransparency}</Link></li>
              </ul>
            </div>

            <div className="footer__section">
              <h4 className="footer__heading">Tag</h4>
              <ul className="footer__list">
                <li><Link className="footer__link" to="/search?destination=phu-quoc">{t.vpTagPhuQuoc}</Link></li>
                <li><Link className="footer__link" to="/search?destination=nha-trang">{t.vpTagNhaTrang}</Link></li>
                <li><Link className="footer__link" to="/search?destination=hoi-an">{t.vpTagHoiAn}</Link></li>
                <li><Link className="footer__link" to="/search?destination=ha-long">{t.vpTagHaLong}</Link></li>
                <li><Link className="footer__link" to="/search?destination=all">{t.vpTagVietnam}</Link></li>
              </ul>
            </div>
          </section>

          {/* Column 4: News & Apps */}
          <section className="footer__column">
            <div className="footer__section">
              <h4 className="footer__heading">{t.vpNewsAndEvents}</h4>
              <ul className="footer__list">
                <li><Link className="footer__link" to="/promotions">{t.navOffers}</Link></li>
                <li><Link className="footer__link" to="/">{t.vpNewsCompany}</Link></li>
                <li><Link className="footer__link" to="/">{t.vpNewsGuide}</Link></li>
                <li><Link className="footer__link" to="/">{t.vpNewsAchievements}</Link></li>
                <li><Link className="footer__link" to="/">{t.vpNewsLegal}</Link></li>
              </ul>
            </div>

          </section>
        </div>
      </div>

      <div className="footer__bottom">
        <div className="footer__bar">
          <div className="footer__copyright">
            Copyright © 2026 Vinpearl.com. All rights reserved
          </div>
          <div className="footer__socials">
            <a href="https://facebook.com" className="footer__social-link">
              <Facebook size={20} />
            </a>
            <a href="https://youtube.com" className="footer__social-link">
              <Youtube size={20} />
            </a>
            <a href="https://instagram.com" className="footer__social-link">
              <Instagram size={20} />
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}

export default Footer
