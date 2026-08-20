const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const CHAT_SESSION_KEY = 'vinpearl_chat_session_v2';

function currentLanguage() {
  const value = localStorage.getItem('site_language');
  return ['en', 'vi', 'ko', 'ja', 'zh'].includes(value) ? value : 'en';
}

async function apiFetch(path, options = {}) {
  const url = new URL(`${API_BASE_URL}${path}`, globalThis.location.origin);
  if ((options.method || 'GET').toUpperCase() === 'GET') {
    url.searchParams.set('lang', currentLanguage());
  }
  return fetch(url.toString(), options);
}

function createSessionId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  return `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function currentPageBootId() {
  // performance.timeOrigin changes after a real page reload, but remains stable
  // across normal SPA navigation and Vite HMR. That gives one conversation
  // session per loaded chat page without persisting forever in localStorage.
  return String(Math.round(globalThis.performance?.timeOrigin || Date.now()));
}

const CHAT_MESSAGES_KEY = 'vinpearl_chat_messages_v2';

function readStoredSession() {
  try {
    const raw = sessionStorage.getItem(CHAT_SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStoredSession(sessionId) {
  if (!sessionId) return null;
  try {
    sessionStorage.setItem(
      CHAT_SESSION_KEY,
      JSON.stringify({
        sessionId,
        pageBootId: currentPageBootId(),
      }),
    );
  } catch {
    // sessionStorage may be unavailable in restricted browser contexts.
  }
  return sessionId;
}

export function setChatSessionId(sessionId) {
  return writeStoredSession(sessionId);
}

export function clearChatSessionId() {
  try {
    sessionStorage.removeItem(CHAT_SESSION_KEY);
  } catch {
    // sessionStorage may be unavailable in restricted browser contexts.
  }
}

export function getChatSessionId() {
  const stored = readStoredSession();
  if (stored?.sessionId) {
    return stored.sessionId;
  }
  return writeStoredSession(createSessionId());
}

export function startNewChatSession() {
  clearStoredMessages();
  return writeStoredSession(createSessionId());
}

export function loadStoredMessages() {
  try {
    const raw = sessionStorage.getItem(CHAT_MESSAGES_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveStoredMessages(messages) {
  try {
    sessionStorage.setItem(CHAT_MESSAGES_KEY, JSON.stringify(messages));
  } catch (e) {
    console.warn('Could not save chat messages to sessionStorage:', e);
  }
}

export function clearStoredMessages() {
  try {
    sessionStorage.removeItem(CHAT_MESSAGES_KEY);
  } catch {
    // ignore
  }
}

// Backward-compatible name used by existing UI code. Starting a new chat must
// preserve the previous authenticated conversation in PostgreSQL so it remains
// available in Chat History; only the active client-side session ID is rotated.
export async function resetChatSession() {
  return startNewChatSession();
}

export async function fetchAboutInfo() {
  const res = await apiFetch('/api/v1/about');
  if (!res.ok) throw new Error(`About API returned status ${res.status}`);
  return res.json();
}

/**
 * Fetch FAQs from PostgreSQL-backed API.
 * @param {{q?: string, category?: string, destination?: string, page?: number, pageSize?: number}} [filters]
 * @returns {Promise<import('../types').FaqListResponse>}
 */
export async function fetchFaqs(filters = {}) {
  const params = new URLSearchParams();
  if (filters.q) params.set('q', filters.q);
  if (filters.category) params.set('category', filters.category);
  if (filters.destination) params.set('destination', filters.destination);
  params.set('page', String(filters.page || 1));
  params.set('page_size', String(filters.pageSize || 20));

  const query = params.toString();
  const res = await apiFetch(`/api/v1/faqs${query ? `?${query}` : ''}`);
  if (!res.ok) throw new Error(`FAQ API returned status ${res.status}`);
  return res.json();
}

export async function fetchDestinations() {
  const res = await apiFetch('/api/v1/catalog/destinations');
  if (!res.ok) throw new Error(`Destinations API returned status ${res.status}`);
  return res.json();
}

export async function fetchHotels(filters = {}) {
  const params = new URLSearchParams();
  if (filters.destination && filters.destination !== 'all') params.set('destination', filters.destination);
  if (filters.type && filters.type !== 'all') params.set('kind', filters.type.toLowerCase());
  if (filters.minGuests) params.set('min_guests', String(filters.minGuests));
  if (filters.maxPrice) params.set('max_price', String(filters.maxPrice));
  params.set('page', String(filters.page || 1));
  params.set('page_size', String(filters.pageSize || 24));
  const res = await apiFetch(`/api/v1/catalog/properties?${params.toString()}`);
  if (!res.ok) throw new Error(`Properties API returned status ${res.status}`);
  return res.json();
}

export async function fetchHotelById(id) {
  const res = await apiFetch(`/api/v1/catalog/properties/${encodeURIComponent(id)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Property API returned status ${res.status}`);
  return res.json();
}

export async function fetchAttractions(filters = {}) {
  const params = new URLSearchParams();
  if (filters.destination && filters.destination !== 'all') params.set('destination', filters.destination);
  if (filters.kind && filters.kind !== 'all') params.set('kind', filters.kind);
  if (filters.language) params.set('lang', filters.language);
  params.set('page', String(filters.page || 1));
  params.set('page_size', String(filters.pageSize || 12));
  const res = await apiFetch(`/api/v1/discovery/attractions?${params.toString()}`);
  if (!res.ok) throw new Error(`Attractions API returned status ${res.status}`);
  return res.json();
}

export async function fetchAttractionById(id, language = 'en') {
  const params = new URLSearchParams({ lang: language });
  const res = await apiFetch(`/api/v1/discovery/attractions/${encodeURIComponent(id)}?${params}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Attraction API returned status ${res.status}`);
  return res.json();
}

export async function fetchGolfCourses(filters = {}) {
  const params = new URLSearchParams();
  if (filters.destination && filters.destination !== 'all') params.set('destination', filters.destination);
  if (filters.language) params.set('lang', filters.language);
  params.set('page', String(filters.page || 1));
  params.set('page_size', String(filters.pageSize || 12));
  const res = await apiFetch(`/api/v1/discovery/golf?${params.toString()}`);
  if (!res.ok) throw new Error(`Golf API returned status ${res.status}`);
  return res.json();
}

export async function fetchGolfCourseById(id, language = 'en') {
  const params = new URLSearchParams({ lang: language });
  const res = await apiFetch(`/api/v1/discovery/golf/${encodeURIComponent(id)}?${params}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Golf detail API returned status ${res.status}`);
  return res.json();
}

export async function fetchMiceVenues(filters = {}) {
  const params = new URLSearchParams();
  if (filters.destination && filters.destination !== 'all') params.set('destination', filters.destination);
  if (filters.layout && filters.layout !== 'all') params.set('layout', filters.layout);
  if (filters.minCapacity) params.set('min_capacity', String(filters.minCapacity));
  if (filters.language) params.set('lang', filters.language);
  params.set('page', String(filters.page || 1));
  params.set('page_size', String(filters.pageSize || 12));
  const res = await apiFetch(`/api/v1/discovery/mice?${params.toString()}`);
  if (!res.ok) throw new Error(`MICE API returned status ${res.status}`);
  return res.json();
}

export async function fetchMiceVenueById(id, language = 'en') {
  const params = new URLSearchParams({ lang: language });
  const res = await apiFetch(`/api/v1/discovery/mice/${encodeURIComponent(id)}?${params}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`MICE detail API returned status ${res.status}`);
  return res.json();
}

