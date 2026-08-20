import { useEffect, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FileText, Search } from 'lucide-react'
import regulationsData from '../../data_crawl/Regulations/vinpearl_regulations.json'
import { useLanguage } from '../context/LanguageContext'
import '../styles/pages/Regulations.css'

const PREFERRED_DOC_TITLE = 'General Terms'
const PREFERRED_DOC_ID = regulationsData.documents?.find(
  (doc) => doc.title === PREFERRED_DOC_TITLE,
)?.id
const translatedRegulationModules = import.meta.glob(
  '../../data_crawl/Regulations/translations/*.json',
  { eager: true },
)
const translatedRegulations = Object.values(translatedRegulationModules).reduce(
  (translations, mod) => {
    const doc = mod.default
    const language = String(doc?.language || '').toLowerCase()

    if (language && doc?.id) {
      translations[language] ||= {}
      translations[language][doc.id] = doc
    }

    return translations
  },
  {},
)

const titleMap = {
  vi: {
    'General Terms': 'Điều khoản chung',
    'General regulations': 'Quy định chung',
    'Payment regulations': 'Quy định thanh toán',
    'Regulations on confirmation of booking information': 'Quy định xác nhận thông tin đặt phòng',
    'Dispute resolution policy': 'Chính sách giải quyết tranh chấp',
    'PRIVACY POLICY (Personal Data Protection Policy)': 'Chính sách bảo vệ dữ liệu cá nhân',
    'Regulations to prevent money laundering and ensure transparency':
      'Quy chế phòng chống rửa tiền và đảm bảo minh bạch',
  },
  en: {
    'General Terms': 'General Terms',
    'General regulations': 'General Regulations',
    'Payment regulations': 'Payment Regulations',
    'Regulations on confirmation of booking information': 'Regulations on Booking Confirmation',
    'Dispute resolution policy': 'Dispute Resolution Policy',
    'PRIVACY POLICY (Personal Data Protection Policy)': 'Privacy Policy',
    'Regulations to prevent money laundering and ensure transparency':
      'Regulations on Anti-Money Laundering & Transparency',
  },
}

function getDocTitle(doc, language = 'en') {
  if (!doc) return language === 'vi' ? 'Quy định' : 'Regulations'
  const langKey = language === 'vi' ? 'vi' : 'en'
  return titleMap[langKey]?.[doc.title] || doc.title
}

function normalizeCell(cell) {
  return cell.trim().replace(/\s+/g, ' ')
}

function getTableKind(row) {
  const cells = row.split('|').map(normalizeCell)
  const normalized = cells.join(' | ')

  if (/Facility name|Beneficiary unit|Account number|Swift code|Tên cơ sở|Đơn vị thụ hưởng|Số tài khoản/i.test(normalized)) {
    return 'accounts'
  }

  if (/Booking email|Booking phone|Email đặt phòng|SĐT đặt phòng/i.test(normalized)) {
    return 'booking'
  }

  if (/Category|Regulations|Notes|Hạng mục|Quy định|Ghi chú/i.test(normalized)) {
    return 'checkIn'
  }

  if (cells.length >= 7) {
    return 'accounts'
  }

  if (cells.length >= 4 && /@|email/i.test(normalized)) {
    return 'booking'
  }

  return 'generic'
}

function buildContentBlocks(content = []) {
  const blocks = []
  let tableRows = []
  let tableKind = ''

  const flushTable = () => {
    if (tableRows.length > 0) {
      blocks.push({ type: 'table', rows: tableRows })
      tableRows = []
      tableKind = ''
    }
  }

  content.forEach((item) => {
    if (item.includes('|')) {
      const nextKind = getTableKind(item)
      if (tableRows.length > 0 && nextKind !== 'generic' && tableKind !== nextKind) {
        flushTable()
      }

      if (!tableKind || tableKind === 'generic') {
        tableKind = nextKind
      }

      if (
        tableRows.length === 0 &&
        nextKind === 'accounts' &&
        !/Facility name|Tên cơ sở|Swift code/i.test(item)
      ) {
        tableRows.push('Number | Facility name | Beneficiary unit | Account number | Bank | Address | Swift code')
      }

      tableRows.push(item)
      return
    }

    flushTable()

    blocks.push({ type: 'paragraph', text: item })
  })

  flushTable()

  return blocks
}

