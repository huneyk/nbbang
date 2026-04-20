import React, { useEffect, useState } from 'react';
import apiClient from '../api/client';

export default function AdminSettingsModal({ open, onClose, onSaved }) {
  const [status, setStatus] = useState({ google_api_key_set: false, koreaexim_api_key_set: false });
  const [google, setGoogle] = useState('');
  const [koreaexim, setKoreaexim] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');

  useEffect(() => {
    if (!open) return;
    setError('');
    setSaved('');
    setGoogle('');
    setKoreaexim('');
    apiClient.get('/api/admin/app-settings')
      .then((res) => setStatus(res.data?.data || {}))
      .catch((e) => setError(e?.response?.data?.error || '관리자 설정을 불러올 수 없습니다.'));
  }, [open]);

  if (!open) return null;

  const submit = async () => {
    setLoading(true);
    setError('');
    setSaved('');
    const updates = {};
    if (google.trim()) updates.google_api_key = google.trim();
    if (koreaexim.trim()) updates.koreaexim_api_key = koreaexim.trim();
    if (!Object.keys(updates).length) {
      setError('갱신할 키 값을 입력하세요.');
      setLoading(false);
      return;
    }
    try {
      const res = await apiClient.put('/api/admin/app-settings', updates);
      setStatus(res.data?.data || {});
      setSaved('저장되었습니다.');
      setGoogle('');
      setKoreaexim('');
      onSaved && onSaved();
    } catch (e) {
      setError(e?.response?.data?.error || '저장에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <h2 style={styles.title}>관리자 - API 키 설정</h2>
          <button type="button" onClick={onClose} style={styles.closeBtn}>✕</button>
        </div>

        <p style={styles.desc}>
          모든 사용자가 공유하는 API 키를 관리합니다. 빈 칸으로 두면 기존 값이 유지됩니다.
        </p>

        <div style={styles.row}>
          <label style={styles.label}>
            Google API Key
            <span style={status.google_api_key_set ? styles.badgeOk : styles.badgeOff}>
              {status.google_api_key_set ? '설정됨' : '미설정'}
            </span>
          </label>
          <input
            type="password"
            value={google}
            onChange={(e) => setGoogle(e.target.value)}
            placeholder="새 키를 입력하면 덮어씁니다"
            style={styles.input}
            autoComplete="off"
          />
        </div>

        <div style={styles.row}>
          <label style={styles.label}>
            한국수출입은행 API Key
            <span style={status.koreaexim_api_key_set ? styles.badgeOk : styles.badgeOff}>
              {status.koreaexim_api_key_set ? '설정됨' : '미설정'}
            </span>
          </label>
          <input
            type="password"
            value={koreaexim}
            onChange={(e) => setKoreaexim(e.target.value)}
            placeholder="새 키를 입력하면 덮어씁니다"
            style={styles.input}
            autoComplete="off"
          />
        </div>

        {error && <div style={styles.error}>{error}</div>}
        {saved && <div style={styles.info}>{saved}</div>}

        <div style={styles.actions}>
          <button type="button" onClick={onClose} style={styles.secondary}>닫기</button>
          <button type="button" onClick={submit} disabled={loading} style={styles.primary}>
            {loading ? '저장 중…' : '저장'}
          </button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  backdrop: {
    position: 'fixed', inset: 0,
    background: 'rgba(0,0,0,0.5)', zIndex: 1000,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 16,
  },
  modal: {
    background: '#fff', borderRadius: 12, padding: 24,
    width: '100%', maxWidth: 480, color: '#1a1a2e',
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: 8,
  },
  title: { margin: 0, fontSize: 18 },
  closeBtn: {
    background: 'transparent', border: 'none', fontSize: 18, cursor: 'pointer', color: '#888',
  },
  desc: { fontSize: 13, color: '#666', marginBottom: 20 },
  row: { marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 6 },
  label: {
    display: 'flex', alignItems: 'center', gap: 8,
    fontSize: 13, fontWeight: 600, color: '#333',
  },
  input: {
    padding: '10px 12px', border: '1px solid #d0d0d8',
    borderRadius: 8, fontSize: 14, outline: 'none',
  },
  badgeOk: {
    background: '#e6f7f0', color: '#127a5a',
    fontSize: 11, padding: '2px 8px', borderRadius: 999,
  },
  badgeOff: {
    background: '#fde8ec', color: '#c0334d',
    fontSize: 11, padding: '2px 8px', borderRadius: 999,
  },
  actions: {
    display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12,
  },
  primary: {
    background: '#e94560', color: '#fff', border: 'none',
    padding: '10px 18px', borderRadius: 8, cursor: 'pointer', fontWeight: 600,
  },
  secondary: {
    background: '#f4f6fb', color: '#333', border: '1px solid #e0e0e0',
    padding: '10px 18px', borderRadius: 8, cursor: 'pointer',
  },
  error: {
    background: '#fde8ec', color: '#c0334d',
    padding: '8px 12px', borderRadius: 8, fontSize: 13, marginBottom: 8,
  },
  info: {
    background: '#e6f7f0', color: '#127a5a',
    padding: '8px 12px', borderRadius: 8, fontSize: 13, marginBottom: 8,
  },
};
