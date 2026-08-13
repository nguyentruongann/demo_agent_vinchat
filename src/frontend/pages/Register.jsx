import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Lock, Mail, Phone, Sparkles, User, UserPlus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import '../styles/pages/Register.css'

function Register() {
  const { register } = useAuth()
  const { t, language } = useLanguage()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    if (!email.trim() && !phone.trim()) {
      setError('Vui lòng nhập ít nhất email hoặc số điện thoại.')
      return
    }
    setSubmitting(true)
    try {
      await register({ name, email, phone, password, locale: language?.toLowerCase?.() || 'vi' })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'Không thể tạo tài khoản.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="register-page">
      <section className="register-page__card">
        <Link className="register-page__back" to="/"><ArrowLeft className="register-page__back-icon" /><span>{t.backToHome}</span></Link>
        <div className="register-page__heading">
          <div className="register-page__mark"><Sparkles className="register-page__mark-icon" /></div>
          <h1>{t.registerTitle}</h1>
          <p>Tên là bắt buộc; cần ít nhất email hoặc số điện thoại.</p>
        </div>
        <form className="register-page__form" onSubmit={handleSubmit}>
          <div className="register-page__field">
            <label className="register-page__label" htmlFor="register-name"><User className="register-page__label-icon" /><span>{t.fullName} *</span></label>
            <input className="register-page__input" id="register-name" type="text" required autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="register-page__field">
            <label className="register-page__label" htmlFor="register-email"><Mail className="register-page__label-icon" /><span>{t.emailAddress}</span></label>
            <input className="register-page__input" id="register-email" type="email" autoComplete="email" placeholder="guest@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="register-page__field">
            <label className="register-page__label" htmlFor="register-phone"><Phone className="register-page__label-icon" /><span>Số điện thoại</span></label>
            <input className="register-page__input" id="register-phone" type="tel" autoComplete="tel" placeholder="0901234567" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <div className="register-page__field">
            <label className="register-page__label" htmlFor="register-password"><Lock className="register-page__label-icon" /><span>{t.password} *</span></label>
            <input className="register-page__input" id="register-password" type="password" required minLength="8" autoComplete="new-password" placeholder="Tối thiểu 8 ký tự" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <p className="register-page__error" role="alert">{error}</p>}
          <button className="register-page__submit" type="submit" disabled={submitting}><UserPlus className="register-page__submit-icon" /><span>{submitting ? 'Đang tạo...' : t.createAccount}</span></button>
        </form>
        <p className="register-page__login">{t.alreadyHaveAccount} <Link to="/login">{t.signIn}</Link></p>
      </section>
    </main>
  )
}

export default Register
