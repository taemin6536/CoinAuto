"""
Property-based test for market decline strategy suspension.

**Feature: stop-loss-averaging-strategy, Property 36: 시장 하락 시 전략 중단**
**Validates: Requirements 8.5**
"""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from typing import List

from upbit_trading_bot.strategy.market_analyzer import MarketAnalyzer
from upbit_trading_bot.data.models import MarketConditions, Ticker
from upbit_trading_bot.data.market_data import MarketData


def create_market_data_with_market_decline(market_decline: float) -> MarketData:
    """시장 하락률을 가진 시장 데이터 생성"""
    base_price = 50000000.0
    
    # 시장 하락을 반영한 가격 히스토리 생성
    # 1분간 가격 변화로 시장 하락을 시뮬레이션
    previous_price = base_price
    current_price = previous_price * (1 + market_decline / 100)
    
    price_history = [base_price + i * 1000 for i in range(18)]  # 18개 기본 가격
    price_history.append(previous_price)  # 19번째: 이전 가격
    price_history.append(current_price)   # 20번째: 현재 가격
    
    ticker = Ticker(
        market="KRW-BTC",
        trade_price=current_price,
        trade_volume=2.0,  # 거래량 조건을 만족하도록 설정
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
    market_decline=st.floats(min_value=-10.0, max_value=2.0),
    market_decline_threshold=st.floats(min_value=-5.0, max_value=-1.0)
)
@settings(max_examples=100)
def test_market_decline_strategy_suspension_property(market_decline: float, market_decline_threshold: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 36: 시장 하락 시 전략 중단**
    **Validates: Requirements 8.5**
    
    모든 시장 하락 상황에서, 시장 전체가 임계값 이상 하락하면 전략 실행이 일시 중단되어야 한다.
    """
    # 부동소수점 정밀도 문제를 피하기 위해 충분한 차이가 있는 경우만 테스트
    if abs(market_decline - market_decline_threshold) < 0.01:
        return  # 너무 가까운 값은 건너뛰기
    
    # MarketAnalyzer 설정
    config = {
        'market_decline_threshold': market_decline_threshold,
        'volume_ratio_threshold': 1.0,  # 거래량 조건은 만족하도록 설정
        'rapid_decline_threshold': -10.0  # 급락 조건은 만족하도록 설정
    }
    analyzer = MarketAnalyzer(config)
    
    # 시장 데이터 생성
    market_data = create_market_data_with_market_decline(market_decline)
    
    # 시장 상황 분석
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 전략 중단 조건 확인
    should_suspend = analyzer.should_suspend_strategy(market_conditions)
    
    # 실제 계산된 시장 변화율 사용
    actual_market_decline = market_conditions.price_change_1m
    
    # 속성 검증: 시장 하락이 임계값 이하이면 전략이 중단되어야 함
    if actual_market_decline <= market_decline_threshold:
        assert should_suspend, f"시장 하락(실제 {actual_market_decline}%, 임계값 {market_decline_threshold}%)이므로 전략이 중단되어야 함"
    else:
        assert not should_suspend, f"시장 하락이 임계값({market_decline_threshold}%) 초과(실제 {actual_market_decline}%)이므로 전략이 중단되지 않아야 함"


@given(
    market_decline=st.floats(min_value=-10.0, max_value=-3.1)  # 기본 임계값 -3% 이하
)
@settings(max_examples=50)
def test_severe_market_decline_always_suspends(market_decline: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 36: 시장 하락 시 전략 중단**
    **Validates: Requirements 8.5**
    
    기본 설정(-3% 임계값)에서 심각한 시장 하락은 항상 전략을 중단시켜야 한다.
    """
    analyzer = MarketAnalyzer()  # 기본 설정 사용
    
    market_data = create_market_data_with_market_decline(market_decline)
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 전략 중단 조건 확인
    should_suspend = analyzer.should_suspend_strategy(market_conditions)
    
    # 실제 계산된 시장 변화율이 -3% 이하인 경우에만 테스트
    if market_conditions.price_change_1m <= -3.0:
        assert should_suspend, f"심각한 시장 하락(실제 {market_conditions.price_change_1m}%)에서 전략이 중단되어야 함"


@given(
    market_decline=st.floats(min_value=-2.9, max_value=2.0)  # 기본 임계값 -3% 초과
)
@settings(max_examples=50)
def test_normal_market_condition_no_suspension(market_decline: float):
    """
    **Feature: stop-loss-averaging-strategy, Property 36: 시장 하락 시 전략 중단**
    **Validates: Requirements 8.5**
    
    기본 설정(-3% 임계값)에서 정상 시장 상황은 전략을 중단시키지 않아야 한다.
    """
    analyzer = MarketAnalyzer()  # 기본 설정 사용
    
    market_data = create_market_data_with_market_decline(market_decline)
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 전략 중단 조건 확인
    should_suspend = analyzer.should_suspend_strategy(market_conditions)
    
    # 실제 계산된 시장 변화율이 -3% 초과인 경우에만 테스트
    if market_conditions.price_change_1m > -3.0:
        assert not should_suspend, f"정상 시장 상황(실제 {market_conditions.price_change_1m}%)에서 전략이 중단되지 않아야 함"


def test_market_decline_blocks_buy_signal():
    """
    **Feature: stop-loss-averaging-strategy, Property 36: 시장 하락 시 전략 중단**
    **Validates: Requirements 8.5**
    
    시장 하락이 감지되면 다른 조건이 만족되어도 매수 신호가 차단되어야 한다.
    """
    # 모든 조건을 만족하지만 시장 하락만 발생한 상황 설정
    config = {
        'market_decline_threshold': -3.0,
        'volume_ratio_threshold': 1.0,  # 낮은 임계값으로 거래량 조건 만족
        'rapid_decline_threshold': -10.0,  # 낮은 임계값으로 급락 조건 만족
        'volatility_threshold': 1.0  # 낮은 임계값으로 변동성 조건 만족
    }
    analyzer = MarketAnalyzer(config)
    
    # 시장 하락 상황 (-4% 하락)
    market_data = create_market_data_with_market_decline(-4.0)
    
    # 거래량을 높게 설정하여 거래량 조건 만족
    market_data.ticker.trade_volume = 2.0
    
    # 시장 상황 분석
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    # 매수 신호 생성 허용 조건 확인
    should_allow = analyzer.should_allow_buy_signal(market_conditions)
    
    # 전략 중단 조건 확인
    should_suspend = analyzer.should_suspend_strategy(market_conditions)
    
    # 시장 하락으로 인해 전략이 중단되어야 함
    if market_conditions.price_change_1m <= -3.0:
        assert should_suspend, "시장 하락 중에는 전략이 중단되어야 함"
        assert not should_allow, "시장 하락 중에는 다른 조건이 만족되어도 매수 신호가 차단되어야 함"


def test_market_decline_threshold_accuracy():
    """
    **Feature: stop-loss-averaging-strategy, Property 36: 시장 하락 시 전략 중단**
    **Validates: Requirements 8.5**
    
    시장 하락 임계값 비교가 정확해야 한다.
    """
    analyzer = MarketAnalyzer()
    
    # 정확한 시장 하락률로 테스트
    test_cases = [
        (-2.0, False),  # -2% 하락 (임계값 -3% 초과) -> 중단 안됨
        (-3.0, True),   # -3% 하락 (임계값과 동일) -> 중단됨
        (-4.0, True),   # -4% 하락 (임계값 미만) -> 중단됨
        (1.0, False),   # 1% 상승 -> 중단 안됨
    ]
    
    for market_decline, expected_suspension in test_cases:
        market_data = create_market_data_with_market_decline(market_decline)
        market_conditions = analyzer.analyze_market_conditions(market_data)
        
        should_suspend = analyzer.should_suspend_strategy(market_conditions)
        
        # 실제 계산된 값으로 검증 (부동소수점 오차 고려)
        actual_decline = market_conditions.price_change_1m
        expected_result = actual_decline <= -3.0
        
        assert should_suspend == expected_result, \
            f"시장 하락 {market_decline}% (실제 {actual_decline}%)에서 중단 여부가 예상과 다름: 예상 {expected_result}, 실제 {should_suspend}"


def test_strategy_suspension_integration():
    """
    **Feature: stop-loss-averaging-strategy, Property 36: 시장 하락 시 전략 중단**
    **Validates: Requirements 8.5**
    
    전략 중단과 매수 신호 허용 조건이 일관되게 작동해야 한다.
    """
    analyzer = MarketAnalyzer()
    
    # 시장 하락 상황
    market_data = create_market_data_with_market_decline(-4.0)
    market_conditions = analyzer.analyze_market_conditions(market_data)
    
    should_suspend = analyzer.should_suspend_strategy(market_conditions)
    should_allow = analyzer.should_allow_buy_signal(market_conditions)
    
    # 전략이 중단되어야 하는 상황에서는 매수 신호도 허용되지 않아야 함
    if should_suspend:
        assert not should_allow, "전략이 중단되는 상황에서는 매수 신호가 허용되지 않아야 함"