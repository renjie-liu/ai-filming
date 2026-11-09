import { create } from 'zustand'
import type { SupportedLanguage } from '../i18n'

/** 界面级状态：侧栏折叠与语言。登录用户由 `auth/AuthContext` 管理，不放这里。 */
interface AppState {
  siderCollapsed: boolean
  language: SupportedLanguage
  setLanguage: (lang: SupportedLanguage) => void
  toggleSider: () => void
}

export const useAppStore = create<AppState>((set) => ({
  siderCollapsed: false,
  language: 'zh-CN',
  setLanguage: (lang) => set(() => ({ language: lang })),
  toggleSider: () =>
    set((state) => ({
      siderCollapsed: !state.siderCollapsed,
    })),
}))
