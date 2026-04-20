import React, { useEffect, useState } from 'react';

function useIsMobile(breakpoint = 760) {
  const getMatch = () =>
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia(`(max-width: ${breakpoint}px)`).matches;

  const [isMobile, setIsMobile] = useState(getMatch);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(`(max-width: ${breakpoint}px)`);
    const handler = (e) => setIsMobile(e.matches);
    setIsMobile(mql.matches);
    if (mql.addEventListener) mql.addEventListener('change', handler);
    else mql.addListener(handler);
    return () => {
      if (mql.removeEventListener) mql.removeEventListener('change', handler);
      else mql.removeListener(handler);
    };
  }, [breakpoint]);

  return isMobile;
}

const SECTIONS = [
  { id: 'quickstart', icon: '🚀', title: '빠른 시작' },
  { id: 'login', icon: '🔐', title: '로그인 / 회원가입' },
  { id: 'trip', icon: '🧳', title: '여행 설정' },
  { id: 'expense', icon: '🧾', title: '경비 입력' },
  { id: 'type', icon: '👥', title: '공동 / 개인 지출' },
  { id: 'rate', icon: '💱', title: '환율 관리' },
  { id: 'summary', icon: '📊', title: '정산 확인' },
  { id: 'report', icon: '📥', title: '리포트 다운로드' },
  { id: 'trips', icon: '📂', title: '여행 관리' },
  { id: 'faq', icon: '❓', title: '자주 묻는 질문' },
];

