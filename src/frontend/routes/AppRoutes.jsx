import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import ChatWidget from '../components/ChatWidget'
import Footer from '../components/Footer'
import Header from '../components/Header'
import About from '../pages/About'
import Chatbot from '../pages/Chatbot'
import Home from '../pages/Home'
import HotelDetail from '../pages/HotelDetail'
import Login from '../pages/Login'
import Promotions from '../pages/Promotions'
import PromotionDetail from '../pages/PromotionDetail'
import Register from '../pages/Register'
import SearchResults from '../pages/SearchResults'
import Ticket from '../pages/Ticket'
import Regulations from '../pages/Regulations'
import StaffTickets from '../pages/StaffTickets'
import AdminStaff from '../pages/AdminStaff'
import { useAuth } from '../context/AuthContext'
import '../styles/routes/AppRoutes.css'

function AppLayout({ children }) {
  const { pathname } = useLocation()
  const hideFloatingChat = pathname === '/chat' || pathname === '/chatbot'

  return (
    <div className="app-routes">
      <Header />
      <main className="app-routes__main">{children}</main>
      <Footer />
      {!hideFloatingChat && <ChatWidget />}
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
    <Routes>
      <Route path="/" element={<AppLayout><Home /></AppLayout>} />
      <Route path="/about" element={<AppLayout><About /></AppLayout>} />
      <Route path="/search" element={<AppLayout><SearchResults /></AppLayout>} />
      <Route path="/hotels/:hotelId" element={<AppLayout><HotelDetail /></AppLayout>} />
      <Route path="/regulations" element={<AppLayout><Regulations /></AppLayout>} />
      <Route path="/promotions" element={<AppLayout><Promotions /></AppLayout>} />
      <Route path="/promotions/:promotionId" element={<AppLayout><PromotionDetail /></AppLayout>} />
      <Route path="/chat" element={<AppLayout><Chatbot /></AppLayout>} />
      <Route path="/chatbot" element={<AppLayout><Chatbot /></AppLayout>} />
      <Route path="/support" element={<AppLayout><Ticket /></AppLayout>} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/staff/tickets" element={<AppLayout><RequireRole roles={['staff', 'admin']}><StaffTickets /></RequireRole></AppLayout>} />
      <Route path="/admin/staff" element={<AppLayout><RequireRole roles={['admin']}><AdminStaff /></RequireRole></AppLayout>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default AppRoutes
