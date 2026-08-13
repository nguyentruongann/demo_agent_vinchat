import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  fetchCurrentUser,
  loginAccount,
  logoutAccount,
  registerAccount,
} from '../services/api';

const AuthContext = createContext(undefined);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    fetchCurrentUser()
      .then((current) => {
        if (active) setUser(current);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const login = async (identifier, password) => {
    const authenticated = await loginAccount(identifier, password);
    setUser(authenticated);
    return authenticated;
  };

  const register = async (data) => {
    const authenticated = await registerAccount(data);
    setUser(authenticated);
    return authenticated;
  };

  const logout = async () => {
    await logoutAccount();
    setUser(null);
  };

  const value = useMemo(() => ({
    user,
    loading,
    login,
    register,
    logout,
    isStaff: user?.role === 'staff' || user?.role === 'admin',
    isAdmin: user?.role === 'admin',
  }), [user, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};
