import React, { useState, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';
import './App.css';

// 데스크톱 앱에서는 상대 경로 사용, 개발 모드에서는 localhost 사용
const API_BASE = process.env.REACT_APP_API_BASE !== undefined 
  ? process.env.REACT_APP_API_BASE 
  : 'http://localhost:5001';

function App() {
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [toast, setToast] = useState(null);
  const [previewImage, setPreviewImage] = useState(null);
  
  // 폼 상태
  const [formData, setFormData] = useState({
    date: new Date().toISOString().split('T')[0],
    category: '기타',
    amount: '',
    currency: 'JPY',
    payment_method: '현금',
    description: '',
    payer: '공훈의',
    receipt_image: null
  });

  // 환율 상태
  const [exchangeRates, setExchangeRates] = useState({
    JPY: 9.5,
    USD: 1350
  });

  // 데이터 로드
  const loadData = useCallback(async () => {
    try {
      const [expensesRes, summaryRes, configRes] = await Promise.all([
        axios.get(`${API_BASE}/api/expenses`),
        axios.get(`${API_BASE}/api/summary`),
        axios.get(`${API_BASE}/api/config`)
      ]);
      
      setExpenses(expensesRes.data.data || []);
      setSummary(summaryRes.data.data);
      setConfig(configRes.data.data);
      
      if (configRes.data.data?.exchange_rates) {
        setExchangeRates({
          JPY: configRes.data.data.exchange_rates.JPY,
          USD: configRes.data.data.exchange_rates.USD
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
  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
  
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
          payer: '공훈의',
          receipt_image: null
        });
        setPreviewImage(null);
        loadData();
      }
    } catch (error) {
      console.error('경비 등록 오류:', error);
      showToast('경비 등록에 실패했습니다.', 'error');
    } finally {
      setLoading(false);
    }
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

  // 환율 업데이트
  const handleRateChange = async (currency, value) => {
    const rate = parseFloat(value) || 0;
    setExchangeRates(prev => ({ ...prev, [currency]: rate }));
    
    try {
      await axios.put(`${API_BASE}/api/exchange-rates`, {
        [currency]: rate
      });
    } catch (error) {
      console.error('환율 업데이트 오류:', error);
    }
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
      <header>
        <h1>🌏 여행 경비 정산</h1>
        <p>영수증을 업로드하면 자동으로 분석합니다</p>
      </header>

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
              <input {...getInputProps()} />
              <div className="dropzone-icon">
                {analyzing ? <div className="loading"></div> : '🧾'}
              </div>
              <p>
                {analyzing 
                  ? '영수증 분석 중...' 
                  : '영수증 이미지를 드래그하거나 클릭하세요'}
              </p>
              <small>JPG, PNG, GIF, WEBP 지원</small>
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
                    <option value="KRW">🇰🇷 KRW (원)</option>
                    <option value="JPY">🇯🇵 JPY (엔)</option>
                    <option value="USD">🇺🇸 USD (달러)</option>
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
                    <option value="신용카드">💳 신용카드 (+2.5%)</option>
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

              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? <div className="loading"></div> : '➕ 경비 등록'}
              </button>
            </form>
          </div>

          <div className="card" style={{ marginTop: '1.5rem' }}>
            <h2 className="card-title">
              <span>💱</span> 환율 설정
            </h2>
            <div className="exchange-rates">
              <div className="rate-item">
                <label>1 JPY =</label>
                <input
                  type="number"
                  step="0.1"
                  value={exchangeRates.JPY}
                  onChange={(e) => handleRateChange('JPY', e.target.value)}
                />
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>KRW</span>
              </div>
              <div className="rate-item">
                <label>1 USD =</label>
                <input
                  type="number"
                  step="1"
                  value={exchangeRates.USD}
                  onChange={(e) => handleRateChange('USD', e.target.value)}
                />
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>KRW</span>
              </div>
            </div>
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
                      <th>날짜</th>
                      <th>지출 항목</th>
                      <th>금액</th>
                      <th>결제수단</th>
                      <th>원화 환산액</th>
                      <th>세부 내역</th>
                      <th>지불한 사람</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {expenses.map(expense => (
                      <tr key={expense._id}>
                        <td>{expense.date}</td>
                        <td>
                          <span className="badge badge-category">{expense.category}</span>
                        </td>
                        <td className="amount">
                          {formatAmount(expense.amount)} {expense.currency}
                        </td>
                        <td>
                          <span className={`badge ${expense.payment_method === '현금' ? 'badge-cash' : 'badge-card'}`}>
                            {expense.payment_method === '현금' ? '💵' : '💳'} {expense.payment_method}
                          </span>
                        </td>
                        <td className="amount krw-amount">
                          ₩{formatAmount(expense.krw_amount)}
                        </td>
                        <td>{expense.description}</td>
                        <td>{expense.payer}</td>
                        <td>
                          <button 
                            className="delete-btn"
                            onClick={() => handleDelete(expense._id)}
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
            <p style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              총 {summary.expense_count}건
            </p>
          </div>
          
          <div className="summary-card per-person">
            <h3>👥 1인당 분담액</h3>
            <div className="value">
              {formatAmount(summary.per_person)}
              <span className="unit">원</span>
            </div>
            <p style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              {summary.num_participants}명 기준
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

          <div className="summary-card">
            <h3>💸 정산 내역</h3>
            <div className="settlements">
              {summary.settlements && Object.entries(summary.settlements).map(([name, data]) => (
                <div 
                  key={name} 
                  className={`settlement-item ${data.difference > 0 ? 'receive' : data.difference < 0 ? 'pay' : 'settled'}`}
                >
                  <div>
                    <div className="settlement-name">{name}</div>
                    <div className="settlement-paid">지불: ₩{formatAmount(data.paid)}</div>
                  </div>
                  <div className="settlement-amount">
                    <div className={`diff ${data.difference > 0 ? 'positive' : data.difference < 0 ? 'negative' : ''}`}>
                      {data.difference > 0 ? '+' : ''}{formatAmount(data.difference)}원
                    </div>
                    <div className="status">{data.status}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        </>
      )}

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
