"""
일일 손실 한도 관리 속성 테스트.

**Feature: stop-loss-averaging-strategy, Property 8: 일일 손실 한도 관리**
**검증: 요구사항 2.3**

모든 일일 거래에서, 누적 손실이 설정된 한도를 초과하면 당일 거래가 중단되어야 한다.
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime, timedelta
from typing import Dict, Any

from upbit_trading_bot.strategy.risk_controller import RiskController, Trade


@st.composite
def risk_config_strategy(draw):
    """리스크 설정 생성 전략"""
    return {
        'daily_loss_limit': draw(st.floats(min_value=1000.0, max_value=50000.0)),
        'consecutive_loss_limit': draw(st.integers(min_value=1, max_value=10)),
        'min_balance_threshold': draw(st.floats(min_value=5000.0, max_value=100000.0))
    }


@st.composite
def daily_loss_scenario_strategy(draw):
    """일일 손실 시나리오 생성 전략"""
    daily_loss_limit = draw(st.floats(min_value=1000.0, max_value=50000.0))
    
    # 한도 내, 한도와 같음, 한도 초과의 세 가지 경우
    loss_type = draw(st.sampled_from(['within_limit', 'at_limit', 'exceeds_limit']))
    
    if loss_type == 'within_limit':
        current_loss = draw(st.floats(min_value=0.0, max_value=daily_loss_limit * 0.99))
    elif loss_type == 'at_limit':
        current_loss = daily_loss_limit
    else:  # exceeds_limit
        current_loss = draw(st.floats(min_value=daily_loss_limit * 1.01, max_value=daily_loss_limit * 2.0))
    
    return {
        'daily_loss_limit': daily_loss_limit,
        'current_loss': current_loss,
        'expected_result': loss_type != 'exceeds_limit'
    }


@st.composite
def market_conditions_strategy(draw):
    """시장 상황 생성 전략"""
    return {
        'daily_loss': draw(st.floats(min_value=0.0, max_value=100000.0)),
        'balance': draw(st.floats(min_value=0.0, max_value=1000000.0)),
        'min_order_amount': draw(st.floats(min_value=1000.0, max_value=10000.0))
    }


class TestDailyLossLimitManagement:
    """일일 손실 한도 관리 속성 테스트"""
    
    @given(daily_loss_scenario_strategy())
    def test_daily_loss_limit_enforcement(self, scenario):
        """
        **Feature: stop-loss-averaging-strategy, Property 8: 일일 손실 한도 관리**
        **검증: 요구사항 2.3**
        
        모든 일일 거래에서, 누적 손실이 설정된 한도를 초과하면 당일 거래가 중단되어야 한다.
        """
        # Given: 리스크 컨트롤러와 손실 시나리오
        config = {
            'daily_loss_limit': scenario['daily_loss_limit'],
            'consecutive_loss_limit': 3,
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        # When: 일일 손실 한도를 확인
        result = risk_controller.check_daily_loss_limit(scenario['current_loss'])
        
        # Then: 예상된 결과와 일치해야 함
        assert result == scenario['expected_result'], (
            f"일일 손실 한도 확인 실패: "
            f"현재 손실 {scenario['current_loss']:,.0f}, "
            f"한도 {scenario['daily_loss_limit']:,.0f}, "
            f"예상 결과 {scenario['expected_result']}, "
            f"실제 결과 {result}"
        )
    
    @given(risk_config_strategy(), market_conditions_strategy())
    def test_strategy_suspension_on_daily_loss_limit(self, config, market_conditions):
        """
        일일 손실 한도 초과 시 전략 중단 확인
        """
        # Given: 리스크 컨트롤러
        risk_controller = RiskController(config)
        
        # 일일 손실이 한도를 초과하는 경우
        market_conditions['daily_loss'] = config['daily_loss_limit'] * 1.5
        
        # When: 전략 중단 조건을 확인
        should_suspend = risk_controller.should_suspend_strategy(market_conditions)
        
        # Then: 전략이 중단되어야 함
        assert should_suspend == True, (
            f"일일 손실 한도 초과 시 전략이 중단되어야 함: "
            f"일일 손실 {market_conditions['daily_loss']:,.0f}, "
            f"한도 {config['daily_loss_limit']:,.0f}"
        )
    
    @given(risk_config_strategy())
    def test_daily_loss_calculation_accuracy(self, config):
        """
        일일 손실 계산의 정확성 확인
        """
        # Given: 리스크 컨트롤러와 거래 기록
        risk_controller = RiskController(config)
        
        # 손실 거래들 생성
        trades = [
            Trade(
                market='KRW-BTC',
                side='sell',
                price=50000000.0,
                quantity=0.001,
                timestamp=datetime.now(),
                is_stop_loss=True,
                pnl=-1000.0
            ),
            Trade(
                market='KRW-ETH',
                side='sell',
                price=3000000.0,
                quantity=0.01,
                timestamp=datetime.now(),
                is_stop_loss=True,
                pnl=-500.0
            )
        ]
        
        # When: 거래를 기록하고 일일 손실을 계산
        for trade in trades:
            risk_controller.record_trade(trade)
        
        daily_loss = risk_controller.get_daily_loss()
        
        # Then: 일일 손실이 정확하게 계산되어야 함
        expected_loss = sum(abs(t.pnl) for t in trades if t.pnl < 0)
        assert daily_loss == expected_loss, (
            f"일일 손실 계산 오류: 예상 {expected_loss}, 실제 {daily_loss}"
        )
    
    @given(st.floats(min_value=1000.0, max_value=50000.0))
    def test_zero_loss_within_limit(self, daily_loss_limit):
        """
        손실이 없는 경우 항상 한도 내에 있어야 함
        """
        # Given: 리스크 컨트롤러
        config = {
            'daily_loss_limit': daily_loss_limit,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        # When: 손실이 0인 경우 확인
        result = risk_controller.check_daily_loss_limit(0.0)
        
        # Then: 항상 True여야 함
        assert result == True, "손실이 0인 경우 항상 한도 내에 있어야 함"
    
    @given(st.floats(min_value=1000.0, max_value=50000.0))
    def test_negative_loss_handling(self, daily_loss_limit):
        """
        음수 손실(이익) 처리 확인
        """
        # Given: 리스크 컨트롤러
        config = {
            'daily_loss_limit': daily_loss_limit,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        # When: 음수 손실(이익)을 확인
        result = risk_controller.check_daily_loss_limit(-1000.0)
        
        # Then: 항상 True여야 함 (이익은 손실 한도에 영향 없음)
        assert result == True, "음수 손실(이익)은 항상 한도 내에 있어야 함"


if __name__ == "__main__":
    pytest.main([__file__])