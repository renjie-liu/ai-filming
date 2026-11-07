import type React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import Settings from './pages/Settings'
import NotFound from './pages/NotFound'
import ModelManagement from './pages/aiStudio/models/ModelManagement'
import WorksPage from './pages/creator/WorksPage'
import CreatorPage from './pages/creator/CreatorPage'
import './App.css'

/**
 * 路由：应用只有「作品列表」「创作页」两个业务页面，加上模型管理与系统设置。
 * 旧的 /projects 路径统一跳到作品列表。
 */
const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/works" replace />} />
          <Route path="works" element={<WorksPage />} />
          <Route path="works/:projectId" element={<CreatorPage />} />
          <Route path="projects/*" element={<Navigate to="/works" replace />} />
          <Route path="models" element={<ModelManagement />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
