import React, { useState } from 'react';
import apiClient from '../api/client';
import { useAuth } from './AuthContext';

/**
 * 비밀번호가 설정되지 않은 사용자(예: 인증번호 로그인으로 들어온 기존 회원)에게
 * 강제로 비밀번호 설정을 요구하는 모달. 닫기 버튼 / 외부 클릭으로 닫을 수 없다.
 */
export default function PasswordSetupModal({ open, onCompleted }) {
  const { user, setUser } = useAuth();
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!open) return null;

  const submit = async () => {
    setError('');
    if (password.length < 8) {
      setError('비밀번호는 최소 8자 이상이어야 합니다.');
      return;
    }
    if (password !== passwordConfirm) {
      setError('비밀번호 확인이 일치하지 않습니다.');
      return;
    }
    setLoading(true);
    try {
      const res = await apiClient.post('/api/auth/set-password', {
        new_password: password,
      });
      const nextUser = res.data?.data?.user || user;
      setUser(nextUser);
      onCompleted && onCompleted();
    } catch (e) {
      setError(e?.response?.data?.error || '비밀번호 설정에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.overlay}>
      <div style={styles.card}>
        <h2 style={styles.title}>🔐 비밀번호 설정</h2>
        <p style={styles.desc}>
          서비스 이용을 위해 비밀번호를 설정해 주세요. 다음 로그인부터 이메일과
          비밀번호로 로그인할 수 있습니다.
        </p>

        <label style={styles.label}>
          새 비밀번호 (8자 이상)
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="최소 8자"
            style={styles.input}
            autoComplete="new-password"
            autoFocus
          />
        </label>

        <label style={styles.label}>
          비밀번호 확인
          <input
            type="password"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
            placeholder="비밀번호 재입력"
            style={styles.input}
            autoComplete="new-password"
          />
        </label>

        {error && <div style={styles.error}>{error}</div>}

        <button
          type="button"
          onClick={submit}
          disabled={loading}
          style={styles.primary}
        >
          {loading ? '저장 중…' : '비밀번호 저장'}
        </button>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 9999,
    background: 'rgba(10, 30, 20, 0.65)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 16,
  },
  card: {
    width: '100%', maxWidth: 420,
    background: '#ffffff', borderRadius: 16, padding: 28,
    boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
    display: 'flex', flexDirection: 'column', gap: 12,
  },
  title: { margin: 0, fontSize: 20, color: '#1a2e22' },
  desc: { margin: 0, fontSize: 13, color: '#556b5c', lineHeight: 1.5 },
  label: {
    display: 'flex', flexDirection: 'column', gap: 6,
    fontSize: 13, color: '#3d5c47', fontWeight: 500,
  },
  input: {
    padding: '10px 12px', borderRadius: 8,
    border: '1px solid #c5e1cf', fontSize: 15, outline: 'none',
    background: '#ffffff', color: '#1a2e22',
  },
  primary: {
    marginTop: 8, padding: '12px 16px', borderRadius: 10, border: 'none',
    background: 'linear-gradient(135deg, #2ecc71 0%, #00b894 100%)',
    color: '#fff', fontSize: 15, fontWeight: 600, cursor: 'pointer',
    boxShadow: '0 6px 16px rgba(46, 204, 113, 0.35)',
  },
  error: {
    padding: '10px 12px', background: '#fde8ec',
    color: '#c0334d', borderRadius: 8, fontSize: 13,
    border: '1px solid #f6c9d2',
  },
};
