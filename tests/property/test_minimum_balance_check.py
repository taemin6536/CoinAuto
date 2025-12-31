"""
최소 잔고 확인 속성 테스트.

**Feature: stop-loss-averaging-strategy, Property 10: 최소 잔고 확인**
**검증: 요구사항 2.5**

모든 거래 시도에서, 계좌 잔고가 최소 거래 금액 미만이면 거래가 중단되어야 한다.
"""

import pytest
from hypothesis import given, strategies as st, assume
from typing import Dict, Any

from upbit_trading_bot.strategy.risk_controller import RiskController


@st.composite
def balance_scenario_strategy(draw):
    """잔고 시나리오 생성 전략"""
    min_balance_threshold = draw(st.floats(min_value=5000.0, max_value=50000.0))
    min_order_amount = draw(st.floats(min_value=1000.0, max_value=20000.0))
    
    # 효과적인 최소 잔고는 둘 중 큰 값
    effective_min_balance = max(min_balance_threshold, min_order_amount)
    
    # 시나리오 타입: 충분함, 부족함, 경계값
    scenario_type = draw(st.sampled_from(['sufficient', 'insufficient', 'boundary']))
    
    if scenario_type == 'sufficient':
        balance = draw(st.floats(min_value=effective_min_balance * 1.1, max_value=effective_min_balance * 5.0))
    elif scenario_type == 'insufficient':
        balance = draw(st.floats(min_value=0.0, max_value=effective_min_balance * 0.9))
    else:  # boundary
        # 경계값 근처 (±1% 범위)
        boundary_range = effective_min_balance * 0.01
        balance = draw(st.floats(
            min_value=effective_min_balance - boundary_range,
            max_value=effective_min_balance + boundary_range
        ))
    
    return {
        'min_balance_threshold': min_balance_threshold,
        'min_order_amount': min_order_amount,
        'balance': balance,
        'effective_min_balance': effective_min_balance,
        'expected_result': balance >= effective_min_balance
    }


@st.composite
def order_validation_scenario_strategy(draw):
    """주문 검증 시나리오 생성 전략"""
    min_balance_threshold = draw(st.floats(min_value=5000.0, max_value=50000.0))
    available_balance = draw(st.floats(min_value=0.0, max_value=200000.0))
    order_size = draw(st.floats(min_value=0.0, max_value=100000.0))
    
    return {
        'min_balance_threshold': min_balance_threshold,
        'available_balance': available_balance,
        'order_size': order_size
    }


