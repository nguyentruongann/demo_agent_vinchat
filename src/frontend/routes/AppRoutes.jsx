import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import ChatWidget from '../components/ChatWidget'
import Footer from '../components/Footer'
import Header from '../components/Header'
import About from '../pages/About'
import Auth from '../pages/Auth'
import Chatbot from '../pages/Chatbot'
import Home from '../pages/Home'
import HotelDetail from '../pages/HotelDetail'
import Promotions from '../pages/Promotions'
import PromotionDetail from '../pages/PromotionDetail'
import SearchResults from '../pages/SearchResults'
import Ticket from '../pages/Ticket'
import Regulations from '../pages/Regulations'
import Faq from '../pages/Faq'
import ExperienceDetail from '../pages/ExperienceDetail'
import Experiences from '../pages/Experiences'
import MeetingDetail from '../pages/MeetingDetail'
import Meetings from '../pages/Meetings'
import StaffTickets from '../pages/StaffTickets'
import AdminStaff from '../pages/AdminStaff'
import { useAuth } from '../context/AuthContext'
import '../styles/routes/AppRoutes.css'

function ScrollToTop() {
  const { pathname, search, hash } = useLocation()

  useEffect(() => {
    if (hash) return
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [pathname, search, hash])

  return null
}

function AppLayout({ children }) {
  const { pathname } = useLocation()
  const isChatPage = pathname === '/chat' || pathname === '/chatbot'

  return (
    <div className={`app-routes ${isChatPage ? 'app-routes--chat' : ''}`}>
      <Header />
      <main className="app-routes__main">{children}</main>
      {!isChatPage && <Footer />}
      {!isChatPage && <ChatWidget />}
    </div>
  )
}


function RequireRole({ roles, children }) {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ padding: 40 }}>Đang kiểm tra đăng nhập...</div>
  if (!user) return <Navigate to="/login" replace state={{ from: window.location.pathname }} />
  if (!roles.includes(user.role)) return <Navigate to="/" replace />
  return children
}

function AppRoutes() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<AppLayout><Home /></AppLayout>} />
        <Route path="/about" element={<AppLayout><About /></AppLayout>} />
        <Route path="/experiences" element={<AppLayout><Experiences /></AppLayout>} />
        <Route path="/experiences/attractions/:attractionId" element={<AppLayout><ExperienceDetail type="attraction" /></AppLayout>} />
        <Route path="/experiences/golf/:courseId" element={<AppLayout><ExperienceDetail type="golf" /></AppLayout>} />
        <Route path="/meetings" element={<AppLayout><Meetings /></AppLayout>} />
        <Route path="/meetings/:venueId" element={<AppLayout><MeetingDetail /></AppLayout>} />
        <Route path="/search" element={<AppLayout><SearchResults /></AppLayout>} />
        <Route path="/hotels/:hotelId" element={<AppLayout><HotelDetail /></AppLayout>} />
        <Route path="/regulations" element={<AppLayout><Regulations /></AppLayout>} />
        <Route path="/faq" element={<AppLayout><Faq /></AppLayout>} />
        <Route path="/promotions" element={<AppLayout><Promotions /></AppLayout>} />
        <Route path="/promotions/:promotionId" element={<AppLayout><PromotionDetail /></AppLayout>} />
        <Route path="/chat" element={<AppLayout><Chatbot /></AppLayout>} />
        <Route path="/chatbot" element={<AppLayout><Chatbot /></AppLayout>} />
        <Route path="/support" element={<AppLayout><Ticket /></AppLayout>} />
        <Route path="/login" element={<Auth initialTab="login" />} />
        <Route path="/register" element={<Auth initialTab="register" />} />
        <Route path="/staff/tickets" element={<AppLayout><RequireRole roles={['staff', 'admin']}><StaffTickets /></RequireRole></AppLayout>} />
        <Route path="/admin/staff" element={<AppLayout><RequireRole roles={['admin']}><AdminStaff /></RequireRole></AppLayout>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}

export default AppRoutes
