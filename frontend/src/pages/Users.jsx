import { useState, useEffect, useCallback } from 'react'
import { Plus, Pencil, Trash2, Loader2, X, Check, Users as UsersIcon, Search, Shield, ShieldCheck, UserRound } from 'lucide-react'
import clsx from 'clsx'
import { SkeletonHeader, SkeletonList } from '../components/Skeleton'
import { ModalPortal } from '../context/ModalPortal'
import PresenceDot, { lastSeenLabel } from '../components/PresenceDot'
import { parseBackendTime } from '../utils/time'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export default function Users() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Filters
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')        // 'all' | 'admin' | 'supervisor' | 'agent'
  const [statusFilter, setStatusFilter] = useState('all')    // 'all' | 'active' | 'inactive'
  const [presenceFilter, setPresenceFilter] = useState('all')// 'all' | 'online' | 'idle' | 'offline'
  const [sortBy, setSortBy] = useState('name')               // 'name' | 'recent' | 'joined'
  const [showModal, setShowModal] = useState(false)
  const [modalData, setModalData] = useState({
    email: '',
    full_name: '',
    password: '',
    role: 'agent',
  })
  const [submitting, setSubmitting] = useState(false)
  const [modalError, setModalError] = useState(null)
  const [modalSuccess, setModalSuccess] = useState(false)
  // Edit modal state
  const [showEditModal, setShowEditModal] = useState(false)
  const [editData, setEditData] = useState({ id: null, full_name: '', role: 'agent', status: 'active' })
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editSuccess, setEditSuccess] = useState(false)

  // Fetch users
  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/auth/users`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to load users')
      const data = await res.json()
      setUsers(data.users || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchUsers()
    // Refresh presence indicators every 30s without a full skeleton reload
    const timer = setInterval(() => {
      fetch(`${API_BASE}/auth/users`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data?.users) setUsers(data.users) })
        .catch(() => { /* silent */ })
    }, 30_000)
    return () => clearInterval(timer)
  }, [fetchUsers])

  const validateForm = () => {
    if (!modalData.email.trim()) return 'Email is required'
    if (!modalData.full_name.trim()) return 'Full name is required'
    if (!modalData.password.trim()) return 'Password is required'
    if (modalData.password.length < 8) return 'Password must be at least 8 characters'

    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/
    if (!emailRegex.test(modalData.email)) return 'Invalid email format'

    if (modalData.full_name.length < 2) return 'Full name must be at least 2 characters'

    return null
  }

  const createUser = async (e) => {
    e.preventDefault()
    setModalError(null)
    setModalSuccess(false)

    const validationError = validateForm()
    if (validationError) {
      setModalError(validationError)
      return
    }

    setSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/auth/signup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify(modalData),
      })

      const data = await res.json()

      if (!res.ok) {
        throw new Error(data.error || 'Failed to create user')
      }

      setModalSuccess(true)
      setUsers(prev => [...prev, data.user])
      
      // Reset form after short delay
      setTimeout(() => {
        setShowModal(false)
        setModalData({ email: '', full_name: '', password: '', role: 'agent' })
        setModalSuccess(false)
      }, 1500)
    } catch (err) {
      setModalError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const openEditModal = (user) => {
    setEditData({
      id: user.id,
      full_name: user.full_name,
      email: user.email,
      password: '',
      role: user.role,
      status: user.status,
    })
    setEditError(null)
    setEditSuccess(false)
    setShowEditModal(true)
  }

  const closeEditModal = () => {
    setShowEditModal(false)
    setEditError(null)
    setEditSuccess(false)
    setEditData({ id: null, full_name: '', email: '', password: '', role: 'agent', status: 'active' })
  }

  const updateUser = async (e) => {
    e.preventDefault()
    setEditError(null)
    setEditSuccess(false)

    if (!editData.full_name.trim() || editData.full_name.length < 2) {
      setEditError('Full name must be at least 2 characters')
      return
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(editData.email)) {
      setEditError('Invalid email format')
      return
    }

    // Password is optional on edit — only validate if the field has a value
    if (editData.password && editData.password.length < 8) {
      setEditError('Password must be at least 8 characters')
      return
    }

    // Build payload — only send password if it was actually entered
    const payload = {
      full_name: editData.full_name.trim(),
      email: editData.email.trim(),
      role: editData.role,
      status: editData.status,
    }
    if (editData.password) {
      payload.password = editData.password
    }

    setEditSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/auth/users/${editData.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify(payload),
      })

      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to update user')

      setEditSuccess(true)
      setUsers(prev => prev.map(u => u.id === editData.id ? data.user : u))

      setTimeout(() => {
        closeEditModal()
      }, 1200)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setEditSubmitting(false)
    }
  }

  const deleteUser = async (userId, userName) => {
    if (!confirm(`Delete user "${userName}"? This cannot be undone.`)) return

    try {
      const res = await fetch(`${API_BASE}/auth/users/${userId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to delete user')
      setUsers(prev => prev.filter(u => u.id !== userId))
    } catch (err) {
      alert(`Error: ${err.message}`)
    }
  }

  const roleConfig = {
    admin: { bg: 'bg-red-50', text: 'text-red-700', label: 'Admin' },
    supervisor: { bg: 'bg-blue-50', text: 'text-blue-700', label: 'Supervisor' },
    agent: { bg: 'bg-gray-50', text: 'text-gray-700', label: 'Agent' },
  }

  const getInitials = (name) => {
    return name
      .split(' ')
      .map(n => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  // Computed: KPI counts
  const totalUsers = users.length
  const activeUsers = users.filter(u => u.status === 'active').length
  const onlineUsers = users.filter(u => u.presence === 'online').length

  // Computed: filtered + sorted list
  const visibleUsers = (() => {
    let result = users
    const q = search.trim().toLowerCase()
    if (q) {
      result = result.filter(u =>
        (u.full_name || '').toLowerCase().includes(q) ||
        (u.email || '').toLowerCase().includes(q)
      )
    }
    if (roleFilter !== 'all') result = result.filter(u => u.role === roleFilter)
    if (statusFilter !== 'all') result = result.filter(u => u.status === statusFilter)
    if (presenceFilter !== 'all') result = result.filter(u => (u.presence || 'offline') === presenceFilter)

    return [...result].sort((a, b) => {
      if (sortBy === 'name') return (a.full_name || '').localeCompare(b.full_name || '')
      if (sortBy === 'joined') {
        const da = parseBackendTime(a.created_at)?.getTime() || 0
        const db = parseBackendTime(b.created_at)?.getTime() || 0
        return db - da  // newest first
      }
      if (sortBy === 'recent') {
        const da = parseBackendTime(a.last_seen_at)?.getTime() || 0
        const db = parseBackendTime(b.last_seen_at)?.getTime() || 0
        return db - da  // most recent first
      }
      return 0
    })
  })()

  return (
    <div className="space-y-5 w-full max-w-5xl mx-auto">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Users</h1>
          <p className="text-xs sm:text-sm text-gray-500 mt-0.5">Manage team members and permissions</p>
        </div>
        <button
          onClick={() => {
            setShowModal(true)
            setModalError(null)
            setModalSuccess(false)
          }}
          className="btn-primary flex items-center gap-2 text-xs py-2 px-3 shrink-0"
        >
          <Plus size={14} /> Add User
        </button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Total',  value: totalUsers,  Icon: UserRound,    color: 'text-gray-700',   bg: 'bg-gray-100' },
          { label: 'Active', value: activeUsers, Icon: ShieldCheck,  color: 'text-green-600',  bg: 'bg-green-50' },
          { label: 'Online', value: onlineUsers, Icon: UsersIcon,    color: 'text-brand-600',  bg: 'bg-brand-50' },
        ].map(({ label, value, Icon, color, bg }) => (
          <div key={label} className="card p-3 sm:p-4 min-w-0">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0', bg)}>
                <Icon size={14} className={color} />
              </div>
            </div>
            <p className="text-xl sm:text-2xl font-bold text-gray-900 tabular-nums leading-none">{value}</p>
            <p className="text-[10px] sm:text-xs text-gray-500 font-semibold mt-1.5 uppercase tracking-wide truncate">{label}</p>
          </div>
        ))}
      </div>

      {/* Filter row */}
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-3 sm:items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-0">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Search by name or email…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="input w-full pl-9 text-xs"
          />
        </div>

        {/* Role */}
        <select
          value={roleFilter}
          onChange={e => setRoleFilter(e.target.value)}
          className="input text-xs shrink-0 cursor-pointer"
        >
          <option value="all">All roles</option>
          <option value="admin">Admin</option>
          <option value="supervisor">Supervisor</option>
          <option value="agent">Agent</option>
        </select>

        {/* Status */}
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="input text-xs shrink-0 cursor-pointer"
        >
          <option value="all">All status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>

        {/* Presence */}
        <select
          value={presenceFilter}
          onChange={e => setPresenceFilter(e.target.value)}
          className="input text-xs shrink-0 cursor-pointer"
        >
          <option value="all">All presence</option>
          <option value="online">Online</option>
          <option value="idle">Idle</option>
          <option value="offline">Offline</option>
        </select>

        {/* Sort */}
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
          className="input text-xs shrink-0 cursor-pointer"
        >
          <option value="name">Sort: Name (A-Z)</option>
          <option value="recent">Sort: Recently active</option>
          <option value="joined">Sort: Newest first</option>
        </select>
      </div>

      {/* Active filter chip — only shows when filters reduce the list */}
      {(search || roleFilter !== 'all' || statusFilter !== 'all' || presenceFilter !== 'all') && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-gray-500">
            Showing <span className="font-semibold text-gray-900">{visibleUsers.length}</span> of {totalUsers} users
          </span>
          <button
            onClick={() => {
              setSearch('')
              setRoleFilter('all')
              setStatusFilter('all')
              setPresenceFilter('all')
            }}
            className="text-brand-600 hover:text-brand-700 font-semibold"
          >
            Clear filters
          </button>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3.5 text-xs text-red-600 font-medium">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          <SkeletonList count={5} />
        </div>
      ) : (
        <div className="space-y-4">
          {users.length === 0 ? (
            <div className="text-center py-16 px-4">
              <div className="w-12 h-12 rounded-lg bg-gray-100 flex items-center justify-center mx-auto mb-4">
                <UsersIcon size={24} className="text-gray-400" />
              </div>
              <p className="text-sm text-gray-500 font-medium">No users yet</p>
              <p className="text-xs text-gray-400 mt-1">Create your first team member to get started</p>
            </div>
          ) : visibleUsers.length === 0 ? (
            <div className="text-center py-12 px-4">
              <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center mx-auto mb-3">
                <Search size={18} className="text-gray-400" />
              </div>
              <p className="text-sm text-gray-500 font-medium">No users match these filters</p>
              <button
                onClick={() => {
                  setSearch('')
                  setRoleFilter('all')
                  setStatusFilter('all')
                  setPresenceFilter('all')
                }}
                className="text-xs text-brand-600 hover:text-brand-700 font-semibold mt-2"
              >
                Clear filters
              </button>
            </div>
          ) : (
            <div className="grid gap-3">
              {visibleUsers.map(user => {
                const joinDate = parseBackendTime(user.created_at)?.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) || '—'
                const roleInfo = roleConfig[user.role]
                return (
                  <div key={user.id} className="card p-4 hover:shadow-md transition-all duration-200">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-start gap-3.5 flex-1">
                        {/* Avatar */}
                        <div className="w-10 h-10 rounded-xl bg-black text-white flex items-center justify-center font-semibold text-xs shrink-0 mt-0.5">
                          {getInitials(user.full_name)}
                        </div>
                        
                        {/* User info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1.5">
                            <h3 className="text-sm font-semibold text-gray-900">{user.full_name}</h3>
                            <span className={clsx('px-2 py-0.5 rounded-md text-xs font-semibold capitalize', roleInfo.bg, roleInfo.text)}>
                              {roleInfo.label}
                            </span>
                          </div>
                          <p className="text-xs text-gray-500 font-mono truncate">{user.email}</p>
                          <div className="flex items-center gap-3 mt-2 text-xs text-gray-400 flex-wrap">
                            <span>Joined {joinDate}</span>
                            <span className={clsx('px-1.5 py-0.5 rounded font-medium text-xs', 
                              user.status === 'active' ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'
                            )}>
                              {user.status}
                            </span>
                            <span className="inline-flex items-center gap-1.5">
                              <PresenceDot status={user.presence || 'offline'} />
                              <span className={clsx(
                                'capitalize font-medium',
                                user.presence === 'online' ? 'text-green-700'
                                  : user.presence === 'idle' ? 'text-amber-700'
                                  : 'text-gray-500'
                              )}>
                                {user.presence || 'offline'}
                              </span>
                              {lastSeenLabel(user.last_seen_at, user.presence) && (
                                <span className="text-gray-400">
                                  · {lastSeenLabel(user.last_seen_at, user.presence)}
                                </span>
                              )}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => openEditModal(user)}
                          className="text-gray-400 hover:text-gray-700 transition-colors p-2 hover:bg-gray-100 rounded-lg"
                          title="Edit user"
                        >
                          <Pencil size={16} />
                        </button>
                        <button
                          onClick={() => deleteUser(user.id, user.full_name)}
                          className="text-gray-400 hover:text-red-600 transition-colors p-2 hover:bg-red-50 rounded-lg"
                          title="Delete user"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* New User Modal */}
      {showModal && (
        <ModalPortal>
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
            <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-screen mx-4 p-6 space-y-4">
            {/* Header */}
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <h2 className="text-lg font-bold text-gray-900">Create New User</h2>
                <p className="text-xs text-gray-500 mt-0.5">Add a new team member to your workspace</p>
              </div>
              <button
                onClick={() => {
                  setShowModal(false)
                  setModalError(null)
                  setModalSuccess(false)
                  setModalData({ email: '', full_name: '', password: '', role: 'agent' })
                }}
                className="btn-ghost p-1 shrink-0"
              >
                <X size={18} />
              </button>
            </div>

            {modalError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600 font-medium">
                {modalError}
              </div>
            )}

            {modalSuccess && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700 font-medium flex items-center gap-2">
                <Check size={14} className="shrink-0" /> User created successfully!
              </div>
            )}

            <form onSubmit={createUser} className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1.5">Full Name</label>
                <input
                  type="text"
                  placeholder="John Doe"
                  value={modalData.full_name}
                  onChange={(e) => setModalData(prev => ({ ...prev, full_name: e.target.value }))}
                  className="input w-full text-xs"
                  disabled={modalSuccess}
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1.5">Email</label>
                <input
                  type="email"
                  placeholder="john@example.com"
                  value={modalData.email}
                  onChange={(e) => setModalData(prev => ({ ...prev, email: e.target.value }))}
                  className="input w-full text-xs"
                  disabled={modalSuccess}
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1.5">Password</label>
                <input
                  type="password"
                  placeholder="Min 8 characters"
                  value={modalData.password}
                  onChange={(e) => setModalData(prev => ({ ...prev, password: e.target.value }))}
                  className="input w-full text-xs"
                  disabled={modalSuccess}
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1.5">Role</label>
                <select
                  value={modalData.role}
                  onChange={(e) => setModalData(prev => ({ ...prev, role: e.target.value }))}
                  className="input w-full text-xs"
                  disabled={modalSuccess}
                >
                  <option value="agent">Agent</option>
                  <option value="supervisor">Supervisor</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false)
                    setModalError(null)
                    setModalSuccess(false)
                    setModalData({ email: '', full_name: '', password: '', role: 'agent' })
                  }}
                  className="btn-ghost flex-1 text-sm"
                  disabled={submitting || modalSuccess}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || modalSuccess}
                  className="flex-1 px-4 py-2 rounded-lg font-semibold text-sm transition-all text-white bg-black hover:bg-gray-800 disabled:opacity-50 flex items-center justify-center gap-1.5"
                >
                  {submitting ? (
                    <>
                      <Loader2 size={13} className="animate-spin" /> Creating...
                    </>
                  ) : modalSuccess ? (
                    <>
                      <Check size={13} /> Created!
                    </>
                  ) : (
                    <>
                      <Plus size={13} /> Create
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
        </ModalPortal>
      )}

      {/* Edit User Modal */}
      {showEditModal && (
        <ModalPortal>
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
            <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-screen mx-4 p-6 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <h2 className="text-lg font-bold text-gray-900">Edit User</h2>
                  <p className="text-xs text-gray-500 mt-0.5">Update name, email, password, role, or status</p>
                </div>
                <button onClick={closeEditModal} className="btn-ghost p-1 shrink-0">
                  <X size={18} />
                </button>
              </div>

              {editError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600 font-medium">
                  {editError}
                </div>
              )}

              {editSuccess && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700 font-medium flex items-center gap-2">
                  <Check size={14} className="shrink-0" /> User updated successfully!
                </div>
              )}

              <form onSubmit={updateUser} className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1.5">Full Name</label>
                  <input
                    type="text"
                    value={editData.full_name}
                    onChange={(e) => setEditData(prev => ({ ...prev, full_name: e.target.value }))}
                    className="input w-full text-xs"
                    disabled={editSuccess}
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1.5">Email</label>
                  <input
                    type="email"
                    value={editData.email}
                    onChange={(e) => setEditData(prev => ({ ...prev, email: e.target.value }))}
                    className="input w-full text-xs"
                    disabled={editSuccess}
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1.5">
                    Password
                    <span className="font-normal text-gray-400 ml-1.5">(leave blank to keep current)</span>
                  </label>
                  <input
                    type="password"
                    placeholder="Min 8 characters"
                    value={editData.password}
                    onChange={(e) => setEditData(prev => ({ ...prev, password: e.target.value }))}
                    className="input w-full text-xs"
                    disabled={editSuccess}
                    autoComplete="new-password"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1.5">Role</label>
                  <select
                    value={editData.role}
                    onChange={(e) => setEditData(prev => ({ ...prev, role: e.target.value }))}
                    className="input w-full text-xs"
                    disabled={editSuccess}
                  >
                    <option value="agent">Agent</option>
                    <option value="supervisor">Supervisor</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1.5">Status</label>
                  <select
                    value={editData.status}
                    onChange={(e) => setEditData(prev => ({ ...prev, status: e.target.value }))}
                    className="input w-full text-xs"
                    disabled={editSuccess}
                  >
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                    <option value="suspended">Suspended</option>
                  </select>
                </div>

                <div className="flex gap-3 pt-2">
                  <button
                    type="button"
                    onClick={closeEditModal}
                    className="btn-ghost flex-1 text-sm"
                    disabled={editSubmitting || editSuccess}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={editSubmitting || editSuccess}
                    className="flex-1 px-4 py-2 rounded-lg font-semibold text-sm transition-all text-white bg-black hover:bg-gray-800 disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    {editSubmitting ? (
                      <>
                        <Loader2 size={13} className="animate-spin" /> Saving...
                      </>
                    ) : editSuccess ? (
                      <>
                        <Check size={13} /> Saved!
                      </>
                    ) : (
                      <>
                        <Check size={13} /> Save
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </ModalPortal>
      )}
    </div>
  )
}
