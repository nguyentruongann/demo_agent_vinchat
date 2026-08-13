/**
 * @typedef {'EN' | 'VI' | 'KO' | 'ZH'} Language
 */

/**
 * @typedef {Object} RoomType
 * @property {string} id
 * @property {string} name
 * @property {number} price
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
 * @property {number} price
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