import React, { useState, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';
import './App.css';

// 데스크톱 앱에서는 상대 경로 사용, 개발 모드에서는 localhost 사용
const API_BASE = process.env.REACT_APP_API_BASE !== undefined 
  ? process.env.REACT_APP_API_BASE 
  : 'http://localhost:5001';

// 최대 파일 크기 (50MB)
const MAX_FILE_SIZE = 50 * 1024 * 1024;

function App() {
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [toast, setToast] = useState(null);
  const [previewImage, setPreviewImage] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showNewTripConfirm, setShowNewTripConfirm] = useState(false);
  const [trips, setTrips] = useState([]);
  const [settingsTab, setSettingsTab] = useState('current'); // 'current' or 'trips'
  
  // 설정 상태
  const [settings, setSettings] = useState({
    trip_title: '여행 경비 정산',
    participants: [],
    categories: [],
    credit_card_fee_rate: 2.5,
    exchange_rates: { JPY: 9.5, USD: 1350 }
  });
  
  // 통화 관리 상태
  const [currencies, setCurrencies] = useState([
    { code: 'KRW', name: '원', flag: '🇰🇷', rate: 1.0, is_base: true },
    { code: 'JPY', name: '엔', flag: '🇯🇵', rate: 9.5, is_base: false },
    { code: 'USD', name: '달러', flag: '🇺🇸', rate: 1350.0, is_base: false }
  ]);
  const [expandedExpenses, setExpandedExpenses] = useState(new Set());
  const [isExchangeCardOpen, setIsExchangeCardOpen] = useState(true);
  const [showCurrencyModal, setShowCurrencyModal] = useState(false);
  const [editingCurrency, setEditingCurrency] = useState(null);
  const [currencyForm, setCurrencyForm] = useState({
    code: '',
    name: '',
    flag: '🏳️',
    rate: ''
  });
  
  // 설정 폼 상태 (편집용)
  const [settingsForm, setSettingsForm] = useState({
    trip_title: '',
    participants: '',
    categories: '',
    credit_card_fee_rate: 2.5,
    google_api_key: '',
    koreaexim_api_key: ''
  });
  
  // 새 여행 폼 상태
  const [newTripForm, setNewTripForm] = useState({
    trip_title: '',
    participants: '',
    categories: '교통비, 식사비, 음료/간식, 숙박비, 기타',
    credit_card_fee_rate: 2.5
  });
  
  // 폼 상태
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
    personal_expense_for: ''
  });

  // 환율 상태
  const [exchangeRates, setExchangeRates] = useState({
    JPY: 9.5,
    USD: 1350
  });
  const [exchangeRateInfo, setExchangeRateInfo] = useState({});
  const [fetchingRates, setFetchingRates] = useState(false);

  // 데이터 로드
  const loadData = useCallback(async () => {
    try {
      const [expensesRes, summaryRes, configRes, settingsRes, currenciesRes] = await Promise.all([
        axios.get(`${API_BASE}/api/expenses`),
        axios.get(`${API_BASE}/api/summary`),
        axios.get(`${API_BASE}/api/config`),
        axios.get(`${API_BASE}/api/settings`),
        axios.get(`${API_BASE}/api/currencies`)
      ]);
      
      setExpenses(expensesRes.data.data || []);
      setSummary(summaryRes.data.data);
      setConfig(configRes.data.data);

      // 환율 갱신 정보
      if (configRes.data.data?.exchange_rate_info) {
        setExchangeRateInfo(configRes.data.data.exchange_rate_info);
      }
      
      // 통화 목록 로드
      if (currenciesRes.data.data) {
        setCurrencies(currenciesRes.data.data);
        // exchange_rates 동기화
        const rates = {};
        currenciesRes.data.data.forEach(c => {
          rates[c.code] = c.rate;
        });
        setExchangeRates(rates);
      }
      
      // 설정 로드
      const loadedSettings = settingsRes.data.data;
      setSettings(loadedSettings);
      
      // 설정 폼 초기화
      setSettingsForm({
        trip_title: loadedSettings.trip_title || '여행 경비 정산',
        participants: (loadedSettings.participants || []).join(', '),
        categories: (loadedSettings.categories || []).join(', '),
        credit_card_fee_rate: loadedSettings.credit_card_fee_rate || 2.5,
        google_api_key: loadedSettings.google_api_key || '',
        koreaexim_api_key: loadedSettings.koreaexim_api_key || ''
      });
      
      // 기본 payer 설정 (첫 번째 참가자)
      if (loadedSettings.participants?.length > 0) {
        setFormData(prev => {
          // 현재 payer가 참가자 목록에 없거나 비어있으면 첫 번째 참가자로 설정
          const currentPayerValid = prev.payer && loadedSettings.participants.includes(prev.payer);
          return {
            ...prev,
            payer: currentPayerValid ? prev.payer : loadedSettings.participants[0]
          };
        });
      }
    } catch (error) {
      console.error('데이터 로드 오류:', error);
      showToast('서버 연결에 실패했습니다.', 'error');
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 토스트 메시지
  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  // 드롭존 설정
  const onDrop = useCallback(async (acceptedFiles, rejectedFiles) => {
    // 거부된 파일 처리
    if (rejectedFiles.length > 0) {
      const rejection = rejectedFiles[0];
      if (rejection.errors.some(e => e.code === 'file-too-large')) {
        showToast('파일이 너무 큽니다. 50MB 이하의 이미지를 업로드해주세요.', 'error');
      } else {
        showToast('지원하지 않는 파일 형식입니다.', 'error');
      }
      return;
    }
    
    if (acceptedFiles.length === 0) return;
    
    const file = acceptedFiles[0];
    
    // 파일 크기 체크
    if (file.size > MAX_FILE_SIZE) {
      showToast('파일이 너무 큽니다. 50MB 이하의 이미지를 업로드해주세요.', 'error');
      return;
    }
    
    // 미리보기 이미지 설정
    const reader = new FileReader();
    reader.onload = (e) => setPreviewImage(e.target.result);
    reader.readAsDataURL(file);
    
    // 영수증 분석
    setAnalyzing(true);
    const formDataUpload = new FormData();
    formDataUpload.append('receipt', file);
    
    try {
      const response = await axios.post(`${API_BASE}/api/upload-receipt`, formDataUpload, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      if (response.data.success) {
        const data = response.data.data;
        if (data.receipt_image) {
          setPreviewImage(`${API_BASE}/api/receipts/${data.receipt_image}/image`);
        }
        setFormData(prev => ({
          ...prev,
          date: data.date || prev.date,
          category: data.category || prev.category,
          amount: data.amount || '',
          currency: data.currency || prev.currency,
          payment_method: data.payment_method || prev.payment_method,
          description: data.description || '',
          receipt_image: data.receipt_image
        }));
        showToast('영수증 분석이 완료되었습니다!');
      } else {
        showToast(response.data.error || '분석에 실패했습니다.', 'error');
      }
    } catch (error) {
      console.error('영수증 업로드 오류:', error);
      // 서버 에러 응답 처리
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

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.webp']
    },
    maxFiles: 1,
    maxSize: MAX_FILE_SIZE
  });

  // 폼 입력 핸들러
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  // 경비 등록
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.amount || !formData.payer) {
      showToast('금액과 지불한 사람을 입력해주세요.', 'error');
      return;
    }
    
    // 개인 지출인데 해당자를 선택하지 않은 경우
    if (formData.is_personal_expense && !formData.personal_expense_for) {
      showToast('개인 지출 해당자를 선택해주세요.', 'error');
      return;
    }
    
    setLoading(true);
    
    try {
      const response = await axios.post(`${API_BASE}/api/expenses`, formData);
      
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
          personal_expense_for: ''
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

  const toggleExpense = (id) => {
    setExpandedExpenses(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // 경비 삭제
  const handleDelete = async (id) => {
    if (!window.confirm('이 경비를 삭제하시겠습니까?')) return;
    
    try {
      await axios.delete(`${API_BASE}/api/expenses/${id}`);
      showToast('경비가 삭제되었습니다.');
      loadData();
    } catch (error) {
      console.error('삭제 오류:', error);
      showToast('삭제에 실패했습니다.', 'error');
    }
  };

  // 최신 환율 수동 가져오기
  const handleFetchLatestRates = async () => {
    setFetchingRates(true);
    try {
      const response = await axios.post(`${API_BASE}/api/exchange-rates/fetch`);
      if (response.data.success) {
        const { rates, source, updated_at, rate_type, currencies: updatedCurrencies } = response.data.data;
        
        setExchangeRates(prev => ({ ...prev, ...rates }));
        setExchangeRateInfo({ source, updated_at, rate_type });
        
        if (updatedCurrencies) {
          setCurrencies(updatedCurrencies);
        }
        
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

  // 환율 업데이트
  const handleRateChange = async (currency, value) => {
    const rate = parseFloat(value) || 0;
    setExchangeRates(prev => ({ ...prev, [currency]: rate }));
    
    // currencies 상태도 업데이트
    setCurrencies(prev => prev.map(c => 
      c.code === currency ? { ...c, rate } : c
    ));
    
    try {
      await axios.put(`${API_BASE}/api/exchange-rates`, {
        [currency]: rate
      });
    } catch (error) {
      console.error('환율 업데이트 오류:', error);
    }
  };

  // 통화 모달 열기
  const openCurrencyModal = (currency = null) => {
    if (currency) {
      // 수정 모드
      setEditingCurrency(currency);
      setCurrencyForm({
        code: currency.code,
        name: currency.name,
        flag: currency.flag,
        rate: currency.rate
      });
    } else {
      // 추가 모드
      setEditingCurrency(null);
      setCurrencyForm({
        code: '',
        name: '',
        flag: '🏳️',
        rate: ''
      });
    }
    setShowCurrencyModal(true);
  };

  // 통화 폼 입력 핸들러
  const handleCurrencyFormChange = (e) => {
    const { name, value } = e.target;
    setCurrencyForm(prev => ({ ...prev, [name]: value }));
  };

  // 통화 저장 (추가/수정)
  const handleSaveCurrency = async () => {
    if (!currencyForm.code || !currencyForm.name || !currencyForm.rate) {
      showToast('통화 코드, 이름, 환율을 모두 입력해주세요.', 'error');
      return;
    }

    try {
      setLoading(true);
      
      if (editingCurrency) {
        // 수정
        await axios.put(`${API_BASE}/api/currencies/${editingCurrency.code}`, {
          name: currencyForm.name,
          flag: currencyForm.flag,
          rate: parseFloat(currencyForm.rate)
        });
        showToast('통화가 수정되었습니다!');
      } else {
        // 추가
        await axios.post(`${API_BASE}/api/currencies`, {
          code: currencyForm.code.toUpperCase(),
          name: currencyForm.name,
          flag: currencyForm.flag,
          rate: parseFloat(currencyForm.rate)
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

  // 설정 모달 열기
  const openSettings = () => {
    setSettingsForm({
      trip_title: settings.trip_title || '여행 경비 정산',
      participants: (settings.participants || []).join(', '),
      categories: (settings.categories || []).join(', '),
      credit_card_fee_rate: settings.credit_card_fee_rate || 2.5,
      google_api_key: settings.google_api_key || '',
      koreaexim_api_key: settings.koreaexim_api_key || ''
    });
    setSettingsTab('current');
    setShowSettings(true);
    loadTrips(); // 저장된 여행 목록 로드
  };

  // 설정 저장
  const handleSaveSettings = async () => {
    try {
      setLoading(true);
      
      const newSettings = {
        trip_title: settingsForm.trip_title.trim() || '여행 경비 정산',
        participants: settingsForm.participants.split(',').map(p => p.trim()).filter(p => p),
        categories: settingsForm.categories.split(',').map(c => c.trim()).filter(c => c),
        credit_card_fee_rate: parseFloat(settingsForm.credit_card_fee_rate) || 2.5,
        exchange_rates: exchangeRates,
        google_api_key: settingsForm.google_api_key.trim(),
        koreaexim_api_key: settingsForm.koreaexim_api_key.trim()
      };
      
      // 참가자가 비어있으면 경고
      if (newSettings.participants.length === 0) {
        showToast('최소 1명의 참가자를 입력해주세요.', 'error');
        setLoading(false);
        return;
      }
      
      // 카테고리가 비어있으면 기본값 설정
      if (newSettings.categories.length === 0) {
        newSettings.categories = ['기타'];
      }
      
      await axios.put(`${API_BASE}/api/settings`, newSettings);
      
      setSettings(newSettings);
      setShowSettings(false);
      showToast('설정이 저장되었습니다!');
      
      // 데이터 새로고침
      loadData();
    } catch (error) {
      console.error('설정 저장 오류:', error);
      showToast('설정 저장에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

  // 설정 폼 입력 핸들러
  const handleSettingsChange = (e) => {
    const { name, value } = e.target;
    setSettingsForm(prev => ({ ...prev, [name]: value }));
  };

  // 새 여행 폼 입력 핸들러
  const handleNewTripFormChange = (e) => {
    const { name, value } = e.target;
    setNewTripForm(prev => ({ ...prev, [name]: value }));
  };

  // 새 여행 확인 모달 열기
  const openNewTripConfirm = () => {
    setNewTripForm({
      trip_title: '',
      participants: '',
      categories: '교통비, 식사비, 음료/간식, 숙박비, 기타',
      credit_card_fee_rate: 2.5
    });
    setShowNewTripConfirm(true);
  };

  // 새 여행 생성
  const handleCreateNewTrip = async () => {
    if (!newTripForm.trip_title.trim() || !newTripForm.participants.trim()) {
      showToast('여행 타이틀과 참가자를 입력해주세요.', 'error');
      return;
    }

    try {
      setLoading(true);
      
      // 현재 여행 아카이브 및 새 여행 시작
      await axios.post(`${API_BASE}/api/trips/new`, {
        trip_title: newTripForm.trip_title.trim(),
        participants: newTripForm.participants.split(',').map(p => p.trim()).filter(p => p),
        categories: newTripForm.categories.split(',').map(c => c.trim()).filter(c => c),
        credit_card_fee_rate: parseFloat(newTripForm.credit_card_fee_rate) || 2.5
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

  // 저장된 여행 목록 로드
  const loadTrips = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/trips`);
      setTrips(response.data.data || []);
    } catch (error) {
      console.error('여행 목록 로드 오류:', error);
    }
  };

  // 여행 불러오기
  const handleLoadTrip = async (tripId) => {
    if (!window.confirm('현재 데이터를 저장하고 선택한 여행을 불러올까요?')) return;
    
    try {
      setLoading(true);
      await axios.get(`${API_BASE}/api/trips/${tripId}`);
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

  // 여행 삭제
  const handleDeleteTrip = async (tripId, tripTitle) => {
    if (!window.confirm(`"${tripTitle}" 여행을 삭제할까요? 이 작업은 되돌릴 수 없습니다.`)) return;
    
    try {
      await axios.delete(`${API_BASE}/api/trips/${tripId}`);
      showToast('여행이 삭제되었습니다.');
      loadTrips();
    } catch (error) {
      console.error('여행 삭제 오류:', error);
      showToast(error.response?.data?.error || '여행 삭제에 실패했습니다.', 'error');
    }
  };

  // 날짜 포맷
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  // 금액 포맷
  const formatAmount = (amount) => {
    return new Intl.NumberFormat('ko-KR').format(Math.round(amount));
  };

  // 리포트 다운로드
  const handleDownloadReport = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${API_BASE}/api/report/download`);
      const blob = await response.blob();
      
      // 파일명 생성
      const now = new Date();
      const dateStr = now.toISOString().slice(0,10).replace(/-/g, '');
      const timeStr = now.toTimeString().slice(0,8).replace(/:/g, '');
      const filename = `expense_${dateStr}_${timeStr}.xlsx`;
      
      // 다운로드 링크 생성
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
      showToast('리포트가 다운로드되었습니다!');
    } catch (error) {
      console.error('리포트 다운로드 오류:', error);
      showToast('리포트 다운로드에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
  };

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
        <button className="navbar-settings-btn" onClick={openSettings} title="설정">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </nav>

      <div className="main-grid">
        {/* 좌측: 입력 폼 */}
        <div className="left-panel">
          <div className="card">
            <h2 className="card-title">
              <span>📷</span> 영수증 업로드
            </h2>
            
            <div 
              {...getRootProps()} 
              className={`dropzone ${isDragActive ? 'active' : ''}`}
            >
              <input {...getInputProps({ capture: 'environment' })} />
              <div className="dropzone-icon">
                {analyzing ? <div className="loading"></div> : '🧾'}
              </div>
              <p>
                {analyzing 
                  ? '영수증 분석 중...' 
                  : '영수증을 촬영하거나 이미지를 선택하세요'}
              </p>
              <small>JPG, PNG, GIF, WEBP 지원 · 영수증 영역 자동 인식</small>
            </div>
            
            {previewImage && (
              <img src={previewImage} alt="영수증 미리보기" className="preview-image" />
            )}
            
            {formData.receipt_image && formData.amount && (
              <div className="ocr-result">
                <h4>✓ 분석 결과</h4>
                <div className="ocr-result-item">
                  <span>날짜</span>
                  <span>{formData.date}</span>
                </div>
                <div className="ocr-result-item">
                  <span>금액</span>
                  <span>{formatAmount(formData.amount)} {formData.currency}</span>
                </div>
                <div className="ocr-result-item">
                  <span>결제수단</span>
                  <span>{formData.payment_method}</span>
                </div>
                <div className="ocr-result-item">
                  <span>분류</span>
                  <span>{formData.category}</span>
                </div>
              </div>
            )}
          </div>

          <div className="card" style={{ marginTop: '1.5rem' }}>
            <h2 className="card-title">
              <span>✏️</span> 경비 입력
            </h2>
            
            <form onSubmit={handleSubmit}>
              <div className="form-row">
                <div className="form-group">
                  <label>날짜</label>
                  <input
                    type="date"
                    name="date"
                    value={formData.date}
                    onChange={handleInputChange}
                  />
                </div>
                <div className="form-group">
                  <label>지출 항목</label>
                  <select
                    name="category"
                    value={formData.category}
                    onChange={handleInputChange}
                  >
                    {config?.categories?.map(cat => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>금액</label>
                  <input
                    type="number"
                    name="amount"
                    value={formData.amount}
                    onChange={handleInputChange}
                    placeholder="금액 입력"
                  />
                </div>
                <div className="form-group">
                  <label>화폐 단위</label>
                  <select
                    name="currency"
                    value={formData.currency}
                    onChange={handleInputChange}
                  >
                    {currencies.map(curr => (
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
                  <select
                    name="payment_method"
                    value={formData.payment_method}
                    onChange={handleInputChange}
                  >
                    <option value="현금">💵 현금</option>
                    <option value="신용카드">💳 신용카드 (+{settings.credit_card_fee_rate || 2.5}%)</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>지불한 사람</label>
                  <select
                    name="payer"
                    value={formData.payer}
                    onChange={handleInputChange}
                    required
                  >
                    <option value="">선택하세요</option>
                    {config?.participants?.map(p => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>세부 내역</label>
                <input
                  type="text"
                  name="description"
                  value={formData.description}
                  onChange={handleInputChange}
                  placeholder="가게명, 메모 등"
                />
              </div>

              <div className="form-group expense-type-group">
                <label>지출 유형</label>
                <div className="expense-type-options">
                  <label className={`expense-type-option ${!formData.is_personal_expense ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="expense_type"
                      checked={!formData.is_personal_expense}
                      onChange={() => setFormData(prev => ({ 
                        ...prev, 
                        is_personal_expense: false,
                        personal_expense_for: ''
                      }))}
                    />
                    <span className="expense-type-label">👥 공동 경비</span>
                  </label>
                  <label className={`expense-type-option ${formData.is_personal_expense ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="expense_type"
                      checked={formData.is_personal_expense}
                      onChange={() => setFormData(prev => ({ 
                        ...prev, 
                        is_personal_expense: true 
                      }))}
                    />
                    <span className="expense-type-label">👤 개인 지출</span>
                  </label>
                </div>
              </div>

              {formData.is_personal_expense && (
                <div className="form-group personal-expense-for">
                  <label>개인 지출 해당자</label>
                  <select
                    name="personal_expense_for"
                    value={formData.personal_expense_for}
                    onChange={handleInputChange}
                    required
                  >
                    <option value="">해당자 선택</option>
                    {config?.participants?.map(p => (
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
              onClick={() => setIsExchangeCardOpen(prev => !prev)}
            >
              <span className={`card-toggle-chevron ${isExchangeCardOpen ? 'open' : ''}`}>▶</span>
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
                        hour: '2-digit', minute: '2-digit'
                      })}
                    </span>
                    {exchangeRateInfo.source && (
                      <span className="rate-info-source">{exchangeRateInfo.source}</span>
                    )}
                  </div>
                )}

                <div className="exchange-rates">
                  {currencies.filter(c => !c.is_base).map(curr => (
                    <div className="rate-item" key={curr.code}>
                      <label>{curr.flag} 1 {curr.code} =</label>
                      <input
                        type="number"
                        step="0.1"
                        value={exchangeRates[curr.code] || curr.rate}
                        onChange={(e) => handleRateChange(curr.code, e.target.value)}
                      />
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>KRW</span>
                    </div>
                  ))}
                  {currencies.filter(c => !c.is_base).length === 0 && (
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

        {/* 우측: 경비 내역 테이블 */}
        <div className="right-panel">
          <div className="card">
            <h2 className="card-title">
              <span>📋</span> 경비 내역
            </h2>
            
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
                      <th style={{ width: '2rem' }}></th>
                      <th>날짜</th>
                      <th>지출 항목</th>
                      <th>금액</th>
                      <th>원화 환산액</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {expenses.map(expense => {
                      const isExpanded = expandedExpenses.has(expense._id);
                      return (
                        <React.Fragment key={expense._id}>
                          <tr 
                            className={`expense-summary-row ${expense.is_personal_expense ? 'personal-expense-row' : ''} ${isExpanded ? 'expanded' : ''}`}
                            onClick={() => toggleExpense(expense._id)}
                          >
                            <td className="toggle-cell" data-label="">
                              <span className={`toggle-chevron ${isExpanded ? 'open' : ''}`}>▶</span>
                            </td>
                            <td data-label="날짜">{expense.date}</td>
                            <td data-label="지출 항목">
                              <span className="badge badge-category">{expense.category}</span>
                            </td>
                            <td data-label="금액" className="amount">
                              {formatAmount(expense.amount)} {expense.currency}
                            </td>
                            <td data-label="원화 환산액" className="amount krw-amount">
                              ₩{formatAmount(expense.krw_amount)}
                            </td>
                            <td className="mobile-toggle-hint" data-label="">
                              {isExpanded ? '접기' : '펼치기'}
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr className={`expense-detail-row ${expense.is_personal_expense ? 'personal-expense-row' : ''}`}>
                              <td colSpan="6" data-label="">
                                <div className="expense-detail-grid">
                                  <div className="detail-item">
                                    <span className="detail-label">결제수단</span>
                                    <span className={`badge ${expense.payment_method === '현금' ? 'badge-cash' : 'badge-card'}`}>
                                      {expense.payment_method === '현금' ? '💵' : '💳'} {expense.payment_method}
                                    </span>
                                  </div>
                                  <div className="detail-item">
                                    <span className="detail-label">적용 환율</span>
                                    <span className="amount exchange-rate">
                                      {expense.exchange_rate ? expense.exchange_rate.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '-'}
                                    </span>
                                  </div>
                                  <div className="detail-item">
                                    <span className="detail-label">세부 내역</span>
                                    <span>{expense.description || '-'}</span>
                                  </div>
                                  <div className="detail-item">
                                    <span className="detail-label">지불한 사람</span>
                                    <span>{expense.payer}</span>
                                  </div>
                                  <div className="detail-item">
                                    <span className="detail-label">유형</span>
                                    {expense.is_personal_expense ? (
                                      <span className="badge badge-personal" title={`${expense.personal_expense_for}의 개인 지출`}>
                                        👤 {expense.personal_expense_for}
                                      </span>
                                    ) : (
                                      <span className="badge badge-shared">👥 공동</span>
                                    )}
                                  </div>
                                  <div className="detail-item detail-actions">
                                    <button 
                                      className="delete-btn"
                                      onClick={(e) => { e.stopPropagation(); handleDelete(expense._id); }}
                                      title="삭제"
                                    >
                                      🗑️ 삭제
                                    </button>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 요약 섹션 */}
      {summary && (
        <>
        <div className="report-actions">
          <button 
            className="btn btn-download" 
            onClick={handleDownloadReport}
            disabled={loading || expenses.length === 0}
          >
            {loading ? '다운로드 중...' : '📥 경비 리포트 다운로드 (Excel)'}
          </button>
        </div>
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
                        style={{ 
                          width: `${(amount / summary.total_krw) * 100}%` 
                        }}
                      ></div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>

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
        </>
      )}

      {/* 설정 모달 */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>⚙️ 설정</h2>
              <button className="modal-close" onClick={() => setShowSettings(false)}>×</button>
            </div>
            
            {/* 탭 네비게이션 */}
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
              {/* 현재 여행 설정 탭 */}
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
                    <small className="form-hint">정산에 참여할 사람들의 이름을 쉼표로 구분하여 입력하세요</small>
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
                    <small className="form-hint">지출 분류를 쉼표로 구분하여 입력하세요</small>
                  </div>
                  
                  <div className="form-group">
                    <label>신용카드 수수료율 (%)</label>
                    <input
                      type="number"
                      name="credit_card_fee_rate"
                      value={settingsForm.credit_card_fee_rate}
                      onChange={handleSettingsChange}
                      step="0.1"
                      min="0"
                      max="10"
                      placeholder="2.5"
                    />
                    <small className="form-hint">해외 결제 시 추가되는 수수료율을 입력하세요</small>
                  </div>
                  
                  <div className="form-group">
                    <label>🔑 Google API Key</label>
                    <input
                      type="password"
                      name="google_api_key"
                      value={settingsForm.google_api_key}
                      onChange={handleSettingsChange}
                      placeholder="AIza..."
                    />
                    <small className="form-hint">영수증 OCR 분석을 위한 Google API 키를 입력하세요 (Gemini 2.5 Flash)</small>
                  </div>
                  
                  <div className="form-group">
                    <label>🏦 한국수출입은행 API Key (선택)</label>
                    <input
                      type="password"
                      name="koreaexim_api_key"
                      value={settingsForm.koreaexim_api_key}
                      onChange={handleSettingsChange}
                      placeholder="API 키 입력..."
                    />
                    <small className="form-hint">
                      공식 환율 데이터를 위한 API 키입니다. 미입력시 무료 API로 자동 대체됩니다.
                      <a href="https://www.koreaexim.go.kr/ir/HPHKIR020M01?apino=2&viewtype=C#tab2" 
                         target="_blank" rel="noopener noreferrer"
                         style={{ marginLeft: '4px', color: 'var(--accent)' }}>
                        무료 발급
                      </a>
                    </small>
                  </div>
                  
                  <div className="new-trip-section">
                    <button className="btn btn-new-trip" onClick={openNewTripConfirm}>
                      ✨ 새 여행 시작하기
                    </button>
                    <small className="form-hint" style={{ textAlign: 'center', display: 'block', marginTop: '0.5rem' }}>
                      현재 여행을 저장하고 새로운 여행을 시작합니다
                    </small>
                  </div>
                </>
              )}
              
              {/* 저장된 여행 목록 탭 */}
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
                    trips.map(trip => (
                      <div key={trip.id} className="trip-item">
                        <div className="trip-info">
                          <div className="trip-title">{trip.title}</div>
                          <div className="trip-meta">
                            <span>📅 {formatDate(trip.archived_at)}</span>
                            <span>📋 {trip.expense_count}건</span>
                            <span>💰 ₩{formatAmount(trip.total_krw)}</span>
                          </div>
                        </div>
                        <div className="trip-actions">
                          <button 
                            className="btn btn-trip-load"
                            onClick={() => handleLoadTrip(trip.id)}
                            disabled={loading}
                          >
                            불러오기
                          </button>
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
                <button className="btn btn-primary" onClick={handleSaveSettings} disabled={loading}>
                  {loading ? <div className="loading"></div> : '저장'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 새 여행 생성 확인 모달 */}
      {showNewTripConfirm && (
        <div className="modal-overlay" onClick={() => setShowNewTripConfirm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>✨ 새 여행 시작</h2>
              <button className="modal-close" onClick={() => setShowNewTripConfirm(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="confirm-message">
                <p>⚠️ 새 여행을 시작하면 현재 데이터가 저장되고 초기화됩니다.</p>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                  저장된 여행은 설정 &gt; 저장된 여행 탭에서 다시 불러올 수 있습니다.
                </p>
              </div>
              
              <div className="form-group" style={{ marginTop: '1.5rem' }}>
                <label>새 여행 타이틀 *</label>
                <input
                  type="text"
                  name="trip_title"
                  value={newTripForm.trip_title}
                  onChange={handleNewTripFormChange}
                  placeholder="예: 2025 유럽 여행"
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
              
              <div className="form-group">
                <label>신용카드 수수료율 (%)</label>
                <input
                  type="number"
                  name="credit_card_fee_rate"
                  value={newTripForm.credit_card_fee_rate}
                  onChange={handleNewTripFormChange}
                  step="0.1"
                  min="0"
                  max="10"
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

      {/* 통화 추가/수정 모달 */}
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

      {/* 푸터 */}
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

      {/* 토스트 메시지 */}
      {toast && (
        <div className={`toast ${toast.type}`}>
          {toast.message}
        </div>
      )}
    </div>
  );
}

export default App;
