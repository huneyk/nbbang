import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import './App.css';
import apiClient, { API_BASE, tokenStorage } from './api/client';
import { useAuth } from './auth/AuthContext';
import LoginPage from './auth/LoginPage';
import PasswordSetupModal from './auth/PasswordSetupModal';
import AdminPanel from './admin/AdminPanel';
import UsageGuide from './UsageGuide';
import { InstallButton } from './InstallPrompt';

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

const buildAuthedUrl = (path) => {
  const token = tokenStorage.get();
  const sep = path.includes('?') ? '&' : '?';
  return token ? `${API_BASE}${path}${sep}jwt=${encodeURIComponent(token)}` : `${API_BASE}${path}`;
};

const fetchAuthed = (path, options = {}) => {
  const token = tokenStorage.get();
  const headers = { ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return fetch(`${API_BASE}${path}`, { ...options, headers });
};

function App() {
  const { user, loading: authLoading, isAuthenticated, isAdmin, hasPassword, logout } = useAuth();

  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [config, setConfig] = useState(null);
  const [settings, setSettings] = useState({});
  const [previewImage, setPreviewImage] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const [exchangeRates, setExchangeRates] = useState({});
  const [exchangeRateInfo, setExchangeRateInfo] = useState({ source: '', updated_at: '', rate_type: '' });
  const [fetchingRates, setFetchingRates] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showAdminSettings, setShowAdminSettings] = useState(false);
  const [showUsageGuide, setShowUsageGuide] = useState(false);
  const [showCurrencyModal, setShowCurrencyModal] = useState(false);
  const [showNewTripConfirm, setShowNewTripConfirm] = useState(false);
  const [editingCurrency, setEditingCurrency] = useState(null);
  const [currencies, setCurrencies] = useState([]);
  const [trips, setTrips] = useState([]);
  const [settingsTab, setSettingsTab] = useState('current');
  const [receiptModalImage, setReceiptModalImage] = useState(null);
  const [isExpenseListOpen, setIsExpenseListOpen] = useState(false);
  const [isExchangeCardOpen, setIsExchangeCardOpen] = useState(false);

  const [settingsForm, setSettingsForm] = useState({
    trip_title: '여행 경비 정산',
    participants: '',
    categories: '',
    credit_card_fee_rate: 0,
  });

  const [currencyForm, setCurrencyForm] = useState({
    code: '', name: '', flag: '🏳️', rate: '',
  });

  const [newTripForm, setNewTripForm] = useState({
    trip_title: '',
    participants: '',
    categories: '교통비, 식사비, 음료/간식, 숙박비, 기타',
  });

  const [formData, setFormData] = useState({
    date: new Date().toISOString().split('T')[0],
    category: '기타',
    amount: '',
    currency: 'JPY',
    payment_method: '현금',
    description: '',
    payer: '',
    receipt_image: null,
    is_personal_expense: false,
    personal_expense_for: '',
  });

  const isSingleParticipant = (config?.participants?.length || 0) === 1;

  // 데이터 로드
  const loadData = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const [expensesRes, summaryRes, configRes, settingsRes, currenciesRes, tripsRes] = await Promise.all([
        apiClient.get('/api/expenses'),
        apiClient.get('/api/summary'),
        apiClient.get('/api/config'),
        apiClient.get('/api/settings'),
        apiClient.get('/api/currencies'),
        apiClient.get('/api/trips'),
      ]);

      setExpenses(expensesRes.data.data);
      setSummary(summaryRes.data.data);
      setConfig(configRes.data.data);

      if (configRes.data.data?.exchange_rate_info) {
        setExchangeRateInfo(configRes.data.data.exchange_rate_info);
      }

      if (currenciesRes.data.data) {
        setCurrencies(currenciesRes.data.data);
        const rates = {};
        currenciesRes.data.data.forEach((c) => { rates[c.code] = c.rate; });
        setExchangeRates(rates);
      }

      const loadedSettings = settingsRes.data.data;
      setSettings(loadedSettings);

      setSettingsForm({
        trip_title: loadedSettings.trip_title || '여행 경비 정산',
        participants: (loadedSettings.participants || []).join(', '),
        categories: (loadedSettings.categories || []).join(', '),
        credit_card_fee_rate: loadedSettings.credit_card_fee_rate ?? 0,
      });

      if (loadedSettings.participants?.length > 0) {
        setFormData((prev) => {
          const currentPayerValid = prev.payer && loadedSettings.participants.includes(prev.payer);
          return {
            ...prev,
            payer: currentPayerValid ? prev.payer : loadedSettings.participants[0],
          };
        });
      }

      const tripList = tripsRes.data.data || [];
      setTrips(tripList);

      // 트립이 하나도 없으면(최초 로그인) 새 여행 시작 모달을 자동으로 연다.
      if (tripList.length === 0) {
        setNewTripForm({
          trip_title: '',
          participants: '',
          categories: '교통비, 식사비, 음료/간식, 숙박비, 기타',
        });
        setShowNewTripConfirm(true);
      }
    } catch (error) {
      console.error('데이터 로드 오류:', error);
      if (error?.response?.status !== 401) {
        showToast('서버 연결에 실패했습니다.', 'error');
      }
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated) loadData();
  }, [isAuthenticated, loadData]);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const cameraInputRef = useRef(null);
  const galleryInputRef = useRef(null);

  const processReceiptFile = useCallback(async (file) => {
    if (!file) return;
    if (!file.type || !file.type.startsWith('image/')) {
      showToast('지원하지 않는 파일 형식입니다.', 'error');
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      showToast('파일이 너무 큽니다. 50MB 이하의 이미지를 업로드해주세요.', 'error');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => setPreviewImage(e.target.result);
    reader.readAsDataURL(file);

    setAnalyzing(true);
    const formDataUpload = new FormData();
    formDataUpload.append('receipt', file);

    try {
      const response = await apiClient.post('/api/upload-receipt', formDataUpload, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      if (response.data.success) {
        const data = response.data.data;
        if (data.receipt_image) {
          setPreviewImage(buildAuthedUrl(`/api/receipts/${data.receipt_image}/image`));
        }
        setFormData((prev) => ({
          ...prev,
          date: data.date || prev.date,
          category: data.category || prev.category,
          amount: data.amount || '',
          currency: data.currency || prev.currency,
          payment_method: data.payment_method || prev.payment_method,
          description: data.description || '',
          receipt_image: data.receipt_image,
        }));
        showToast('영수증 분석이 완료되었습니다!');
      } else {
        showToast(response.data.error || '분석에 실패했습니다.', 'error');
      }
    } catch (error) {
      console.error('영수증 업로드 오류:', error);
      if (error.response?.status === 413) {
        showToast('파일이 너무 큽니다. 50MB 이하의 이미지를 업로드해주세요.', 'error');
      } else if (error.response?.data?.error) {
        showToast(error.response.data.error, 'error');
      } else {
        showToast('영수증 분석에 실패했습니다. 서버 연결을 확인해주세요.', 'error');
      }
    } finally {
      setAnalyzing(false);
    }
  }, []);

  const onDrop = useCallback(async (acceptedFiles, rejectedFiles) => {
    if (rejectedFiles.length > 0) {
      const rejection = rejectedFiles[0];
      if (rejection.errors.some((e) => e.code === 'file-too-large')) {
        showToast('파일이 너무 큽니다. 50MB 이하의 이미지를 업로드해주세요.', 'error');
      } else {
        showToast('지원하지 않는 파일 형식입니다.', 'error');
      }
      return;
    }
    if (acceptedFiles.length === 0) return;
    await processReceiptFile(acceptedFiles[0]);
  }, [processReceiptFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.webp'] },
    maxFiles: 1,
    maxSize: MAX_FILE_SIZE,
  });

  const handleMobileFileChange = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) await processReceiptFile(file);
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.amount || !formData.payer) {
      showToast('금액과 지불한 사람을 입력해주세요.', 'error');
      return;
    }
    if (formData.is_personal_expense && !formData.personal_expense_for) {
      showToast('개인 지출 해당자를 선택해주세요.', 'error');
      return;
    }
    setLoading(true);
    try {
      const response = await apiClient.post('/api/expenses', formData);
      if (response.data.success) {
        showToast('경비가 등록되었습니다!');
        setFormData({
          date: new Date().toISOString().split('T')[0],
          category: '기타',
          amount: '',
          currency: 'JPY',
          payment_method: '현금',
          description: '',
          payer: settings.participants?.[0] || '',
          receipt_image: null,
          is_personal_expense: false,
          personal_expense_for: '',
        });
        setPreviewImage(null);
        loadData();
      }
    } catch (error) {
      console.error('경비 등록 오류:', error);
      showToast(error.response?.data?.error || '경비 등록에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('이 경비를 삭제하시겠습니까?')) return;
    try {
      await apiClient.delete(`/api/expenses/${id}`);
      showToast('경비가 삭제되었습니다.');
      loadData();
    } catch (error) {
      console.error('삭제 오류:', error);
      showToast('삭제에 실패했습니다.', 'error');
    }
  };

  const handleFetchLatestRates = async () => {
    setFetchingRates(true);
    try {
      const response = await apiClient.post('/api/exchange-rates/fetch');
      if (response.data.success) {
        const { rates, source, updated_at, rate_type, currencies: updatedCurrencies } = response.data.data;
        setExchangeRates((prev) => ({ ...prev, ...rates }));
        setExchangeRateInfo({ source, updated_at, rate_type });
        if (updatedCurrencies) setCurrencies(updatedCurrencies);
        showToast(`환율이 갱신되었습니다 (${source})`, 'success');
        loadData();
      }
    } catch (error) {
      console.error('환율 갱신 오류:', error);
      showToast(error.response?.data?.error || '환율 갱신에 실패했습니다.', 'error');
    } finally {
      setFetchingRates(false);
    }
  };

  const handleRateChange = async (currency, value) => {
    const rate = parseFloat(value) || 0;
    setExchangeRates((prev) => ({ ...prev, [currency]: rate }));
    setCurrencies((prev) => prev.map((c) => (c.code === currency ? { ...c, rate } : c)));
    try {
      await apiClient.put('/api/exchange-rates', { [currency]: rate });
    } catch (error) {
      console.error('환율 업데이트 오류:', error);
    }
  };

  const openCurrencyModal = (currency = null) => {
    if (currency) {
      setEditingCurrency(currency);
      setCurrencyForm({
        code: currency.code,
        name: currency.name,
        flag: currency.flag,
        rate: currency.rate,
      });
    } else {
      setEditingCurrency(null);
      setCurrencyForm({ code: '', name: '', flag: '🏳️', rate: '' });
    }
    setShowCurrencyModal(true);
  };

  const handleCurrencyFormChange = (e) => {
    const { name, value } = e.target;
    setCurrencyForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSaveCurrency = async () => {
    if (!currencyForm.code || !currencyForm.name || !currencyForm.rate) {
      showToast('통화 코드, 이름, 환율을 모두 입력해주세요.', 'error');
      return;
    }
    try {
      setLoading(true);
      if (editingCurrency) {
        await apiClient.put(`/api/currencies/${editingCurrency.code}`, {
          name: currencyForm.name,
          flag: currencyForm.flag,
          rate: parseFloat(currencyForm.rate),
        });
        showToast('통화가 수정되었습니다!');
      } else {
        await apiClient.post('/api/currencies', {
          code: currencyForm.code.toUpperCase(),
          name: currencyForm.name,
          flag: currencyForm.flag,
          rate: parseFloat(currencyForm.rate),
        });
        showToast('통화가 추가되었습니다!');
      }
      setShowCurrencyModal(false);
      loadData();
    } catch (error) {
      console.error('통화 저장 오류:', error);
      showToast(error.response?.data?.error || '통화 저장에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const openSettings = () => {
    // 저장된 여행이 하나도 없으면(최초 상태) 설정 모달 대신 '첫 여행 시작하기' 모달을 연다.
    if (!trips || trips.length === 0) {
      setNewTripForm({
        trip_title: '',
        participants: '',
        categories: '교통비, 식사비, 음료/간식, 숙박비, 기타',
      });
      setShowNewTripConfirm(true);
      return;
    }
    setSettingsForm({
      trip_title: settings.trip_title || '여행 경비 정산',
      participants: (settings.participants || []).join(', '),
      categories: (settings.categories || []).join(', '),
      credit_card_fee_rate: settings.credit_card_fee_rate ?? 0,
    });
    setSettingsTab('current');
    setShowSettings(true);
    loadTrips();
  };

  const handleSaveSettings = async ({ keepOpen = false } = {}) => {
    try {
      setLoading(true);
      const newSettings = {
        trip_title: settingsForm.trip_title.trim() || '여행 경비 정산',
        participants: settingsForm.participants.split(',').map((p) => p.trim()).filter((p) => p),
        categories: settingsForm.categories.split(',').map((c) => c.trim()).filter((c) => c),
        credit_card_fee_rate: (() => {
          const parsed = parseFloat(settingsForm.credit_card_fee_rate);
          return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
        })(),
        exchange_rates: exchangeRates,
      };
      if (newSettings.participants.length === 0) {
        showToast('최소 1명의 참가자를 입력해주세요.', 'error');
        setLoading(false);
        return;
      }
      if (newSettings.categories.length === 0) newSettings.categories = ['기타'];

      // 신용카드 수수료율은 사용자 계정 프로필에 저장(트립 공용 값 아님).
      await apiClient.patch('/api/auth/me', {
        credit_card_fee_rate: newSettings.credit_card_fee_rate,
      });
      await apiClient.put('/api/settings', newSettings);

      // 사용자가 입력한 값을 그대로 state와 form에 반영.
      // 서버 응답을 덮어 쓰지 않음으로써 0과 같은 falsy 값도 안전하게 유지된다.
      setSettings((prev) => ({ ...prev, ...newSettings }));
      setSettingsForm({
        trip_title: newSettings.trip_title,
        participants: newSettings.participants.join(', '),
        categories: newSettings.categories.join(', '),
        credit_card_fee_rate: newSettings.credit_card_fee_rate,
      });

      if (!keepOpen) setShowSettings(false);
      showToast('설정이 저장되었습니다!');
      await loadData();
    } catch (error) {
      console.error('설정 저장 오류:', error);
      showToast('설정 저장에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSettingsChange = (e) => {
    const { name, value } = e.target;
    setSettingsForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleNewTripFormChange = (e) => {
    const { name, value } = e.target;
    setNewTripForm((prev) => ({ ...prev, [name]: value }));
  };

  const openNewTripConfirm = () => {
    setNewTripForm({
      trip_title: '',
      participants: '',
      categories: '교통비, 식사비, 음료/간식, 숙박비, 기타',
    });
    setShowNewTripConfirm(true);
  };

  const handleCreateNewTrip = async () => {
    if (!newTripForm.trip_title.trim() || !newTripForm.participants.trim()) {
      showToast('여행 타이틀과 참가자를 입력해주세요.', 'error');
      return;
    }
    try {
      setLoading(true);
      await apiClient.post('/api/trips/new', {
        trip_title: newTripForm.trip_title.trim(),
        participants: newTripForm.participants.split(',').map((p) => p.trim()).filter((p) => p),
        categories: newTripForm.categories.split(',').map((c) => c.trim()).filter((c) => c),
      });
      setShowNewTripConfirm(false);
      setShowSettings(false);
      showToast('새 여행이 시작되었습니다!');
      loadData();
      loadTrips();
    } catch (error) {
      console.error('새 여행 생성 오류:', error);
      showToast(error.response?.data?.error || '새 여행 생성에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadTrips = async () => {
    try {
      const response = await apiClient.get('/api/trips');
      setTrips(response.data.data || []);
    } catch (error) {
      console.error('여행 목록 로드 오류:', error);
    }
  };

  const handleLoadTrip = async (tripId) => {
    if (!window.confirm('선택한 여행을 불러올까요?')) return;
    try {
      setLoading(true);
      await apiClient.get(`/api/trips/${tripId}`);
      setShowSettings(false);
      showToast('여행을 불러왔습니다!');
      loadData();
      loadTrips();
    } catch (error) {
      console.error('여행 불러오기 오류:', error);
      showToast(error.response?.data?.error || '여행 불러오기에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTrip = async (tripId, tripTitle) => {
    if (!window.confirm(`"${tripTitle}" 여행을 삭제할까요? 이 작업은 되돌릴 수 없습니다.`)) return;
    try {
      await apiClient.delete(`/api/trips/${tripId}`);
      showToast('여행이 삭제되었습니다.');
      loadTrips();
      loadData();
    } catch (error) {
      console.error('여행 삭제 오류:', error);
      showToast(error.response?.data?.error || '여행 삭제에 실패했습니다.', 'error');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  const formatAmount = (amount) => new Intl.NumberFormat('ko-KR').format(Math.round(amount));

  const handleDownloadReport = async () => {
    try {
      setLoading(true);
      const response = await fetchAuthed('/api/report/download');
      if (!response.ok) {
        showToast('엑셀 리포트 다운로드에 실패했습니다.', 'error');
        return;
      }
      const blob = await response.blob();
      const now = new Date();
      const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
      const timeStr = now.toTimeString().slice(0, 8).replace(/:/g, '');
      const filename = `expense_${dateStr}_${timeStr}.xlsx`;
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      showToast('엑셀 리포트가 다운로드되었습니다!');
    } catch (error) {
      console.error('리포트 다운로드 오류:', error);
      showToast('리포트 다운로드에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadReceipts = async () => {
    try {
      setLoading(true);
      const response = await fetchAuthed('/api/report/download-receipts');
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        showToast(errorData.error || '영수증 다운로드에 실패했습니다.', 'error');
        return;
      }
      const blob = await response.blob();
      const now = new Date();
      const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
      const timeStr = now.toTimeString().slice(0, 8).replace(/:/g, '');
      const filename = `receipts_${dateStr}_${timeStr}.pdf`;
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      showToast('영수증 PDF가 다운로드되었습니다!');
    } catch (error) {
      console.error('영수증 다운로드 오류:', error);
      showToast('영수증 다운로드에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  if (authLoading) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#1a1a2e', color: '#fff', fontSize: 16,
      }}>
        로딩 중…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <div className="app">
      <nav className="navbar">
        <div className="navbar-logo">
          <img src="/npang_logo.png" alt="Npang" />
        </div>
        <div className="navbar-title">
          <h1>🌏 {settings.trip_title || '여행 경비 정산'}</h1>
          <p>"N빵 하자!" 영수증만 찰칵! 여행 경비 정산 실시간으로 끝!</p>
        </div>
        <div className="navbar-actions">
          <span className="user-chip">
            👤 {user?.name || user?.email}
            {isAdmin && <span style={{
              marginLeft: 6, padding: '2px 8px', borderRadius: 999,
              background: '#ffc300', color: '#1a1a2e', fontSize: 11, fontWeight: 700,
            }}>ADMIN</span>}
          </span>
          {isAdmin && (
            <button
              type="button"
              onClick={() => setShowAdminSettings(true)}
              style={{
                padding: '6px 12px', borderRadius: 8, border: '1px solid var(--border-color)',
                background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12,
              }}
              title="관리자 설정"
            >
              🛠 관리자
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowUsageGuide(true)}
            style={{
              padding: '6px 12px', borderRadius: 8, border: '1px solid var(--border-color)',
              background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12,
            }}
            title="사용법 안내"
          >
            📖 사용법
          </button>
          <InstallButton className="navbar-install-btn" />
          <button
            type="button"
            onClick={logout}
            style={{
              padding: '6px 12px', borderRadius: 8, border: '1px solid var(--border-color)',
              background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12,
            }}
          >
            로그아웃
          </button>
          <button
            className={`navbar-settings-btn${(!trips || trips.length === 0) ? ' needs-setup' : ''}`}
            onClick={openSettings}
            title={(!trips || trips.length === 0) ? '첫 여행을 설정하세요' : '설정'}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
      </nav>

      <div className="main-grid">
        <div className="left-panel">
          <div className="card">
            <h2 className="card-title">
              <span>📷</span> 영수증 업로드
            </h2>

            <div {...getRootProps()} className={`dropzone dropzone-desktop ${isDragActive ? 'active' : ''}`}>
              <input {...getInputProps()} />
              <div className="dropzone-icon">
                {analyzing ? <div className="loading"></div> : '🧾'}
              </div>
              <p>
                {analyzing ? '영수증 분석 중...' : '영수증을 촬영하거나 이미지를 선택하세요'}
              </p>
              <small>JPG, PNG, GIF, WEBP 지원 · 영수증 영역 자동 인식</small>
            </div>

            <div className="upload-mobile">
              <button
                type="button"
                className="upload-tile"
                onClick={() => !analyzing && cameraInputRef.current?.click()}
                disabled={analyzing}
              >
                <div className="upload-tile-icon">
                  {analyzing ? <div className="loading"></div> : '📷'}
                </div>
                <div className="upload-tile-title">카메라</div>
                <small>영수증 촬영</small>
              </button>
              <button
                type="button"
                className="upload-tile"
                onClick={() => !analyzing && galleryInputRef.current?.click()}
                disabled={analyzing}
              >
                <div className="upload-tile-icon">
                  {analyzing ? <div className="loading"></div> : '🖼️'}
                </div>
                <div className="upload-tile-title">사진 앨범</div>
                <small>사진 파일 업로드</small>
              </button>
              <input
                ref={cameraInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                style={{ display: 'none' }}
                onChange={handleMobileFileChange}
              />
              <input
                ref={galleryInputRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={handleMobileFileChange}
              />
            </div>
            <p className="upload-mobile-hint">
              {analyzing ? '영수증 분석 중...' : 'JPG, PNG, GIF, WEBP 지원 · 영수증 영역 자동 인식'}
            </p>

            {previewImage && (
              <img src={previewImage} alt="영수증 미리보기" className="preview-image" />
            )}

            {formData.receipt_image && formData.amount && (
              <div className="ocr-result">
                <h4>✓ 분석 결과</h4>
                <div className="ocr-result-item"><span>날짜</span><span>{formData.date}</span></div>
                <div className="ocr-result-item"><span>금액</span><span>{formatAmount(formData.amount)} {formData.currency}</span></div>
                <div className="ocr-result-item"><span>결제수단</span><span>{formData.payment_method}</span></div>
                <div className="ocr-result-item"><span>분류</span><span>{formData.category}</span></div>
              </div>
            )}
          </div>

          <div className="card" style={{ marginTop: '1.5rem' }}>
            <h2 className="card-title"><span>✏️</span> 경비 입력</h2>

            <form onSubmit={handleSubmit}>
              <div className="form-row">
                <div className="form-group">
                  <label>날짜</label>
                  <input type="date" name="date" value={formData.date} onChange={handleInputChange} />
                </div>
                <div className="form-group">
                  <label>지출 항목</label>
                  <select name="category" value={formData.category} onChange={handleInputChange}>
                    {config?.categories?.map((cat) => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>금액</label>
                  <input type="number" name="amount" value={formData.amount}
                    onChange={handleInputChange} placeholder="금액 입력" />
                </div>
                <div className="form-group">
                  <label>화폐 단위</label>
                  <select name="currency" value={formData.currency} onChange={handleInputChange}>
                    {currencies.map((curr) => (
                      <option key={curr.code} value={curr.code}>
                        {curr.flag} {curr.code} ({curr.name})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>결제 수단</label>
                  <select name="payment_method" value={formData.payment_method} onChange={handleInputChange}>
                    <option value="현금">💵 현금</option>
                    <option value="신용카드">
                      💳 신용카드{formData.currency === 'KRW' || !(settings.credit_card_fee_rate > 0) ? '' : ` (+${settings.credit_card_fee_rate}%)`}
                    </option>
                  </select>
                </div>
                <div className="form-group">
                  <label>{isSingleParticipant ? '정산책임자' : '지불한 사람'}</label>
                  {isSingleParticipant ? (
                    <input type="text" value={config.participants[0]} readOnly className="readonly-input" />
                  ) : (
                    <select name="payer" value={formData.payer} onChange={handleInputChange} required>
                      <option value="">선택하세요</option>
                      {config?.participants?.map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  )}
                </div>
              </div>

              <div className="form-group">
                <label>세부 내역</label>
                <input type="text" name="description" value={formData.description}
                  onChange={handleInputChange} placeholder="가게명, 메모 등" />
              </div>

              {!isSingleParticipant && (
                <div className="form-group expense-type-group">
                  <label>지출 유형</label>
                  <div className="expense-type-options">
                    <label className={`expense-type-option ${!formData.is_personal_expense ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="expense_type"
                        checked={!formData.is_personal_expense}
                        onChange={() => setFormData((prev) => ({
                          ...prev, is_personal_expense: false, personal_expense_for: '',
                        }))}
                      />
                      <span className="expense-type-label">👥 공동 경비</span>
                    </label>
                    <label className={`expense-type-option ${formData.is_personal_expense ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="expense_type"
                        checked={formData.is_personal_expense}
                        onChange={() => setFormData((prev) => ({ ...prev, is_personal_expense: true }))}
                      />
                      <span className="expense-type-label">👤 개인 지출</span>
                    </label>
                  </div>
                </div>
              )}

              {!isSingleParticipant && formData.is_personal_expense && (
                <div className="form-group personal-expense-for">
                  <label>개인 지출 해당자</label>
                  <select name="personal_expense_for" value={formData.personal_expense_for}
                    onChange={handleInputChange} required>
                    <option value="">해당자 선택</option>
                    {config?.participants?.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                  <small className="form-hint">이 지출은 선택한 사람에게만 전액 청구됩니다</small>
                </div>
              )}

              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? <div className="loading"></div> : '➕ 추가 하기'}
              </button>
            </form>
          </div>

          <div className="card card-collapsible" style={{ marginTop: '1.5rem' }}>
            <h2
              className="card-title card-title-toggle"
              onClick={() => setIsExchangeCardOpen((prev) => !prev)}
            >
              <span className={`card-toggle-chevron chevron-exchange ${isExchangeCardOpen ? 'open' : ''}`}>▶</span>
              <span>💱</span> 환율 설정
              <span className="card-title-badge">현찰살때</span>
              <button
                className="add-currency-btn"
                onClick={(e) => { e.stopPropagation(); openCurrencyModal(); }}
                title="통화 추가"
              >
                ➕
              </button>
            </h2>

            {isExchangeCardOpen && (
              <div className="card-collapsible-body">
                <div className="exchange-rate-actions">
                  <button
                    className="btn btn-fetch-rate"
                    onClick={handleFetchLatestRates}
                    disabled={fetchingRates}
                    title="최신 환율 가져오기"
                  >
                    {fetchingRates ? <div className="loading"></div> : '🔄 최신 환율 가져오기'}
                  </button>
                </div>

                {exchangeRateInfo.updated_at && (
                  <div className="exchange-rate-info">
                    <span className="rate-info-label">마지막 갱신:</span>
                    <span className="rate-info-value">
                      {new Date(exchangeRateInfo.updated_at).toLocaleString('ko-KR', {
                        year: 'numeric', month: '2-digit', day: '2-digit',
                        hour: '2-digit', minute: '2-digit',
                      })}
                    </span>
                    {exchangeRateInfo.source && (
                      <span className="rate-info-source">{exchangeRateInfo.source}</span>
                    )}
                  </div>
                )}

                <div className="exchange-rates">
                  {currencies.filter((c) => !c.is_base).map((curr) => (
                    <div className="rate-item" key={curr.code}>
                      <label>{curr.flag} 1 {curr.code} =</label>
                      <input
                        type="number"
                        step="0.1"
                        value={exchangeRates[curr.code] || curr.rate}
                        onChange={(e) => handleRateChange(curr.code, e.target.value)}
                      />
                      <span className="rate-unit">KRW</span>
                    </div>
                  ))}
                  {currencies.filter((c) => !c.is_base).length === 0 && (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                      등록된 외화가 없습니다. ➕ 버튼을 눌러 통화를 추가하세요.
                    </p>
                  )}
                </div>
                <small className="exchange-rate-note">
                  매일 오전 4시에 자동 갱신됩니다. 환율은 수동으로도 조정할 수 있습니다.
                </small>
              </div>
            )}
          </div>
        </div>

        <div className="right-panel">
          <div className="card card-collapsible">
            <h2
              className="card-title card-title-toggle"
              onClick={() => setIsExpenseListOpen((prev) => !prev)}
            >
              <span className={`card-toggle-chevron chevron-expense ${isExpenseListOpen ? 'open' : ''}`}>▶</span>
              <span>📋</span> 경비 내역
              {expenses.length > 0 && (
                <span className="card-title-badge" style={{ background: 'rgba(46, 204, 113, 0.15)', color: 'var(--accent-green)' }}>
                  {expenses.length}건
                </span>
              )}
            </h2>

            <div className="card-collapsible-body">
              <div className="expense-table-wrapper">
                {expenses.length === 0 ? (
                  <div className="empty-state">
                    <span>📝</span>
                    <p>등록된 경비가 없습니다.</p>
                    <p style={{ fontSize: '0.9rem' }}>영수증을 업로드하거나 직접 입력해주세요.</p>
                  </div>
                ) : (
                  <table className="expense-table">
                    <thead>
                      <tr>
                        <th>날짜</th>
                        <th>지출 항목</th>
                        <th>금액</th>
                        <th>결제수단</th>
                        <th>적용 환율</th>
                        <th>원화 환산액</th>
                        <th>세부 내역</th>
                        <th>지불한 사람</th>
                        <th>영수증</th>
                        <th>유형</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {(isExpenseListOpen ? expenses : expenses.slice(0, 1)).map((expense) => (
                        <tr key={expense.id || expense._id} className={expense.is_personal_expense ? 'personal-expense-row' : ''}>
                          <td data-label="날짜">{expense.date}</td>
                          <td data-label="지출 항목">
                            <span className="badge badge-category">{expense.category}</span>
                          </td>
                          <td data-label="금액" className="amount">
                            {formatAmount(expense.amount)} {expense.currency}
                          </td>
                          <td data-label="결제수단">
                            <span className={`badge ${expense.payment_method === '현금' ? 'badge-cash' : 'badge-card'}`}>
                              {expense.payment_method === '현금' ? '💵' : '💳'} {expense.payment_method}
                            </span>
                          </td>
                          <td data-label="적용 환율" className="amount exchange-rate">
                            {expense.exchange_rate ? expense.exchange_rate.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '-'}
                          </td>
                          <td data-label="원화 환산액" className="amount krw-amount">
                            ₩{formatAmount(expense.krw_amount)}
                          </td>
                          <td data-label="세부 내역">{expense.description || '-'}</td>
                          <td data-label="지불한 사람">{expense.payer}</td>
                          <td data-label="영수증" className="receipt-cell">
                            {expense.receipt_image ? (
                              <button
                                className="receipt-icon-btn"
                                onClick={() => setReceiptModalImage(buildAuthedUrl(`/api/receipts/${expense.receipt_image}/image`))}
                                title="영수증 보기"
                              >
                                🧾
                              </button>
                            ) : (
                              <span className="no-receipt">-</span>
                            )}
                          </td>
                          <td data-label="유형">
                            {expense.is_personal_expense ? (
                              <span className="badge badge-personal" title={`${expense.personal_expense_for}의 개인 지출`}>
                                👤 {expense.personal_expense_for}
                              </span>
                            ) : (
                              <span className="badge badge-shared">👥 공동</span>
                            )}
                          </td>
                          <td>
                            <button
                              className="delete-btn"
                              onClick={() => handleDelete(expense.id || expense._id)}
                              title="삭제"
                            >
                              🗑️
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
              {!isExpenseListOpen && expenses.length > 1 && (
                <div className="collapsed-hint" onClick={() => setIsExpenseListOpen(true)}>
                  + {expenses.length - 1}건 더보기
                </div>
              )}
              {isExpenseListOpen && expenses.length > 1 && (
                <div className="collapse-bottom-btn" onClick={() => setIsExpenseListOpen(false)}>
                  <span className="card-toggle-chevron chevron-expense open">▶</span>
                  접기
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {summary && (
        <>
          <div className="summary-grid">
            <div className="summary-card total">
              <h3>💰 총 경비</h3>
              <div className="value">
                {formatAmount(summary.total_krw)}
                <span className="unit">원</span>
              </div>
              <div className="summary-breakdown">
                <p>
                  👥 공동 경비: ₩{formatAmount(summary.shared_total_krw || summary.total_krw)} ({summary.shared_expense_count || summary.expense_count}건)
                </p>
                {(summary.personal_total_krw > 0 || summary.personal_expense_count > 0) && (
                  <p>
                    👤 개인 지출: ₩{formatAmount(summary.personal_total_krw || 0)} ({summary.personal_expense_count || 0}건)
                  </p>
                )}
              </div>
            </div>

            {!isSingleParticipant && (
              <div className="summary-card per-person">
                <h3>👥 1인당 분담액</h3>
                <div className="value">
                  {formatAmount(summary.per_person)}
                  <span className="unit">원</span>
                </div>
                <p style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  {summary.num_participants}명 기준 (공동 경비만)
                </p>
              </div>
            )}

            <div className="summary-card">
              <h3>📊 카테고리별 지출</h3>
              <div className="category-breakdown">
                {summary.category_totals && Object.entries(summary.category_totals)
                  .filter(([_, amount]) => amount > 0)
                  .sort((a, b) => b[1] - a[1])
                  .map(([category, amount]) => (
                    <div key={category} className="category-item">
                      <div className="category-header">
                        <span className="category-name">{category}</span>
                        <span className="category-amount">₩{formatAmount(amount)}</span>
                      </div>
                      <div className="category-bar">
                        <div
                          className="category-bar-fill"
                          style={{ width: `${(amount / summary.total_krw) * 100}%` }}
                        ></div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </div>

          {!isSingleParticipant && (
            <div className="summary-card settlement-card-full">
              <h3>💸 정산 내역</h3>
              <div className="settlements">
                {summary.settlements && Object.entries(summary.settlements).map(([name, data]) => (
                  <div
                    key={name}
                    className={`settlement-item ${data.difference > 0 ? 'pay' : data.difference < 0 ? 'receive' : 'settled'}`}
                  >
                    <div className="settlement-info">
                      <div className="settlement-name">{name}</div>
                      <div className="settlement-paid">공동 경비 지불: ₩{formatAmount(data.paid)}</div>
                      {data.paid_for_others > 0 && (
                        <div className="settlement-paid-for-others">타인 개인지출 대납: ₩{formatAmount(data.paid_for_others)}</div>
                      )}
                      {data.personal_expense > 0 && (
                        <div className="settlement-personal">
                          <span className="personal-label">👤 개인 지출: ₩{formatAmount(data.personal_expense)}</span>
                          {data.personal_expense_details && data.personal_expense_details.length > 0 && (
                            <div className="personal-expense-details">
                              {data.personal_expense_details.map((detail, idx) => (
                                <div key={idx} className="personal-expense-detail-item">
                                  <span className="detail-amount">₩{formatAmount(detail.amount)}</span>
                                  <span className="detail-payer">{detail.payer} 결제</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="settlement-amount">
                      <div className={`diff ${data.difference > 0 ? 'negative' : data.difference < 0 ? 'positive' : ''}`}>
                        {data.difference > 0 ? '+' : ''}{formatAmount(data.difference)}원
                      </div>
                      <div className="status">{data.status}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="report-actions">
            <button
              className="btn btn-download"
              onClick={handleDownloadReport}
              disabled={loading || expenses.length === 0}
            >
              {loading ? '다운로드 중...' : '📊 엑셀로 다운로드'}
            </button>
            <button
              className="btn btn-download btn-download-receipt"
              onClick={handleDownloadReceipts}
              disabled={loading || expenses.length === 0}
            >
              {loading ? '다운로드 중...' : '🧾 영수증 첨부 다운로드'}
            </button>
          </div>
        </>
      )}

      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>⚙️ 설정</h2>
              <button className="modal-close" onClick={() => setShowSettings(false)}>×</button>
            </div>

            <div className="modal-tabs">
              <button
                className={`modal-tab ${settingsTab === 'current' ? 'active' : ''}`}
                onClick={() => setSettingsTab('current')}
              >
                📝 현재 여행 설정
              </button>
              <button
                className={`modal-tab ${settingsTab === 'trips' ? 'active' : ''}`}
                onClick={() => setSettingsTab('trips')}
              >
                📂 저장된 여행 ({trips.length})
              </button>
            </div>

            <div className="modal-body">
              {settingsTab === 'current' && (
                <>
                  <div className="form-group">
                    <label>여행 타이틀</label>
                    <input
                      type="text"
                      name="trip_title"
                      value={settingsForm.trip_title}
                      onChange={handleSettingsChange}
                      placeholder="예: 2024 일본 여행"
                    />
                  </div>

                  <div className="form-group">
                    <label>참가자 (쉼표로 구분)</label>
                    <input
                      type="text"
                      name="participants"
                      value={settingsForm.participants}
                      onChange={handleSettingsChange}
                      placeholder="예: 홍길동, 김철수, 이영희"
                    />
                    <small className="form-hint">- 정산에 참여할 사람들의 이름을 쉼표로 구분하여 입력하세요</small>
                    <small className="form-hint">- 경비를 주로 집행할 분의 성함을 맨 앞에 입력해주세요.</small>
                    <small className="form-hint" style={{ color: 'orange' }}>* 참가자를 한 사람만 입력하면, 총무 1인용 정산 도구가 됩니다.</small>
                  </div>

                  <div className="form-group">
                    <label>지출 항목 (쉼표로 구분)</label>
                    <input
                      type="text"
                      name="categories"
                      value={settingsForm.categories}
                      onChange={handleSettingsChange}
                      placeholder="예: 교통비, 식사비, 숙박비, 기타"
                    />
                    <small className="form-hint">- 지출 분류를 쉼표로 구분하여 입력하세요. <br/>- AI가 자동으로 분류해드립니다.</small>
                  </div>

                  <div className="form-group">
                    <label>해외결제 신용카드 수수료율 (%) — 내 계정</label>
                    <input
                      type="number"
                      name="credit_card_fee_rate"
                      value={settingsForm.credit_card_fee_rate}
                      onChange={handleSettingsChange}
                      step="0.1"
                      min="0"
                      max="10"
                      placeholder="0"
                    />
                    <small className="form-hint">- 해외 결제 시 추가되는 수수료율을 입력하세요</small>
                    <small className="form-hint">- 이 값은 <strong>내 계정</strong>에 저장되며, 모든 여행에 공통으로 적용됩니다</small>
                    <small className="form-hint" style={{ color: 'orange' }}>
                      ※ 해외 결제의 경우 건별, 결제금액별 수수료가 추가됩니다.
                      카드사마다 서로 달리 적용되니 확인해서 입력하시기 바랍니다.
                    </small>
                    <small className="form-hint" style={{ color: 'orange' }}>
                      ※ 화폐 단위가 <strong>KRW(원)</strong>인 경우에는 이 수수료율이 적용되지 않습니다.
                    </small>
                  </div>

                  <div className="save-current-section">
                    <button
                      className="btn btn-primary btn-save-current"
                      onClick={() => handleSaveSettings()}
                      disabled={loading}
                    >
                      {loading ? <div className="loading"></div> : '💾 현재 여행에 저장'}
                    </button>
                    <small className="form-hint" style={{ textAlign: 'center', display: 'block', marginTop: '0.5rem' }}>
                      - 위 수정 사항을 현재 여행에 반영합니다
                    </small>
                  </div>

                  <div className="new-trip-section">
                    <button className="btn btn-new-trip" onClick={openNewTripConfirm}>
                      ✨ 새 여행 시작하기
                    </button>
                    <small className="form-hint" style={{ textAlign: 'center', display: 'block', marginTop: '0.5rem' }}>
                      - 현재 여행을 저장하고 새로운 여행을 시작합니다
                    </small>
                  </div>
                </>
              )}

              {settingsTab === 'trips' && (
                <div className="trips-list">
                  {trips.length === 0 ? (
                    <div className="empty-trips">
                      <span>📭</span>
                      <p>저장된 여행이 없습니다.</p>
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        새 여행을 시작하면 현재 여행이 자동으로 저장됩니다.
                      </p>
                    </div>
                  ) : (
                    trips.map((trip) => (
                      <div key={trip.id} className="trip-item">
                        <div className="trip-info">
                          <div className="trip-title">
                            {trip.title}
                            {trip.is_active && (
                              <span style={{
                                marginLeft: 8, padding: '2px 8px', borderRadius: 999,
                                background: '#00d9a5', color: '#fff', fontSize: 10,
                              }}>현재</span>
                            )}
                          </div>
                          <div className="trip-meta">
                            <span>📅 {formatDate(trip.created_at)}</span>
                            <span>📋 {trip.expense_count}건</span>
                            <span>💰 ₩{formatAmount(trip.total_krw)}</span>
                          </div>
                        </div>
                        <div className="trip-actions">
                          {!trip.is_active && (
                            <button
                              className="btn btn-trip-load"
                              onClick={() => handleLoadTrip(trip.id)}
                              disabled={loading}
                            >
                              불러오기
                            </button>
                          )}
                          <button
                            className="btn btn-trip-delete"
                            onClick={() => handleDeleteTrip(trip.id, trip.title)}
                          >
                            🗑️
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            {settingsTab === 'current' && (
              <div className="modal-footer">
                <button className="btn btn-secondary" onClick={() => setShowSettings(false)}>
                  취소
                </button>
                <button className="btn btn-primary" onClick={() => handleSaveSettings()} disabled={loading}>
                  {loading ? <div className="loading"></div> : '저장'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {showNewTripConfirm && (
        <div className="modal-overlay" onClick={() => setShowNewTripConfirm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{trips.length === 0 ? '✨ 첫 여행 시작하기' : '✨ 새 여행 시작'}</h2>
              <button className="modal-close" onClick={() => setShowNewTripConfirm(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="confirm-message">
                {trips.length === 0 ? (
                  <>
                    <p>👋 환영합니다! 여행 경비 정산을 시작해볼까요?</p>
                    <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                      여행 타이틀과 참가자를 입력하면 경비 입력을 시작할 수 있습니다.
                    </p>
                  </>
                ) : (
                  <>
                    <p>⚠️ 새 여행을 시작하면 현재 여행이 저장되고 새 여행이 활성 상태가 됩니다.</p>
                    <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                      저장된 여행은 설정 &gt; 저장된 여행 탭에서 다시 불러올 수 있습니다.
                    </p>
                  </>
                )}
              </div>

              <div className="form-group" style={{ marginTop: '1.5rem' }}>
                <label>새 여행 타이틀 *</label>
                <input
                  type="text"
                  name="trip_title"
                  value={newTripForm.trip_title}
                  onChange={handleNewTripFormChange}
                  placeholder="예: 2026 유럽 여행"
                  autoFocus
                />
              </div>

              <div className="form-group">
                <label>참가자 (쉼표로 구분) *</label>
                <input
                  type="text"
                  name="participants"
                  value={newTripForm.participants}
                  onChange={handleNewTripFormChange}
                  placeholder="예: 홍길동, 김철수, 이영희"
                />
              </div>

              <div className="form-group">
                <label>지출 항목 (쉼표로 구분)</label>
                <input
                  type="text"
                  name="categories"
                  value={newTripForm.categories}
                  onChange={handleNewTripFormChange}
                  placeholder="예: 교통비, 식사비, 숙박비, 기타"
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowNewTripConfirm(false)}>
                취소
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCreateNewTrip}
                disabled={loading || !newTripForm.trip_title.trim() || !newTripForm.participants.trim()}
              >
                {loading ? <div className="loading"></div> : '새 여행 시작'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showCurrencyModal && (
        <div className="modal-overlay" onClick={() => setShowCurrencyModal(false)}>
          <div className="modal currency-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>💱 {editingCurrency ? '통화 수정' : '통화 추가'}</h2>
              <button className="modal-close" onClick={() => setShowCurrencyModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-row">
                <div className="form-group">
                  <label>통화 코드</label>
                  <input
                    type="text"
                    name="code"
                    value={currencyForm.code}
                    onChange={handleCurrencyFormChange}
                    placeholder="예: EUR, GBP, CNY"
                    maxLength={5}
                    disabled={!!editingCurrency}
                    style={{ textTransform: 'uppercase' }}
                  />
                  <small className="form-hint">3자리 통화 코드 (예: EUR, GBP)</small>
                </div>
                <div className="form-group">
                  <label>플래그/아이콘</label>
                  <input
                    type="text"
                    name="flag"
                    value={currencyForm.flag}
                    onChange={handleCurrencyFormChange}
                    placeholder="🏳️"
                    maxLength={4}
                  />
                  <small className="form-hint">국기 이모지 (예: 🇪🇺, 🇬🇧)</small>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>통화 이름</label>
                  <input
                    type="text"
                    name="name"
                    value={currencyForm.name}
                    onChange={handleCurrencyFormChange}
                    placeholder="예: 유로, 파운드"
                  />
                </div>
                <div className="form-group">
                  <label>환율 (1 단위 = ? KRW)</label>
                  <input
                    type="number"
                    name="rate"
                    value={currencyForm.rate}
                    onChange={handleCurrencyFormChange}
                    placeholder="예: 1450"
                    step="0.01"
                    min="0"
                  />
                  <small className="form-hint">1 외화 = ? 원</small>
                </div>
              </div>

              {currencyForm.code && currencyForm.rate && (
                <div className="currency-preview">
                  <span>{currencyForm.flag} 1 {currencyForm.code.toUpperCase()} = </span>
                  <strong>{Number(currencyForm.rate).toLocaleString()} KRW</strong>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowCurrencyModal(false)}>
                취소
              </button>
              <button className="btn btn-primary" onClick={handleSaveCurrency} disabled={loading}>
                {loading ? <div className="loading"></div> : (editingCurrency ? '수정' : '추가')}
              </button>
            </div>
          </div>
        </div>
      )}

      {receiptModalImage && (
        <div className="modal-overlay" onClick={() => setReceiptModalImage(null)}>
          <div className="modal receipt-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>🧾 영수증</h2>
              <button className="modal-close" onClick={() => setReceiptModalImage(null)}>×</button>
            </div>
            <div className="modal-body receipt-modal-body">
              <img
                src={receiptModalImage}
                alt="영수증"
                className="receipt-modal-image"
                onError={(e) => {
                  e.target.style.display = 'none';
                  e.target.parentNode.innerHTML = '<p class="receipt-error">영수증 이미지를 불러올 수 없습니다.</p>';
                }}
              />
            </div>
          </div>
        </div>
      )}

      <AdminPanel
        open={showAdminSettings}
        onClose={() => setShowAdminSettings(false)}
      />

      <PasswordSetupModal
        open={isAuthenticated && !hasPassword}
      />

      <UsageGuide
        open={showUsageGuide}
        onClose={() => setShowUsageGuide(false)}
      />

      <footer className="site-footer">
        <div className="footer-content">
          <div className="footer-left">
            <img src="/asi_logo.png" alt="Advanced Society Initiative" className="footer-logo" />
            <div className="footer-info">
              <strong>고도화 사회 이니셔티브</strong>
              <span>Advanced Society Initiative</span>
              <span>사업자 등록번호 : 310-29-01213</span>
            </div>
          </div>
          <div className="footer-right">
            <span>&copy; 2026 Advanced Society Initiative. All rights reserved.</span>
          </div>
        </div>
      </footer>

      {toast && (
        <div className={`toast ${toast.type}`}>
          {toast.message}
        </div>
      )}
    </div>
  );
}

export default App;