const textTranslationMap = {
  vi: {
    'General content': 'Nội dung chung',
    'ARTICLE 1. DEFINITIONS': 'ĐIỀU 1. ĐỊNH NGHĨA',
    'ARTICLE 2. GENERAL PROVISIONS': 'ĐIỀU 2. ĐIỀU KHOẢN CHUNG',
    'ARTICLE 3. CHECK IN AND CHECK OUT REGULATIONS:': 'ĐIỀU 3. QUY ĐỊNH NHẬN VÀ TRẢ PHÒNG:',
    'ARTICLE 4. REGULATIONS ON ROOM CHARGES AND SERVICES': 'ĐIỀU 4. QUY ĐỊNH VỀ GIÁ PHÒNG VÀ DỊCH VỤ',
    'ARTICLE 5. CANCELLATION AND MODIFICATION REGULATIONS': 'ĐIỀU 5. QUY ĐỊNH HỦY VÀ ĐỔI ĐẶT PHÒNG',
    'ARTICLE 6. RESPONSIBILITIES OF THE PARTIES': 'ĐIỀU 6. TRÁCH NHIỆM CỦA CÁC BÊN',
    'ARTICLE 7. FORCE MAJEURE': 'ĐIỀU 7. TRƯỜNG HỢP BẤT KHẢ KHÁNG',
    'ARTICLE 8. GOVERNING LAW AND DISPUTE RESOLUTION': 'ĐIỀU 8. LUẬT ÁP DỤNG VÀ GIẢI QUYẾT TRANH CHẤP',
    'ARTICLE 9. DURATION AND TERMINATION OF CONTRACT': 'ĐIỀU 9. THỜI HẠN VÀ CHẤM DỨT HỢP ĐỒNG',
    'ARTICLE 10. NOTICES AND COMMUNICATIONS': 'ĐIỀU 10. THÔNG BÁO VÀ LIÊN LẠC',
    'ARTICLE 11. TECHNICAL ERRORS': 'ĐIỀU 11. LỖI KỸ THUẬT',
    '1. Check-in and check-out time': '1. Thời gian nhận phòng và trả phòng',
    'Unless otherwise notified and/or confirmed by the Hotel, check-in and check-out regulations apply as follows:':
      'Trừ khi có thông báo và/hoặc xác nhận khác từ Khách Sạn, quy định về nhận và trả phòng được áp dụng như sau:',
  },
}

function translateText(text, language = 'en') {
  if (language === 'vi') {
    return textTranslationMap.vi[text?.trim()] || text
  }
  return text
}

