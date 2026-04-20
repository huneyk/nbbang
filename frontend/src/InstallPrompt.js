import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

const DISMISS_KEY = 'npang_install_dismissed_at';
const DISMISS_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000; // 7일

const isIOSDevice = () => {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  const isIPad = /iPad/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  return /iPhone|iPod/.test(ua) || isIPad;
};

const isStandaloneMode = () => {
  if (typeof window === 'undefined') return false;
  const mql = window.matchMedia && window.matchMedia('(display-mode: standalone)');
  return (mql && mql.matches) || window.navigator.standalone === true;
};

const wasRecentlyDismissed = () => {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    const at = parseInt(raw, 10);
    if (!Number.isFinite(at)) return false;
    return Date.now() - at < DISMISS_COOLDOWN_MS;
  } catch {
    return false;
  }
};

const markDismissed = () => {
  try {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
  } catch {
    // no-op
  }
};

const InstallContext = createContext(null);

export function InstallPromptProvider({ children }) {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [standalone, setStandalone] = useState(isStandaloneMode);
  const [showBanner, setShowBanner] = useState(false);
  const [showIosGuide, setShowIosGuide] = useState(false);

  const ios = useMemo(isIOSDevice, []);

  useEffect(() => {
    if (standalone) return undefined;

    const handleBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      if (!wasRecentlyDismissed()) setShowBanner(true);
    };

    const handleInstalled = () => {
      setDeferredPrompt(null);
      setShowBanner(false);
      setShowIosGuide(false);
      setStandalone(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleInstalled);

    // iOS Safari는 beforeinstallprompt를 지원하지 않으므로 수동 안내 배너를 띄운다.
    if (ios && !wasRecentlyDismissed()) {
      const timer = setTimeout(() => setShowBanner(true), 1500);
      return () => {
        clearTimeout(timer);
        window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
        window.removeEventListener('appinstalled', handleInstalled);
      };
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleInstalled);
    };
  }, [standalone, ios]);

  const triggerInstall = useCallback(async () => {
    if (deferredPrompt) {
      try {
        await deferredPrompt.prompt();
        await deferredPrompt.userChoice;
      } catch {
        // no-op
      } finally {
        setDeferredPrompt(null);
        setShowBanner(false);
      }
      return;
    }
    if (ios) {
      setShowIosGuide(true);
      setShowBanner(false);
    }
  }, [deferredPrompt, ios]);

  const dismissBanner = useCallback(() => {
    markDismissed();
    setShowBanner(false);
  }, []);

  const canInstall = !standalone && (!!deferredPrompt || ios);

  const value = useMemo(
    () => ({
      canInstall,
      isIOS: ios,
      standalone,
      triggerInstall,
      dismissBanner,
      showBanner,
      showIosGuide,
      closeIosGuide: () => setShowIosGuide(false),
    }),
    [canInstall, ios, standalone, triggerInstall, dismissBanner, showBanner, showIosGuide]
  );

  return (
    <InstallContext.Provider value={value}>
      {children}
      <InstallBanner />
    </InstallContext.Provider>
  );
}

export function useInstallPrompt() {
  return useContext(InstallContext) || {
    canInstall: false,
    isIOS: false,
    standalone: false,
    triggerInstall: () => {},
    dismissBanner: () => {},
    showBanner: false,
    showIosGuide: false,
    closeIosGuide: () => {},
  };
}

function InstallBanner() {
  const {
    canInstall, standalone, showBanner, showIosGuide,
    triggerInstall, dismissBanner, closeIosGuide,
  } = useInstallPrompt();

  if (standalone) return null;

  return (
    <>
      {showBanner && canInstall && (
        <div className="install-banner" role="dialog" aria-label="홈 화면에 추가">
          <img src="/Nbang_icon_192.png" alt="Npang" className="install-banner-icon" />
          <div className="install-banner-text">
            <strong>Npang을 홈 화면에 추가</strong>
            <span>앱처럼 빠르게 실행하고 바로 영수증을 찍어보세요</span>
          </div>
          <div className="install-banner-actions">
            <button type="button" className="install-btn-primary" onClick={triggerInstall}>
              홈 화면에 추가
            </button>
            <button
              type="button"
              className="install-btn-dismiss"
              onClick={dismissBanner}
              aria-label="닫기"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {showIosGuide && (
        <div className="install-modal-overlay" onClick={closeIosGuide}>
          <div className="install-modal" onClick={(e) => e.stopPropagation()}>
            <div className="install-modal-header">
              <img src="/Nbang_icon_192.png" alt="Npang" className="install-modal-icon" />
              <div>
                <h3>Npang 홈 화면에 추가</h3>
                <p>Safari에서 몇 단계만 진행하면 앱처럼 사용할 수 있어요.</p>
              </div>
              <button
                type="button"
                className="install-modal-close"
                onClick={closeIosGuide}
                aria-label="닫기"
              >
                ×
              </button>
            </div>
            <ol className="install-steps">
              <li>
                <span className="install-step-badge">1</span>
                하단(또는 상단)의 <strong>공유 버튼</strong>
                <span className="ios-share-icon" aria-hidden="true">⬆</span>
                을 탭하세요.
              </li>
              <li>
                <span className="install-step-badge">2</span>
                메뉴에서 <strong>'홈 화면에 추가'</strong>를 선택하세요.
              </li>
              <li>
                <span className="install-step-badge">3</span>
                이름이 <strong>'Npang'</strong>인지 확인 후 <strong>'추가'</strong>를 탭하세요.
              </li>
            </ol>
            <button
              type="button"
              className="install-btn-primary install-btn-block"
              onClick={() => { markDismissed(); closeIosGuide(); }}
            >
              확인
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export function InstallButton({ className, children }) {
  const { canInstall, triggerInstall } = useInstallPrompt();
  if (!canInstall) return null;
  return (
    <button
      type="button"
      className={className || 'install-nav-btn'}
      onClick={triggerInstall}
      title="홈 화면에 추가"
    >
      {children || <>📲 홈 화면에 추가</>}
    </button>
  );
}

export default InstallPromptProvider;
