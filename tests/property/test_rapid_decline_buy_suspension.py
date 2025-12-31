"""
Property-based test for rapid decline buy suspension.

**Feature: stop-loss-averaging-strategy, Property 34: 급락 시 매수 중단**
**Validates: Requirements 8.3**
"""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from typing import List

from upbit_trading_bot.strategy.market_analyzer import MarketAnalyzer
from upbit_trading_bot.data.models import MarketConditions, Ticker
from upbit_trading_bot.data.market_data import MarketData


def create_market_data_with_price_change(price_change_1m: float) -> MarketData:
    """1분간 가격 변화율을 가진 시장 데이터 생성"""
    base_price = 50000000.0
    
    # 1분간 가격 변화를 반영한 가격 히스토리 생성
    # 마지막 두 가격으로 변화율 계산
    previous_price = base_price
    current_price = previous_price * (1 + price_change_1m / 100)
    
    price_history = [base_price + i * 1000 for i in range(18)]  # 18개 기본 가격
    price_history.append(previous_price)  # 19번째: 이전 가격
    price_history.append(current_price)   # 20번째: 현재 가격
    
    ticker = Ticker(
        market="KRW-BTC",
        trade_price=current_price,
        trade_volume=1.5,
        timestamp=datetime.now(),
        change_rate=0.01  # 24시간 변화율 (별도)
    )
    
    market_data = MarketData(
        ticker=ticker,
        orderbook=None,
        timestamp=datetime.now(),
        price_history=price_history
    )
    
    return market_data


