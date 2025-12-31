"""
Property-based test for volume condition check.

**Feature: stop-loss-averaging-strategy, Property 33: 거래량 조건 확인**
**Validates: Requirements 8.2**
"""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from typing import List

from upbit_trading_bot.strategy.market_analyzer import MarketAnalyzer
from upbit_trading_bot.data.models import MarketConditions, Ticker
from upbit_trading_bot.data.market_data import MarketData


def create_market_data_with_volume_ratio(volume_ratio: float) -> MarketData:
    """거래량 비율을 가진 시장 데이터 생성"""
    # 기본 거래량을 1.0으로 설정하고, 현재 거래량을 비율에 맞게 조정
    base_volume = 1.0
    current_volume = base_volume * volume_ratio
    
    ticker = Ticker(
        market="KRW-BTC",
        trade_price=50000000.0,
        trade_volume=current_volume,
        timestamp=datetime.now(),
        change_rate=0.01  # 1% 변화
    )
    
    # 기본 가격 히스토리 생성 (거래량 계산을 위해 충분한 데이터)
    price_history = [50000000.0 + i * 1000 for i in range(20)]
    
    market_data = MarketData(
        ticker=ticker,
        orderbook=None,
        timestamp=datetime.now(),
        price_history=price_history
    )
    
    return market_data


@given(
    volume_ratio=st.floats(min_value=0.1, max_value=5.0),
    volume_threshold=st.floats(min_value=1.0, max_value=3.0)
)
@settings(max_examples=100)
def test_volume_condition_check_property(volume_ratio: float, volume_threshold: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 33: 거래량 조건 확인**
    **Validates: Requirements 8.2**
    
    모든 매수 신호 생성에서, 거래량이 평균 거래량의 임계값 이상일 때만 허용되어야 한다.
    """
    # MarketAnalyzer 설정
    config = {'volume_ratio_threshold': volume_threshold}
    analyzer = MarketAnalyzer(config)
    
    # 시장 데이터 생성
    market_data = create_market_data_with_volume_ratio(volume_ratio)
    
    # 시장 상황 분석
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 매수 신호 생성 허용 조건 확인
    should_allow = analyzer.should_allow_buy_signal(market_conditions)
    
    # 속성 검증: 거래량 비율이 임계값 이상이어야 매수 신호 허용
    # (다른 조건들도 만족해야 하므로, 거래량 조건만 확인)
    volume_condition_met = market_conditions.volume_ratio >= volume_threshold
    
    if volume_ratio >= volume_threshold:
        # 거래량 조건은 만족하지만, 다른 조건(급락, 시장 하락)에 따라 결과가 달라질 수 있음
        assert volume_condition_met, f"거래량 비율 {volume_ratio}가 임계값 {volume_threshold} 이상이므로 거래량 조건은 만족해야 함"
    else:
        # 거래량 조건이 만족되지 않으면 매수 신호가 허용되지 않아야 함
        assert not should_allow, f"거래량 비율 {volume_ratio}가 임계값 {volume_threshold} 미만이므로 매수 신호가 허용되지 않아야 함"


@given(
    volume_ratio=st.floats(min_value=1.5, max_value=5.0)  # 기본 임계값 1.5 이상
)
@settings(max_examples=50)
def test_high_volume_meets_condition(volume_ratio: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 33: 거래량 조건 확인**
    **Validates: Requirements 8.2**
    
    기본 설정(1.5배 임계값)에서 높은 거래량은 항상 거래량 조건을 만족해야 한다.
    """
    analyzer = MarketAnalyzer()  # 기본 설정 사용
    
    market_data = create_market_data_with_volume_ratio(volume_ratio)
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 거래량 조건만 확인
    volume_condition_met = market_conditions.volume_ratio >= analyzer.volume_ratio_threshold
    
    assert volume_condition_met, f"거래량 비율 {volume_ratio}는 기본 임계값 1.5 이상이므로 거래량 조건을 만족해야 함"


@given(
    volume_ratio=st.floats(min_value=0.1, max_value=1.4)  # 기본 임계값 1.5 미만
)
@settings(max_examples=50)
def test_low_volume_fails_condition(volume_ratio: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 33: 거래량 조건 확인**
    **Validates: Requirements 8.2**
    
    기본 설정(1.5배 임계값)에서 낮은 거래량은 거래량 조건을 만족하지 않아야 한다.
    """
    analyzer = MarketAnalyzer()  # 기본 설정 사용
    
    market_data = create_market_data_with_volume_ratio(volume_ratio)
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 매수 신호 허용 조건 확인 (거래량 조건 때문에 허용되지 않아야 함)
    should_allow = analyzer.should_allow_buy_signal(market_conditions)
    
    assert not should_allow, f"거래량 비율 {volume_ratio}는 기본 임계값 1.5 미만이므로 매수 신호가 허용되지 않아야 함"


def test_volume_ratio_calculation_accuracy():
    """
    **Feature: stop-loss-averaging-strategy, Property 33: 거래량 조건 확인**
    **Validates: Requirements 8.2**
    
    거래량 비율 계산이 정확해야 한다.
    """
    analyzer = MarketAnalyzer()
    
    # 정확한 거래량 비율로 테스트
    test_cases = [
        (1.0, 1.0),   # 평균과 동일
        (2.0, 2.0),   # 2배
        (0.5, 0.5),   # 절반
        (3.0, 3.0),   # 3배
    ]
    
    for volume_ratio, expected_ratio in test_cases:
        market_data = create_market_data_with_volume_ratio(volume_ratio)
        market_conditions = analyzer.analyze_market_conditions(market_data)
        
        # 부동소수점 오차 허용
        assert abs(market_conditions.volume_ratio - expected_ratio) < 0.1, \
            f"거래량 비율 계산 오류: 예상 {expected_ratio}, 실제 {market_conditions.volume_ratio}"