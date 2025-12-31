"""
Property-based tests for trailing stop execution functionality.

Tests Property 40: 트레일링 스톱 실행
Validates Requirements 9.4
"""

import pytest
from hypothesis import given, strategies as st, assume
from upbit_trading_bot.strategy.trailing_stop_manager import TrailingStopManager


class TestTrailingStopExecution:
    """트레일링 스톱 실행 속성 테스트"""
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        initial_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_execution_at_trail_percentage(self, target_profit, initial_price, trail_percentage):
        """
        **Feature: stop-loss-averaging-strategy, Property 40: 트레일링 스톱 실행**
        
        모든 트레일링 스톱 활성화 후, 최고점 대비 -1% 하락 시 남은 포지션이 매도되어야 한다
        **검증: 요구사항 9.4**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        manager.activate(initial_price)
        
        # When: 최고점 대비 정확히 트레일링 비율만큼 하락 (부동소수점 오차 고려)
        decline_price = initial_price * (1 - trail_percentage / 100) - 0.001
        should_trigger = manager.should_trigger_stop(decline_price)
        
        # Then: 트레일링 스톱이 실행되어야 함
        assert should_trigger is True
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        initial_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
        decline_ratio=st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False)
    )
    def test_no_trailing_stop_execution_above_trail_percentage(self, target_profit, initial_price, trail_percentage, decline_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 40: 트레일링 스톱 실행**
        
        트레일링 비율 미만의 하락에서는 트레일링 스톱이 실행되지 않아야 한다
        **검증: 요구사항 9.4**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        manager.activate(initial_price)
        
        # When: 트레일링 비율보다 작은 하락 (트레일링 비율의 일부만 하락)
        small_decline_ratio = (trail_percentage / 100) * decline_ratio
        decline_price = initial_price * (1 - small_decline_ratio)
        should_trigger = manager.should_trigger_stop(decline_price)
        
        # Then: 트레일링 스톱이 실행되지 않아야 함
        assert should_trigger is False
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        initial_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        higher_price=st.floats(min_value=1.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_execution_after_high_price_update(self, target_profit, initial_price, higher_price, trail_percentage):
        """
        **Feature: stop-loss-averaging-strategy, Property 40: 트레일링 스톱 실행**
        
        최고가 업데이트 후 새로운 최고점 대비 트레일링 비율만큼 하락 시 실행되어야 한다
        **검증: 요구사항 9.4**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        manager.activate(initial_price)
        
        # When: 더 높은 가격으로 최고가 업데이트
        new_high_price = initial_price * higher_price
        manager.update_high_price(new_high_price)
        
        # Then: 새로운 최고가가 설정되어야 함
        assert manager.get_high_price() == new_high_price
        
        # When: 새로운 최고점 대비 트레일링 비율만큼 하락 (부동소수점 오차 고려)
        decline_price = new_high_price * (1 - trail_percentage / 100) - 0.001
        should_trigger = manager.should_trigger_stop(decline_price)
        
        # Then: 트레일링 스톱이 실행되어야 함
        assert should_trigger is True
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        initial_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_no_trailing_stop_execution_when_not_activated(self, target_profit, initial_price, trail_percentage):
        """
        **Feature: stop-loss-averaging-strategy, Property 40: 트레일링 스톱 실행**
        
        트레일링 스톱이 활성화되지 않은 상태에서는 실행되지 않아야 한다
        **검증: 요구사항 9.4**
        """
        # Given: 트레일링 스톱 관리자 생성 (활성화하지 않음)
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        
        # When: 큰 하락이 발생해도
        decline_price = initial_price * 0.5  # 50% 하락
        should_trigger = manager.should_trigger_stop(decline_price)
        
        # Then: 트레일링 스톱이 실행되지 않아야 함
        assert should_trigger is False
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        initial_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
        excess_decline=st.floats(min_value=1.01, max_value=2.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_execution_below_trail_percentage(self, target_profit, initial_price, trail_percentage, excess_decline):
        """
        **Feature: stop-loss-averaging-strategy, Property 40: 트레일링 스톱 실행**
        
        트레일링 비율을 초과하는 하락에서도 트레일링 스톱이 실행되어야 한다
        **검증: 요구사항 9.4**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        manager.activate(initial_price)
        
        # When: 트레일링 비율을 초과하는 하락
        excess_decline_ratio = (trail_percentage / 100) * excess_decline
        decline_price = initial_price * (1 - excess_decline_ratio)
        should_trigger = manager.should_trigger_stop(decline_price)
        
        # Then: 트레일링 스톱이 실행되어야 함
        assert should_trigger is True
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        initial_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_price_calculation_accuracy(self, target_profit, initial_price, trail_percentage):
        """
        **Feature: stop-loss-averaging-strategy, Property 40: 트레일링 스톱 실행**
        
        트레일링 스톱 가격이 정확히 계산되어야 한다
        **검증: 요구사항 9.4**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        manager.activate(initial_price)
        
        # When: 스톱 가격 조회
        stop_price = manager.get_stop_price()
        
        # Then: 스톱 가격이 정확히 계산되어야 함
        expected_stop_price = initial_price * (1 - trail_percentage / 100)
        assert abs(stop_price - expected_stop_price) < 0.01
        
        # When: 정확히 스톱 가격에서 실행 확인
        should_trigger_at_stop = manager.should_trigger_stop(stop_price)
        
        # Then: 정확히 스톱 가격에서 실행되어야 함
        assert should_trigger_at_stop is True
        
        # When: 스톱 가격보다 약간 높은 가격에서 확인
        slightly_higher = stop_price * 1.001
        should_trigger_higher = manager.should_trigger_stop(slightly_higher)
        
        # Then: 스톱 가격보다 높으면 실행되지 않아야 함
        assert should_trigger_higher is False
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        initial_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        price_increases=st.lists(
            st.floats(min_value=1.01, max_value=1.1, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=5
        ),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_execution_with_multiple_high_updates(self, target_profit, initial_price, price_increases, trail_percentage):
        """
        **Feature: stop-loss-averaging-strategy, Property 40: 트레일링 스톱 실행**
        
        여러 번의 최고가 업데이트 후에도 트레일링 스톱이 정확히 실행되어야 한다
        **검증: 요구사항 9.4**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        manager.activate(initial_price)
        
        # When: 여러 번 가격 상승으로 최고가 업데이트
        current_price = initial_price
        for increase_ratio in price_increases:
            current_price = current_price * increase_ratio
            manager.update_high_price(current_price)
        
        # Then: 최종 최고가가 정확히 설정되어야 함
        final_high = manager.get_high_price()
        assert final_high == current_price
        
        # When: 최종 최고가 대비 트레일링 비율만큼 하락 (부동소수점 오차 고려)
        decline_price = final_high * (1 - trail_percentage / 100) - 0.001
        should_trigger = manager.should_trigger_stop(decline_price)
        
        # Then: 트레일링 스톱이 실행되어야 함
        assert should_trigger is True
        
        # And: 스톱 가격이 최종 최고가 기준으로 계산되어야 함
        expected_stop_price = final_high * (1 - trail_percentage / 100)
        actual_stop_price = manager.get_stop_price()
        assert abs(actual_stop_price - expected_stop_price) < 0.01
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        initial_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        lower_price=st.floats(min_value=0.5, max_value=0.99, allow_nan=False, allow_infinity=False),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_no_update_with_lower_price(self, target_profit, initial_price, lower_price, trail_percentage):
        """
        **Feature: stop-loss-averaging-strategy, Property 40: 트레일링 스톱 실행**
        
        더 낮은 가격으로는 최고가가 업데이트되지 않고 기존 스톱 가격을 유지해야 한다
        **검증: 요구사항 9.4**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        manager.activate(initial_price)
        
        # When: 초기 스톱 가격 저장
        initial_stop_price = manager.get_stop_price()
        
        # And: 더 낮은 가격으로 업데이트 시도
        lower_price_value = initial_price * lower_price
        manager.update_high_price(lower_price_value)
        
        # Then: 최고가가 업데이트되지 않아야 함
        assert manager.get_high_price() == initial_price
        
        # And: 스톱 가격도 변경되지 않아야 함
        assert manager.get_stop_price() == initial_stop_price
        
        # When: 기존 스톱 가격에서 실행 확인
        should_trigger = manager.should_trigger_stop(initial_stop_price)
        
        # Then: 여전히 실행되어야 함
        assert should_trigger is True