/**
 * Fetch promotions from the PostgreSQL-backed API.
 * @param {{destination?: string, status?: string, search?: string}} [filters]
 * @returns {Promise<{items: import('../types').Promotion[], total: number}>}
 */
export async function fetchPromotions(filters = {}) {
  const params = new URLSearchParams();
  if (filters.destination && filters.destination !== 'all') {
    params.set('destination', filters.destination);
  }
  if (filters.status && filters.status !== 'all') {
    params.set('status', filters.status);
  }
  if (filters.search) {
    params.set('search', filters.search);
  }
  params.set('page_size', String(filters.pageSize || 12));

  const query = params.toString();
  const res = await apiFetch(`/api/v1/promotions${query ? `?${query}` : ''}`);
  if (!res.ok) {
    throw new Error(`Promotions API returned status ${res.status}`);
  }

  const payload = await res.json();
  if (Array.isArray(payload)) {
    return { items: payload, total: payload.length };
  }

  return {
    items: Array.isArray(payload.items) ? payload.items : [],
    total: Number(payload.total ?? payload.items?.length ?? 0),
    translationFallback: Boolean(payload.translation_fallback),
  };
}

export async function fetchPromotionById(id) {
  const res = await apiFetch(`/api/v1/promotions/${encodeURIComponent(id)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Promotion Detail API returned status ${res.status}`);
  return res.json();
}

