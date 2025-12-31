"""
Property-based tests for second partial sell functionality.

Tests Property 38: 두 번째 부분 매도
Validates Requirements 9.2
"""

import pytest
from hypothesis import given, strategies as st, assume
from upbit_trading_bot.strategy.partial_sell_manager import PartialSellManager


class TestSecondPartialSell:
    """두 번째 부분 매도 속성 테스트"""
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_second_partial_sell_at_target_profit(self, target_profit, total_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 38: 두 번째 부분 매도**
        
        모든 포지션에서, 목표 수익률 도달 시 포지션의 50%가 추가 매도되어야 한다
        **검증: 요구사항 9.2**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # And: 첫 번째 부분 매도 완료 (목표 수익률의 50%에서)
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3  # 첫 번째 매도 확인
        
        # When: 목표 수익률에 도달
        current_pnl = target_profit
        sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 50% 매도 비율이 반환되어야 함
        assert sell_ratio is not None
        assert abs(sell_ratio - 0.5) < 0.001
        
        # And: 매도 수량이 정확히 계산되어야 함
        sell_quantity = manager.calculate_sell_quantity(total_quantity, sell_ratio)
        expected_quantity = total_quantity * 0.5
        assert abs(sell_quantity - expected_quantity) < 0.000001
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
        pnl_ratio=st.floats(min_value=0.5, max_value=0.99, allow_nan=False, allow_infinity=False)
    )
    def test_no_second_partial_sell_below_target_profit(self, target_profit, total_quantity, pnl_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 38: 두 번째 부분 매도**
        
        목표 수익률 미만에서는 두 번째 부분 매도가 발생하지 않아야 한다
        **검증: 요구사항 9.2**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # And: 첫 번째 부분 매도 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 목표 수익률 미만에 도달
        current_pnl = target_profit * pnl_ratio
        sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 두 번째 매도 신호가 없어야 함
        assert sell_ratio is None
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
        pnl_ratio=st.floats(min_value=1.0, max_value=2.0, allow_nan=False, allow_infinity=False)
    )
    def test_second_partial_sell_only_once(self, target_profit, total_quantity, pnl_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 38: 두 번째 부분 매도**
        
        두 번째 부분 매도는 한 번만 실행되어야 한다
        **검증: 요구사항 9.2**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # And: 첫 번째 부분 매도 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 목표 수익률 이상에 처음 도달
        current_pnl = target_profit * pnl_ratio
        first_second_sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 두 번째 매도 신호가 있어야 함
        assert first_second_sell_ratio == 0.5
        
        # When: 같은 수익률에서 다시 확인
        second_second_sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 추가 매도 신호는 없어야 함 (이미 완료됨)
        assert second_second_sell_ratio is None
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_second_partial_sell_exact_target_profit(self, target_profit, total_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 38: 두 번째 부분 매도**
        
        정확히 목표 수익률에서 두 번째 부분 매도가 실행되어야 한다
        **검증: 요구사항 9.2**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # And: 첫 번째 부분 매도 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 정확히 목표 수익률에 도달
        current_pnl = target_profit
        sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 50% 매도 비율이 반환되어야 함
        assert sell_ratio == 0.5
        
        # And: 매도 수량 계산이 정확해야 함
        sell_quantity = manager.calculate_sell_quantity(total_quantity, sell_ratio)
        expected_quantity = total_quantity * 0.5
        
        # 부동소수점 오차 허용
        assert abs(sell_quantity - expected_quantity) < 0.000001
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_second_partial_sell_without_first_sell(self, target_profit, total_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 38: 두 번째 부분 매도**
        
        첫 번째 부분 매도 없이 목표 수익률에 도달해도 두 번째 부분 매도가 실행되어야 한다
        **검증: 요구사항 9.2**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 첫 번째 부분 매도 없이 바로 목표 수익률에 도달
        current_pnl = target_profit
        sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 첫 번째 매도 신호가 반환되어야 함 (30%)
        # (내부적으로 첫 번째 레벨이 먼저 처리됨)
        assert sell_ratio == 0.3
        
        # When: 다시 확인
        second_sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 두 번째 매도 신호가 반환되어야 함 (50%)
        assert second_sell_ratio == 0.5
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
        pnl_ratio=st.floats(min_value=1.0, max_value=2.0, allow_nan=False, allow_infinity=False)
    )
    def test_second_partial_sell_quantity_never_exceeds_total(self, target_profit, total_quantity, pnl_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 38: 두 번째 부분 매도**
        
        두 번째 부분 매도 수량이 총 보유 수량을 초과하지 않아야 한다
        **검증: 요구사항 9.2**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # And: 첫 번째 부분 매도 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 목표 수익률 이상에 도달
        current_pnl = target_profit * pnl_ratio
        sell_ratio = manager.should_partial_sell(current_pnl)
        
        if sell_ratio is not None:
            # Then: 매도 수량이 총 수량을 초과하지 않아야 함
            sell_quantity = manager.calculate_sell_quantity(total_quantity, sell_ratio)
            assert sell_quantity <= total_quantity
            assert sell_quantity > 0
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    def test_remaining_quantity_after_both_partial_sells(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 38: 두 번째 부분 매도**
        
        두 번의 부분 매도 후 남은 수량 비율이 정확해야 한다
        **검증: 요구사항 9.2**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 첫 번째 부분 매도 완료
        first_pnl = target_profit * 0.5
        first_sell_ratio = manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # And: 두 번째 부분 매도 완료
        second_pnl = target_profit
        second_sell_ratio = manager.should_partial_sell(second_pnl)
        assert second_sell_ratio == 0.5
        
        # Then: 남은 수량 비율이 20%여야 함 (100% - 30% - 50% = 20%)
        remaining_ratio = manager.get_remaining_quantity_ratio()
        assert abs(remaining_ratio - 0.2) < 0.001