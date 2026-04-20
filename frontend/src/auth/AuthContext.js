import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import apiClient, { onUnauthorized, tokenStorage } from '../api/client';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => tokenStorage.get());
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    if (!tokenStorage.get()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await apiClient.get('/api/auth/me');
      setUser(res.data?.data || null);
    } catch (_) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
    const off = onUnauthorized(() => {
      setUser(null);
      setToken('');
    });
    return off;
  }, [fetchMe]);

  const loginWithToken = useCallback((accessToken, userObj) => {
    tokenStorage.set(accessToken);
    setToken(accessToken);
    setUser(userObj);
  }, []);

  const logout = useCallback(async () => {
    try { await apiClient.post('/api/auth/logout'); } catch (_) {}
    tokenStorage.clear();
    setToken('');
    setUser(null);
  }, []);

  const value = useMemo(() => ({
    user,
    token,
    loading,
    isAuthenticated: !!user,
    isAdmin: !!user?.is_admin,
    hasPassword: !!user?.has_password,
    loginWithToken,
    logout,
    refresh: fetchMe,
    setUser,
  }), [user, token, loading, loginWithToken, logout, fetchMe]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};
