import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  Clock,
  FileText,
  Globe,
  Headphones,
  Mail,
  Phone,
  Send,
  User,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { useAuth } from '../context/AuthContext'
import { fetchTickets, submitSupportTicket } from '../services/api'
import '../styles/pages/Ticket.css'

function Ticket() {
  const { language, t } = useLanguage()
  const { user } = useAuth()
  const [customerName, setCustomerName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [prefLang, setPrefLang] = useState(language)
  const [subject, setSubject] = useState('')
  const [content, setContent] = useState('')
  const [tickets, setTickets] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [submittedSuccess, setSubmittedSuccess] = useState(false)

  useEffect(() => {
    if (user) {
      setCustomerName((current) => current || user.name || '')
      setEmail((current) => current || user.email || '')
      setPhone((current) => current || user.phone || '')
    }
    fetchTickets().then((data) => setTickets(data)).catch(() => setTickets([]))
  }, [user])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!customerName || (!email && !phone) || !content) return

    setSubmitting(true)
    try {
      const newTicket = await submitSupportTicket({
        customerName,
        email,
        phone,
        language: prefLang,
        subject: subject || t.generalInquiry,
        content,
      })

      setTickets((current) => [newTicket, ...current])
      setSubmittedSuccess(true)
      setCustomerName('')
      setEmail('')
      setPhone('')
      setSubject('')
      setContent('')
      window.setTimeout(() => setSubmittedSuccess(false), 5000)
    } finally {
      setSubmitting(false)
    }
  }

  function getStatusBadge(status) {
    if (status === 'Resolved') {
      return (
        <span className="ticket-page__status ticket-page__status--resolved">
          <CheckCircle2 className="ticket-page__status-icon" />
          {t.statusResolved}
        </span>
      )
    }

    if (status === 'Processing') {
      return (
        <span className="ticket-page__status ticket-page__status--processing">
          <Clock className="ticket-page__status-icon" />
          {t.statusProcessing}
        </span>
      )
    }

    return (
      <span className="ticket-page__status ticket-page__status--pending">
        <Clock className="ticket-page__status-icon" />
        {t.statusPending}
      </span>
    )
  }

  return (
    <main className="ticket-page">
      <div className="ticket-page__container">
        <section className="ticket-page__header">
          <div className="ticket-page__badge">
            <Headphones className="ticket-page__badge-icon" />
            <span>{t.ticketBadge}</span>
          </div>
          <h1>{t.supportTitle}</h1>
          <p>{t.ticketSubtitle}</p>
        </section>

        {submittedSuccess && (
          <div className="ticket-page__success">
            <CheckCircle2 className="ticket-page__success-icon" />
            <div>
              <h5>{t.ticketSuccessTitle}</h5>
              <p>{t.ticketSuccessDesc}</p>
            </div>
          </div>
        )}

        <section className="ticket-page__layout">
          <div className="ticket-page__form-card">
            <h2>{t.submitTicket}</h2>

            <form className="ticket-page__form" onSubmit={handleSubmit}>
              <div className="ticket-page__field">
                <label className="ticket-page__label" htmlFor="ticket-name">
                  <User className="ticket-page__label-icon" />
                  <span>{t.fullName} *</span>
                </label>
                <input
                  id="ticket-name"
                  type="text"
                  required
                  placeholder={t.nameExample}
                  value={customerName}
                  onChange={(event) => setCustomerName(event.target.value)}
                />
              </div>

              <div className="ticket-page__field-grid">
                <div className="ticket-page__field">
                  <label className="ticket-page__label" htmlFor="ticket-email">
                    <Mail className="ticket-page__label-icon" />
                    <span>{t.emailAddress}</span>
                  </label>
                  <input
                    id="ticket-email"
                    type="email"
                    placeholder="guest@example.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </div>

                <div className="ticket-page__field">
                  <label className="ticket-page__label" htmlFor="ticket-phone">
                    <Phone className="ticket-page__label-icon" />
                    <span>{t.phoneZalo} ({t.contactRequiredHint})</span>
                  </label>
                  <input
                    id="ticket-phone"
                    type="text"
                    placeholder="+84 901 234 567"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                  />
                </div>
              </div>

              <div className="ticket-page__field-grid">
                <div className="ticket-page__field">
                  <label className="ticket-page__label" htmlFor="ticket-language">
                    <Globe className="ticket-page__label-icon" />
                    <span>{t.preferredLanguage}</span>
                  </label>
                  <select
                    id="ticket-language"
                    value={prefLang}
                    onChange={(event) => setPrefLang(event.target.value)}
                  >
                    <option value="en">{t.english}</option>
                    <option value="vi">{t.vietnamese}</option>
                    <option value="ko">{t.korean}</option>
                    <option value="ja">{t.japanese}</option>
                    <option value="zh">{t.chinese}</option>
                  </select>
                </div>

                <div className="ticket-page__field">
                  <label className="ticket-page__label" htmlFor="ticket-subject">
                    <FileText className="ticket-page__label-icon" />
                    <span>{t.subject}</span>
                  </label>
                  <input
                    id="ticket-subject"
                    type="text"
                    placeholder={t.subjectExample}
                    value={subject}
                    onChange={(event) => setSubject(event.target.value)}
                  />
                </div>
              </div>

              <div className="ticket-page__field">
                <label className="ticket-page__label" htmlFor="ticket-content">
                  {t.inquiryDetails} *
                </label>
                <textarea
                  id="ticket-content"
                  required
                  rows="4"
                  placeholder={t.inquiryPlaceholder}
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                />
              </div>

              <button
                className="ticket-page__submit"
                type="submit"
                disabled={submitting}
              >
                <Send className="ticket-page__submit-icon" />
                <span>{submitting ? t.submittingTicket : t.submitTicket}</span>
              </button>
            </form>
          </div>

          <section className="ticket-page__history">
            <h2>
              {t.ticketHistory} ({tickets.length})
            </h2>

            <div className="ticket-page__history-list">
              {tickets.map((ticket) => (
                <article className="ticket-page__ticket" key={ticket.id}>
                  <div className="ticket-page__ticket-header">
                    <span className="ticket-page__ticket-id">{ticket.id}</span>
                    {getStatusBadge(ticket.status)}
                  </div>

                  <h3>{ticket.subject}</h3>
                  <p>"{ticket.content}"</p>

                  <div className="ticket-page__ticket-meta">
                    <span>
                      {t.submittedBy}: <strong>{ticket.customerName}</strong>
                    </span>
                    <span>{t.dateLabel}: {ticket.createdAt}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </section>
      </div>
    </main>
  )
}

export default Ticket
