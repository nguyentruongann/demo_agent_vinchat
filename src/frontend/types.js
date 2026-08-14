/**
 * @typedef {'en' | 'vi' | 'ko' | 'ja' | 'zh'} Language
 */

/**
 * @typedef {Object} RoomType
 * @property {string} id
 * @property {string} name
 * @property {number | null} price
 * @property {string | null} [currency]
 * @property {string} size
 * @property {string} guests
 * @property {string} [description]
 * @property {string} [image]
 */

/**
 * @typedef {Object} HotelPolicies
 * @property {string} checkIn
 * @property {string} checkOut
 * @property {string} children
 * @property {string} cancellation
 * @property {string} payment
 */

/**
 * @typedef {Object} Hotel
 * @property {string} id
 * @property {string} name
 * @property {string} destination
 * @property {string} location
 * @property {number | null} price
 * @property {string | null} [currency]
 * @property {number} rating
 * @property {number} reviewsCount
 * @property {'Resort' | 'Hotel' | 'Villa' | 'Combo'} type
 * @property {string[]} images
 * @property {string[]} amenities
 * @property {string} description
 * @property {HotelPolicies} policies
 * @property {RoomType[]} rooms
 * @property {boolean} [featured]
 */

/**
 * @typedef {Object} Destination
 * @property {string} id
 * @property {string} name
 * @property {string} label
 * @property {string} image
 * @property {string} count
 * @property {string} description
 */

/**
 * @typedef {Object} ComboOffer
 * @property {string} id
 * @property {string} title
 * @property {string} destination
 * @property {number} originalPrice
 * @property {number} offerPrice
 * @property {string} tag
 * @property {string} image
 * @property {string} duration
 * @property {string[]} includes
 */

/**
 * @typedef {Object} ChatMessage
 * @property {string} id
 * @property {'user' | 'assistant'} sender
 * @property {string} text
 * @property {string} timestamp
 * @property {Language} [language]
 * @property {string} [route]
 * @property {string} [ticketId]
 * @property {SourceItem[]} [sources]
 * @property {Hotel[]} [relatedHotels]
 * @property {string[]} [suggestedQuestions]
 */

/**
 * @typedef {Object} Ticket
 * @property {string} id
 * @property {string} customerName
 * @property {string} email
 * @property {string} [phone]
 * @property {Language} language
 * @property {string} subject
 * @property {string} content
 * @property {'Pending' | 'Processing' | 'Resolved'} status
 * @property {string} createdAt
 */

/**
 * @typedef {Object} User
 * @property {string} id
 * @property {string} name
 * @property {string} email
 * @property {string} [avatar]
 */

/**
 * @typedef {Object} Promotion
 * @property {string} id
 * @property {string} title
 * @property {string | null} [summary]
 * @property {string | null} [discount_text]
 * @property {'active' | 'upcoming' | 'expired' | 'unknown'} [status]
 * @property {string | null} [validity_from]
 * @property {string | null} [validity_to]
 * @property {string | null} [booking_url]
 * @property {string | null} [image_url]
 * @property {boolean} [is_nationwide]
 * @property {Array<string | {id?: string, name?: string}>} [destinations]
 */

/**
 * @typedef {Object} SourceItem
 * @property {string} source_file
 * @property {string | null} [category]
 * @property {string | null} [path]
 * @property {number | null} [score]
 */

/**
 * @template T
 * @typedef {Object} PaginatedResponse
 * @property {T[]} items
 * @property {number} page
 * @property {number} page_size
 * @property {number} total
 */

// Keep this file as an ES module so its typedefs can be imported explicitly:
// /** @typedef {import('../types').Hotel} Hotel */
export {}
