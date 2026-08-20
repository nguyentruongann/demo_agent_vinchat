import { useEffect, useState } from 'react'
import { ShieldPlus, UserCog } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { createStaffAccount, fetchStaffAccounts, updateStaffAccount } from '../services/api'
import '../styles/pages/AdminStaff.css'

function AdminStaff() {
  const { t } = useLanguage()
  const [accounts, setAccounts] = useState([])
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '', role: 'staff' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function load() {
    try { setAccounts(await fetchStaffAccounts()) }
    catch (err) { setError(err.message || t.staffLoadError) }
  }
  useEffect(() => { load() }, [])

  async function submit(event) {
    event.preventDefault()
    setError(''); setSuccess('')
    if (!form.email.trim() && !form.phone.trim()) {
      setError(t.staffContactRequired)
      return
    }
    try {
      await createStaffAccount(form)
      setSuccess(t.staffCreated)
      setForm({ name: '', email: '', phone: '', password: '', role: 'staff' })
      await load()
    } catch (err) { setError(err.message || t.staffCreateError) }
  }

  async function _toggleActive(account) {
    try {
      await updateStaffAccount(account.id, { is_active: account.is_active === false })
      await load()
    } catch (err) { setError(err.message || t.staffUpdateError) }
  }

  return (
    <main className="admin-staff">
      <section className="admin-staff__header"><UserCog size={22} /><div><h1>{t.staffManagement}</h1><p>{t.staffManagementDesc}</p></div></section>
      {error && <div className="admin-staff__error">{error}</div>}
      {success && <div className="admin-staff__success">{success}</div>}
      <section className="admin-staff__grid">
        <form className="admin-staff__form" onSubmit={submit}>
          <h2><ShieldPlus size={18} /> {t.createStaffAccount}</h2>
          <label>{t.fullName} *<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>{t.emailAddress}<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>{t.phone}<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
          <label>{t.password} *<input type="password" minLength="8" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
          <label>{t.role}<select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="staff">{t.consultingStaff}</option><option value="admin">{t.admin}</option></select></label>
          <button type="submit">{t.createAccount}</button>
        </form>
        <section className="admin-staff__list">
          <h2>{t.staffList}</h2>
          {accounts.map((account) => (
            <article key={account.id}>
              <div><strong>{account.name}</strong><span>{account.role}</span></div>
              <p>{account.email || account.phone || t.noContact}</p>
            </article>
          ))}
        </section>
      </section>
    </main>
  )
}

export default AdminStaff