export default function UsageGuide({ open, onClose }) {
  const [activeId, setActiveId] = useState('quickstart');
  const isMobile = useIsMobile();

  if (!open) return null;

  const handleJump = (id) => {
    setActiveId(id);
    const el = document.getElementById(`guide-section-${id}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div
        style={{ ...styles.modal, ...(isMobile ? styles.modalMobile : {}) }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ ...styles.header, ...(isMobile ? styles.headerMobile : {}) }}>
          <div style={styles.titleWrap}>
            <span style={styles.titleEmoji}>📖</span>
            <div>
              <h2 style={styles.title}>Npang 사용법 안내</h2>
              {!isMobile && (
                <p style={styles.subtitle}>영수증만 찰칵! 여행 경비 정산, 이렇게 사용하세요.</p>
              )}
            </div>
          </div>
          <button type="button" onClick={onClose} style={styles.closeBtn} aria-label="닫기">✕</button>
        </div>

        <div style={{ ...styles.body, ...(isMobile ? styles.bodyMobile : {}) }}>
          <aside style={isMobile ? styles.navMobile : styles.nav}>
            {!isMobile && <div style={styles.navTitle}>목차</div>}
            <div style={isMobile ? styles.navListMobile : undefined}>
              {SECTIONS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => handleJump(s.id)}
                  style={{
                    ...(isMobile ? styles.navItemMobile : styles.navItem),
                    ...(activeId === s.id
                      ? (isMobile ? styles.navItemActiveMobile : styles.navItemActive)
                      : {}),
                  }}
                >
                  <span style={styles.navIcon}>{s.icon}</span>
                  <span>{s.title}</span>
                </button>
              ))}
            </div>
          </aside>

          <section style={{ ...styles.content, ...(isMobile ? styles.contentMobile : {}) }}>
            <Section id="quickstart" icon="🚀" title="빠른 시작">
              <div style={styles.quickstartCard}>
                <p style={styles.quickstartLead}>
                  처음이라면 아래 3단계만 따라 해보세요.
                </p>
                <ol style={styles.quickstartSteps}>
                <li>
                  <strong>로그인</strong> 후 <strong>⚙️ 설정</strong> 버튼을 눌러
                  <em> 여행 타이틀</em>을 입력하고, 경비를 <strong>1/n으로 분담할
                  참가자 이름</strong>을 입력합니다.
                </li>
                  <li>
                    영수증을 스마트폰 카메라로 촬영해서 입력하면 AI가 자동으로
                    날짜·금액·카테고리를 채워줍니다.
                    <span style={styles.quickstartNote}> (사진 이미지를 업로드해도 됩니다.)</span>
                  </li>
                <li>
                  하단의 <strong>💸 정산 내역</strong>에서 누가 얼마를 주고받을지
                  한눈에 확인하고, <strong>📊 엑셀 다운로드</strong>로 공유하세요.
                  <br />
                  <small style={{ color: '#7a9b85' }}>
                    (회사 경비 보고용으로 영수증이 첨부된 내역도 다운로드할 수 있습니다.)
                  </small>
                </li>
                </ol>
                <div style={styles.quickstartTip}>
                  <span style={styles.tipLabel}>💡 TIP</span>
                  <span>
                    혼자서 경비를 기록하고 싶다면 <strong>참가자를 한 명만 입력</strong>하세요.
                    1인용 총무 모드로 전환되어 분담 계산 없이 지출만 관리할 수 있습니다.
                  </span>
                </div>
              </div>
            </Section>

            <Section id="login" icon="🔐" title="로그인 / 회원가입">
              <ul style={styles.ul}>
                <li>이메일 + <strong>비밀번호</strong> 설정 방식입니다.</li>
                <li>
                  <strong>회원가입</strong> 시 이메일과 비밀번호(8자 이상)를 입력하고
                  <em> 인증번호 받기</em>를 누르면 6자리 코드가 메일로 발송됩니다.
                  받은 코드를 입력하면 가입이 완료됩니다.
                </li>
                <li>
                  <strong>로그인</strong>은 가입한 이메일과 비밀번호로 바로 할 수 있습니다.
                  (이름은 선택 입력이며 언제든 변경 가능)
                </li>
                <li>
                  비밀번호를 잊었다면 로그인 화면의 <strong>비밀번호 찾기</strong>에서
                  인증번호를 받아 새 비밀번호로 재설정할 수 있습니다.
                </li>
              </ul>
              <Tip>
                인증번호 메일이 오지 않는다면 스팸 메일함을 확인해주세요.
                재전송은 60초 후에 가능합니다.
              </Tip>
            </Section>

            <Section id="trip" icon="🧳" title="여행 설정">
              <p>우측 상단 <strong>⚙️ 설정</strong> 버튼에서 현재 여행 정보를 관리합니다.</p>
              <ul style={styles.ul}>
                <li><strong>여행 타이틀</strong> &mdash; 예: <em>2026 도쿄 벚꽃 여행</em></li>
                <li>
                  <strong>참가자</strong> &mdash; 쉼표로 구분해 입력하세요.
                  <br />첫 번째로 입력한 분이 <em>주 경비 집행자</em>로 설정됩니다.
                </li>
                <li>
                  <strong>지출 항목</strong> &mdash; 기본값은 <em>교통비, 식사비, 음료/간식, 숙박비, 기타</em>.
                  AI가 영수증을 보고 자동 분류합니다.
                </li>
                <li>
                  <strong>신용카드 수수료율(%)</strong> &mdash; 해외 결제 시 적용할
                  수수료율 (기본 2.5%). <em>내 계정</em>에 저장되어 모든 여행에
                  공통으로 적용되며, 신용카드 결제 경비에 자동으로 가산됩니다.
                </li>
              </ul>
            </Section>

            <Section id="expense" icon="🧾" title="경비 입력">
              <h4 style={styles.h4}>방법 1. 영수증 사진 업로드 (권장)</h4>
              <ol style={styles.steps}>
                <li><strong>📷 영수증 업로드</strong> 영역을 탭해 사진을 찍거나 이미지를 선택합니다.</li>
                <li>AI(Google Gemini)가 영수증을 분석해 날짜·금액·화폐·카테고리를 자동 채움합니다.</li>
                <li>내용을 확인하고 필요하면 수정 후 <strong>➕ 추가 하기</strong>를 누르세요.</li>
              </ol>
              <p style={styles.sub}>
                지원 포맷: JPG · PNG · GIF · WEBP / 최대 50MB
              </p>

              <h4 style={styles.h4}>방법 2. 직접 입력</h4>
              <p>
                영수증이 없어도 <strong>✏️ 경비 입력</strong> 폼에서 수동으로 등록할 수 있습니다.
                금액과 지불한 사람은 필수 입력입니다.
              </p>
              <Tip>
                영수증 사진은 서버에 안전하게 저장되며, 경비 내역의 🧾 아이콘을 눌러
                언제든지 다시 볼 수 있습니다. 영수증 PDF 다운로드에도 포함됩니다.
              </Tip>
            </Section>

            <Section id="type" icon="👥" title="공동 / 개인 지출">
              <p>참가자가 2명 이상이면 지출 유형을 선택할 수 있습니다.</p>
              <div style={styles.cards}>
                <div style={styles.card}>
                  <div style={styles.cardTitle}>👥 공동 경비</div>
                  <div style={styles.cardDesc}>
                    모두가 함께 사용한 경비입니다. <br />
                    참가자 수로 <strong>N분의 1</strong> 나누어 정산됩니다.
                  </div>
                </div>
                <div style={styles.card}>
                  <div style={styles.cardTitle}>👤 개인 지출</div>
                  <div style={styles.cardDesc}>
                    특정 한 사람의 지출입니다. <br />
                    해당자에게만 <strong>전액 청구</strong>되며, 다른 사람이
                    대신 결제했다면 그 금액만 되돌려받게 됩니다.
                  </div>
                </div>
              </div>
            </Section>

            <Section id="rate" icon="💱" title="환율 관리">
              <ul style={styles.ul}>
                <li>
                  좌측 <strong>💱 환율 설정</strong> 카드를 펼쳐 현재 환율을 확인·수정합니다.
                  (기준: <em>현찰 살 때</em>)
                </li>
                <li>
                  <strong>🔄 최신 환율 가져오기</strong> 버튼으로 한국수출입은행 고시
                  환율을 즉시 반영할 수 있습니다.
                </li>
                <li>매일 <strong>오전 4시</strong>에도 자동 갱신됩니다.</li>
                <li>
                  ➕ 버튼을 눌러 <strong>새 통화</strong>를 추가할 수 있습니다. (예: EUR, GBP, CNY)
                </li>
              </ul>
              <Tip>
                경비가 이미 등록된 뒤 환율을 수정해도, <strong>저장 시점의 환율</strong>이
                경비에 그대로 유지됩니다. 환율 변경은 새로 입력하는 경비부터 적용됩니다.
              </Tip>
            </Section>

            <Section id="summary" icon="📊" title="정산 확인">
              <ul style={styles.ul}>
                <li><strong>💰 총 경비</strong> &mdash; 공동/개인 지출 합계(원화 환산)를 표시합니다.</li>
                <li><strong>👥 1인당 분담액</strong> &mdash; 공동 경비만 N분의 1로 계산됩니다.</li>
                <li><strong>📊 카테고리별 지출</strong> &mdash; 가장 많이 쓴 항목을 시각화합니다.</li>
                <li>
                  <strong>💸 정산 내역</strong> &mdash; 참가자별로
                  <span style={{ color: '#27ae60', fontWeight: 700 }}> 받을 금액</span> /
                  <span style={{ color: '#c0334d', fontWeight: 700 }}> 보낼 금액</span>을
                  한눈에 보여줍니다.
                </li>
              </ul>
              <Tip>
                정산 결과의 금액 부호는 <strong>+는 더 내야 할 금액</strong>,
                <strong> −는 돌려받을 금액</strong>을 의미합니다.
              </Tip>
            </Section>

            <Section id="report" icon="📥" title="리포트 다운로드">
              <div style={styles.cards}>
                <div style={styles.card}>
                  <div style={styles.cardTitle}>📊 엑셀로 다운로드</div>
                  <div style={styles.cardDesc}>
                    전체 경비 내역, 카테고리 합계, 정산 요약이 시트별로 정리된
                    <strong> .xlsx</strong> 파일을 내려받습니다.
                  </div>
                </div>
                <div style={styles.card}>
                  <div style={styles.cardTitle}>🧾 영수증 첨부 다운로드</div>
                  <div style={styles.cardDesc}>
                    업로드된 영수증 이미지를 경비 내역과 함께 엮은
                    <strong> PDF</strong> 파일로 받을 수 있습니다. 회사 경비 보고용으로 유용합니다.
                  </div>
                </div>
              </div>
            </Section>

            <Section id="trips" icon="📂" title="여행 관리">
              <ul style={styles.ul}>
                <li>
                  <strong>✨ 새 여행 시작하기</strong> &mdash; 현재 여행을 자동 저장하고
                  빈 상태에서 새 여행을 시작합니다.
                </li>
                <li>
                  <strong>📂 저장된 여행</strong> 탭에서 지난 여행을
                  <em> 불러오기 / 삭제</em> 할 수 있습니다.
                </li>
                <li>
                  여행을 삭제하면 해당 여행의 경비와 영수증 이미지도 함께 삭제되며,
                  <strong> 복구할 수 없습니다</strong>.
                </li>
              </ul>
            </Section>

            <Section id="faq" icon="❓" title="자주 묻는 질문">
              <FaqItem
                q="영수증 분석이 정확하지 않아요."
                a="흔들림 없는 밝은 환경에서 영수증 전체가 프레임에 들어오도록 촬영하면 인식률이 높아집니다. 결과가 틀릴 경우 입력 폼에서 직접 수정 후 저장하세요."
              />
              <FaqItem
                q="환율을 실수로 바꿨는데, 이전 경비에 반영되나요?"
                a="아니요. 각 경비에는 등록 당시의 환율이 함께 저장됩니다. 환율 수정은 이후 새로 등록하는 경비에만 적용됩니다."
              />
              <FaqItem
                q="참가자를 도중에 추가/변경할 수 있나요?"
                a="네, 설정에서 언제든 변경할 수 있습니다. 단, 참가자 변경 시 1인당 분담액은 즉시 새 인원으로 다시 계산됩니다."
              />
              <FaqItem
                q="신용카드 수수료율은 어떻게 계산되나요?"
                a="결제 수단을 '신용카드'로 선택한 경비에 한해, 내 계정에 저장된 수수료율(기본 2.5%)이 원화 환산액에 자동 가산됩니다. 사용자마다 개별로 설정하며 모든 여행에 공통 적용됩니다."
              />
              <FaqItem
                q="로그아웃하면 데이터가 사라지나요?"
                a="아니요. 모든 경비와 영수증은 서버에 계정별로 저장되며, 다시 로그인하면 그대로 이어서 사용할 수 있습니다."
              />
            </Section>

            <div style={styles.footerNote}>
              더 궁금한 점이 있다면 관리자에게 문의해주세요. 즐거운 여행 되세요! ✈️
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Section({ id, icon, title, children }) {
  return (
    <div id={`guide-section-${id}`} style={styles.section}>
      <h3 style={styles.sectionTitle}>
        <span style={styles.sectionIcon}>{icon}</span>
        {title}
      </h3>
      <div style={styles.sectionBody}>{children}</div>
    </div>
  );
}

function Tip({ children }) {
  return (
    <div style={styles.tip}>
      <span style={styles.tipLabel}>💡 TIP</span>
      <span>{children}</span>
    </div>
  );
}

function FaqItem({ q, a }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={styles.faq}>
      <button type="button" onClick={() => setOpen((v) => !v)} style={styles.faqQ}>
        <span style={{ ...styles.faqChevron, transform: open ? 'rotate(90deg)' : 'none' }}>▶</span>
        <span>{q}</span>
      </button>
      {open && <div style={styles.faqA}>{a}</div>}
    </div>
  );
}

const styles = {
  backdrop: {
    position: 'fixed', inset: 0,
    background: 'rgba(0, 0, 0, 0.55)',
    backdropFilter: 'blur(4px)',
    WebkitBackdropFilter: 'blur(4px)',
    zIndex: 1100,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 16,
    animation: 'fadeIn 0.2s ease',
  },
  modal: {
    width: '100%',
    maxWidth: 920,
    maxHeight: '92vh',
    background: '#ffffff',
    borderRadius: 16,
    border: '1px solid #c5e1cf',
    boxShadow: '0 20px 60px rgba(46, 204, 113, 0.22)',
    overflow: 'hidden',
    display: 'flex', flexDirection: 'column',
  },
  modalMobile: {
    maxHeight: '96vh',
    borderRadius: 12,
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '18px 22px',
    borderBottom: '1px solid #c5e1cf',
    background: 'linear-gradient(135deg, #f0f9f4 0%, #e4f3eb 100%)',
  },
  headerMobile: {
    padding: '12px 14px',
  },
  titleWrap: { display: 'flex', alignItems: 'center', gap: 14 },
  titleEmoji: { fontSize: 32 },
  title: {
    margin: 0, fontSize: 20, fontWeight: 700, color: '#1a2e22',
    fontFamily: "'Nunito', 'Jua', sans-serif",
  },
  subtitle: {
    margin: '2px 0 0', fontSize: 13, color: '#7a9b85',
    fontFamily: "'Gamja Flower', cursive", letterSpacing: '0.3px',
  },
  closeBtn: {
    width: 32, height: 32,
    background: 'transparent', border: 'none',
    fontSize: 18, cursor: 'pointer', color: '#7a9b85',
    borderRadius: 6,
  },
  body: {
    display: 'flex',
    flex: 1,
    minHeight: 0,
  },
  bodyMobile: {
    flexDirection: 'column',
  },
  nav: {
    width: 220,
    flexShrink: 0,
    padding: '16px 10px',
    borderRight: '1px solid #e4f3eb',
    background: '#fbfefc',
    overflowY: 'auto',
  },
  navMobile: {
    width: '100%',
    flexShrink: 0,
    padding: '8px 10px',
    borderBottom: '1px solid #e4f3eb',
    background: '#fbfefc',
    overflowX: 'auto',
    overflowY: 'hidden',
    WebkitOverflowScrolling: 'touch',
  },
  navListMobile: {
    display: 'flex',
    gap: 6,
    flexWrap: 'nowrap',
    width: 'max-content',
  },
  navItemMobile: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    flexShrink: 0,
    padding: '7px 12px',
    background: '#ffffff',
    border: '1px solid #c5e1cf',
    borderRadius: 999,
    cursor: 'pointer',
    fontSize: 13,
    color: '#3d5c47',
    whiteSpace: 'nowrap',
  },
  navItemActiveMobile: {
    background: '#e4f3eb',
    borderColor: '#27ae60',
    color: '#27ae60',
    fontWeight: 700,
  },
  navTitle: {
    fontSize: 11, fontWeight: 700, color: '#7a9b85',
    textTransform: 'uppercase', letterSpacing: '1px',
    padding: '0 10px 8px',
  },
  navItem: {
    display: 'flex', alignItems: 'center', gap: 8,
    width: '100%',
    padding: '9px 10px',
    background: 'transparent', border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 13.5, color: '#3d5c47',
    textAlign: 'left',
    marginBottom: 2,
  },
  navItemActive: {
    background: '#e4f3eb',
    color: '#27ae60',
    fontWeight: 700,
  },
  navIcon: { fontSize: 15 },
  content: {
    flex: 1,
    padding: '20px 26px 28px',
    overflowY: 'auto',
    color: '#1a2e22',
    lineHeight: 1.65,
  },
  contentMobile: {
    padding: '14px 16px 22px',
  },
  section: { marginBottom: 28 },
  sectionTitle: {
    display: 'flex', alignItems: 'center', gap: 10,
    fontSize: 17, fontWeight: 700, color: '#1a2e22',
    margin: '0 0 10px',
    paddingBottom: 8,
    borderBottom: '1px dashed #c5e1cf',
  },
  sectionIcon: { fontSize: 20 },
  sectionBody: { fontSize: 14, color: '#3d5c47' },
  lead: { fontSize: 14, color: '#3d5c47', margin: '0 0 10px' },
  quickstartCard: {
    padding: '18px 22px 20px',
    background: 'linear-gradient(135deg, #f0f9f4 0%, #e4f3eb 100%)',
    border: '1px solid #c5e1cf',
    borderLeft: '4px solid #2ecc71',
    borderRadius: 12,
    boxShadow: '0 4px 14px rgba(46, 204, 113, 0.10)',
    margin: '4px 0 6px',
  },
  quickstartLead: {
    fontSize: 16,
    color: '#1a2e22',
    fontWeight: 600,
    margin: '0 0 12px',
    lineHeight: 1.6,
  },
  quickstartSteps: {
    margin: '0 0 12px 22px',
    padding: 0,
    fontSize: 15.5,
    color: '#1a2e22',
    lineHeight: 1.8,
  },
  quickstartNote: {
    color: '#7a9b85',
    fontSize: 14,
    fontStyle: 'italic',
  },
  quickstartTip: {
    display: 'flex', gap: 10, alignItems: 'flex-start',
    marginTop: 14,
    padding: '12px 16px',
    background: '#ffffff',
    border: '1px solid #c5e1cf',
    borderLeft: '3px solid #2ecc71',
    borderRadius: 8,
    fontSize: 14.5,
    color: '#3d5c47',
    lineHeight: 1.65,
  },
  h4: {
    margin: '14px 0 6px', fontSize: 14, fontWeight: 700, color: '#27ae60',
  },
  sub: { fontSize: 12.5, color: '#7a9b85', margin: '4px 0 10px' },
  steps: { margin: '0 0 10px 20px', padding: 0 },
  ul: { margin: '0 0 10px 20px', padding: 0 },
  tip: {
    display: 'flex', gap: 10, alignItems: 'flex-start',
    margin: '12px 0 6px',
    padding: '10px 14px',
    background: '#f0f9f4',
    border: '1px solid #c5e1cf',
    borderLeft: '3px solid #2ecc71',
    borderRadius: 8,
    fontSize: 13, color: '#3d5c47',
    lineHeight: 1.55,
  },
  tipLabel: {
    flexShrink: 0,
    fontWeight: 700, color: '#27ae60', fontSize: 12,
    letterSpacing: '0.5px',
  },
  cards: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: 12,
    margin: '10px 0',
  },
  card: {
    padding: '14px 16px',
    background: '#fbfefc',
    border: '1px solid #c5e1cf',
    borderRadius: 10,
  },
  cardTitle: {
    fontSize: 14, fontWeight: 700, color: '#27ae60',
    marginBottom: 6,
  },
  cardDesc: { fontSize: 13, color: '#3d5c47', lineHeight: 1.6 },
  faq: {
    borderBottom: '1px solid #e4f3eb',
    padding: '4px 0',
  },
  faqQ: {
    display: 'flex', alignItems: 'center', gap: 10,
    width: '100%',
    padding: '10px 4px',
    background: 'transparent', border: 'none', cursor: 'pointer',
    fontSize: 14, color: '#1a2e22', fontWeight: 600,
    textAlign: 'left',
  },
  faqChevron: {
    display: 'inline-block',
    fontSize: 10, color: '#7a9b85',
    transition: 'transform 0.2s ease',
  },
  faqA: {
    padding: '0 4px 12px 24px',
    fontSize: 13.5, color: '#3d5c47', lineHeight: 1.7,
  },
  footerNote: {
    marginTop: 24, padding: '14px 16px',
    background: '#e4f3eb',
    borderRadius: 10,
    textAlign: 'center',
    fontSize: 13, color: '#27ae60', fontWeight: 600,
    fontFamily: "'Gamja Flower', cursive",
    letterSpacing: '0.3px',
  },
};
