"""
Property-based tests for stop loss adjustment functionality.

Tests Property 41: 손절선 조정
Validates Requirements 9.5
"""

import pytest
from hypothesis import given, strategies as st, assume
from upbit_trading_bot.strategy.partial_sell_manager import PartialSellManager


class TestStopLossAdjustment:
    """손절선 조정 속성 테스트"""
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_stop_loss_adjustment_after_first_partial_sell(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 41: 손절선 조정**
        
        모든 부분 매도 완료 후, 남은 포지션의 손절선이 손익분기점으로 조정되어야 한다
        **검증: 요구사항 9.5**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 첫 번째 부분 매도 전 손절선 조정 확인
        should_adjust_before = manager.should_adjust_stop_loss()
        
        # Then: 첫 번째 부분 매도 전에는 손절선 조정이 필요하지 않음
        assert should_adjust_before is False
        
        # When: 첫 번째 부분 매도 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # Then: 첫 번째 부분 매도 후 손절선 조정이 필요해야 함
        should_adjust_after = manager.should_adjust_stop_loss()
        assert should_adjust_after is True
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_stop_loss_adjustment_only_once(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 41: 손절선 조정**
        
        손절선 조정은 한 번만 수행되어야 한다
        **검증: 요구사항 9.5**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # And: 첫 번째 부분 매도 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 손절선 조정 필요 확인
        should_adjust_first = manager.should_adjust_stop_loss()
        assert should_adjust_first is True
        
        # And: 손절선 조정 완료 표시
        manager.mark_stop_loss_adjusted()
        
        # Then: 다시 확인했을 때 손절선 조정이 필요하지 않아야 함
        should_adjust_second = manager.should_adjust_stop_loss()
        assert should_adjust_second is False
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_stop_loss_adjustment_not_needed_without_partial_sell(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 41: 손절선 조정**
        
        부분 매도가 없으면 손절선 조정이 필요하지 않아야 한다
        **검증: 요구사항 9.5**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 부분 매도 없이 손절선 조정 확인
        should_adjust = manager.should_adjust_stop_loss()
        
        # Then: 손절선 조정이 필요하지 않아야 함
        assert should_adjust is False
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_stop_loss_adjustment_after_second_partial_sell(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 41: 손절선 조정**
        
        두 번째 부분 매도 후에는 추가 손절선 조정이 필요하지 않아야 한다
        **검증: 요구사항 9.5**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # And: 첫 번째 부분 매도 완료 및 손절선 조정 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        manager.mark_stop_loss_adjusted()
        
        # When: 두 번째 부분 매도 완료
        second_pnl = target_profit
        second_sell_ratio = manager.should_partial_sell(second_pnl)
        assert second_sell_ratio == 0.5
        
        # Then: 추가 손절선 조정이 필요하지 않아야 함
        should_adjust = manager.should_adjust_stop_loss()
        assert should_adjust is False
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_stop_loss_adjustment_status_in_manager_status(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 41: 손절선 조정**
        
        관리자 상태에서 손절선 조정 상태가 정확히 반영되어야 한다
        **검증: 요구사항 9.5**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 초기 상태 확인
        initial_status = manager.get_status()
        
        # Then: 초기에는 손절선 조정이 완료되지 않았어야 함
        assert initial_status['stop_loss_adjusted'] is False
        
        # When: 첫 번째 부분 매도 완료 후 손절선 조정
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        manager.mark_stop_loss_adjusted()
        
        # Then: 상태에서 손절선 조정 완료가 반영되어야 함
        adjusted_status = manager.get_status()
        assert adjusted_status['stop_loss_adjusted'] is True
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_stop_loss_adjustment_reset_functionality(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 41: 손절선 조정**
        
        관리자 리셋 시 손절선 조정 상태도 초기화되어야 한다
        **검증: 요구사항 9.5**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # And: 첫 번째 부분 매도 완료 및 손절선 조정 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        manager.mark_stop_loss_adjusted()
        
        # When: 관리자 리셋
        manager.reset()
        
        # Then: 손절선 조정 상태가 초기화되어야 함
        should_adjust_after_reset = manager.should_adjust_stop_loss()
        assert should_adjust_after_reset is False
        
        # And: 상태에서도 초기화가 반영되어야 함
        reset_status = manager.get_status()
        assert reset_status['stop_loss_adjusted'] is False
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_remaining_quantity_calculation_after_adjustment(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 41: 손절선 조정**
        
        손절선 조정 후 남은 수량 비율이 정확히 계산되어야 한다
        **검증: 요구사항 9.5**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 첫 번째 부분 매도 완료 (30% 매도)
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # Then: 남은 수량 비율이 70%여야 함
        remaining_ratio = manager.get_remaining_quantity_ratio()
        assert abs(remaining_ratio - 0.7) < 0.001
        
        # When: 손절선 조정 완료
        manager.mark_stop_loss_adjusted()
        
        # Then: 남은 수량 비율은 여전히 70%여야 함
        remaining_ratio_after_adjustment = manager.get_remaining_quantity_ratio()
        assert abs(remaining_ratio_after_adjustment - 0.7) < 0.001