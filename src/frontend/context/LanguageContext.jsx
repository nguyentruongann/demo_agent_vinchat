import { createContext, useContext, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LANGUAGE_STORAGE_KEY, SUPPORTED_LANGUAGES } from '../i18n'
import en from '../locales/en.json'
import ja from '../locales/ja.json'
import ko from '../locales/ko.json'
import vi from '../locales/vi.json'
import zh from '../locales/zh.json'

const UI_TRANSLATIONS = { en: en.ui, vi: vi.ui, ko: ko.ui, ja: ja.ui, zh: zh.ui }
const LanguageContext = createContext(undefined)

export function LanguageProvider({ children }) {
  const { i18n, t: translate } = useTranslation()
  const [language, setLanguageState] = useState(() => {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY)
    return SUPPORTED_LANGUAGES.includes(stored) ? stored : 'en'
  })

  const setLanguage = (nextLanguage) => {
    const normalized = String(nextLanguage).toLowerCase()
    if (!SUPPORTED_LANGUAGES.includes(normalized)) return
    setLanguageState(normalized)
    localStorage.setItem(LANGUAGE_STORAGE_KEY, normalized)
    void i18n.changeLanguage(normalized)
  }

  const t = useMemo(() => ({
    ...en.ui,
    ...(UI_TRANSLATIONS[language] || en.ui),
    navHotels: translate('nav.hotels'),
    navExperiences: translate('nav.experiences'),
    navOffers: translate('nav.offers'),
    navNews: translate('nav.news'),
    navMeetings: translate('nav.meetings'),
    navRegulations: translate('nav.policies'),
  }), [language, translate])

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t, translate }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) throw new Error('useLanguage must be used within a LanguageProvider')
  return context
}
