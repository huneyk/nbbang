"""인증번호 이메일 발송 (Gmail SMTP)."""
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from config import Config

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    pass


_PURPOSE_LABEL = {
    'signup': '회원가입',
    'login': '로그인',
    'reset': '비밀번호 재설정',
}


def _purpose_label(purpose: str) -> str:
    return _PURPOSE_LABEL.get(purpose, '인증')


def _build_html_body(code: str, purpose: str, ttl_minutes: int) -> str:
    purpose_text = _purpose_label(purpose)
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 480px; margin: 0 auto; padding: 32px 24px;
                background: #ffffff; color: #1a1a2e;">
      <h1 style="font-size: 22px; margin: 0 0 8px;">Npang {purpose_text} 인증</h1>
      <p style="font-size: 14px; color: #555; margin: 0 0 24px;">
        아래 인증번호를 {ttl_minutes}분 이내에 입력해 주세요.
      </p>
      <div style="background: #f4f6fb; border-radius: 12px; padding: 24px;
                  text-align: center; letter-spacing: 8px;
                  font-size: 32px; font-weight: 700; color: #e94560;">
        {code}
      </div>
      <p style="font-size: 12px; color: #888; margin: 24px 0 0;">
        본인이 요청하지 않은 메일이라면 무시해 주세요. 이 인증번호는 자동으로 만료됩니다.
      </p>
    </div>
    """.strip()


def _build_text_body(code: str, purpose: str, ttl_minutes: int) -> str:
    purpose_text = _purpose_label(purpose)
    return (
        f"[Npang] {purpose_text} 인증번호: {code}\n"
        f"{ttl_minutes}분 이내에 입력해 주세요.\n"
        '본인이 요청하지 않은 메일이라면 무시하세요.'
    )


def send_verification_code(to_email: str, code: str, purpose: str) -> None:
    """Gmail SMTP를 통해 인증번호 메일을 발송합니다.

    Raises:
        EmailNotConfiguredError: GMAIL_USER/GMAIL_APP_PASSWORD가 설정되지 않은 경우
    """
    if not Config.GMAIL_USER or not Config.GMAIL_APP_PASSWORD:
        raise EmailNotConfiguredError(
            'Gmail SMTP가 설정되지 않았습니다. '
            'GMAIL_USER, GMAIL_APP_PASSWORD 환경변수를 확인하세요.'
        )

    ttl_minutes = max(1, Config.VERIFICATION_CODE_TTL_SECONDS // 60)
    purpose_text = _purpose_label(purpose)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'[Npang] {purpose_text} 인증번호: {code}'
    msg['From'] = formataddr((Config.MAIL_FROM_NAME, Config.GMAIL_USER))
    msg['To'] = to_email

    msg.attach(MIMEText(_build_text_body(code, purpose, ttl_minutes), 'plain', 'utf-8'))
    msg.attach(MIMEText(_build_html_body(code, purpose, ttl_minutes), 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as smtp:
            smtp.login(Config.GMAIL_USER, Config.GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        logger.info(f'인증번호 메일 발송 완료: {to_email} ({purpose})')
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f'Gmail SMTP 인증 실패: {e}')
        raise EmailNotConfiguredError(
            'Gmail SMTP 인증에 실패했습니다. 앱 비밀번호를 확인하세요.'
        ) from e
    except Exception as e:
        logger.error(f'메일 발송 실패: {e}')
        raise
