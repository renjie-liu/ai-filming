import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import zhLayout from './locales/zh-CN/layout.json'
import zhCommon from './locales/zh-CN/common.json'
import zhSettings from './locales/zh-CN/settings.json'
import zhNotFound from './locales/zh-CN/notFound.json'
import zhGuide from './locales/zh-CN/guide.json'
import enLayout from './locales/en-US/layout.json'
import enCommon from './locales/en-US/common.json'
import enSettings from './locales/en-US/settings.json'
import enNotFound from './locales/en-US/notFound.json'
import enGuide from './locales/en-US/guide.json'

export type SupportedLanguage = 'zh-CN' | 'en-US'

const resources = {
  'zh-CN': {
    common: zhCommon,
    layout: zhLayout,
    settings: zhSettings,
    notFound: zhNotFound,
    guide: zhGuide,
  },
  'en-US': {
    common: enCommon,
    layout: enLayout,
    settings: enSettings,
    notFound: enNotFound,
    guide: enGuide,
  },
}

/**
 * 界面语言在 localStorage 中的存储键。
 *
 * 默认始终使用简体中文（应用页面文案以中文为主），不再跟随浏览器语言；
 * 只有用户在顶部切换语言后才会使用其选择。键名带 v2 后缀，
 * 以忽略旧版本按浏览器语言自动缓存的 `jellyfish_language`。
 */
export const LANGUAGE_STORAGE_KEY = 'jellyfish_language_v2'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'zh-CN',
    supportedLngs: ['zh-CN', 'en-US'],
    ns: ['common', 'layout', 'settings', 'notFound', 'guide'],
    defaultNS: 'layout',
    interpolation: {
      escapeValue: false,
    },
    detection: {
      // 仅读取用户显式选择的语言；未选择时回退到 zh-CN（不检测浏览器语言）。
      order: ['localStorage'],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: [],
    },
  })

export default i18n

