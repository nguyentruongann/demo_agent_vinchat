import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import ja from './locales/ja.json'
import ko from './locales/ko.json'
import vi from './locales/vi.json'
import zh from './locales/zh.json'

export const SUPPORTED_LANGUAGES = ['en', 'vi', 'ko', 'ja', 'zh']
export const LANGUAGE_STORAGE_KEY = 'site_language'

const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY)
const initialLanguage = SUPPORTED_LANGUAGES.includes(stored) ? stored : 'en'

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, vi: { translation: vi }, ko: { translation: ko }, ja: { translation: ja }, zh: { translation: zh } },
  lng: initialLanguage,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
