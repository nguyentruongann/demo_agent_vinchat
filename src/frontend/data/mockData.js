export const DESTINATIONS = [
  {
    id: 'phu-quoc',
    name: 'Phú Quốc',
    label: 'Phú Quốc Island Sanctuary',
    image: 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=1000&q=80',
    count: '12 Luxury Properties',
    description: 'Pristine white beaches, emerald ocean waters, world-class golf, and safari adventures.'
  },
  {
    id: 'nha-trang',
    name: 'Nha Trang',
    label: 'Nha Trang Bay Haven',
    image: 'https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=1000&q=80',
    count: '8 Oceanfront Resorts',
    description: 'Exclusive island retreats with cable car access, private cliffside villas, and coral diving.'
  },
  {
    id: 'hoi-an',
    name: 'Hội An',
    label: 'Hội An Heritage Coast',
    image: 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1000&q=80',
    count: '6 Boutique Villas',
    description: 'Timeless Indochine architecture, championship 18-hole golf, and cultural heritage.'
  },
  {
    id: 'ha-long',
    name: 'Hạ Long',
    label: 'Hạ Long Bay Sanctuary',
    image: 'https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=1000&q=80',
    count: '5 Island Sanctuaries',
    description: 'Exclusive private island resort surrounded 360-degrees by UNESCO World Heritage karsts.'
  }
];

export const HOTELS = [
  {
    id: 'vintravel-grand-phu-quoc',
    name: 'VinTravel Grand Resort & Spa Phú Quốc',
    destination: 'phu-quoc',
    location: 'Bãi Dài, Gành Dầu, Phú Quốc Island',
    price: 4500000,
    rating: 4.9,
    reviewsCount: 420,
    type: 'Resort',
    featured: true,
    images: [
      'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1200&q=80',
      'https://images.unsplash.com/photo-1582719508461-905c673771fd?auto=format&fit=crop&w=1200&q=80',
      'https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=1200&q=80',
      'https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=1200&q=80'
    ],
    amenities: [
      'Infinity Ocean Pool',
      'Private Beachfront',
      'Akoya Luxury Spa',
      'Kid\'s Club & Safari',
      'Golf Course Access',
      'Airport Transfer',
      'Fine Dining Restaurants'
    ],
    description: 'Nestled along the pristine northern shores of Phú Quốc Island, VinTravel Grand Resort offers ultimate tranquility, private oceanfront villas, world-class 18-hole golf links, and tailor-made wellness journeys guided by expert therapists.',
    policies: {
      checkIn: '14:00 PM',
      checkOut: '12:00 PM',
      children: 'Children under 4 stay free of charge using existing bedding. Children aged 4-11 incur a surcharge of 450,000 VND/night including breakfast.',
      cancellation: 'Free cancellation up to 72 hours prior to arrival. 100% room rate charge applies thereafter.',
      payment: 'All major credit cards (Visa, Mastercard, AMEX), bank transfers, and digital payment apps accepted.'
    },
    rooms: [
      {
        id: 'r1',
        name: 'Deluxe Ocean View King',
        price: 4500000,
        size: '46 sqm',
        guests: '2 Adults, 1 Child',
        description: 'Elegantly furnished with a private balcony overlooking the sparkling Gulf of Thailand.',
        image: 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80'
      },
      {
        id: 'r2',
        name: 'Executive Suite Sea Front',
        price: 7200000,
        size: '85 sqm',
        guests: '2 Adults, 2 Children',
        description: 'Spacious oceanfront suite featuring a master bathtub, separate living room, and butler service.',
        image: 'https://images.unsplash.com/photo-1582719508461-905c673771fd?auto=format&fit=crop&w=800&q=80'
      },
      {
        id: 'r3',
        name: 'Presidential 3-Bedroom Pool Villa',
        price: 16500000,
        size: '340 sqm',
        guests: '6 Adults, 3 Children',
        description: 'Ultimate privacy with a private infinity pool, direct beach access, fully equipped kitchen, and 24/7 dedicated butler.',
        image: 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=800&q=80'
      }
    ]
  },
  {
    id: 'vintravel-luxury-villas-nha-trang',
    name: 'VinTravel Luxury Ocean Villas Nha Trang',
    destination: 'nha-trang',
    location: 'Hòn Tre Island, Nha Trang Bay',
    price: 6200000,
    rating: 4.95,
    reviewsCount: 580,
    type: 'Villa',
    featured: true,
    images: [
      'https://images.unsplash.com/photo-1582719508461-905c673771fd?auto=format&fit=crop&w=1200&q=80',
      'https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=1200&q=80',
      'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1200&q=80'
    ],
    amenities: [
      'Private Infinity Pool',
      'Sea-Crossing Cable Car',
      'VinWonders Amusement Park',
      'Private Butler',
      'Overwater Spa Cabanas',
      'Helipad Transfer'
    ],
    description: 'Perched on private coastal cliffs overlooking emerald waters on Hòn Tre Island, these luxury villas provide dedicated butler service, private infinity pools, and exclusive unlimited access to VinWonders Theme Park.',
    policies: {
      checkIn: '15:00 PM',
      checkOut: '12:00 PM',
      children: 'Complimentary stay and breakfast for kids under 6. Cable car tickets included for all registered guests.',
      cancellation: 'Flexible cancellation up to 48 hours prior to arrival.',
      payment: 'Credit cards, bank transfer, or luxury crypto gateway.'
    },
    rooms: [
      {
        id: 'v1',
        name: 'Tropical 2-Bedroom Ocean Villa',
        price: 6200000,
        size: '180 sqm',
        guests: '4 Adults, 2 Children',
        description: 'Featuring direct sea views, private garden patio, and sun loungers next to a private pool.',
        image: 'https://images.unsplash.com/photo-1582719508461-905c673771fd?auto=format&fit=crop&w=800&q=80'
      },
      {
        id: 'v2',
        name: 'Beachfront 4-Bedroom Estate',
        price: 21000000,
        size: '450 sqm',
        guests: '8 Adults, 4 Children',
        description: 'Expansive family residence with private beachfront lawn, outdoor dining pavilion, and daily wine tasting.',
        image: 'https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=800&q=80'
      }
    ]
  },
  {
    id: 'vintravel-heritage-resort-hoi-an',
    name: 'VinTravel Heritage Golf Resort Hội An',
    destination: 'hoi-an',
    location: 'Bình Minh Beach, Hội An, Quảng Nam',
    price: 3800000,
    rating: 4.82,
    reviewsCount: 310,
    type: 'Resort',
    featured: true,
    images: [
      'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=80',
      'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1200&q=80'
    ],
    amenities: [
      '18-Hole Championship Golf',
      'Organic Farm-to-Table Dining',
      'Heritage Craft Workshops',
      'Large Lagoon Pool',
      'Shuttle to Ancient Town'
    ],
    description: 'Harmoniously blends classic Vietnamese royal aesthetic with contemporary luxury next to an award-winning 18-hole championship golf course and pristine Bình Minh coastline.',
    policies: {
      checkIn: '14:00 PM',
      checkOut: '12:00 PM',
      children: 'Kid-friendly zone with daily traditional lantern making workshops.',
      cancellation: 'Full refund 5 days prior to arrival date.',
      payment: 'Card, cash, or pre-paid voucher code.'
    },
    rooms: [
      {
        id: 'h1',
        name: 'Garden Villa Suite',
        price: 3800000,
        size: '55 sqm',
        guests: '2 Adults, 1 Child',
        description: 'Surrounded by lush tropical gardens with handcrafted mahogany furniture and open-air rainfall shower.',
        image: 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80'
      }
    ]
  },
  {
    id: 'vintravel-emerald-bay-ha-long',
    name: 'VinTravel Emerald Bay Island Resort Hạ Long',
    destination: 'ha-long',
    location: 'Rều Island, Bãi Cháy, Hạ Long',
    price: 5100000,
    rating: 4.88,
    reviewsCount: 290,
    type: 'Hotel',
    featured: false,
    images: [
      'https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=1200&q=80',
      'https://images.unsplash.com/photo-1582719508461-905c673771fd?auto=format&fit=crop&w=1200&q=80'
    ],
    amenities: [
      '360 Panoramic Bay Views',
      'Private Express Ferry Shuttles',
      'Heated Indoor Pool & Hot Tubs',
      'French Gastronomy Restaurant',
      'Sunset Cruise Service'
    ],
    description: 'An exclusive island sanctuary surrounded 360 degrees by the magnificent limestone peaks of UNESCO World Heritage Hạ Long Bay. Accessible only via private express ferry.',
    policies: {
      checkIn: '14:00 PM',
      checkOut: '12:00 PM',
      children: 'Ferry shuttle is free for children under 12 accompanied by adults.',
      cancellation: '72 hours notice required for free cancellation.',
      payment: 'All credit cards accepted.'
    },
    rooms: [
      {
        id: 'hl1',
        name: 'Grand Bay View Suite',
        price: 5100000,
        size: '62 sqm',
        guests: '2 Adults, 1 Child',
        description: 'Floor-to-ceiling windows with panoramic views of limestone islands emerging from misty sea.',
        image: 'https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=800&q=80'
      }
    ]
  }
];

