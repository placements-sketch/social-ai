import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ConfirmationProvider } from './context/ConfirmationContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { ToastProvider } from './components/Toast'
import Layout from './components/Layout'
import Login from './pages/Login'
import Unauthorized from './pages/Unauthorized'
import Dashboard from './pages/Dashboard'
import Messages from './pages/Messages'
import Products from './pages/Products'
import AISettings from './pages/AISettings'
import Automation from './pages/Automation'
import Channels from './pages/Channels'
import Analytics from './pages/Analytics'
import Logs from './pages/Logs'
import Settings from './pages/Settings'
import Users from './pages/Users'
import Customers from './pages/Customers'
import CustomerDetail from './pages/CustomerDetail'

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <ConfirmationProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/unauthorized" element={<Unauthorized />} />

            {/* Protected routes */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />

              {/* All users can access these */}
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="messages" element={<Messages />} />
              <Route
                path="products"
                element={
                  <ProtectedRoute requiredRole={['admin', 'supervisor']}>
                    <Products />
                  </ProtectedRoute>
                }
              />
              <Route path="analytics" element={<Analytics />} />
              <Route path="logs" element={<Logs />} />

              {/* Admin + Supervisor */}
              <Route
                path="customers"
                element={
                  <ProtectedRoute requiredRole={['admin', 'supervisor']}>
                    <Customers />
                  </ProtectedRoute>
                }
              />

              <Route
                path="customers/:id"
                element={
                  <ProtectedRoute requiredRole={['admin', 'supervisor']}>
                    <CustomerDetail />
                  </ProtectedRoute>
                }
              />

              {/* Admin only */}
              <Route
                path="ai"
                element={
                  <ProtectedRoute requiredRole={['admin']}>
                    <AISettings />
                  </ProtectedRoute>
                }
              />
              <Route
                path="automation"
                element={
                  <ProtectedRoute requiredRole={['admin']}>
                    <Automation />
                  </ProtectedRoute>
                }
              />
              <Route
                path="channels"
                element={
                  <ProtectedRoute requiredRole={['admin']}>
                    <Channels />
                  </ProtectedRoute>
                }
              />
              <Route
                path="settings"
                element={
                  <ProtectedRoute requiredRole={['admin']}>
                    <Settings />
                  </ProtectedRoute>
                }
              />
              <Route
                path="users"
                element={
                  <ProtectedRoute requiredRole={['admin']}>
                    <Users />
                  </ProtectedRoute>
                }
              />
            </Route>
          </Routes>
        </ConfirmationProvider>
      </ToastProvider>
    </AuthProvider>
  )
}