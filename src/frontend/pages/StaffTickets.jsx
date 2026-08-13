import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Clock3, RefreshCw, ShieldCheck, UserCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { fetchStaffTickets, updateStaffTicket } from '../services/api'
import '../styles/pages/StaffTickets.css'

const STATUS_LABELS = {
  open: 'Mới',
  in_progress: 'Đang xử lý',
  resolved: 'Đã xử lý',
  closed: 'Đã đóng',
}

function StaffTickets() {
  const { user } = useAuth()
  const [tickets, setTickets] = useState([])
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [updatingId, setUpdatingId] = useState(null)

  async function load() {
    setLoading(true)
    setError('')
    try {
      setTickets(await fetchStaffTickets(status))
    } catch (err) {
      setError(err.message || 'Không tải được ticket.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [status])

  const counts = useMemo(() => tickets.reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1
    return acc
  }, {}), [tickets])

  async function changeTicket(ticketId, changes) {
    setUpdatingId(ticketId)
    setError('')
    try {
      const updated = await updateStaffTicket(ticketId, changes)
      setTickets((current) => current.map((item) => item.id === ticketId ? updated : item))
    } catch (err) {
      setError(err.message || 'Không cập nhật được ticket.')
    } finally {
      setUpdatingId(null)
    }
  }

  return (
    <main className="staff-tickets">
      <section className="staff-tickets__header">
        <div>
          <span className="staff-tickets__eyebrow"><ShieldCheck size={16} /> Khu vực nhân viên</span>
          <h1>Quản lý ticket hỗ trợ</h1>
          <p>Xin chào {user?.name}. Nhân viên có thể nhận và cập nhật ticket; admin có thêm quyền quản lý tài khoản nhân viên.</p>
        </div>
        <button type="button" className="staff-tickets__refresh" onClick={load} disabled={loading}><RefreshCw size={16} /> Làm mới</button>
      </section>

      <section className="staff-tickets__toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Tất cả trạng thái</option>
          <option value="open">Mới</option>
          <option value="in_progress">Đang xử lý</option>
          <option value="resolved">Đã xử lý</option>
          <option value="closed">Đã đóng</option>
        </select>
        <div className="staff-tickets__counts">
          <span>Mới: {counts.open || 0}</span>
          <span>Đang xử lý: {counts.in_progress || 0}</span>
          <span>Đã xử lý: {counts.resolved || 0}</span>
        </div>
      </section>

      {error && <div className="staff-tickets__error">{error}</div>}
      {loading ? <p>Đang tải ticket...</p> : (
        <section className="staff-tickets__list">
          {tickets.length === 0 && <div className="staff-tickets__empty">Chưa có ticket phù hợp bộ lọc.</div>}
          {tickets.map((ticket) => (
            <article className="staff-ticket" key={ticket.id}>
              <div className="staff-ticket__top">
                <div>
                  <strong>{ticket.id}</strong>
                  <span className={`staff-ticket__status staff-ticket__status--${ticket.status}`}>{STATUS_LABELS[ticket.status] || ticket.status}</span>
                </div>
                <span>{new Date(ticket.created_at).toLocaleString('vi-VN')}</span>
              </div>
              <h2>{ticket.subject || 'Yêu cầu hỗ trợ từ chatbot'}</h2>
              <p className="staff-ticket__content">{ticket.content || ticket.reason || 'Không có nội dung.'}</p>
              {ticket.reason && <p className="staff-ticket__reason"><b>Lý do chuyển hỗ trợ:</b> {ticket.reason}</p>}
              <div className="staff-ticket__contact">
                <span><b>Khách:</b> {ticket.customer_name || 'Chưa có tên'}</span>
                <span><b>Email:</b> {ticket.email || '—'}</span>
                <span><b>SĐT:</b> {ticket.phone || '—'}</span>
                <span><b>Phụ trách:</b> {ticket.assigned_to_name || 'Chưa gán'}</span>
              </div>
              <div className="staff-ticket__actions">
                {ticket.status === 'open' && (
                  <button disabled={updatingId === ticket.id} onClick={() => changeTicket(ticket.id, { status: 'in_progress' })}><UserCheck size={15} /> Nhận xử lý</button>
                )}
                {ticket.status !== 'resolved' && ticket.status !== 'closed' && (
                  <button disabled={updatingId === ticket.id} onClick={() => changeTicket(ticket.id, { status: 'resolved' })}><CheckCircle2 size={15} /> Đánh dấu đã xử lý</button>
                )}
                {ticket.status === 'resolved' && (
                  <button disabled={updatingId === ticket.id} onClick={() => changeTicket(ticket.id, { status: 'closed' })}><Clock3 size={15} /> Đóng ticket</button>
                )}
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  )
}

export default StaffTickets
