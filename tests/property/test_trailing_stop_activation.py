"""
Property-based tests for trailing stop activation functionality.

Tests Property 39: 트레일링 스톱 활성화
Validates Requirements 9.3
"""

import pytest
from hypothesis import given, strategies as st, assume
from upbit_trading_bot.strategy.trailing_stop_manager import TrailingStopManager


class TestTrailingStopActivation:
    """트레일링 스톱 활성화 속성 테스트"""
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_activation_at_150_percent_target(self, target_profit, current_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 39: 트레일링 스톱 활성화**
        
        모든 포지션에서, 목표 수익률의 150% 도달 시 트레일링 스톱이 활성화되어야 한다
        **검증: 요구사항 9.3**
        """
        # Given: 트레일링 스톱 관리자 생성 (목표 수익률의 150%에서 활성화, 1% 트레일링)
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, 1.0)
        
        # When: 목표 수익률의 150%에 도달
        current_pnl = activation_profit
        should_activate = manager.should_activate(current_pnl)
        
        # Then: 트레일링 스톱이 활성화되어야 함
        assert should_activate is True
        
        # When: 트레일링 스톱 활성화 실행
        manager.activate(current_price)
        
        # Then: 활성화 상태가 True여야 함
        assert manager.is_activated() is True
        assert manager.get_high_price() == current_price
        assert manager.get_stop_price() is not None
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        pnl_ratio=st.floats(min_value=0.1, max_value=1.49, allow_nan=False, allow_infinity=False)
    )
    def test_no_trailing_stop_activation_below_150_percent(self, target_profit, pnl_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 39: 트레일링 스톱 활성화**
        
        목표 수익률의 150% 미만에서는 트레일링 스톱이 활성화되지 않아야 한다
        **검증: 요구사항 9.3**
        """
        # Given: 트레일링 스톱 관리자 생성
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, 1.0)
        
        # When: 목표 수익률의 150% 미만에 도달
        current_pnl = target_profit * pnl_ratio
        should_activate = manager.should_activate(current_pnl)
        
        # Then: 트레일링 스톱이 활성화되지 않아야 함
        assert should_activate is False
        assert manager.is_activated() is False
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        pnl_ratio=st.floats(min_value=1.5, max_value=3.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_activation_above_150_percent(self, target_profit, current_price, pnl_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 39: 트레일링 스톱 활성화**
        
        목표 수익률의 150% 이상에서는 트레일링 스톱이 활성화되어야 한다
        **검증: 요구사항 9.3**
        """
        # Given: 트레일링 스톱 관리자 생성
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, 1.0)
        
        # When: 목표 수익률의 150% 이상에 도달
        current_pnl = target_profit * pnl_ratio
        should_activate = manager.should_activate(current_pnl)
        
        # Then: 트레일링 스톱이 활성화되어야 함
        assert should_activate is True
        
        # When: 트레일링 스톱 활성화 실행
        manager.activate(current_price)
        
        # Then: 활성화 상태가 True여야 함
        assert manager.is_activated() is True
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_activation_exact_threshold(self, target_profit, current_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 39: 트레일링 스톱 활성화**
        
        정확히 목표 수익률의 150%에서 트레일링 스톱이 활성화되어야 한다
        **검증: 요구사항 9.3**
        """
        # Given: 트레일링 스톱 관리자 생성
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, 1.0)
        
        # When: 정확히 목표 수익률의 150%에 도달
        current_pnl = activation_profit
        should_activate = manager.should_activate(current_pnl)
        
        # Then: 트레일링 스톱이 활성화되어야 함
        assert should_activate is True
        
        # When: 트레일링 스톱 활성화 실행
        manager.activate(current_price)
        
        # Then: 활성화 상태와 초기 설정이 정확해야 함
        assert manager.is_activated() is True
        assert manager.get_high_price() == current_price
        
        # 스톱 가격이 현재 가격의 99% (1% 트레일링)여야 함
        expected_stop_price = current_price * 0.99
        assert abs(manager.get_stop_price() - expected_stop_price) < 0.01
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        trail_percentage=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_activation_with_different_trail_percentages(self, target_profit, current_price, trail_percentage):
        """
        **Feature: stop-loss-averaging-strategy, Property 39: 트레일링 스톱 활성화**
        
        다양한 트레일링 비율에서 트레일링 스톱이 정확히 활성화되어야 한다
        **검증: 요구사항 9.3**
        """
        # Given: 다양한 트레일링 비율로 트레일링 스톱 관리자 생성
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, trail_percentage)
        
        # When: 목표 수익률의 150%에 도달하여 활성화
        current_pnl = activation_profit
        should_activate = manager.should_activate(current_pnl)
        assert should_activate is True
        
        manager.activate(current_price)
        
        # Then: 트레일링 비율에 따른 스톱 가격이 정확해야 함
        expected_stop_price = current_price * (1 - trail_percentage / 100)
        assert abs(manager.get_stop_price() - expected_stop_price) < 0.01
        
        # And: 활성화 상태가 정확해야 함
        assert manager.is_activated() is True
        assert manager.get_high_price() == current_price
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_already_activated_remains_active(self, target_profit, current_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 39: 트레일링 스톱 활성화**
        
        이미 활성화된 트레일링 스톱은 계속 활성화 상태를 유지해야 한다
        **검증: 요구사항 9.3**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, 1.0)
        manager.activate(current_price)
        
        # When: 활성화 후 다시 활성화 조건 확인
        should_activate = manager.should_activate(activation_profit)
        
        # Then: 여전히 활성화 상태여야 함
        assert should_activate is True
        assert manager.is_activated() is True
        
        # When: 수익률이 낮아져도 이미 활성화된 상태는 유지
        lower_pnl = target_profit * 1.0  # 150% 미만
        should_activate_lower = manager.should_activate(lower_pnl)
        
        # Then: 여전히 활성화 상태여야 함
        assert should_activate_lower is True
        assert manager.is_activated() is True
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_activation_status_tracking(self, target_profit, current_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 39: 트레일링 스톱 활성화**
        
        트레일링 스톱 활성화 상태가 정확히 추적되어야 한다
        **검증: 요구사항 9.3**
        """
        # Given: 트레일링 스톱 관리자 생성
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, 1.0)
        
        # When: 초기 상태 확인
        initial_status = manager.get_status()
        
        # Then: 초기에는 비활성화 상태여야 함
        assert initial_status['is_active'] is False
        assert initial_status['high_price'] is None
        assert initial_status['stop_price'] is None
        
        # When: 트레일링 스톱 활성화
        manager.activate(current_price)
        activated_status = manager.get_status()
        
        # Then: 활성화 상태가 정확히 반영되어야 함
        assert activated_status['is_active'] is True
        assert activated_status['high_price'] == current_price
        assert activated_status['stop_price'] is not None
        assert activated_status['activation_profit'] == activation_profit
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_trailing_stop_reset_functionality(self, target_profit, current_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 39: 트레일링 스톱 활성화**
        
        트레일링 스톱 리셋 시 모든 상태가 초기화되어야 한다
        **검증: 요구사항 9.3**
        """
        # Given: 트레일링 스톱 관리자 생성 및 활성화
        activation_profit = target_profit * 1.5
        manager = TrailingStopManager(activation_profit, 1.0)
        manager.activate(current_price)
        
        # When: 활성화 상태 확인
        assert manager.is_activated() is True
        assert manager.get_high_price() is not None
        assert manager.get_stop_price() is not None
        
        # When: 리셋 실행
        manager.reset()
        
        # Then: 모든 상태가 초기화되어야 함
        assert manager.is_activated() is False
        assert manager.get_high_price() is None
        assert manager.get_stop_price() is None
        
        # And: 상태 정보에서도 초기화가 반영되어야 함
        reset_status = manager.get_status()
        assert reset_status['is_active'] is False
        assert reset_status['high_price'] is None
        assert reset_status['stop_price'] is None