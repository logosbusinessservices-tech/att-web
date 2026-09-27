import { createContext, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      setLoading(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setLoading(false))
  }, [])

  async function login(username, password) {
    const res = await api.login(username, password)
    localStorage.setItem('token', res.access_token)
    const me = await api.me()
    setUser(me)
    return me
  }

  // Complete a login when we already hold a token (e.g. from OTP verification).
  async function loginWithToken(token) {
    localStorage.setItem('token', token)
    const me = await api.me()
    setUser(me)
    return me
  }

  function logout() {
    localStorage.removeItem('token')
    setUser(null)
  }

  // Re-fetch the profile (e.g. after changing password clears must_change).
  async function refreshUser() {
    const me = await api.me()
    setUser(me)
    return me
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, loginWithToken, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