export async function sendChatMessage(prompt, language = 'en', options = {}) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/chat`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      signal: options.signal,
      body: JSON.stringify({
        message: prompt,
        session_id: options.sessionId || getChatSessionId(),
        user_id: null,
      }),
    });

    if (!res.ok) {
      const errorPayload = await res.json().catch(() => null);
      const detail = typeof errorPayload?.detail === 'string'
        ? errorPayload.detail
        : `Chat API returned status ${res.status}`;
      throw new Error(detail);
    }

    const result = await res.json();
    if (result.session_id) setChatSessionId(result.session_id);
    return {
      id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      sender: 'assistant',
      text: result.answer,
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      }),
      language: result.language || language,
      route: result.route,
      ticketId: result.ticket_id,
      sessionId: result.session_id,
      sources: result.sources || [],
      relatedHotels: [],
    };
  } catch (e) {
    // A user-initiated stop must stay a cancellation. Do not convert AbortError
    // into a local fallback response, otherwise the UI appears to ignore Stop.
    if (e?.name === 'AbortError') throw e;

    if (import.meta.env.VITE_ENABLE_CHAT_FALLBACK === 'true') {
      console.warn('Chat API failed, using local fallback:', e);
      return generateFallbackResponse(prompt, language);
    }

    throw e;
  }
}

export async function fetchChatSessions(limit = 50) {
  if (!getAuthToken()) return [];
  const safeLimit = Math.max(1, Math.min(Number(limit) || 50, 100));
  return apiJson(`/api/v1/chat/sessions?limit=${safeLimit}`);
}

export async function fetchChatSessionMessages(sessionId) {
  if (!getAuthToken()) {
    throw new Error('Authentication is required to load chat history.');
  }
  return apiJson(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages`);
}

export async function deleteChatSession(sessionId) {
  if (!getAuthToken()) return null;
  return apiJson(`/api/v1/chat/${encodeURIComponent(sessionId)}/history`, {
    method: 'DELETE',
  });
}

export async function submitSupportTicket(ticketData) {
  const payload = await apiJson('/api/v1/tickets', {
    method: 'POST',
    body: JSON.stringify({
      customer_name: ticketData.customerName,
      email: ticketData.email || null,
      phone: ticketData.phone || null,
      language: String(ticketData.language || 'vi').toLowerCase(),
      subject: ticketData.subject || 'General inquiry',
      content: ticketData.content,
    }),
  });
  return {
    id: payload.id,
    customerName: payload.customer_name,
    email: payload.email,
    phone: payload.phone,
    language: payload.language,
    subject: payload.subject,
    content: payload.content,
    status: payload.status === 'open' ? 'Pending' : payload.status === 'in_progress' ? 'Processing' : payload.status === 'resolved' ? 'Resolved' : 'Closed',
    createdAt: new Date(payload.created_at).toLocaleDateString('vi-VN'),
  };
}

export async function fetchTickets() {
  if (!getAuthToken()) return [];
  const rows = await apiJson('/api/v1/tickets/mine');
  return rows.map((payload) => ({
    id: payload.id,
    customerName: payload.customer_name,
    email: payload.email,
    phone: payload.phone,
    language: payload.language,
    subject: payload.subject,
    content: payload.content,
    status: payload.status === 'open' ? 'Pending' : payload.status === 'in_progress' ? 'Processing' : payload.status === 'resolved' ? 'Resolved' : 'Closed',
    createdAt: new Date(payload.created_at).toLocaleDateString('vi-VN'),
  }));
}

