import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import requests

from config import Config

logger = logging.getLogger(__name__)

CASH_BUY_SPREADS = {
    'USD': 0.022,
    'JPY': 0.017,
    'EUR': 0.023,
    'GBP': 0.020,
    'CNY': 0.060,
    'HKD': 0.024,
    'AUD': 0.020,
    'CAD': 0.020,
    'CHF': 0.020,
    'SGD': 0.020,
    'THB': 0.050,
    'TWD': 0.050,
    'VND': 0.050,
    'PHP': 0.050,
    'MYR': 0.050,
    'IDR': 0.050,
    'NZD': 0.025,
    'SEK': 0.025,
    'NOK': 0.025,
    'DKK': 0.025,
}
DEFAULT_SPREAD = 0.025

KOREAEXIM_PER_100 = {'JPY(100)', 'IDR(100)', 'VND(100)'}

DEFAULT_FETCH_CURRENCIES = ['USD', 'JPY', 'CNY', 'EUR', 'HKD']

CURRENCY_INFO = {
    'USD': {'name': '달러', 'flag': '🇺🇸'},
    'JPY': {'name': '엔', 'flag': '🇯🇵'},
    'CNY': {'name': '위안', 'flag': '🇨🇳'},
    'EUR': {'name': '유로', 'flag': '🇪🇺'},
    'HKD': {'name': '홍콩달러', 'flag': '🇭🇰'},
    'GBP': {'name': '파운드', 'flag': '🇬🇧'},
    'AUD': {'name': '호주달러', 'flag': '🇦🇺'},
    'CAD': {'name': '캐나다달러', 'flag': '🇨🇦'},
    'CHF': {'name': '스위스프랑', 'flag': '🇨🇭'},
    'SGD': {'name': '싱가포르달러', 'flag': '🇸🇬'},
    'THB': {'name': '바트', 'flag': '🇹🇭'},
    'TWD': {'name': '대만달러', 'flag': '🇹🇼'},
    'VND': {'name': '동', 'flag': '🇻🇳'},
    'PHP': {'name': '페소', 'flag': '🇵🇭'},
}


def _apply_cash_buy_spread(base_rate: float, currency_code: str) -> float:
    spread = CASH_BUY_SPREADS.get(currency_code, DEFAULT_SPREAD)
    return round(base_rate * (1 + spread * 1.005), 2)


def _fetch_from_koreaexim(api_key: str, target_currencies: List[str]) -> Tuple[Dict, str]:
    """한국수출입은행 API에서 매매기준율을 가져와 현찰살때 환율을 계산합니다."""
    for days_back in range(7):
        search_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
        url = 'https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON'
        params = {
            'authkey': api_key,
            'searchdate': search_date,
            'data': 'AP01'
        }

        try:
            resp = requests.get(url, params=params, timeout=15,
                                headers={'Accept-Charset': 'utf-8'})
            data = resp.json()

            if not data or (isinstance(data, dict) and data.get('result') == 2):
                continue

            rates = {}
            for item in data:
                cur_unit = item.get('cur_unit', '')
                base_code = cur_unit.replace('(100)', '').strip()

                if base_code not in target_currencies:
                    continue

                rate_str = item.get('deal_bas_r', '0')
                base_rate = float(rate_str.replace(',', ''))

                if cur_unit in KOREAEXIM_PER_100:
                    base_rate = base_rate / 100

                cash_buy = _apply_cash_buy_spread(base_rate, base_code)
                rates[base_code] = cash_buy

            if rates:
                return rates, f'한국수출입은행 ({search_date[:4]}.{search_date[4:6]}.{search_date[6:]})'

        except Exception as e:
            logger.warning(f'KOREAEXIM API 조회 실패 ({search_date}): {e}')
            continue

    return {}, ''


def _fetch_from_free_api(target_currencies: List[str]) -> Tuple[Dict, str]:
    """무료 환율 API를 폴백으로 사용하여 매매기준율을 가져온 뒤 현찰살때로 변환합니다."""
    try:
        resp = requests.get('https://open.er-api.com/v6/latest/KRW', timeout=15)
        data = resp.json()

        if data.get('result') != 'success':
            return {}, ''

        api_rates = data.get('rates', {})
        rates = {}

        for code in target_currencies:
            if code in api_rates and api_rates[code] > 0:
                base_rate = 1.0 / api_rates[code]
                cash_buy = _apply_cash_buy_spread(base_rate, code)
                rates[code] = cash_buy

        update_str = datetime.now().strftime('%Y.%m.%d')
        return rates, f'ExchangeRate-API ({update_str})'

    except Exception as e:
        logger.warning(f'Free API 조회 실패: {e}')
        return {}, ''


def fetch_exchange_rates(settings: dict) -> dict:
    """환율을 조회하여 현찰살때 기준 환율 딕셔너리를 반환합니다.

    한국수출입은행 API 키는 전역 admin 설정(app_settings)에서 가져옵니다.
    settings 인자는 사용자 트립의 통화 목록(currencies)을 결정하는 데에만 사용됩니다.
    """
    from services.app_settings_service import get_app_settings
    koreaexim_key = (get_app_settings().get('koreaexim_api_key') or '').strip()
    if not koreaexim_key:
        koreaexim_key = os.getenv('KOREAEXIM_API_KEY', '')

    currencies = settings.get('currencies', [])
    target_codes = [c['code'] for c in currencies if not c.get('is_base')]
    for code in DEFAULT_FETCH_CURRENCIES:
        if code not in target_codes:
            target_codes.append(code)

    rates: Dict[str, float] = {}
    source = ''

    if koreaexim_key:
        rates, source = _fetch_from_koreaexim(koreaexim_key, target_codes)

    missing = [c for c in target_codes if c not in rates]
    if missing:
        fallback_rates, fallback_source = _fetch_from_free_api(missing)
        for code, rate in fallback_rates.items():
            if code not in rates:
                rates[code] = rate
        if not source:
            source = fallback_source

    return {
        'rates': rates,
        'source': source or '조회 실패',
        'updated_at': datetime.now().isoformat(),
        'rate_type': '현찰살때 (추정)',
    }


def apply_fetched_rates(settings: dict, fetch_result: dict) -> dict:
    """조회한 환율 결과를 settings에 적용하고 반환합니다."""
    new_rates = fetch_result.get('rates', {})
    if not new_rates:
        return settings

    exchange_rates = settings.get('exchange_rates', {'KRW': 1.0})
    currencies = settings.get('currencies', [])

    existing_codes = {c['code'] for c in currencies}

    for code, rate in new_rates.items():
        exchange_rates[code] = rate
        Config.EXCHANGE_RATES[code] = rate

        if code in existing_codes:
            for curr in currencies:
                if curr['code'] == code:
                    curr['rate'] = rate
                    break
        else:
            info = CURRENCY_INFO.get(code, {'name': code, 'flag': '🏳️'})
            currencies.append({
                'code': code,
                'name': info['name'],
                'flag': info['flag'],
                'rate': rate,
                'is_base': False,
            })

    settings['exchange_rates'] = exchange_rates
    settings['currencies'] = currencies
    settings['exchange_rate_info'] = {
        'source': fetch_result.get('source', ''),
        'updated_at': fetch_result.get('updated_at', ''),
        'rate_type': fetch_result.get('rate_type', ''),
    }

    return settings
