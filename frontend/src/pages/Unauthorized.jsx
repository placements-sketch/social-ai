import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Lock, ArrowLeft } from 'lucide-react'

export default function Unauthorized() {
  const navigate = useNavigate()
  const { user } = useAuth()

  return (
    <div className="min-h-screen bg-black flex items-center justify-center relative overflow-hidden">
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-white/5 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-white/5 rounded-full blur-3xl"></div>
      </div>

      {/* Main container */}
      <div className="relative z-10 w-full max-w-md px-6 text-center">
        {/* Icon */}
        <div className="inline-flex items-center justify-center w-16 h-16 bg-white/10 border border-white/20 rounded-lg mb-6">
          <Lock className="w-8 h-8 text-white" />
        </div>

        {/* Content */}
        <h1 className="text-3xl font-bold text-white mb-3">Access Denied</h1>
        <p className="text-gray-400 mb-2">
          You don't have permission to access this page.
        </p>
        <p className="text-gray-500 text-sm mb-8">
          Your current role is <span className="text-white font-semibold capitalize">{user?.role}</span>
        </p>

        {/* Info Box */}
        <div className="bg-white/5 border border-white/10 rounded-lg p-4 mb-8">
          <p className="text-xs text-gray-400 mb-3">Your Permissions</p>
          <div className="space-y-2 text-left">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-white/40"></div>
              <span className="text-sm text-gray-300">Dashboard</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-white/40"></div>
              <span className="text-sm text-gray-300">Messages</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-white/40"></div>
              <span className="text-sm text-gray-300">Analytics</span>
            </div>
            {user?.role === 'admin' && (
              <>
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-white/40"></div>
                  <span className="text-sm text-gray-300">Settings</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-white/40"></div>
                  <span className="text-sm text-gray-300">User Management</span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Button */}
        <button
          onClick={() => navigate('/dashboard')}
          className="w-full bg-white text-black py-3 rounded-lg font-semibold hover:bg-gray-100 transition-all flex items-center justify-center gap-2 group"
        >
          <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
          Back to Dashboard
        </button>

        {/* Footer */}
        <p className="text-xs text-gray-600 mt-6">
          If you believe this is an error, contact your administrator
        </p>
      </div>
    </div>
  )
}