function generateFallbackResponse(prompt, language) {
  const lower = prompt.toLowerCase();
  const isVietnamese = String(language).toLowerCase() === 'vi';
  let text = '';
  let relatedHotels = [];

  // Check if query is about regulations, bank accounts, booking contacts, check-in times
  const isRegulationsQuery =
    lower.includes('nhận phòng') ||
    lower.includes('trả phòng') ||
    lower.includes('check-in') ||
    lower.includes('check in') ||
    lower.includes('check-out') ||
    lower.includes('check out') ||
    lower.includes('tài khoản') ||
    lower.includes('thanh toán') ||
    lower.includes('account') ||
    lower.includes('swift') ||
    lower.includes('sđt') ||
    lower.includes('liên hệ') ||
    lower.includes('quy định') ||
    lower.includes('regulation') ||
    lower.includes('policy');

  if (isRegulationsQuery) {
    if (lower.includes('nhận phòng') || lower.includes('check-in') || lower.includes('check in') || lower.includes('trả phòng') || lower.includes('check-out')) {
      text = isVietnamese
        ? "Theo Quy định nhận và trả phòng của Vinpearl:\n• Thời gian nhận phòng (Check-in): 14:00 (Vinpearl Luxury Nha Trang) / 15:00 (các khách sạn khác).\n• Thời gian trả phòng (Check-out): Không quá 12:00 giờ trưa.\n• Phí nhận phòng sớm / trả phòng muộn: Tính 50% - 100% giá phòng tùy theo mốc thời gian cụ thể."
        : "According to Vinpearl Check-in & Check-out Regulations:\n• Check-in time: 14:00 (Vinpearl Luxury Nha Trang) / 15:00 (Other hotels).\n• Check-out time: No later than 12:00 noon.\n• Early check-in / late check-out fees: 50% - 100% of room rate depending on the timeframe.";
    } else if (lower.includes('tài khoản') || lower.includes('account') || lower.includes('swift') || lower.includes('ngân hàng') || lower.includes('bank')) {
      text = isVietnamese
        ? "Thông tin tài khoản thanh toán Vinpearl (Phụ lục 02):\n• Vinpearl Resort & Spa Hạ Long: Vietcombank Quảng Ninh - STK: 0141005558899 (VND)\n• Vinpearl Resort Nha Trang: Techcombank - STK: 19127850127299 (VND)\n• Vinpearl Resort & Spa Phú Quốc: Vietcombank Hoàng Mai - STK: 0931005550015 (VND)"
        : "Vinpearl Payment Accounts Info (Appendix 02):\n• Vinpearl Resort & Spa Ha Long: Vietcombank Quang Ninh - Acc: 0141005558899 (VND)\n• Vinpearl Resort Nha Trang: Techcombank - Acc: 19127850127299 (VND)\n• Vinpearl Resort & Spa Phu Quoc: Vietcombank Hoang Mai - Acc: 0931005550015 (VND)";
    } else if (lower.includes('sđt') || lower.includes('liên hệ') || lower.includes('phone') || lower.includes('email') || lower.includes('contact')) {
      text = isVietnamese
        ? "Danh sách liên lạc đặt phòng các cơ sở Vinpearl (Phụ lục 01):\n• Nha Trang: res.VPLRNT@vinpearl.com | SĐT: 84-258 359 8900\n• Phú Quốc: res.VPRSPQ@vinpearl.com | SĐT: 84-297 355 0550\n• Hạ Long: res.VPRSHL@vinpearl.com | SĐT: 84-203 385 7858\n• Đà Nẵng - Hội An: res.VPRGNHA@vinpearl.com | SĐT: 84-235 367 6888"
        : "Vinpearl Booking Contact Info (Appendix 01):\n• Nha Trang: res.VPLRNT@vinpearl.com | Phone: 84-258 359 8900\n• Phu Quoc: res.VPRSPQ@vinpearl.com | Phone: 84-297 355 0550\n• Ha Long: res.VPRSHL@vinpearl.com | Phone: 84-203 385 7858\n• Da Nang - Hoi An: res.VPRGNHA@vinpearl.com | Phone: 84-235 367 6888";
    } else {
      text = isVietnamese
        ? "Tổng hợp quy định Vinpearl:\nHệ thống quy định Vinpearl bao gồm 7 tài liệu chính về Điều khoản chung, Quy định nhận trả phòng, Quy định thanh toán, Chính sách bảo mật và Quy chế giải quyết tranh chấp."
        : "Vinpearl Regulations Summary:\nVinpearl regulations portfolio includes 7 official documents covering General Terms, Check-in/Check-out rules, Payment regulations, Privacy policy, and Dispute resolution procedures.";
    }
  } else if (lower.includes('budget') || lower.includes('10m') || lower.includes('price')) {
    text = isVietnamese
      ? "Với ngân sách khoảng 10 triệu VNĐ, tôi đề xuất gói nghỉ dưỡng 3 ngày 2 đêm tại VinTravel Grand Resort Phú Quốc hoặc Biệt thự biển Nha Trang bao gồm ăn sáng và vé vui chơi:"
      : "For a budget around 10M VND, I recommend a 3D2N stay at VinTravel Grand Resort Phú Quốc or our Luxury Ocean Villas in Nha Trang including breakfast and park tickets:";
    relatedHotels = [];
  } else if (lower.includes('nha trang') || lower.includes('3 days') || lower.includes('3 ngày')) {
    text = isVietnamese
      ? "Lịch trình 3 ngày 2 đêm gợi ý tại Nha Trang:\n• Ngày 1: Đón cáp treo qua đảo, nhận Biệt thự biển & ăn tối hải sản.\n• Ngày 2: Vui chơi thỏa thích tại Công viên VinWonders & trị liệu Spa Akoya.\n• Ngày 3: Thưởng thức buffet sáng, tắm biển riêng & tiễn sân bay."
      : "Here is a recommended 3D2N Nha Trang itinerary:\n• Day 1: Cable car arrival, Ocean Villa check-in & seafood dining.\n• Day 2: Unlimited fun at VinWonders Theme Park & Akoya Spa treatments.\n• Day 3: Oceanfront breakfast buffet, private beach relaxing & airport transfer.";
    relatedHotels = [];
  } else if (lower.includes('children') || lower.includes('kids') || lower.includes('trẻ em') || lower.includes('family')) {
    text = isVietnamese
      ? "Chính sách gia đình tại các khu nghỉ dưỡng VinTravel vô cùng ưu đãi: Trẻ em dưới 4 tuổi được miễn phí hoàn toàn. Có CLB Trẻ em (Kid's Club) miễn phí và hồ bơi nông an toàn."
      : "Our family policies are designed for pure peace of mind: Children under 4 stay free of charge. Resorts feature dedicated Kid's Clubs, shallow splash pools, and professional babysitting.";
    relatedHotels = [];
  } else {
    text = isVietnamese
      ? `Cảm ơn bạn đã hỏi! Tôi đã tìm kiếm trong hệ thống khu nghỉ dưỡng VinTravel. Khu nghỉ dưỡng VinTravel Grand Phú Quốc và Biệt thự Hòn Tre Nha Trang hoàn toàn phù hợp với tiêu chuẩn thượng lưu của bạn.`
      : `Thank you for asking! I have analyzed our luxury resort portfolio. VinTravel Grand Resort & Spa in Phú Quốc and our Ocean Villas in Nha Trang fit your preferences seamlessly.`;
    relatedHotels = [];
  }

  return {
    id: `msg-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
    sender: 'assistant',
    text,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    language,
    relatedHotels
  };
}

// ---------------------------------------------------------------------------
// Authentication / staff APIs
// ---------------------------------------------------------------------------
const AUTH_TOKEN_KEY = 'vinpearl_auth_token';

export function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token) {
  if (token) localStorage.setItem(AUTH_TOKEN_KEY, token);
  else localStorage.removeItem(AUTH_TOKEN_KEY);
}

function authHeaders(extra = {}) {
  const token = getAuthToken();
  return {
    ...extra,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function apiJson(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: authHeaders({
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    }),
  });
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    let detail = payload?.detail || `API returned status ${res.status}`;
    if (Array.isArray(detail)) detail = detail.map((item) => item.msg).join('; ');
    throw new Error(detail);
  }
  return payload;
}

export async function registerAccount({ name, email, phone, password, locale = 'vi' }) {
  const payload = await apiJson('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      name,
      email: email || null,
      phone: phone || null,
      password,
      locale,
    }),
  });
  setAuthToken(payload.access_token);
  return payload.user;
}

export async function loginAccount(identifier, password) {
  const payload = await apiJson('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ identifier, password }),
  });
  setAuthToken(payload.access_token);
  return payload.user;
}

export async function fetchCurrentUser() {
  if (!getAuthToken()) return null;
  try {
    return await apiJson('/api/v1/auth/me');
  } catch {
    setAuthToken(null);
    return null;
  }
}

export async function logoutAccount() {
  try {
    if (getAuthToken()) await apiJson('/api/v1/auth/logout', { method: 'POST' });
  } finally {
    setAuthToken(null);
  }
}

export async function fetchStaffTickets(status = '') {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  return apiJson(`/api/v1/staff/tickets${query}`);
}

export async function updateStaffTicket(ticketId, changes) {
  return apiJson(`/api/v1/staff/tickets/${encodeURIComponent(ticketId)}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  });
}

export async function fetchStaffAccounts() {
  return apiJson('/api/v1/auth/staff');
}

export async function createStaffAccount(data) {
  return apiJson('/api/v1/auth/staff', {
    method: 'POST',
    body: JSON.stringify({
      name: data.name,
      email: data.email || null,
      phone: data.phone || null,
      password: data.password,
      role: data.role || 'staff',
      locale: data.locale || 'vi',
    }),
  });
}

export async function updateStaffAccount(userId, changes) {
  return apiJson(`/api/v1/auth/staff/${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  });
}
