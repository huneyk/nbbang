import React, { useState } from 'react';
import apiClient from '../api/client';
import { useAuth } from './AuthContext';
import UsageGuide from '../UsageGuide';

const TABS = [
  { id: 'login', label: '로그인' },
  { id: 'signup', label: '회원가입' },
];

// mode 값:
// - 'login_password' : 이메일 + 비밀번호 로그인 (로그인 탭 기본)
// - 'login_code_email' / 'login_code_code' : 인증번호 로그인 폴백
// - 'signup_email'   / 'signup_code'      : 회원가입 (코드 요청 → 코드+비밀번호 확정)
// - 'reset_email'    / 'reset_code'       : 비밀번호 재설정
export default function LoginPage() {
  const { loginWithToken } = useAuth();
  const [tab, setTab] = useState('login');
  const [mode, setMode] = useState('login_password');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [resendIn, setResendIn] = useState(0);
  const [showGuide, setShowGuide] = useState(false);

  const resetTransientState = () => {
    setPassword('');
    setPasswordConfirm('');
    setCode('');
    setError('');
    setInfo('');
  };

  const switchTab = (next) => {
    setTab(next);
    setMode(next === 'signup' ? 'signup_email' : 'login_password');
    resetTransientState();
  };

  const startResendCountdown = (seconds = 60) => {
    setResendIn(seconds);
    const t = setInterval(() => {
      setResendIn((s) => {
        if (s <= 1) { clearInterval(t); return 0; }
        return s - 1;
      });
    }, 1000);
  };

  // 인증번호 요청: purpose에 따라 mode 전환
  const requestCode = async (purpose) => {
    setError('');
    setInfo('');
    if (!email.trim()) {
      setError('이메일을 입력해주세요.');
      return;
    }
    if (purpose === 'signup') {
      if (password.length < 8) {
        setError('비밀번호는 최소 8자 이상이어야 합니다.');
        return;
      }
      if (password !== passwordConfirm) {
        setError('비밀번호 확인이 일치하지 않습니다.');
        return;
      }
    }
    setLoading(true);
    try {
      await apiClient.post('/api/auth/request-code', {
        email: email.trim(),
        purpose,
      });
      const nextMode = purpose === 'signup'
        ? 'signup_code'
        : purpose === 'reset'
          ? 'reset_code'
          : 'login_code_code';
      setMode(nextMode);
      setInfo(`${email}로 인증번호를 보냈습니다. 메일함을 확인해주세요.`);
      startResendCountdown(60);
    } catch (e) {
      setError(e?.response?.data?.error || '인증번호 발송에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const loginWithPassword = async () => {
    setError('');
    setInfo('');
    if (!email.trim()) {
      setError('이메일을 입력해주세요.');
      return;
    }
    if (!password) {
      setError('비밀번호를 입력해주세요.');
      return;
    }
    setLoading(true);
    try {
      const res = await apiClient.post('/api/auth/login', {
        email: email.trim(),
        password,
      });
      const { access_token, user } = res.data?.data || {};
      if (!access_token) throw new Error('토큰이 없습니다.');
      loginWithToken(access_token, user);
    } catch (e) {
      const status = e?.response?.status;
      const serverError = e?.response?.data?.error;
      if (status === 409) {
        // 비밀번호 미설정 계정 → 인증번호 로그인으로 유도
        setError(serverError || '비밀번호가 설정되지 않은 계정입니다. 인증번호로 로그인해주세요.');
      } else {
        setError(serverError || '로그인에 실패했습니다.');
      }
    } finally {
      setLoading(false);
    }
  };

  // /verify-code 호출. purpose에 따라 password 포함 여부가 다름.
  const verifyCode = async (purpose) => {
    setError('');
    if (!/^\d{6}$/.test(code.trim())) {
      setError('인증번호 6자리를 입력해주세요.');
      return;
    }
    if (purpose === 'reset') {
      if (password.length < 8) {
        setError('새 비밀번호는 최소 8자 이상이어야 합니다.');
        return;
      }
      if (password !== passwordConfirm) {
        setError('새 비밀번호 확인이 일치하지 않습니다.');
        return;
      }
    }
    setLoading(true);
    try {
      const payload = {
        email: email.trim(),
        code: code.trim(),
        purpose,
      };
      if (purpose === 'signup') {
        payload.name = name.trim();
        payload.password = password;
      }
      if (purpose === 'reset') {
        payload.password = password;
      }
      const res = await apiClient.post('/api/auth/verify-code', payload);
      const { access_token, user } = res.data?.data || {};
      if (!access_token) throw new Error('토큰이 없습니다.');
      loginWithToken(access_token, user);
    } catch (e) {
      setError(e?.response?.data?.error || '인증에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const renderLoginPassword = () => (
    <div style={styles.form}>
      <label style={styles.label}>
        이메일
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          style={styles.input}
          autoFocus
        />
      </label>
      <label style={styles.label}>
        비밀번호
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') loginWithPassword(); }}
          placeholder="비밀번호"
          style={styles.input}
          autoComplete="current-password"
        />
      </label>
      <button
        type="button"
        onClick={loginWithPassword}
        disabled={loading}
        style={styles.primaryButton}
      >
        {loading ? '확인 중…' : '로그인'}
      </button>
      <div style={styles.actionsRow}>
        <button
          type="button"
          onClick={() => { setMode('login_code_email'); resetTransientState(); }}
          style={styles.linkButton}
        >
          인증번호로 로그인
        </button>
        <button
          type="button"
          onClick={() => { setMode('reset_email'); resetTransientState(); }}
          style={styles.linkButton}
        >
          비밀번호 찾기
        </button>
      </div>
    </div>
  );

  const renderLoginCodeEmail = () => (
    <div style={styles.form}>
      <div style={styles.modeHint}>인증번호로 로그인 (임시/폴백)</div>
      <label style={styles.label}>
        이메일
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          style={styles.input}
          autoFocus
        />
      </label>
      <button
        type="button"
        onClick={() => requestCode('login')}
        disabled={loading}
        style={styles.primaryButton}
      >
        {loading ? '전송 중…' : '인증번호 받기'}
      </button>
      <div style={styles.actionsRow}>
        <button
          type="button"
          onClick={() => { setMode('login_password'); resetTransientState(); }}
          style={styles.linkButton}
        >
          ← 비밀번호 로그인으로
        </button>
      </div>
    </div>
  );

  const renderLoginCodeCode = () => (
    <div style={styles.form}>
      <div style={styles.codeNote}>{email}</div>
      <label style={styles.label}>
        인증번호 (6자리)
        <input
          type="text"
          inputMode="numeric"
          pattern="\d{6}"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          placeholder="123456"
          style={{ ...styles.input, letterSpacing: '8px', textAlign: 'center', fontSize: 20 }}
          autoFocus
        />
      </label>
      <button
        type="button"
        onClick={() => verifyCode('login')}
        disabled={loading}
        style={styles.primaryButton}
      >
        {loading ? '확인 중…' : '로그인'}
      </button>
      <div style={styles.actionsRow}>
        <button
          type="button"
          onClick={() => { setMode('login_code_email'); setCode(''); setError(''); }}
          style={styles.linkButton}
        >
          이메일 변경
        </button>
        <button
          type="button"
          onClick={() => requestCode('login')}
          disabled={loading || resendIn > 0}
          style={{ ...styles.linkButton, opacity: resendIn > 0 ? 0.5 : 1 }}
        >
          {resendIn > 0 ? `재전송 (${resendIn}s)` : '인증번호 재전송'}
        </button>
      </div>
    </div>
  );

  const renderSignupEmail = () => (
    <div style={styles.form}>
      <label style={styles.label}>
        이름 (선택)
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="홍길동"
          style={styles.input}
        />
      </label>
      <label style={styles.label}>
        이메일
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          style={styles.input}
          autoFocus
        />
      </label>
      <label style={styles.label}>
        비밀번호 (8자 이상)
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="최소 8자"
          style={styles.input}
          autoComplete="new-password"
        />
      </label>
      <label style={styles.label}>
        비밀번호 확인
        <input
          type="password"
          value={passwordConfirm}
          onChange={(e) => setPasswordConfirm(e.target.value)}
          placeholder="비밀번호 재입력"
          style={styles.input}
          autoComplete="new-password"
        />
      </label>
      <button
        type="button"
        onClick={() => requestCode('signup')}
        disabled={loading}
        style={styles.primaryButton}
      >
        {loading ? '전송 중…' : '인증번호 받기'}
      </button>
    </div>
  );

  const renderSignupCode = () => (
    <div style={styles.form}>
      <div style={styles.codeNote}>{email}</div>
      <label style={styles.label}>
        인증번호 (6자리)
        <input
          type="text"
          inputMode="numeric"
          pattern="\d{6}"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          placeholder="123456"
          style={{ ...styles.input, letterSpacing: '8px', textAlign: 'center', fontSize: 20 }}
          autoFocus
        />
      </label>
      <button
        type="button"
        onClick={() => verifyCode('signup')}
        disabled={loading}
        style={styles.primaryButton}
      >
        {loading ? '확인 중…' : '가입 완료'}
      </button>
      <div style={styles.actionsRow}>
        <button
          type="button"
          onClick={() => { setMode('signup_email'); setCode(''); setError(''); }}
          style={styles.linkButton}
        >
          이전 단계
        </button>
        <button
          type="button"
          onClick={() => requestCode('signup')}
          disabled={loading || resendIn > 0}
          style={{ ...styles.linkButton, opacity: resendIn > 0 ? 0.5 : 1 }}
        >
          {resendIn > 0 ? `재전송 (${resendIn}s)` : '인증번호 재전송'}
        </button>
      </div>
    </div>
  );

  const renderResetEmail = () => (
    <div style={styles.form}>
      <div style={styles.modeHint}>비밀번호 재설정</div>
      <label style={styles.label}>
        가입된 이메일
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          style={styles.input}
          autoFocus
        />
      </label>
      <button
        type="button"
        onClick={() => requestCode('reset')}
        disabled={loading}
        style={styles.primaryButton}
      >
        {loading ? '전송 중…' : '인증번호 받기'}
      </button>
      <div style={styles.actionsRow}>
        <button
          type="button"
          onClick={() => { setMode('login_password'); resetTransientState(); }}
          style={styles.linkButton}
        >
          ← 로그인으로
        </button>
      </div>
    </div>
  );

  const renderResetCode = () => (
    <div style={styles.form}>
      <div style={styles.codeNote}>{email}</div>
      <label style={styles.label}>
        인증번호 (6자리)
        <input
          type="text"
          inputMode="numeric"
          pattern="\d{6}"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          placeholder="123456"
          style={{ ...styles.input, letterSpacing: '8px', textAlign: 'center', fontSize: 20 }}
          autoFocus
        />
      </label>
      <label style={styles.label}>
        새 비밀번호 (8자 이상)
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="최소 8자"
          style={styles.input}
          autoComplete="new-password"
        />
      </label>
      <label style={styles.label}>
        새 비밀번호 확인
        <input
          type="password"
          value={passwordConfirm}
          onChange={(e) => setPasswordConfirm(e.target.value)}
          placeholder="비밀번호 재입력"
          style={styles.input}
          autoComplete="new-password"
        />
      </label>
      <button
        type="button"
        onClick={() => verifyCode('reset')}
        disabled={loading}
        style={styles.primaryButton}
      >
        {loading ? '확인 중…' : '비밀번호 재설정 & 로그인'}
      </button>
      <div style={styles.actionsRow}>
        <button
          type="button"
          onClick={() => { setMode('reset_email'); setCode(''); setError(''); }}
          style={styles.linkButton}
        >
          이메일 변경
        </button>
        <button
          type="button"
          onClick={() => requestCode('reset')}
          disabled={loading || resendIn > 0}
          style={{ ...styles.linkButton, opacity: resendIn > 0 ? 0.5 : 1 }}
        >
          {resendIn > 0 ? `재전송 (${resendIn}s)` : '인증번호 재전송'}
        </button>
      </div>
    </div>
  );

  const renderBody = () => {
    switch (mode) {
      case 'login_password':  return renderLoginPassword();
      case 'login_code_email': return renderLoginCodeEmail();
      case 'login_code_code':  return renderLoginCodeCode();
      case 'signup_email':    return renderSignupEmail();
      case 'signup_code':     return renderSignupCode();
      case 'reset_email':     return renderResetEmail();
      case 'reset_code':      return renderResetCode();
      default:                return renderLoginPassword();
    }
  };

  return (
    <div style={styles.wrapper}>
      <div style={styles.card}>
        <div style={styles.brand}>
          <img src="/npang_logo.png" alt="Npang" style={styles.brandLogo} />
          <p style={styles.brandSub}>"N빵 하자!" 영수증만 찰칵! 여행 경비 정산 실시간으로 끝!</p>
        </div>

        <div style={styles.tabs}>
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => switchTab(t.id)}
              style={{
                ...styles.tab,
                ...(tab === t.id ? styles.tabActive : {}),
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {renderBody()}

        {info && <div style={styles.info}>{info}</div>}
        {error && <div style={styles.error}>{error}</div>}

        <div style={styles.guideRow}>
          <button
            type="button"
            onClick={() => setShowGuide(true)}
            style={styles.guideButton}
          >
            📖 Npang <span style={{ fontFamily: "'Gamja Flower', cursive" }}>초간단 사용법!</span>
          </button>
        </div>
      </div>
      <UsageGuide open={showGuide} onClose={() => setShowGuide(false)} />
    </div>
  );
}

const styles = {
  wrapper: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: `
      radial-gradient(ellipse at 10% 20%, rgba(46, 204, 113, 0.18) 0%, transparent 55%),
      radial-gradient(ellipse at 90% 80%, rgba(0, 184, 148, 0.20) 0%, transparent 55%),
      linear-gradient(135deg, #f0f9f4 0%, #e4f3eb 100%)
    `,
    padding: 24,
  },
  card: {
    width: '100%',
    maxWidth: 440,
    background: '#ffffff',
    borderRadius: 16,
    padding: 32,
    border: '1px solid #c5e1cf',
    boxShadow: '0 20px 60px rgba(46, 204, 113, 0.18)',
  },
  brand: { textAlign: 'center', marginBottom: 24 },
  brandLogo: {
    height: 144,
    width: 'auto',
    display: 'block',
    margin: '0 auto 8px',
  },
  brandSub: {
    margin: 0,
    fontSize: 14,
    color: '#7a9b85',
    fontFamily: "'Gamja Flower', cursive",
    letterSpacing: '0.3px',
  },
  tabs: {
    display: 'flex',
    gap: 24,
    marginBottom: 20,
    borderBottom: '1px solid #c5e1cf',
    justifyContent: 'center',
  },
  tab: {
    padding: '10px 4px',
    borderRadius: 0,
    borderTop: 'none',
    borderRight: 'none',
    borderLeft: 'none',
    borderBottomWidth: 2,
    borderBottomStyle: 'solid',
    borderBottomColor: 'transparent',
    background: 'transparent',
    cursor: 'pointer',
    fontSize: 15,
    color: '#7a9b85',
    fontWeight: 500,
    marginBottom: -1,
  },
  tabActive: {
    color: '#27ae60',
    borderBottomColor: '#2ecc71',
    fontWeight: 700,
  },
  form: { display: 'flex', flexDirection: 'column', gap: 14 },
  label: { display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13, color: '#3d5c47', fontWeight: 500 },
  input: {
    padding: '10px 12px',
    borderRadius: 8,
    border: '1px solid #c5e1cf',
    fontSize: 15,
    outline: 'none',
    background: '#ffffff',
    color: '#1a2e22',
  },
  primaryButton: {
    padding: '12px 16px',
    borderRadius: 10,
    border: 'none',
    background: 'linear-gradient(135deg, #2ecc71 0%, #00b894 100%)',
    color: '#fff',
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
    boxShadow: '0 6px 16px rgba(46, 204, 113, 0.35)',
  },
  linkButton: {
    background: 'transparent',
    border: 'none',
    color: '#27ae60',
    cursor: 'pointer',
    fontSize: 13,
    textDecoration: 'underline',
    padding: 0,
  },
  actionsRow: {
    display: 'flex',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  modeHint: {
    fontSize: 12,
    color: '#7a9b85',
    textAlign: 'center',
    marginBottom: 4,
  },
  codeNote: {
    fontSize: 13,
    color: '#3d5c47',
    background: '#e4f3eb',
    padding: '8px 12px',
    borderRadius: 8,
    textAlign: 'center',
    border: '1px solid #c5e1cf',
  },
  info: {
    marginTop: 16,
    padding: '10px 12px',
    background: '#e6f7f0',
    color: '#127a5a',
    borderRadius: 8,
    fontSize: 13,
    border: '1px solid #bfe5d2',
  },
  error: {
    marginTop: 16,
    padding: '10px 12px',
    background: '#fde8ec',
    color: '#c0334d',
    borderRadius: 8,
    fontSize: 13,
    border: '1px solid #f6c9d2',
  },
  guideRow: {
    marginTop: 20,
    paddingTop: 16,
    borderTop: '1px solid #e4f3eb',
    textAlign: 'center',
  },
  guideButton: {
    background: 'transparent',
    border: '1px dashed #c5e1cf',
    color: '#27ae60',
    padding: '9px 16px',
    borderRadius: 999,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
  },
};
