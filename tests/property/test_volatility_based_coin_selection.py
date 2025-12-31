"""
Property-based test for volatility-based coin selection.

**Feature: stop-loss-averaging-strategy, Property 32: 변동성 기반 코인 선정**
**Validates: Requirements 8.1**
"""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime, timedelta
from typing import List

from upbit_trading_bot.strategy.market_analyzer import MarketAnalyzer
from upbit_trading_bot.data.models import MarketConditions, Ticker
from upbit_trading_bot.data.market_data import MarketData


def create_market_data_with_volatility(volatility_24h: float) -> MarketData:
    """변동률을 가진 시장 데이터 생성"""
    # change_rate는 소수로 저장되므로 백분율을 소수로 변환
    change_rate = volatility_24h / 100.0
    
    ticker = Ticker(
        market="KRW-BTC",
        trade_price=50000000.0,
        trade_volume=1.5,
        timestamp=datetime.now(),
        change_rate=change_rate
    )
    
    # 기본 가격 히스토리 생성
    price_history = [50000000.0 + i * 1000 for i in range(20)]
    
    market_data = MarketData(
        ticker=ticker,
        orderbook=None,
        timestamp=datetime.now(),
        price_history=price_history
    )
    
    return market_data


@given(
    volatility_24h=st.floats(min_value=0.0, max_value=20.0),
    volatility_threshold=st.floats(min_value=1.0, max_value=10.0)
)
@settings(max_examples=100)
def test_volatility_based_coin_selection_property(volatility_24h: float, volatility_threshold: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 32: 변동성 기반 코인 선정**
    **Validates: Requirements 8.1**
    
    모든 코인에 대해, 24시간 변동률이 임계값 이상이면 우선 거래 대상으로 선정되어야 한다.
    """
    # MarketAnalyzer 설정
    config = {'volatility_threshold': volatility_threshold}
    analyzer = MarketAnalyzer(config)
    
    # 시장 데이터 생성
    market_data = create_market_data_with_volatility(volatility_24h)
    
    # 시장 상황 분석
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 변동성 기반 코인 선정 조건 확인
    should_select = analyzer.should_select_high_volatility_coin(market_conditions)
    
    # 실제 계산된 변동률 사용 (부동소수점 정밀도 문제 해결)
    actual_volatility = market_conditions.volatility_24h
    
    # 속성 검증: 실제 계산된 변동률이 임계값 이상이면 선정되어야 함
    if actual_volatility >= volatility_threshold:
        assert should_select, f"실제 변동률 {actual_volatility}%가 임계값 {volatility_threshold}% 이상이므로 선정되어야 함"
    else:
        assert not should_select, f"실제 변동률 {actual_volatility}%가 임계값 {volatility_threshold}% 미만이므로 선정되지 않아야 함"


@given(
    volatility_24h=st.floats(min_value=5.0, max_value=20.0)  # 기본 임계값 5% 이상
)
@settings(max_examples=50)
def test_high_volatility_always_selected(volatility_24h: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 32: 변동성 기반 코인 선정**
    **Validates: Requirements 8.1**
    
    기본 설정(5% 임계값)에서 높은 변동성 코인은 항상 선정되어야 한다.
    """
    analyzer = MarketAnalyzer()  # 기본 설정 사용
    
    market_data = create_market_data_with_volatility(volatility_24h)
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    should_select = analyzer.should_select_high_volatility_coin(market_conditions)
    
    assert should_select, f"변동률 {volatility_24h}%는 기본 임계값 5% 이상이므로 선정되어야 함"


@given(
    volatility_24h=st.floats(min_value=0.0, max_value=4.9)  # 기본 임계값 5% 미만
)
@settings(max_examples=50)
def test_low_volatility_not_selected(volatility_24h: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 32: 변동성 기반 코인 선정**
    **Validates: Requirements 8.1**
    
    기본 설정(5% 임계값)에서 낮은 변동성 코인은 선정되지 않아야 한다.
    """
    analyzer = MarketAnalyzer()  # 기본 설정 사용
    
    market_data = create_market_data_with_volatility(volatility_24h)
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    should_select = analyzer.should_select_high_volatility_coin(market_conditions)
    
    assert not should_select, f"변동률 {volatility_24h}%는 기본 임계값 5% 미만이므로 선정되지 않아야 함"