function InlineText({ text }) {
  const parts = String(text).split(/(\bVinpearl\b|https?:\/\/[^\s]+|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/gi)

  return parts.map((part, index) => {
    if (/^https?:\/\//i.test(part)) {
      return (
        <a key={index} href={part} target="_blank" rel="noreferrer">
          {part}
        </a>
      )
    }

    if (/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/i.test(part)) {
      return (
        <a key={index} href={`mailto:${part}`} className="regulations-email-link">
          {part}
        </a>
      )
    }

    if (/^Vinpearl$/i.test(part)) {
      return <strong key={index}>{part}</strong>
    }

    return part
  })
}

const checkInCellMap = {
  vi: {
    'Check-in time': 'Thời gian nhận phòng',
    'Check-out time': 'Thời gian trả phòng',
    'Early check-in fee before 6:00 am': 'Phí nhận phòng sớm trước 6:00 giờ sáng',
    'Early check-in fee from 6:00 am to 12:00 noon': 'Phí nhận phòng sớm từ 6:00 giờ sáng đến 12:00 giờ trưa',
    'Early check-in fee is from 6:00 am to 12:00 noon': 'Phí nhận phòng sớm từ 6:00 giờ sáng đến 12:00 giờ trưa',
    'Late check-out fee from after 12:00 to 18:00': 'Phí trả phòng muộn từ sau 12:00 giờ đến 18:00 giờ',
    'Late check-out fee after 18:00': 'Phí trả phòng muộn sau 18:00 giờ',
    '- Vinpearl Luxury Nha Trang: 14:00 on arrival - Other hotels: 15:00 on arrival':
      '- Vinpearl Luxury Nha Trang: 14:00 giờ ngày Khách đến\n\n- Các khách sạn còn lại: 15:00 giờ ngày Khách đến',
    'No later than 12:00 noon on check-out date': 'Không quá 12:00 giờ trưa ngày trả phòng',
    '100% Price for 1 room night': '100% Giá 1 đêm phòng',
    '50% of Room Package Price includes breakfast. Meals and guest services (if needed) will be paid at the published price at the hotel.':
      '50% Giá Gói Phòng bao gồm bữa sáng. Các bữa ăn và dịch vụ khách (nếu có nhu cầu cần sử dụng) sẽ thanh toán theo giá công bố tại khách sạn.',
    '50% of Room Price does not include meals & other services. Meals and incidental services (if needed) will be paid at the published price at the hotel.':
      '50% Giá Phòng không bao gồm bữa ăn & các dịch vụ khác. Các bữa ăn và dịch vụ phát sinh (nếu có nhu cầu sử dụng) sẽ thanh toán theo giá công bố tại khách sạn.',
  },
}

function translateCheckInCell(cell, language = 'en') {
  if (language === 'vi') {
    return checkInCellMap.vi[cell?.trim()] || cell
  }
  return cell
}

const tableHeaderMap = {
  vi: {
    Category: 'Hạng mục',
    Regulations: 'Quy định',
    Notes: 'Ghi chú',
    Number: 'Số',
    No: 'Số',
    'Facility name': 'Tên cơ sở',
    'Beneficiary unit': 'Đơn vị thụ hưởng',
    'Account number': 'Số tài khoản',
    Bank: 'Ngân hàng',
    Address: 'Địa chỉ',
    'Swift code': 'Swift code',
    STT: 'STT',
    'Khu vực': 'Khu vực',
    'Khách sạn': 'Khách sạn',
    'Email đặt phòng': 'Email đặt phòng',
    'SĐT đặt phòng': 'SĐT đặt phòng',
  },
  en: {
    Category: 'Category',
    Regulations: 'Regulations',
    Notes: 'Notes',
    Number: 'Number',
    No: 'No.',
    'Facility name': 'Facility name',
    'Beneficiary unit': 'Beneficiary unit',
    'Account number': 'Account number',
    Bank: 'Bank',
    Address: 'Address',
    'Swift code': 'Swift code',
    STT: 'No.',
    'Khu vực': 'Region',
    'Khách sạn': 'Hotel',
    'Email đặt phòng': 'Booking email',
    'SĐT đặt phòng': 'Booking phone number',
    'Tên cơ sở': 'Facility name',
    'Đơn vị thụ hưởng': 'Beneficiary unit',
    'Số tài khoản': 'Account number',
    'Ngân hàng': 'Bank',
    'Địa chỉ': 'Address',
  },
}

function translateTableHeader(cell, language = 'en') {
  return tableHeaderMap[language]?.[cell] || cell
}

function ContentTable({ rows, language, t }) {
  if (!rows || !Array.isArray(rows) || rows.length === 0) return null

  const parsedRows = rows.map((row) => row.split('|').map(normalizeCell))
  const [header, ...body] = parsedRows

  if (!header || header.length === 0) return null

  const headerText = header.join(' | ')
  const bodyText = body.flat().join(' | ')

  const isCheckInTable =
    header.some((h) => /Category|Hạng mục/i.test(h)) &&
    body.some((r) => r.some((c) => /Check-in|nhận phòng/i.test(c)))

  const isBookingContactTable =
    header.some((h) => /email|phone|điện thoại/i.test(h)) &&
    header.some((h) => /Hotel|Khách sạn/i.test(h))

  const isAccountTable =
    header.some((h) => /Tên cơ sở|Facility name/i.test(h)) ||
    header.some((h) => /Đơn vị thụ hưởng|Beneficiary/i.test(h)) ||
    header.some((h) => /Swift code/i.test(h))

  const detectedCheckInTable =
    isCheckInTable || (/Category|Hạng mục/i.test(headerText) && /Check-in|nhận phòng/i.test(bodyText))
  const detectedBookingContactTable =
    (isBookingContactTable && !isAccountTable) ||
    (/email|phone|SĐT|điện thoại/i.test(headerText) && /Hotel|Khách sạn|Khu vực/i.test(headerText))
  const detectedAccountTable =
    isAccountTable || /Tên cơ sở|Facility name|Đơn vị thụ hưởng|Beneficiary|Swift code/i.test(headerText)

  const normalizeAccountRows = (accountRows) => {
    let previous = Array(header.length).fill('')

    return accountRows.map((row) => {
      const cells = Array(header.length).fill('')
      cells[0] = row[0] || ''

      if (row.length >= header.length) {
        row.slice(1, header.length).forEach((cell, idx) => {
          cells[idx + 1] = cell || ''
        })
      } else if (row.length === 2) {
        cells[3] = row[1] || ''
      } else if (row.length === 3) {
        cells[3] = row[1] || ''
        cells[4] = row[2] || ''
      } else if (row.length === 4) {
        cells[3] = row[1] || ''
        cells[4] = row[2] || ''
        cells[6] = row[3] || ''
      } else if (row.length === 5) {
        cells[1] = row[1] || ''
        cells[2] = row[2] || ''
        cells[3] = row[3] || ''
        cells[5] = row[4] || ''
      } else {
        row.slice(1).forEach((cell, idx) => {
          cells[idx + 1] = cell || ''
        })
      }

      ;[1, 2, 4, 5, 6].forEach((idx) => {
        if (!cells[idx] && previous[idx]) {
          cells[idx] = previous[idx]
        }
      })

      previous = cells.map((cell, idx) => cell || previous[idx] || '')
      return cells
    })
  }

  let processedRows = []

  if (detectedCheckInTable && body.length >= 5) {
    let noteText = ''
    body.forEach((r) => {
      if (r[2] && r[2].trim().length > 0) {
        noteText = r[2].trim()
      }
    })

    if (language === 'vi') {
      noteText =
        'Tùy thuộc vào tình trạng phòng sẵn có và xác nhận đồng ý của Vinpearl. Các khoản phí sẽ phải thanh toán ngay tại thời điểm Vinpearl xác nhận.'
    } else if (!noteText) {
      noteText =
        "Subject to room availability and Vinpearl's confirmation. Fees will have to be paid immediately at the time of confirmation by Vinpearl."
    }

    processedRows = body.map((r, idx) => {
      const col0 = translateCheckInCell(r[0] || '', language)
      const col1 = translateCheckInCell(r[1] || '', language)
      const cells = [col0, col1, '']
      if (idx === 0) {
        return { cells, rowSpans: {}, skipCols: {} }
      }
      if (idx === 1) {
        return { cells, rowSpans: {}, skipCols: {} }
      }
      if (idx === 2) {
        cells[2] = noteText
        return { cells, rowSpans: { 2: Math.max(1, body.length - 2) }, skipCols: {} }
      }
      if (idx > 2) {
        return { cells, rowSpans: {}, skipCols: { 2: true } }
      }
      return { cells, rowSpans: {}, skipCols: {} }
    })
  } else if (detectedAccountTable && body.length > 0) {
    const normalizedBody = normalizeAccountRows(body)
    const numRows = normalizedBody.length
    const colSpansMap = normalizedBody.map(() => ({ rowSpans: {}, skipCols: {} }))

    ;[1, 2, 4, 5, 6].forEach((colIdx) => {
      let r = 0
      while (r < numRows) {
        const val = (normalizedBody[r] && normalizedBody[r][colIdx])
          ? String(normalizedBody[r][colIdx]).trim()
          : ''
        if (val) {
          let span = 1
          let k = r + 1
          while (
            k < numRows &&
            normalizedBody[k] &&
            normalizedBody[k][colIdx] &&
            String(normalizedBody[k][colIdx]).trim() === val
          ) {
            span++
            k++
          }
          if (span > 1) {
            colSpansMap[r].rowSpans[colIdx] = span
            for (let s = r + 1; s < r + span; s++) {
              if (colSpansMap[s]) {
                colSpansMap[s].skipCols[colIdx] = true
              }
            }
          }
          r = k
        } else {
          r++
        }
      }
    })

    processedRows = normalizedBody.map((cells, idx) => ({
      cells,
      rowSpans: colSpansMap[idx]?.rowSpans || {},
      skipCols: colSpansMap[idx]?.skipCols || {},
    }))
  } else if (detectedBookingContactTable && body.length > 0) {
    let currentPhone = ''
    const normalizedBody = body.map((r) => {
      const cells = [...r]
      const lastCell = cells[cells.length - 1] || ''

      if (/[\d\s-]{7,}/.test(lastCell) && !lastCell.includes('@')) {
        currentPhone = lastCell.trim()
      } else {
        if (currentPhone && cells.length < header.length) {
          cells.push(currentPhone)
        }
      }
      return cells
    })

    const numRows = normalizedBody.length
    const colSpansMap = normalizedBody.map(() => ({ rowSpans: {}, skipCols: {} }))

    ;[1, 4].forEach((colIdx) => {
      let r = 0
      while (r < numRows) {
        const val = (normalizedBody[r] && normalizedBody[r][colIdx])
          ? String(normalizedBody[r][colIdx]).trim()
          : ''
        if (val) {
          let span = 1
          let k = r + 1
          while (
            k < numRows &&
            normalizedBody[k] &&
            normalizedBody[k][colIdx] &&
            String(normalizedBody[k][colIdx]).trim() === val
          ) {
            span++
            k++
          }
          if (span > 1) {
            colSpansMap[r].rowSpans[colIdx] = span
            for (let s = r + 1; s < r + span; s++) {
              if (colSpansMap[s]) {
                colSpansMap[s].skipCols[colIdx] = true
              }
            }
          }
          r = k
        } else {
          r++
        }
      }
    })

    processedRows = normalizedBody.map((cells, idx) => ({
      cells,
      rowSpans: colSpansMap[idx]?.rowSpans || {},
      skipCols: colSpansMap[idx]?.skipCols || {},
    }))
  } else {
    processedRows = body.map((r) => ({ cells: [...r], rowSpans: {}, skipCols: {} }))
  }

  const renderCellText = (text) => {
    if (!text) return null
    if (typeof text === 'string' && text.includes('\n')) {
      const lines = text.split('\n').filter((l) => l.trim().length > 0)
      return lines.map((line, lIdx) => (
        <div key={lIdx} style={{ marginBottom: lIdx < lines.length - 1 ? 4 : 0 }}>
          <InlineText text={line} />
        </div>
      ))
    }
    return <InlineText text={text} />
  }

  return (
    <div className="regulations-table-wrapper">
      {detectedAccountTable && (
        <h4 className="regulations-appendix-heading">
          {t.regulationsPaymentAppendix}
        </h4>
      )}
      {detectedBookingContactTable && (
        <h4 className="regulations-appendix-heading">
          {t.regulationsBookingAppendix}
        </h4>
      )}
      <div className="regulations-table-shell">
        <table
        className={`regulations-table ${detectedAccountTable ? 'regulations-table--accounts' : ''} ${
          detectedCheckInTable ? 'regulations-table--checkin' : ''
        }`}
      >
        <thead>
          <tr>
            {header.map((cell, index) => (
              <th key={`${cell}-${index}`}>{translateTableHeader(cell, language)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {processedRows.map((item, rowIndex) => {
            const row = item.cells || []

            return (
              <tr key={rowIndex}>
                {row.map((cellText, colIndex) => {
                  if (item.skipCols && item.skipCols[colIndex]) return null
                  const span = (item.rowSpans && item.rowSpans[colIndex]) || 1

                  return (
                    <td
                      key={colIndex}
                      rowSpan={span}
                      style={{
                        fontWeight: colIndex === 0 ? 600 : 'normal',
                        verticalAlign: span > 1 ? 'middle' : 'top',
                        textAlign: 'left',
                      }}
                    >
                      {renderCellText(cellText)}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  </div>
)
}

function Regulations() {
  const { language: currentLanguage, t } = useLanguage()
  const language = String(currentLanguage).toLowerCase()
  const labels = {
    home: t.regulationsHome,
    pageTitle: t.termsOfService,
    categories: t.regulationsCategoryLabel,
    document: t.regulationsDocumentLabel,
  }
  const [searchParams, setSearchParams] = useSearchParams()
  const documents = useMemo(() => {
    const sourceDocuments = regulationsData.documents || []
    const translations = translatedRegulations[String(currentLanguage).toLowerCase()] || {}

    return sourceDocuments.map((doc) => translations[doc.id] || doc)
  }, [currentLanguage])
  const preferredDocument = useMemo(
    () => documents.find((doc) => doc.id === PREFERRED_DOC_ID) || documents[0],
    [documents]
  )

  const docFromUrl = searchParams.get('doc')
  const activeDocId = useMemo(() => {
    if (docFromUrl && documents.some((doc) => doc.id === docFromUrl)) {
      return docFromUrl
    }
    return preferredDocument?.id || ''
  }, [docFromUrl, documents, preferredDocument])

  const activeDoc = useMemo(() => {
    return documents.find((doc) => doc.id === activeDocId) || preferredDocument
  }, [documents, activeDocId, preferredDocument])

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [activeDocId])

  const activeIndex = documents.findIndex((doc) => doc.id === activeDoc?.id)

  function handleSelectDoc(docId) {
    setSearchParams({ doc: docId })
  }

  return (
    <div className="regulations-page">
      <div className="regulations-top-bar">
        <div className="regulations-top-bar__inner">
          <nav className="regulations-breadcrumb" aria-label="Breadcrumb">
            <Link to="/">{labels.home}</Link>
            <span className="regulations-breadcrumb__sep">&gt;</span>
            <span className="regulations-breadcrumb__current">
              {labels.pageTitle.toUpperCase()}
            </span>
          </nav>
          <h1 className="regulations-top-bar__title">
            {labels.pageTitle.toUpperCase()}
          </h1>
        </div>
      </div>

      <div className="regulations-container">
        <aside className="regulations-sidebar" aria-label="Danh mục quy định">
          <div className="regulations-sidebar__header">
            <FileText className="regulations-sidebar__icon" />
            <span>{labels.categories}</span>
          </div>
          <div className="regulations-tabs">
            {documents.map((doc, index) => (
              <button
                key={doc.id}
                className={`regulations-tab ${doc.id === activeDocId ? 'regulations-tab--active' : ''}`}
                onClick={() => handleSelectDoc(doc.id)}
                type="button"
              >
                <span className="regulations-tab__index">{String(index + 1).padStart(2, '0')}</span>
                <span>{getDocTitle(doc, language)}</span>
              </button>
            ))}
          </div>
        </aside>

        {activeDoc && (
          <article className="regulations-doc">
            <div className="regulations-doc__header">
              <Search className="regulations-doc__icon" />
              <div>
                <p>{`${labels.document} ${activeIndex + 1}`}</p>
                <h2>{getDocTitle(activeDoc, language)}</h2>
              </div>
            </div>

            {activeDoc.sections?.map((section, sectionIndex) => (
              <section key={sectionIndex} className="regulations-section">
                {section.heading && <h3>{translateText(section.heading, language)}</h3>}

                <div className="regulations-section__body">
                  {buildContentBlocks(section.content).map((block, blockIndex) => {
                    if (block.type === 'table') {
                      return <ContentTable key={blockIndex} rows={block.rows} language={language} t={t} />
                    }

                    const isItalicLeadIn = /Trừ khi|Unless otherwise/i.test(block.text)

                    return (
                      <p
                        key={blockIndex}
                        style={{
                          fontStyle: isItalicLeadIn ? 'italic' : 'normal',
                          fontWeight: /^1\.\s/i.test(block.text) ? 700 : 'normal',
                        }}
                      >
                        <InlineText text={translateText(block.text, language)} />
                      </p>
                    )
                  })}
                </div>
              </section>
            ))}
          </article>
        )}
      </div>
    </div>
  )
}

export default Regulations