class TestMinimumBalanceCheck:
    """최소 잔고 확인 속성 테스트"""
    
    @given(balance_scenario_strategy())
    def test_minimum_balance_enforcement(self, scenario):
        """
        **Feature: stop-loss-averaging-strategy, Property 10: 최소 잔고 확인**
        **검증: 요구사항 2.5**
        
        모든 거래 시도에서, 계좌 잔고가 최소 거래 금액 미만이면 거래가 중단되어야 한다.
        """
        # Given: 리스크 컨트롤러와 잔고 시나리오
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': scenario['min_balance_threshold']
        }
        risk_controller = RiskController(config)
        
        # When: 계좌 잔고를 확인
        result = risk_controller.check_account_balance(
            scenario['balance'], 
            scenario['min_order_amount']
        )
        
        # Then: 예상된 결과와 일치해야 함
        assert result == scenario['expected_result'], (
            f"최소 잔고 확인 실패: "
            f"잔고 {scenario['balance']:,.0f}, "
            f"임계값 {scenario['min_balance_threshold']:,.0f}, "
            f"최소 주문 금액 {scenario['min_order_amount']:,.0f}, "
            f"효과적 최소 잔고 {scenario['effective_min_balance']:,.0f}, "
            f"예상 결과 {scenario['expected_result']}, "
            f"실제 결과 {result}"
        )
    
    @given(order_validation_scenario_strategy())
    def test_order_size_validation_with_balance_protection(self, scenario):
        """
        주문 크기 검증 시 잔고 보호 확인
        """
        # Given: 리스크 컨트롤러
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': scenario['min_balance_threshold']
        }
        risk_controller = RiskController(config)
        
        # When: 주문 크기를 검증
        validated_size = risk_controller.validate_order_size(
            scenario['order_size'],
            scenario['available_balance']
        )
        
        # Then: 검증된 주문 크기는 잔고 보호를 고려해야 함
        max_usable_balance = max(0.0, scenario['available_balance'] - scenario['min_balance_threshold'])
        
        if scenario['order_size'] <= 0 or scenario['available_balance'] <= 0:
            # 잘못된 입력의 경우 0이어야 함
            assert validated_size == 0.0
        elif max_usable_balance <= 0:
            # 사용 가능한 잔고가 없는 경우 0이어야 함
            assert validated_size == 0.0
        else:
            # 정상적인 경우 최대 사용 가능 잔고를 초과하지 않아야 함
            expected_size = min(scenario['order_size'], max_usable_balance)
            assert validated_size == expected_size, (
                f"주문 크기 검증 실패: "
                f"요청 크기 {scenario['order_size']:,.0f}, "
                f"사용 가능 잔고 {scenario['available_balance']:,.0f}, "
                f"보호 임계값 {scenario['min_balance_threshold']:,.0f}, "
                f"최대 사용 가능 {max_usable_balance:,.0f}, "
                f"예상 크기 {expected_size:,.0f}, "
                f"실제 크기 {validated_size:,.0f}"
            )
    
    @given(st.floats(min_value=5000.0, max_value=50000.0))
    def test_zero_balance_always_insufficient(self, min_balance_threshold):
        """
        잔고가 0인 경우 항상 부족해야 함
        """
        # Given: 리스크 컨트롤러
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': min_balance_threshold
        }
        risk_controller = RiskController(config)
        
        # When: 잔고가 0인 경우 확인
        result = risk_controller.check_account_balance(0.0, 5000.0)
        
        # Then: 항상 False여야 함
        assert result == False, "잔고가 0인 경우 항상 부족해야 함"
    
    @given(st.floats(min_value=5000.0, max_value=50000.0))
    def test_negative_balance_always_insufficient(self, min_balance_threshold):
        """
        음수 잔고인 경우 항상 부족해야 함
        """
        # Given: 리스크 컨트롤러
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': min_balance_threshold
        }
        risk_controller = RiskController(config)
        
        # When: 음수 잔고인 경우 확인
        negative_balance = -1000.0
        result = risk_controller.check_account_balance(negative_balance, 5000.0)
        
        # Then: 항상 False여야 함
        assert result == False, "음수 잔고인 경우 항상 부족해야 함"
    
    @given(
        st.floats(min_value=5000.0, max_value=50000.0),
        st.floats(min_value=100000.0, max_value=1000000.0)
    )
    def test_very_high_balance_always_sufficient(self, min_balance_threshold, high_balance):
        """
        매우 높은 잔고인 경우 항상 충분해야 함
        """
        assume(high_balance > min_balance_threshold * 10)  # 임계값의 10배 이상
        
        # Given: 리스크 컨트롤러
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': min_balance_threshold
        }
        risk_controller = RiskController(config)
        
        # When: 매우 높은 잔고인 경우 확인
        result = risk_controller.check_account_balance(high_balance, 5000.0)
        
        # Then: 항상 True여야 함
        assert result == True, "매우 높은 잔고인 경우 항상 충분해야 함"
    
    @given(st.floats(min_value=5000.0, max_value=50000.0))
    def test_strategy_suspension_on_insufficient_balance(self, min_balance_threshold):
        """
        잔고 부족 시 전략 중단 확인
        """
        # Given: 리스크 컨트롤러
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': min_balance_threshold
        }
        risk_controller = RiskController(config)
        
        # 잔고가 부족한 시장 상황
        market_conditions = {
            'daily_loss': 1000.0,  # 손실 한도 내
            'balance': min_balance_threshold * 0.5,  # 임계값의 절반
            'min_order_amount': 5000.0
        }
        
        # When: 전략 중단 조건을 확인
        should_suspend = risk_controller.should_suspend_strategy(market_conditions)
        
        # Then: 전략이 중단되어야 함
        assert should_suspend == True, (
            f"잔고 부족 시 전략이 중단되어야 함: "
            f"잔고 {market_conditions['balance']:,.0f}, "
            f"임계값 {min_balance_threshold:,.0f}"
        )
    
    @given(st.floats(min_value=0.0, max_value=100000.0))
    def test_zero_or_negative_order_size_validation(self, available_balance):
        """
        0 또는 음수 주문 크기 검증
        """
        # Given: 리스크 컨트롤러
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        # When: 0 또는 음수 주문 크기를 검증
        zero_result = risk_controller.validate_order_size(0.0, available_balance)
        negative_result = risk_controller.validate_order_size(-1000.0, available_balance)
        
        # Then: 모두 0이어야 함
        assert zero_result == 0.0, "0 주문 크기는 0을 반환해야 함"
        assert negative_result == 0.0, "음수 주문 크기는 0을 반환해야 함"


if __name__ == "__main__":
    pytest.main([__file__])