@given(
    price_change_1m=st.floats(min_value=-10.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    rapid_decline_threshold=st.floats(min_value=-5.0, max_value=-1.0, allow_nan=False, allow_infinity=False)
)
@settings(max_examples=100)
def test_rapid_decline_buy_suspension_property(price_change_1m: float, rapid_decline_threshold: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 34: 급락 시 매수 중단**
    **Validates: Requirements 8.3**
    
    모든 급락 상황에서, 가격이 임계값 이상 하락하고 있으면 매수 신호 생성이 일시 중단되어야 한다.
    """
    # 부동소수점 정밀도 문제를 피하기 위해 충분한 차이가 있는 경우만 테스트
    if abs(price_change_1m - rapid_decline_threshold) < 0.01:
        return  # 너무 가까운 값은 건너뛰기
    
    # MarketAnalyzer 설정
    config = {
        'rapid_decline_threshold': rapid_decline_threshold,
        'volume_ratio_threshold': 1.0,  # 거래량 조건은 만족하도록 설정
        'market_decline_threshold': -10.0  # 시장 전체 하락 조건은 만족하도록 설정
    }
    analyzer = MarketAnalyzer(config)
    
    # 시장 데이터 생성
    market_data = create_market_data_with_price_change(price_change_1m)
    
    # 시장 상황 분석
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 매수 신호 생성 허용 조건 확인
    should_allow = analyzer.should_allow_buy_signal(market_conditions)
    
    # 실제 계산된 가격 변화율 사용
    actual_price_change = market_conditions.price_change_1m
    
    # 속성 검증: 급락 중이면 매수 신호가 허용되지 않아야 함
    if actual_price_change <= rapid_decline_threshold:
        # 급락 상황에서는 매수 신호가 허용되지 않아야 함
        assert not should_allow, f"급락 중(실제 가격 변화 {actual_price_change}%, 임계값 {rapid_decline_threshold}%)이므로 매수 신호가 허용되지 않아야 함"
        # 급락이 올바르게 감지되었는지 확인
        assert market_conditions.is_rapid_decline, f"급락이 올바르게 감지되어야 함"
    else:
        # 급락이 아닌 상황에서는 급락으로 감지되지 않아야 함
        assert not market_conditions.is_rapid_decline, f"실제 가격 변화 {actual_price_change}%가 임계값 {rapid_decline_threshold}% 초과이므로 급락으로 감지되지 않아야 함"


@given(
    price_change_1m=st.floats(min_value=-10.0, max_value=-2.1)  # 기본 임계값 -2% 이하
)
@settings(max_examples=50)
def test_rapid_decline_always_detected(price_change_1m: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 34: 급락 시 매수 중단**
    **Validates: Requirements 8.3**
    
    기본 설정(-2% 임계값)에서 급락은 항상 감지되어야 한다.
    """
    analyzer = MarketAnalyzer()  # 기본 설정 사용
    
    market_data = create_market_data_with_price_change(price_change_1m)
    
    # 급락 감지 확인
    is_rapid_decline = analyzer.detect_rapid_decline(market_data)
    
    assert is_rapid_decline, f"가격 변화 {price_change_1m}%는 기본 임계값 -2% 이하이므로 급락으로 감지되어야 함"


@given(
    price_change_1m=st.floats(min_value=-1.9, max_value=5.0)  # 기본 임계값 -2% 초과
)
@settings(max_examples=50)
def test_normal_decline_not_detected(price_change_1m: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 34: 급락 시 매수 중단**
    **Validates: Requirements 8.3**
    
    기본 설정(-2% 임계값)에서 정상 범위의 변동은 급락으로 감지되지 않아야 한다.
    """
    analyzer = MarketAnalyzer()  # 기본 설정 사용
    
    market_data = create_market_data_with_price_change(price_change_1m)
    
    # 급락 감지 확인
    is_rapid_decline = analyzer.detect_rapid_decline(market_data)
    
    assert not is_rapid_decline, f"가격 변화 {price_change_1m}%는 기본 임계값 -2% 초과이므로 급락으로 감지되지 않아야 함"


def test_rapid_decline_blocks_buy_signal():
    """
    **Feature: stop-loss-averaging-strategy, Property 34: 급락 시 매수 중단**
    **Validates: Requirements 8.3**
    
    급락이 감지되면 다른 조건이 만족되어도 매수 신호가 차단되어야 한다.
    """
    # 모든 조건을 만족하지만 급락만 발생한 상황 설정
    config = {
        'rapid_decline_threshold': -2.0,
        'volume_ratio_threshold': 1.0,  # 낮은 임계값으로 거래량 조건 만족
        'market_decline_threshold': -10.0,  # 낮은 임계값으로 시장 하락 조건 만족
        'volatility_threshold': 1.0  # 낮은 임계값으로 변동성 조건 만족
    }
    analyzer = MarketAnalyzer(config)
    
    # 급락 상황 (-3% 하락)
    market_data = create_market_data_with_price_change(-3.0)
    
    # 거래량을 높게 설정하여 거래량 조건 만족
    market_data.ticker.trade_volume = 2.0
    
    # 시장 상황 분석
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 매수 신호 생성 허용 조건 확인
    should_allow = analyzer.should_allow_buy_signal(market_conditions)
    
    # 급락으로 인해 매수 신호가 차단되어야 함
    assert not should_allow, "급락 중에는 다른 조건이 만족되어도 매수 신호가 차단되어야 함"
    
    # 급락이 올바르게 감지되었는지 확인
    assert market_conditions.is_rapid_decline, "급락이 올바르게 감지되어야 함"


def test_price_change_calculation_accuracy():
    """
    **Feature: stop-loss-averaging-strategy, Property 34: 급락 시 매수 중단**
    **Validates: Requirements 8.3**
    
    1분간 가격 변화율 계산이 정확해야 한다.
    """
    analyzer = MarketAnalyzer()
    
    # 정확한 가격 변화율로 테스트
    test_cases = [
        (0.0, 0.0),     # 변화 없음
        (-1.0, -1.0),   # 1% 하락
        (-2.5, -2.5),   # 2.5% 하락
        (1.5, 1.5),     # 1.5% 상승
    ]
    
    for price_change, expected_change in test_cases:
        market_data = create_market_data_with_price_change(price_change)
        
        # 직접 계산한 변화율 확인
        calculated_change = analyzer.calculate_price_change_1m(market_data)
        
        # 부동소수점 오차 허용
        assert abs(calculated_change - expected_change) < 0.1, \
            f"가격 변화율 계산 오류: 예상 {expected_change}%, 실제 {calculated_change}%"