import React, { useCallback, useEffect, useState } from 'react';
import apiClient from '../api/client';
import { useAuth } from '../auth/AuthContext';

const TABS = [
  { id: 'dashboard', label: '📊 사용자 현황' },
  { id: 'users', label: '👥 회원 관리' },
  { id: 'keys', label: '🔑 API 키 관리' },
];

const formatNumber = (value) => new Intl.NumberFormat('ko-KR').format(Math.round(value || 0));

const formatDateTime = (iso) => {
  if (!iso) return '-';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('ko-KR', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (_) {
    return iso;
  }
};

export default function AdminPanel({ open, onClose }) {
  const { user: currentUser } = useAuth();
  const [tab, setTab] = useState('dashboard');
  const [banner, setBanner] = useState(null);

  useEffect(() => {
    if (!open) {
      setTab('dashboard');
      setBanner(null);
    }
  }, [open]);

  const notify = (message, type = 'info') => {
    setBanner({ message, type });
    setTimeout(() => setBanner(null), 3500);
  };

  if (!open) return null;

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <h2 style={styles.title}>🛠 관리자 페이지</h2>
          <button type="button" onClick={onClose} style={styles.closeBtn}>✕</button>
        </div>

        <div style={styles.tabs}>
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              style={{ ...styles.tab, ...(tab === t.id ? styles.tabActive : {}) }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {banner && (
          <div style={{ ...styles.banner, ...(banner.type === 'error' ? styles.bannerError : styles.bannerInfo) }}>
            {banner.message}
          </div>
        )}

        <div style={styles.body}>
          {tab === 'dashboard' && <DashboardTab notify={notify} />}
          {tab === 'users' && <UsersTab currentUserId={currentUser?.id} notify={notify} />}
          {tab === 'keys' && <KeysTab notify={notify} />}
        </div>
      </div>
    </div>
  );
}

// ===== 탭 1: 사용자 현황 =====

function DashboardTab({ notify }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/admin/stats');
      setStats(res.data?.data || null);
    } catch (e) {
      notify(e?.response?.data?.error || '통계를 불러올 수 없습니다.', 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => { load(); }, [load]);

  if (loading && !stats) return <div style={styles.placeholder}>불러오는 중…</div>;
  if (!stats) return <div style={styles.placeholder}>데이터가 없습니다.</div>;

  const cards = [
    { label: '전체 사용자', value: stats.users?.total, accent: '#4c6ef5' },
    { label: '관리자', value: stats.users?.admins, accent: '#ffc300' },
    { label: '최근 7일 활성', value: stats.users?.active_7d, accent: '#00d9a5' },
    { label: '최근 30일 활성', value: stats.users?.active_30d, accent: '#2ecc71' },
    { label: '최근 7일 가입', value: stats.users?.signups_7d, accent: '#845ef7' },
    { label: '최근 30일 가입', value: stats.users?.signups_30d, accent: '#5c7cfa' },
    { label: '전체 여행 수', value: stats.trips?.total, accent: '#e94560' },
    { label: '전체 경비 건수', value: stats.expenses?.total_count, accent: '#fd7e14' },
  ];

  return (
    <div>
      <div style={styles.cardsGrid}>
        {cards.map((c) => (
          <div key={c.label} style={{ ...styles.statCard, borderLeftColor: c.accent }}>
            <div style={styles.statLabel}>{c.label}</div>
            <div style={styles.statValue}>{formatNumber(c.value)}</div>
          </div>
        ))}
        <div style={{ ...styles.statCard, borderLeftColor: '#20c997', gridColumn: 'span 2' }}>
          <div style={styles.statLabel}>전체 원화 환산 경비</div>
          <div style={styles.statValue}>₩{formatNumber(stats.expenses?.total_krw)}</div>
        </div>
      </div>
      <div style={styles.hintBox}>
        마지막 집계: {formatDateTime(stats.generated_at)}
        <button type="button" onClick={load} style={styles.ghostBtn} disabled={loading}>
          {loading ? '새로고침…' : '🔄 새로고침'}
        </button>
      </div>
    </div>
  );
}

// ===== 탭 2: 회원 관리 =====

function UsersTab({ currentUserId, notify }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/admin/users?with_stats=true');
      setUsers(res.data?.data || []);
    } catch (e) {
      notify(e?.response?.data?.error || '회원 목록을 불러올 수 없습니다.', 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => { load(); }, [load]);

  const toggleAdmin = async (u) => {
    const action = u.is_admin ? '관리자 권한을 해제' : '관리자 권한을 부여';
    if (!window.confirm(`${u.email} 님의 ${action}하시겠습니까?`)) return;
    setBusyId(u.id);
    try {
      await apiClient.patch(`/api/admin/users/${u.id}`, { is_admin: !u.is_admin });
      notify('권한이 변경되었습니다.');
      load();
    } catch (e) {
      notify(e?.response?.data?.error || '권한 변경에 실패했습니다.', 'error');
    } finally {
      setBusyId('');
    }
  };

  const resetPassword = async (u) => {
    if (!window.confirm(`${u.email} 님의 비밀번호를 초기화하시겠습니까?\n사용자는 이메일 인증으로 재설정해야 합니다.`)) return;
    setBusyId(u.id);
    try {
      await apiClient.post(`/api/admin/users/${u.id}/reset-password`);
      notify('비밀번호가 초기화되었습니다.');
      load();
    } catch (e) {
      notify(e?.response?.data?.error || '비밀번호 초기화에 실패했습니다.', 'error');
    } finally {
      setBusyId('');
    }
  };

  const deleteUser = async (u) => {
    if (!window.confirm(`${u.email} 계정과 연결된 모든 여행/경비가 삭제됩니다. 계속하시겠습니까?`)) return;
    if (!window.confirm('이 작업은 되돌릴 수 없습니다. 정말 삭제할까요?')) return;
    setBusyId(u.id);
    try {
      await apiClient.delete(`/api/admin/users/${u.id}`);
      notify(`${u.email} 계정이 삭제되었습니다.`);
      load();
    } catch (e) {
      notify(e?.response?.data?.error || '삭제에 실패했습니다.', 'error');
    } finally {
      setBusyId('');
    }
  };

  const filtered = query.trim()
    ? users.filter((u) => {
        const q = query.trim().toLowerCase();
        return (u.email || '').toLowerCase().includes(q) || (u.name || '').toLowerCase().includes(q);
      })
    : users;

  return (
    <div>
      <div style={styles.toolbar}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="이메일 또는 이름으로 검색"
          style={styles.searchInput}
        />
        <button type="button" onClick={load} style={styles.ghostBtn} disabled={loading}>
          {loading ? '불러오는 중…' : '🔄 새로고침'}
        </button>
      </div>

      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>이메일 / 이름</th>
              <th style={styles.th}>권한</th>
              <th style={styles.th}>가입일</th>
              <th style={styles.th}>마지막 로그인</th>
              <th style={styles.th}>사용 현황</th>
              <th style={styles.th}>관리</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} style={styles.emptyRow}>
                  {loading ? '불러오는 중…' : '표시할 회원이 없습니다.'}
                </td>
              </tr>
            )}
            {filtered.map((u) => {
              const isSelf = u.id === currentUserId;
              const busy = busyId === u.id;
              return (
                <tr key={u.id}>
                  <td style={styles.td}>
                    <div style={styles.userCell}>
                      <strong>{u.email}</strong>
                      <span style={styles.subtext}>{u.name || '이름 미설정'}</span>
                      {!u.has_password && (
                        <span style={styles.badgeWarn}>비밀번호 미설정</span>
                      )}
                    </div>
                  </td>
                  <td style={styles.td}>
                    {u.is_admin ? (
                      <span style={styles.badgeAdmin}>ADMIN</span>
                    ) : (
                      <span style={styles.badgeUser}>USER</span>
                    )}
                    {isSelf && <span style={styles.subtext}> (본인)</span>}
                  </td>
                  <td style={styles.td}>{formatDateTime(u.created_at)}</td>
                  <td style={styles.td}>{formatDateTime(u.last_login_at)}</td>
                  <td style={styles.td}>
                    {u.stats ? (
                      <div style={styles.statsCell}>
                        <span>여행 {u.stats.trip_count}건</span>
                        <span>경비 {u.stats.expense_count}건</span>
                        <span>₩{formatNumber(u.stats.total_krw)}</span>
                      </div>
                    ) : (
                      <span style={styles.subtext}>-</span>
                    )}
                  </td>
                  <td style={styles.td}>
                    <div style={styles.actions}>
                      <button
                        type="button"
                        style={styles.actionBtn}
                        onClick={() => toggleAdmin(u)}
                        disabled={busy || (isSelf && u.is_admin)}
                        title={isSelf && u.is_admin ? '자기 자신의 관리자 권한은 해제할 수 없습니다.' : ''}
                      >
                        {u.is_admin ? '권한 해제' : '관리자 지정'}
                      </button>
                      <button
                        type="button"
                        style={styles.actionBtn}
                        onClick={() => resetPassword(u)}
                        disabled={busy}
                      >
                        비번 초기화
                      </button>
                      <button
                        type="button"
                        style={{ ...styles.actionBtn, ...styles.danger }}
                        onClick={() => deleteUser(u)}
                        disabled={busy || isSelf}
                        title={isSelf ? '자기 자신은 삭제할 수 없습니다.' : ''}
                      >
                        삭제
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ===== 탭 3: API 키 관리 =====

function KeysTab({ notify }) {
  const [status, setStatus] = useState({ google_api_key_set: false, koreaexim_api_key_set: false });
  const [google, setGoogle] = useState('');
  const [koreaexim, setKoreaexim] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/admin/app-settings');
      setStatus(res.data?.data || {});
    } catch (e) {
      notify(e?.response?.data?.error || 'API 키 정보를 불러올 수 없습니다.', 'error');
    }
  }, [notify]);

  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    const updates = {};
    if (google.trim()) updates.google_api_key = google.trim();
    if (koreaexim.trim()) updates.koreaexim_api_key = koreaexim.trim();
    if (!Object.keys(updates).length) {
      notify('갱신할 키 값을 입력하세요.', 'error');
      return;
    }
    setLoading(true);
    try {
      const res = await apiClient.put('/api/admin/app-settings', updates);
      setStatus(res.data?.data || {});
      setGoogle('');
      setKoreaexim('');
      notify('API 키가 저장되었습니다.');
    } catch (e) {
      notify(e?.response?.data?.error || '저장에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <p style={styles.desc}>
        모든 사용자가 공유하는 API 키를 관리합니다. 빈 칸으로 두면 기존 값이 유지됩니다.
      </p>

      <div style={styles.keyRow}>
        <label style={styles.keyLabel}>
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

      <div style={styles.keyRow}>
        <label style={styles.keyLabel}>
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

      {status.updated_at && (
        <div style={styles.subtext}>
          마지막 갱신: {formatDateTime(status.updated_at)}
        </div>
      )}

      <div style={styles.keyActions}>
        <button type="button" onClick={submit} disabled={loading} style={styles.primary}>
          {loading ? '저장 중…' : '저장'}
        </button>
      </div>
    </div>
  );
}

const styles = {
  backdrop: {
    position: 'fixed', inset: 0,
    background: 'rgba(0,0,0,0.55)', zIndex: 1000,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 16,
  },
  modal: {
    background: '#fff', borderRadius: 12,
    width: '100%', maxWidth: 960, maxHeight: '90vh',
    display: 'flex', flexDirection: 'column',
    color: '#1a1a2e', overflow: 'hidden',
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '18px 24px', borderBottom: '1px solid #eee',
  },
  title: { margin: 0, fontSize: 18 },
  closeBtn: {
    background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', color: '#888',
  },
  tabs: {
    display: 'flex', gap: 4, padding: '12px 24px 0',
    borderBottom: '1px solid #eee', background: '#fafafa',
  },
  tab: {
    background: 'transparent', border: 'none',
    padding: '10px 16px', cursor: 'pointer',
    fontSize: 13, fontWeight: 500, color: '#666',
    borderBottom: '2px solid transparent',
  },
  tabActive: {
    color: '#e94560', borderBottomColor: '#e94560',
  },
  banner: {
    margin: '12px 24px 0',
    padding: '10px 14px', borderRadius: 8, fontSize: 13,
  },
  bannerInfo: { background: '#e6f7f0', color: '#127a5a' },
  bannerError: { background: '#fde8ec', color: '#c0334d' },
  body: {
    padding: '20px 24px 24px',
    overflowY: 'auto',
    flex: 1,
  },
  placeholder: { padding: 40, textAlign: 'center', color: '#888' },
  cardsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
    gap: 12,
  },
  statCard: {
    background: '#fafbff', border: '1px solid #eef0f7',
    borderLeft: '4px solid #4c6ef5',
    borderRadius: 8, padding: '14px 16px',
  },
  statLabel: { fontSize: 12, color: '#777', marginBottom: 6 },
  statValue: { fontSize: 22, fontWeight: 700, color: '#1a1a2e' },
  hintBox: {
    marginTop: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    fontSize: 12, color: '#888',
  },
  toolbar: {
    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
  },
  searchInput: {
    flex: 1, padding: '8px 12px', border: '1px solid #d0d0d8',
    borderRadius: 8, fontSize: 13, outline: 'none',
  },
  ghostBtn: {
    background: '#f4f6fb', color: '#333', border: '1px solid #e0e0e0',
    padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 12,
  },
  tableWrap: {
    border: '1px solid #eee', borderRadius: 8, overflow: 'auto',
    maxHeight: '60vh',
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: {
    textAlign: 'left', padding: '10px 12px',
    background: '#f8f9fb', borderBottom: '1px solid #eee',
    position: 'sticky', top: 0, zIndex: 1,
    fontSize: 12, fontWeight: 600, color: '#555',
  },
  td: { padding: '10px 12px', borderBottom: '1px solid #f2f2f2', verticalAlign: 'top' },
  emptyRow: { padding: 30, textAlign: 'center', color: '#888' },
  userCell: { display: 'flex', flexDirection: 'column', gap: 4 },
  subtext: { fontSize: 11, color: '#888' },
  statsCell: { display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12, color: '#555' },
  actions: { display: 'flex', flexWrap: 'wrap', gap: 4 },
  actionBtn: {
    background: '#f4f6fb', color: '#333', border: '1px solid #e0e0e0',
    padding: '5px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 11,
  },
  danger: {
    background: '#fde8ec', color: '#c0334d', border: '1px solid #f5c6cf',
  },
  badgeAdmin: {
    background: '#fff3bf', color: '#7c4a00',
    fontSize: 11, fontWeight: 700,
    padding: '2px 8px', borderRadius: 999,
  },
  badgeUser: {
    background: '#eef0f7', color: '#555',
    fontSize: 11, fontWeight: 600,
    padding: '2px 8px', borderRadius: 999,
  },
  badgeWarn: {
    background: '#fff0e6', color: '#b76e00',
    fontSize: 10, padding: '1px 6px', borderRadius: 4,
    alignSelf: 'flex-start',
  },
  badgeOk: {
    background: '#e6f7f0', color: '#127a5a',
    fontSize: 11, padding: '2px 8px', borderRadius: 999, marginLeft: 8,
  },
  badgeOff: {
    background: '#fde8ec', color: '#c0334d',
    fontSize: 11, padding: '2px 8px', borderRadius: 999, marginLeft: 8,
  },
  desc: { fontSize: 13, color: '#666', marginBottom: 20 },
  keyRow: { marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 6 },
  keyLabel: {
    display: 'flex', alignItems: 'center',
    fontSize: 13, fontWeight: 600, color: '#333',
  },
  input: {
    padding: '10px 12px', border: '1px solid #d0d0d8',
    borderRadius: 8, fontSize: 14, outline: 'none',
  },
  keyActions: {
    display: 'flex', justifyContent: 'flex-end', marginTop: 16,
  },
  primary: {
    background: '#e94560', color: '#fff', border: 'none',
    padding: '10px 20px', borderRadius: 8, cursor: 'pointer', fontWeight: 600,
  },
};
