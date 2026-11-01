import { Grid } from 'antd'

/**
 * 是否为移动端窄屏（宽度 < 768px，即 antd 的 md 断点以下）。
 *
 * 为什么存在：布局、表格、多栏工作台在手机上需要切换为抽屉菜单 / 单栏 / 横向滚动，
 * 统一用这个 hook 判断，避免各页面各自写断点逻辑。
 */
export function useIsMobile(): boolean {
  const screens = Grid.useBreakpoint()
  // 首次渲染 screens 可能为空对象：按「非移动端」处理，断点就绪后会重新渲染。
  if (Object.keys(screens).length === 0) return false
  return !screens.md
}
