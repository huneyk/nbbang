import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { AuthProvider } from './auth/AuthContext';
import { InstallPromptProvider } from './InstallPrompt';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <AuthProvider>
      <InstallPromptProvider>
        <App />
      </InstallPromptProvider>
    </AuthProvider>
  </React.StrictMode>
);

// PWA: 서비스워커 등록 (https 또는 localhost에서만 동작).
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    const isLocalhost = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
    const isSecure = window.location.protocol === 'https:' || isLocalhost;
    if (!isSecure) return;

    navigator.serviceWorker
      .register(`${process.env.PUBLIC_URL || ''}/service-worker.js`)
      .catch((err) => console.warn('SW 등록 실패:', err));
  });
}
