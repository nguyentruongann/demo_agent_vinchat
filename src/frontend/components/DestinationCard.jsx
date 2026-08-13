import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import '../styles/components/DestinationCard.css'

const VI_DESTINATION_COPY = {
  'phu-quoc': {
    name: 'Phú Quốc',
    label: 'Thiên đường nghỉ dưỡng đảo Phú Quốc',
    count: '12 khu nghỉ dưỡng cao cấp',
    description:
      'Bãi cát trắng nguyên sơ, làn nước xanh ngọc, sân golf đẳng cấp và hành trình safari đáng nhớ.',
  },
  'nha-trang': {
    name: 'Nha Trang',
    label: 'Ốc đảo nghỉ dưỡng vịnh Nha Trang',
    count: '8 resort hướng biển',
    description:
      'Khu nghỉ dưỡng đảo riêng với cáp treo, biệt thự ven vách đá và trải nghiệm lặn ngắm san hô.',
  },
  'hoi-an': {
    name: 'Hội An',
    label: 'Bờ biển di sản Hội An',
    count: '6 biệt thự boutique',
    description:
      'Kiến trúc Đông Dương thanh lịch, sân golf 18 lỗ chuẩn quốc tế và không gian di sản giàu bản sắc.',
  },
  'ha-long': {
    name: 'Hạ Long',
    label: 'Ốc đảo nghỉ dưỡng vịnh Hạ Long',
    count: '5 khu nghỉ dưỡng trên đảo',
    description:
      'Resort đảo riêng được bao quanh bởi kỳ quan núi đá vôi UNESCO của vịnh Hạ Long.',
  },
}

function DestinationCard({ destination }) {
  const { language, t } = useLanguage()
  const localizedDestination =
    language === 'VI' ? VI_DESTINATION_COPY[destination.id] : null
  const name = localizedDestination?.name || destination.name
  const label = localizedDestination?.label || destination.label
  const count = localizedDestination?.count || destination.count
  const description = localizedDestination?.description || destination.description

  return (
    <Link
      className="destination-card"
      to={`/search?destination=${destination.id}`}
    >
      <img
        className="destination-card__image"
        src={destination.image}
        alt={name}
      />

      <span className="destination-card__badge">{count}</span>

      <div className="destination-card__content">
        <span className="destination-card__label">{label}</span>
        <h3 className="destination-card__title">{name}</h3>
        <p className="destination-card__description">
          "{description}"
        </p>

        <div className="destination-card__action">
          <span>{t.exploreRetreats}</span>
          <ChevronRight className="destination-card__action-icon" />
        </div>
      </div>
    </Link>
  )
}

export default DestinationCard
