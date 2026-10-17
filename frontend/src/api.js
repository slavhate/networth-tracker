import axios from 'axios';
import { publishWarnings } from './utils/notices';

const API_URL = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  // A request that already names its token (checking a fresh login before storing it) keeps it
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Warnings about unreachable price or NAV sources come back in the X-Warnings header (a JSON array).
const surfaceWarnings = (response) => {
  const raw = response?.headers?.['x-warnings'];
  if (!raw) return;
  try {
    const messages = JSON.parse(raw);
    if (Array.isArray(messages)) publishWarnings(messages.filter((m) => typeof m === 'string' && m.trim()));
  } catch {
    // a malformed header is ignored
  }
};

// Surface warning headers, and handle auth errors
api.interceptors.response.use(
  (response) => {
    surfaceWarnings(response);
    return response;
  },
  (error) => {
    surfaceWarnings(error.response);
    // Login endpoints use 401 for bad credentials/codes; let the form show those inline.
    const isLoginRequest = error.config?.url?.startsWith('/api/auth/login');
    const sentAuth = error.config?.headers?.Authorization;
    const storedToken = localStorage.getItem('token');
    // A request that carried an older token (e.g. sent just before a password change) must not
    // sign out a session that has since received a fresh token.
    const sentWithCurrentToken = !sentAuth || sentAuth === `Bearer ${storedToken}`;
    if (error.response?.status === 401 && !isLoginRequest && sentWithCurrentToken) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  register: (data) => api.post('/api/auth/register', data),
  login: (data) => {
    const formData = new URLSearchParams();
    formData.append('username', data.username);
    formData.append('password', data.password);
    return api.post('/api/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
  },
  // With a token: check a freshly issued token before it is stored
  getMe: (token) => api.get('/api/auth/me', token ? { headers: { Authorization: `Bearer ${token}` } } : undefined),
  verify2fa: (mfaToken, code) => api.post('/api/auth/login/2fa', { mfa_token: mfaToken, code }),
  changePassword: (data) => api.post('/api/auth/password', data),
};

// Two-Factor Authentication API
export const twoFactorAPI = {
  status: () => api.get('/api/auth/2fa/status'),
  setup: () => api.post('/api/auth/2fa/setup'),
  enable: (password, code) => api.post('/api/auth/2fa/enable', { password, code }),
  disable: (password, code) => api.post('/api/auth/2fa/disable', { password, code }),
};

// Path segments built from data are always encoded, so a stray "/", "?" or "#" can't change the route
const seg = (value) => encodeURIComponent(value);

// Assets API
export const assetsAPI = {
  getAll: () => api.get('/api/assets'),
  create: (data) => api.post('/api/assets', data),
  update: (id, data) => api.put(`/api/assets/${seg(id)}`, data),
  delete: (id) => api.delete(`/api/assets/${seg(id)}`),
  refreshNav: (id) => api.post(`/api/assets/${seg(id)}/refresh-nav`),
  refreshMetalRates: () => api.post('/api/assets/refresh-metal-rates'),
};

// Gold and silver rates last fetched (stored; reading them never fetches new ones)
export const metalRatesAPI = {
  get: () => api.get('/api/metal-rates'),
};

// NPS API
export const npsAPI = {
  schemes: () => api.get('/api/nps/schemes'),
};

// Liabilities API
export const liabilitiesAPI = {
  getAll: () => api.get('/api/liabilities'),
  create: (data) => api.post('/api/liabilities', data),
  update: (id, data) => api.put(`/api/liabilities/${seg(id)}`, data),
  delete: (id) => api.delete(`/api/liabilities/${seg(id)}`),
  schedule: (id) => api.get(`/api/liabilities/${seg(id)}/schedule`),
};

// Bank Accounts API
export const bankAccountsAPI = {
  getAll: () => api.get('/api/bank-accounts'),
  create: (data) => api.post('/api/bank-accounts', data),
  update: (id, data) => api.put(`/api/bank-accounts/${seg(id)}`, data),
  delete: (id) => api.delete(`/api/bank-accounts/${seg(id)}`),
};

// Insurances API
export const insurancesAPI = {
  getAll: () => api.get('/api/insurances'),
  create: (data) => api.post('/api/insurances', data),
  update: (id, data) => api.put(`/api/insurances/${seg(id)}`, data),
  delete: (id) => api.delete(`/api/insurances/${seg(id)}`),
};

// Mutual Funds API
export const mutualFundsAPI = {
  getAll: (refreshNav = false) => api.get('/api/mutual-funds', { params: { refresh_nav: refreshNav } }),
  create: (data) => api.post('/api/mutual-funds', data),
  update: (id, data) => api.put(`/api/mutual-funds/${seg(id)}`, data),
  delete: (id) => api.delete(`/api/mutual-funds/${seg(id)}`),
  refreshNav: (id) => api.post(`/api/mutual-funds/${seg(id)}/refresh-nav`),
};

// Equities API
export const equitiesAPI = {
  getAll: (refreshPrices = false) => api.get('/api/equities', { params: { refresh_prices: refreshPrices } }),
  create: (data) => api.post('/api/equities', data),
  update: (id, data) => api.put(`/api/equities/${seg(id)}`, data),
  delete: (id) => api.delete(`/api/equities/${seg(id)}`),
};

// Dashboard API
export const dashboardAPI = {
  getMetrics: () => api.get('/api/dashboard'),
  createSnapshot: () => api.post('/api/snapshot'),
};

// Snapshot Settings API (how often the dashboard saves an automatic snapshot)
export const snapshotSettingsAPI = {
  update: (frequency) => api.put('/api/settings/snapshots', { frequency }),
};

// Exchange Rate API
export const exchangeAPI = {
  getRate: () => api.get('/api/exchange-rate'),
};

// Goal API
export const goalAPI = {
  get: () => api.get('/api/goal'),
  update: (data) => api.put('/api/goal', data),
};

// Backup & Restore API
export const exportAPI = {
  download: () => api.get('/api/export'),
  restore: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/restore', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  }
};

export default api;
