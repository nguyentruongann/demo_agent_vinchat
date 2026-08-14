import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Clock3, RefreshCw, ShieldCheck, UserCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import { fetchStaffTickets, updateStaffTicket } from '../services/api'
import '../styles/pages/StaffTickets.css'

function StaffTickets() {
  const { user } = useAuth()
  const { language, t } = useLanguage()
  const statusLabels = { open: t.statusOpen, in_progress: t.statusProcessing, resolved: t.statusResolved, closed: t.statusClosed }
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
      setError(err.message || t.ticketLoadError)
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
      setError(err.message || t.ticketUpdateError)
    } finally {
      setUpdatingId(null)
    }
  }

  return (
    <main className="staff-tickets">
      <section className="staff-tickets__header">
        <div>
          <span className="staff-tickets__eyebrow"><ShieldCheck size={16} /> {t.staffArea}</span>
          <h1>{t.ticketManagement}</h1>
          <p>{t.staffGreeting.replace('{{name}}', user?.name || '')}</p>
        </div>
        <button type="button" className="staff-tickets__refresh" onClick={load} disabled={loading}><RefreshCw size={16} /> {t.refresh}</button>
      </section>

      <section className="staff-tickets__toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{t.allStatuses}</option>
          <option value="open">{t.statusOpen}</option>
          <option value="in_progress">{t.statusProcessing}</option>
          <option value="resolved">{t.statusResolved}</option>
          <option value="closed">{t.statusClosed}</option>
        </select>
        <div className="staff-tickets__counts">
          <span>{t.statusOpen}: {counts.open || 0}</span>
          <span>{t.statusProcessing}: {counts.in_progress || 0}</span>
          <span>{t.statusResolved}: {counts.resolved || 0}</span>
        </div>
      </section>

      {error && <div className="staff-tickets__error">{error}</div>}
      {loading ? <p>{t.loadingTickets}</p> : (
        <section className="staff-tickets__list">
          {tickets.length === 0 && <div className="staff-tickets__empty">{t.noMatchingTickets}</div>}
          {tickets.map((ticket) => (
            <article className="staff-ticket" key={ticket.id}>
              <div className="staff-ticket__top">
                <div>
                  <strong>{ticket.id}</strong>
                  <span className={`staff-ticket__status staff-ticket__status--${ticket.status}`}>{statusLabels[ticket.status] || ticket.status}</span>
                </div>
                <span>{new Date(ticket.created_at).toLocaleString(language)}</span>
              </div>
              <h2>{ticket.subject || t.chatbotSupportRequest}</h2>
              <p className="staff-ticket__content">{ticket.content || ticket.reason || t.noContent}</p>
              {ticket.reason && <p className="staff-ticket__reason"><b>{t.escalationReason}:</b> {ticket.reason}</p>}
              <div className="staff-ticket__contact">
                <span><b>{t.customer}:</b> {ticket.customer_name || t.unnamedCustomer}</span>
                <span><b>{t.emailAddress}:</b> {ticket.email || '—'}</span>
                <span><b>{t.phone}:</b> {ticket.phone || '—'}</span>
                <span><b>{t.assignee}:</b> {ticket.assigned_to_name || t.unassigned}</span>
              </div>
              <div className="staff-ticket__actions">
                {ticket.status === 'open' && (
                  <button disabled={updatingId === ticket.id} onClick={() => changeTicket(ticket.id, { status: 'in_progress' })}><UserCheck size={15} /> {t.acceptTicket}</button>
                )}
                {ticket.status !== 'resolved' && ticket.status !== 'closed' && (
                  <button disabled={updatingId === ticket.id} onClick={() => changeTicket(ticket.id, { status: 'resolved' })}><CheckCircle2 size={15} /> {t.markResolved}</button>
                )}
                {ticket.status === 'resolved' && (
                  <button disabled={updatingId === ticket.id} onClick={() => changeTicket(ticket.id, { status: 'closed' })}><Clock3 size={15} /> {t.closeTicket}</button>
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
