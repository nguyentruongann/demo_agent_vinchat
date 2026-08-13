import { useEffect, useState } from 'react'
import { ShieldPlus, UserCog } from 'lucide-react'
import { createStaffAccount, fetchStaffAccounts, updateStaffAccount } from '../services/api'
import '../styles/pages/AdminStaff.css'

function AdminStaff() {
  const [accounts, setAccounts] = useState([])
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '', role: 'staff' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function load() {
    try { setAccounts(await fetchStaffAccounts()) }
    catch (err) { setError(err.message || 'Không tải được tài khoản nhân viên.') }
  }
  useEffect(() => { load() }, [])

  async function submit(event) {
    event.preventDefault()
    setError(''); setSuccess('')
    if (!form.email.trim() && !form.phone.trim()) {
      setError('Nhân viên phải có email hoặc số điện thoại.')
      return
    }
    try {
      await createStaffAccount(form)
      setSuccess('Đã tạo tài khoản nhân viên.')
      setForm({ name: '', email: '', phone: '', password: '', role: 'staff' })
      await load()
    } catch (err) { setError(err.message || 'Không tạo được tài khoản.') }
  }

  async function toggleActive(account) {
    try {
      await updateStaffAccount(account.id, { is_active: account.is_active === false })
      await load()
    } catch (err) { setError(err.message || 'Không cập nhật được tài khoản.') }
  }

  return (
    <main className="admin-staff">
      <section className="admin-staff__header"><UserCog size={22} /><div><h1>Quản lý nhân viên tư vấn</h1><p>Chỉ admin có quyền tạo tài khoản staff/admin. Không mở đăng ký công khai cho nhân viên.</p></div></section>
      {error && <div className="admin-staff__error">{error}</div>}
      {success && <div className="admin-staff__success">{success}</div>}
      <section className="admin-staff__grid">
        <form className="admin-staff__form" onSubmit={submit}>
          <h2><ShieldPlus size={18} /> Tạo tài khoản nhân viên</h2>
          <label>Họ tên *<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>Email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Số điện thoại<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
          <label>Mật khẩu *<input type="password" minLength="8" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
          <label>Vai trò<select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="staff">Nhân viên tư vấn</option><option value="admin">Admin</option></select></label>
          <button type="submit">Tạo tài khoản</button>
        </form>
        <section className="admin-staff__list">
          <h2>Danh sách staff/admin</h2>
          {accounts.map((account) => (
            <article key={account.id}>
              <div><strong>{account.name}</strong><span>{account.role}</span></div>
              <p>{account.email || account.phone || 'Không có liên hệ'}</p>
            </article>
          ))}
        </section>
      </section>
    </main>
  )
}

export default AdminStaff
