import axios from 'axios';

export const API_BASE = process.env.REACT_APP_API_BASE !== undefined
  ? process.env.REACT_APP_API_BASE
  : 'http://localhost:5001';

const TOKEN_KEY = 'tour_expense_token';

export const tokenStorage = {
  get: () => {
    try { return localStorage.getItem(TOKEN_KEY) || ''; }
    catch (_) { return ''; }
  },
  set: (token) => {
    try { localStorage.setItem(TOKEN_KEY, token || ''); } catch (_) {}
  },
  clear: () => {
    try { localStorage.removeItem(TOKEN_KEY); } catch (_) {}
  },
};

const apiClient = axios.create({ baseURL: API_BASE });

apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.get();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const unauthorizedListeners = new Set();
export const onUnauthorized = (cb) => {
  unauthorizedListeners.add(cb);
  return () => unauthorizedListeners.delete(cb);
};

apiClient.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status;
    if (status === 401) {
      tokenStorage.clear();
      unauthorizedListeners.forEach((cb) => {
        try { cb(); } catch (_) {}
      });
    }
    return Promise.reject(error);
  },
);

export default apiClient;
