import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authAPI } from './api';

const AuthContext = createContext(null);

// Thrown by register() when the account was created but the automatic sign-in after it failed
export class AccountCreatedError extends Error {
  constructor(cause) {
    super('Account created, but signing in failed. Please sign in.');
    this.name = 'AccountCreatedError';
    this.cause = cause;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // Set when the stored session could not be checked (network error or 5xx); the token is kept
  const [sessionError, setSessionError] = useState(false);

  const restoreSession = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setSessionError(false);
    authAPI.getMe()
      .then((res) => setUser(res.data))
      .catch((err) => {
        if (err?.response?.status === 401) {
          // Only a rejected token ends the session; the API interceptor also clears it
          localStorage.removeItem('token');
          setUser(null);
        } else {
          setSessionError(true);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  // The token is stored only once it has been accepted by /me, so a failed check leaves no half session
  const finishLogin = async (accessToken) => {
    const userResponse = await authAPI.getMe(accessToken);
    localStorage.setItem('token', accessToken);
    setSessionError(false);
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

  // Swap in a fresh access token, e.g. after a password change revoked the old one.
  const replaceToken = (accessToken) => {
    localStorage.setItem('token', accessToken);
  };

  const register = async (data) => {
    await authAPI.register(data);
    try {
      return await login({ username: data.username, password: data.password });
    } catch (err) {
      throw new AccountCreatedError(err);
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setSessionError(false);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{
      user, login, completeMfaLogin, replaceToken, register, logout, loading, sessionError, retrySession: restoreSession
    }}>
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
