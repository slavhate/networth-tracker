import { createContext, useContext, useState, useEffect } from 'react';
import { authAPI } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      authAPI.getMe()
        .then((res) => setUser(res.data))
        .catch(() => localStorage.removeItem('token'))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const finishLogin = async (accessToken) => {
    localStorage.setItem('token', accessToken);
    const userResponse = await authAPI.getMe();
    setUser(userResponse.data);
    return userResponse.data;
  };

  const login = async (credentials) => {
    const response = await authAPI.login(credentials);
    if (response.data.mfa_required) {
      return { mfaRequired: true, mfaToken: response.data.mfa_token };
    }
    const user = await finishLogin(response.data.access_token);
    return { mfaRequired: false, user };
  };

  const completeMfaLogin = async (mfaToken, code) => {
    const response = await authAPI.verify2fa(mfaToken, code);
    return finishLogin(response.data.access_token);
  };

  const register = async (data) => {
    await authAPI.register(data);
    return login({ username: data.username, password: data.password });
  };

  const logout = () => {
    localStorage.removeItem('token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, completeMfaLogin, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