export const COMBOS = [
  {
    id: 'combo-1',
    title: '3D2N Flight + Ocean Villa + Championship Golf Package',
    destination: 'Phú Quốc',
    originalPrice: 12500000,
    offerPrice: 8900000,
    tag: 'BESTSELLER',
    image: 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=800&q=80',
    duration: '3 Days / 2 Nights',
    includes: ['Roundtrip flights', 'Private Ocean Villa', '1 Round 18-hole Golf', 'Daily buffet breakfast', 'Airport express transfer']
  },
  {
    id: 'combo-2',
    title: 'Family Escape: 3D2N All-Inclusive + VinWonders Unlimited Pass',
    destination: 'Nha Trang',
    originalPrice: 10200000,
    offerPrice: 7450000,
    tag: 'FAMILY FAVORITE',
    image: 'https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=800&q=80',
    duration: '3 Days / 2 Nights',
    includes: ['2-Bedroom Ocean Villa', 'Full-board dining (3 meals/day)', 'Unlimited VinWonders Theme Park', 'Cable car tickets']
  },
  {
    id: 'combo-3',
    title: 'Heritage & Wellness Retreat: 2D1N Villa + Akoya Spa',
    destination: 'Hội An',
    originalPrice: 6500000,
    offerPrice: 4800000,
    tag: 'WELLNESS SPECIAL',
    image: 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80',
    duration: '2 Days / 1 Night',
    includes: ['Garden Villa Suite', '60-min Akoya massage', 'Organic farm dinner', 'Shuttle to Ancient Town']
  }
];
