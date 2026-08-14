import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, KeyRound, Lock, LogIn, Sparkles } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import '../styles/pages/Login.css'

function Login() {
  const { login } = useAuth()
  const { t } = useLanguage()
  const navigate = useNavigate()
  const location = useLocation()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
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

  return (
    <main className="login-page">
      <section className="login-page__card">
        <Link className="login-page__back" to="/">
          <ArrowLeft className="login-page__back-icon" />
          <span>{t.backToHome}</span>
        </Link>
        <div className="login-page__heading">
          <div className="login-page__mark"><Sparkles className="login-page__mark-icon" /></div>
          <h1>{t.loginTitle}</h1>
          <p>{t.loginHelp}</p>
        </div>
        <form className="login-page__form" onSubmit={handleSubmit}>
          <div className="login-page__field">
            <label className="login-page__label" htmlFor="login-identifier">
              <KeyRound className="login-page__label-icon" />
              <span>{t.emailOrPhone}</span>
            </label>
            <input
              className="login-page__input"
              id="login-identifier"
              type="text"
              required
              autoComplete="username"
              placeholder={t.emailOrPhonePlaceholder}
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
            />
          </div>
          <div className="login-page__field">
            <label className="login-page__label" htmlFor="login-password">
              <Lock className="login-page__label-icon" /><span>{t.password}</span>
            </label>
            <input
              className="login-page__input"
              id="login-password"
              type="password"
              required
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {error && <p className="login-page__error" role="alert">{error}</p>}
          <button className="login-page__submit" type="submit" disabled={submitting}>
            <LogIn className="login-page__submit-icon" />
            <span>{submitting ? t.signingIn : t.signIn}</span>
          </button>
        </form>
        <p className="login-page__register">{t.noAccount}{' '}<Link to="/register">{t.registerHere}</Link></p>
      </section>
    </main>
  )
}

export default Login
