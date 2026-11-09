import type React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { RequireAdmin, RequireAuth } from './auth/RequireAuth'
import LoginPage from './pages/LoginPage'
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
 * 除 /login 外都要求登录（`RequireAuth`）；模型管理只给管理员（`RequireAdmin`）。
 */
const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <MainLayout />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/works" replace />} />
            <Route path="works" element={<WorksPage />} />
            <Route path="works/:projectId" element={<CreatorPage />} />
            <Route path="projects/*" element={<Navigate to="/works" replace />} />
            <Route
              path="models"
              element={
                <RequireAdmin>
                  <ModelManagement />
                </RequireAdmin>
              }
            />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
