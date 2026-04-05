import axios from 'axios';

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
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
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
  getMe: () => api.get('/api/auth/me'),
};

// Assets API
export const assetsAPI = {
  getAll: () => api.get('/api/assets'),
  get: (id) => api.get(`/api/assets/${id}`),
  create: (data) => api.post('/api/assets', data),
  update: (id, data) => api.put(`/api/assets/${id}`, data),
  delete: (id) => api.delete(`/api/assets/${id}`),
};

// Liabilities API
export const liabilitiesAPI = {
  getAll: () => api.get('/api/liabilities'),
  get: (id) => api.get(`/api/liabilities/${id}`),
  create: (data) => api.post('/api/liabilities', data),
  update: (id, data) => api.put(`/api/liabilities/${id}`, data),
  delete: (id) => api.delete(`/api/liabilities/${id}`),
};

// Bank Accounts API
export const bankAccountsAPI = {
  getAll: () => api.get('/api/bank-accounts'),
  get: (id) => api.get(`/api/bank-accounts/${id}`),
  create: (data) => api.post('/api/bank-accounts', data),
  update: (id, data) => api.put(`/api/bank-accounts/${id}`, data),
  delete: (id) => api.delete(`/api/bank-accounts/${id}`),
  getSummary: () => api.get('/api/bank-accounts-summary'),
};

// Insurances API
export const insurancesAPI = {
  getAll: () => api.get('/api/insurances'),
  get: (id) => api.get(`/api/insurances/${id}`),
  create: (data) => api.post('/api/insurances', data),
  update: (id, data) => api.put(`/api/insurances/${id}`, data),
  delete: (id) => api.delete(`/api/insurances/${id}`),
  getSummary: () => api.get('/api/insurances-summary'),
};

// Mutual Funds API
export const mutualFundsAPI = {
  getAll: (refreshNav = false) => api.get(`/api/mutual-funds?refresh_nav=${refreshNav}`),
  get: (id) => api.get(`/api/mutual-funds/${id}`),
  create: (data) => api.post('/api/mutual-funds', data),
  update: (id, data) => api.put(`/api/mutual-funds/${id}`, data),
  delete: (id) => api.delete(`/api/mutual-funds/${id}`),
  getSummary: () => api.get('/api/mutual-funds-summary'),
  refreshNav: (id) => api.post(`/api/mutual-funds/${id}/refresh-nav`),
  searchNav: (query) => api.get(`/api/nav/search?q=${encodeURIComponent(query)}`),
};

// Equities API
export const equitiesAPI = {
  getAll: (refreshPrices = false) => api.get(`/api/equities?refresh_prices=${refreshPrices}`),
  get: (id) => api.get(`/api/equities/${id}`),
  create: (data) => api.post('/api/equities', data),
  update: (id, data) => api.put(`/api/equities/${id}`, data),
  delete: (id) => api.delete(`/api/equities/${id}`),
  refreshPrice: (id) => api.post(`/api/equities/${id}/refresh-price`),
  getSummary: () => api.get('/api/equities-summary'),
  getStockPrice: (market, symbol) => api.get(`/api/stock-price/${market}/${symbol}`),
};

// Dashboard API
export const dashboardAPI = {
  getMetrics: () => api.get('/api/dashboard'),
  createSnapshot: () => api.post('/api/snapshot'),
};

// Exchange Rate API
export const exchangeAPI = {
  getRate: () => api.get('/api/exchange-rate'),
};

// Goal API
export const goalAPI = {
  get: () => api.get('/api/goal'),
  create: (data) => api.post('/api/goal', data),
  update: (data) => api.put('/api/goal', data),
  delete: () => api.delete('/api/goal'),
};

export default api;
