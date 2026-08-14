import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  ChevronDown,
  Globe,
  LogOut,
  Menu,
  User,
  X,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/Header.css'

const VINPEARL_LOGO_URL =
  'https://statics.vinpearl.com/files/images/new-homepage/vp-logo-blue.svg'

function Header() {
  const { language, setLanguage, t } = useLanguage()
  const { user, logout } = useAuth()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [langDropdownOpen, setLangDropdownOpen] = useState(false)
  const [authDropdownOpen, setAuthDropdownOpen] = useState(false)
  const [isScrolled, setIsScrolled] = useState(false)

  const isHomePage = location.pathname === '/'

  useEffect(() => {
    const handleScroll = () => {
      const threshold = isHomePage ? 480 : 10
      setIsScrolled(window.scrollY > threshold)
    }
    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [isHomePage, location.pathname])

  const languages = [
    { code: 'en', label: 'English' },
    { code: 'vi', label: 'Tiếng Việt' },
    { code: 'ko', label: '한국어' },
    { code: 'ja', label: '日本語' },
    { code: 'zh', label: '中文' },
  ]

  const currentLang = languages.find((item) => item.code === language) || languages[0]
  function handleLogout() {
    logout()
    setMobileMenuOpen(false)
  }

  function cycleMobileLanguage() {
    const currentIndex = languages.findIndex((item) => item.code === language)
    const nextLanguage = languages[(currentIndex + 1) % languages.length]
    setLanguage(nextLanguage.code)
  }

  return (
    <header className={`header ${!isHomePage || isScrolled ? 'header--scrolled' : ''}`}>
      <div className="header__container">
        <div className="header__bar">
          <Link className="header__brand" to="/">
            <img className="header__brand-logo" src={VINPEARL_LOGO_URL} alt="Vinpearl" />
          </Link>

          <nav className="header__nav" aria-label={t.mainNavigation}>
            <Link
              className={`header__link ${location.pathname === '/search' ? 'header__link--active' : ''}`}
              to="/search"
            >
              {t.navHotels}
            </Link>
            <Link
              className={`header__link ${location.pathname === '/' && location.hash === '#experiences' ? 'header__link--active' : ''}`}
              to="/#experiences"
            >
              {t.navExperiences}
            </Link>
            <Link
              className={`header__link ${location.pathname === '/promotions' ? 'header__link--active' : ''}`}
              to="/promotions"
            >
              {t.navOffers}
            </Link>
            <Link
              className={`header__link ${location.pathname === '/regulations' && !location.search ? 'header__link--active' : ''}`}
              to="/regulations"
            >
              {t.navNews}
            </Link>
            <Link
              className={`header__link ${location.pathname === '/support' ? 'header__link--active' : ''}`}
              to="/support"
            >
              {t.navMeetings}
            </Link>
            {user && (user.role === 'staff' || user.role === 'admin') && (
              <Link className={`header__link ${location.pathname.startsWith('/staff') ? 'header__link--active' : ''}`} to="/staff/tickets">{t.staffTickets}</Link>
            )}
            {user?.role === 'admin' && (
              <Link className={`header__link ${location.pathname.startsWith('/admin') ? 'header__link--active' : ''}`} to="/admin/staff">{t.staffMembers}</Link>
            )}
            <Link
              className={`header__link ${location.pathname === '/regulations' && location.search.includes('doc=') ? 'header__link--active' : ''}`}
              to="/regulations?doc=ab8c79e6ba880330"
            >
              {t.navRegulations}
            </Link>
          </nav>

          <div className="header__actions">
            <div
              className={`header__language ${langDropdownOpen ? 'header__language--open' : ''}`}
              onMouseEnter={() => setLangDropdownOpen(true)}
              onMouseLeave={() => setLangDropdownOpen(false)}
              onFocus={() => setLangDropdownOpen(true)}
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) {
                  setLangDropdownOpen(false)
                }
              }}
            >
              <button
                className="header__language-trigger"
                type="button"
                aria-haspopup="true"
              >
                <Globe className="header__language-icon" />
                <span>{currentLang.code.toUpperCase()}</span>
                <ChevronDown className="header__chevron" />
              </button>

              <div className="header__language-menu">
                {languages.map((item) => (
                  <button
                    className={`header__language-option ${
                      language === item.code ? 'header__language-option--active' : ''
                    }`}
                    key={item.code}
                    type="button"
                    onClick={() => {
                      setLanguage(item.code)
                      setLangDropdownOpen(false)
                    }}
                  >
                    <span>{item.code.toUpperCase()}</span>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {user ? (
              <div className="header__user">
                {user.avatar && (
                  <img className="header__avatar" src={user.avatar} alt={user.name} />
                )}
                <span className="header__user-name">{user.name}</span>
                <button
                  className="header__logout"
                  type="button"
                  title={t.signOut}
                  onClick={logout}
                >
                  <LogOut className="header__logout-icon" />
                </button>
              </div>
            ) : (
              <div
                className={`header__language ${authDropdownOpen ? 'header__language--open' : ''}`}
                onMouseEnter={() => setAuthDropdownOpen(true)}
                onMouseLeave={() => setAuthDropdownOpen(false)}
                onFocus={() => setAuthDropdownOpen(true)}
                onBlur={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget)) {
                    setAuthDropdownOpen(false)
                  }
                }}
              >
                <button
                  className="header__language-trigger"
                  type="button"
                  aria-haspopup="true"
                >
                  <User className="header__language-icon" />
                  <span>{t.signIn || 'Tài khoản'}</span>
                  <ChevronDown className="header__chevron" />
                </button>
                <div className="header__language-menu">
                  <Link
                    className="header__language-option"
                    to="/login"
                    onClick={() => setAuthDropdownOpen(false)}
                    style={{ textDecoration: 'none' }}
                  >
                    <span>{t.signIn || 'Đăng nhập'}</span>
                  </Link>
                  <Link
                    className="header__language-option"
                    to="/register"
                    onClick={() => setAuthDropdownOpen(false)}
                    style={{ textDecoration: 'none' }}
                  >
                    <span>{t.navRegister || 'Đăng ký'}</span>
                  </Link>
                </div>
              </div>
            )}
          </div>

          <div className="header__mobile-actions">
            <button
              className="header__mobile-language"
              type="button"
              onClick={cycleMobileLanguage}
            >
              {currentLang.code.toUpperCase()}
            </button>
            <button
              className="header__mobile-toggle"
              type="button"
              aria-label={t.menu}
              onClick={() => setMobileMenuOpen((current) => !current)}
            >
              {mobileMenuOpen ? (
                <X className="header__mobile-icon" />
              ) : (
                <Menu className="header__mobile-icon" />
              )}
            </button>
          </div>
        </div>
      </div>

      {mobileMenuOpen && (
        <div className="header__drawer">
          <Link
            className="header__drawer-link"
            to="/search"
            onClick={() => setMobileMenuOpen(false)}
          >
            {t.navHotels}
          </Link>
          <Link
            className="header__drawer-link"
            to="/promotions"
            onClick={() => setMobileMenuOpen(false)}
          >
            {t.navExperiences}
          </Link>
          <Link
            className="header__drawer-link"
            to="/"
            onClick={() => setMobileMenuOpen(false)}
          >
            {t.navOffers}
          </Link>
          <Link
            className="header__drawer-link"
            to="/regulations"
            onClick={() => setMobileMenuOpen(false)}
          >
            {t.navNews}
          </Link>
          <Link
            className="header__drawer-link"
            to="/support"
            onClick={() => setMobileMenuOpen(false)}
          >
            {t.navMeetings}
          </Link>
          <Link
            className="header__drawer-link"
            to="/regulations?doc=ab8c79e6ba880330"
            onClick={() => setMobileMenuOpen(false)}
          >
            {t.navRegulations}
          </Link>
          {user && (user.role === 'staff' || user.role === 'admin') && (
            <Link className="header__drawer-link" to="/staff/tickets" onClick={() => setMobileMenuOpen(false)}>{t.staffTickets}</Link>
          )}
          {user?.role === 'admin' && (
            <Link className="header__drawer-link" to="/admin/staff" onClick={() => setMobileMenuOpen(false)}>{t.staffMembers}</Link>
          )}
          {user ? (
            <div className="header__drawer-user">
              <div className="header__drawer-profile">
                {user.avatar && (
                  <img className="header__drawer-avatar" src={user.avatar} alt="" />
                )}
                <span>{user.name}</span>
              </div>
              <button className="header__drawer-logout" type="button" onClick={handleLogout}>
                <LogOut className="header__drawer-icon" />
                <span>{t.signOut}</span>
              </button>
            </div>
          ) : (
            <div className="header__drawer-auth">
              <Link
                className="header__drawer-signin"
                to="/login"
                onClick={() => setMobileMenuOpen(false)}
              >
                {t.signIn}
              </Link>
              <Link
                className="header__drawer-register"
                to="/register"
                onClick={() => setMobileMenuOpen(false)}
              >
                {t.navRegister}
              </Link>
            </div>
          )}
        </div>
      )}
    </header>
  )
}

export default Header
