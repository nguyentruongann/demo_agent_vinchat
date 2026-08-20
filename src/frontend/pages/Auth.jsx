import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import '../styles/pages/Auth.css'

const VINPEARL_LOGO_URL = 'https://statics.vinpearl.com/files/images/new-homepage/vp-logo-blue.svg'
const HERO_IMAGE_URL = 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1920&q=80'

const LANGUAGE_OPTIONS = [
  { code: 'vi', flag: '🇻🇳', label: 'VIE' },
  { code: 'en', flag: '🇬🇧', label: 'ENG' },
  { code: 'ko', flag: '🇰🇷', label: 'KOR' },
  { code: 'ja', flag: '🇯🇵', label: 'JPN' },
  { code: 'zh', flag: '🇨🇳', label: 'CHN' },
]

function Auth({ initialTab = 'login' }) {
  const { login, register } = useAuth()
  const { t, language, setLanguage } = useLanguage()
  const navigate = useNavigate()
  const location = useLocation()

  const [tab, setTab] = useState(initialTab === 'register' ? 'register' : 'login')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)

  // login fields
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)

  // register fields
  const [lastName, setLastName] = useState('')
  const [firstNameRest, setFirstNameRest] = useState('')
  const [email, setEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmValue, setConfirmValue] = useState('')
  const [referral, setReferral] = useState('')



  useEffect(() => {
    function closeOnOutsideClick(event) {
      if (!menuRef.current?.contains(event.target)) setMenuOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsideClick)
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick)
  }, [])

  function switchTab(nextTab) {
    setTab(nextTab)
    setError('')
  }

  async function handleLogin(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const user = await login(identifier, password)
      const requested = location.state?.from
      if (requested) navigate(requested, { replace: true })
      else if (user.role === 'admin' || user.role === 'staff') navigate('/staff/tickets', { replace: true })
      else navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || t.loginFailed)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRegister(event) {
    event.preventDefault()
    setError('')
    if (newPassword !== confirmValue) {
      setError(t.passwordMismatch)
      return
    }
    setSubmitting(true)
    try {
      const name = [lastName.trim(), firstNameRest.trim()].filter(Boolean).join(' ')
      await register({
        name,
        email,
        password: newPassword,
        locale: language?.toLowerCase?.() || 'vi',
      })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || t.registerFailed)
    } finally {
      setSubmitting(false)
    }
  }

  const activeLanguage = LANGUAGE_OPTIONS.find((item) => item.code === language) || LANGUAGE_OPTIONS[0]

  return (
    <main className="auth-page">
      <section className="auth-hero">
        <img
          className="auth-hero__image"
          src={HERO_IMAGE_URL}
          alt="Vinpearl luxury resort"
          onError={(event) => { event.currentTarget.onerror = null; event.currentTarget.src = 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=1920&q=80' }}
        />
        <div className="auth-hero__overlay" />
        <div className="auth-hero__content">
          <span className="auth-hero__eyebrow">Vinpearl</span>
          <h1 className="auth-hero__title">
            <span>{t.authHeroTitle1}</span>
            <span>{t.authHeroTitle2}</span>
          </h1>
          <p className="auth-hero__description">{t.authHeroDescription}</p>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-language" ref={menuRef}>
          <button
            type="button"
            className={`auth-language__button ${menuOpen ? 'auth-language__button--open' : ''}`}
            onClick={() => setMenuOpen((open) => !open)}
            aria-haspopup="listbox"
            aria-expanded={menuOpen}
          >
            <span className="auth-language__flag">{activeLanguage.flag}</span>
            <span>{activeLanguage.label}</span>
            <span className="auth-language__caret">▼</span>
          </button>
          {menuOpen && (
            <div className="auth-language__menu" role="listbox">
              {LANGUAGE_OPTIONS.map((option) => (
                <button
                  key={option.code}
                  type="button"
                  role="option"
                  aria-selected={option.code === activeLanguage.code}
                  className={`auth-language__option ${option.code === activeLanguage.code ? 'auth-language__option--active' : ''}`}
                  onClick={() => {
                    setLanguage(option.code)
                    setMenuOpen(false)
                  }}
                >
                  <span className="auth-language__flag">{option.flag}</span>
                  <span>{option.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <Link className="auth-back" to="/">← {t.backToHome}</Link>

        <div className="auth-brands">
          <img className="auth-brands__logo" src={VINPEARL_LOGO_URL} alt="Vinpearl" />
        </div>

        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'login'}
            className={`auth-tabs__tab ${tab === 'login' ? 'auth-tabs__tab--active' : ''}`}
            onClick={() => switchTab('login')}
          >
            {t.signIn}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'register'}
            className={`auth-tabs__tab ${tab === 'register' ? 'auth-tabs__tab--active' : ''}`}
            onClick={() => switchTab('register')}
          >
            {t.registerTitleShort}
          </button>
        </div>

        {tab === 'login' ? (
          <form className="auth-form" onSubmit={handleLogin}>
            <div className="auth-field">
              <label className="auth-field__label" htmlFor="auth-identifier">{t.emailOrPhone}</label>
              <input
                className="auth-field__input"
                id="auth-identifier"
                type="text"
                required
                autoComplete="username"
                placeholder={t.emailOrPhonePlaceholder}
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
              />
            </div>
            <div className="auth-field">
              <label className="auth-field__label" htmlFor="auth-password">{t.password}</label>
              <input
                className="auth-field__input"
                id="auth-password"
                type="password"
                required
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            <div className="auth-form__aside">
              <label className="auth-checkbox">
                <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
                <span>{t.rememberMe}</span>
              </label>
              <a className="auth-link" href="#forgot">{t.forgotPassword}</a>
            </div>

            {error && <p className="auth-form__error" role="alert">{error}</p>}

            <button className="auth-form__submit" type="submit" disabled={submitting}>
              {submitting ? t.signingIn : t.signIn}
            </button>

            <p className="auth-switch">
              {t.noAccount}{' '}
              <button type="button" className="auth-switch__action" onClick={() => switchTab('register')}>
                {t.registerNow}
              </button>
            </p>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleRegister}>
            <div className="auth-form__row">
              <div className="auth-field">
                <label className="auth-field__label" htmlFor="auth-lastname">{t.lastName} *</label>
                <input
                  className="auth-field__input"
                  id="auth-lastname"
                  type="text"
                  required
                  autoComplete="family-name"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                />
              </div>
              <div className="auth-field">
                <label className="auth-field__label" htmlFor="auth-firstname">{t.firstNameRest} *</label>
                <input
                  className="auth-field__input"
                  id="auth-firstname"
                  type="text"
                  required
                  autoComplete="given-name"
                  value={firstNameRest}
                  onChange={(event) => setFirstNameRest(event.target.value)}
                />
              </div>
            </div>

            <div className="auth-field">
              <label className="auth-field__label" htmlFor="auth-email">{t.emailAddress} *</label>
              <input
                className="auth-field__input"
                id="auth-email"
                type="email"
                required
                autoComplete="email"
                placeholder="guest@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>

            <div className="auth-form__row">
              <div className="auth-field">
                <label className="auth-field__label" htmlFor="auth-new-password">{t.password} *</label>
                <input
                  className="auth-field__input"
                  id="auth-new-password"
                  type="password"
                  required
                  minLength="8"
                  autoComplete="new-password"
                  placeholder={t.passwordMinimum}
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                />
              </div>
              <div className="auth-field">
                <label className="auth-field__label" htmlFor="auth-confirm">{t.confirmPassword} *</label>
                <input
                  className="auth-field__input"
                  id="auth-confirm"
                  type="password"
                  required
                  minLength="8"
                  autoComplete="new-password"
                  placeholder="••••••••"
                  value={confirmValue}
                  onChange={(event) => setConfirmValue(event.target.value)}
                />
              </div>
            </div>

            <div className="auth-field">
              <label className="auth-field__label" htmlFor="auth-referral">
                {t.referralCode} <em>({t.optionalLabel})</em>
              </label>
              <input
                className="auth-field__input"
                id="auth-referral"
                type="text"
                placeholder={t.referralPlaceholder}
                value={referral}
                onChange={(event) => setReferral(event.target.value)}
              />
            </div>

            {error && <p className="auth-form__error" role="alert">{error}</p>}

            <button className="auth-form__submit" type="submit" disabled={submitting}>
              {submitting ? t.creatingAccount : t.registerTitleShort}
            </button>

            <p className="auth-switch">
              {t.alreadyHaveAccount}{' '}
              <button type="button" className="auth-switch__action" onClick={() => switchTab('login')}>
                {t.loginNow}
              </button>
            </p>
          </form>
        )}
      </section>
    </main>
  )
}

export default Auth
