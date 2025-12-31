"""
Property-based tests for first partial sell functionality.

Tests Property 37: 첫 번째 부분 매도
Validates Requirements 9.1
"""

import pytest
from hypothesis import given, strategies as st, assume
from upbit_trading_bot.strategy.partial_sell_manager import PartialSellManager


class TestFirstPartialSell:
    """첫 번째 부분 매도 속성 테스트"""
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_first_partial_sell_at_50_percent_target(self, target_profit, total_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 37: 첫 번째 부분 매도**
        
        모든 포지션에서, 목표 수익률의 50% 도달 시 포지션의 30%가 부분 매도되어야 한다
        **검증: 요구사항 9.1**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 목표 수익률의 50%에 도달
        current_pnl = target_profit * 0.5
        sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 30% 매도 비율이 반환되어야 함
        assert sell_ratio is not None
        assert abs(sell_ratio - 0.3) < 0.001
        
        # And: 매도 수량이 정확히 계산되어야 함
        sell_quantity = manager.calculate_sell_quantity(total_quantity, sell_ratio)
        expected_quantity = total_quantity * 0.3
        assert abs(sell_quantity - expected_quantity) < 0.000001
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
        pnl_ratio=st.floats(min_value=0.49, max_value=0.499, allow_nan=False, allow_infinity=False)
    )
    def test_no_partial_sell_below_50_percent_threshold(self, target_profit, total_quantity, pnl_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 37: 첫 번째 부분 매도**
        
        목표 수익률의 50% 미만에서는 첫 번째 부분 매도가 발생하지 않아야 한다
        **검증: 요구사항 9.1**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 목표 수익률의 50% 미만에 도달
        current_pnl = target_profit * pnl_ratio
        sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 매도 신호가 없어야 함
        assert sell_ratio is None
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
        pnl_ratio=st.floats(min_value=0.5, max_value=0.99, allow_nan=False, allow_infinity=False)
    )
    def test_first_partial_sell_only_once(self, target_profit, total_quantity, pnl_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 37: 첫 번째 부분 매도**
        
        첫 번째 부분 매도는 한 번만 실행되어야 한다
        **검증: 요구사항 9.1**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 목표 수익률의 50% 이상에 처음 도달
        current_pnl = target_profit * pnl_ratio
        first_sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 첫 번째 매도 신호가 있어야 함
        assert first_sell_ratio == 0.3
        
        # When: 같은 수익률에서 다시 확인
        second_sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 두 번째 매도 신호는 없어야 함 (이미 완료됨)
        assert second_sell_ratio is None
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_first_partial_sell_exact_threshold(self, target_profit, total_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 37: 첫 번째 부분 매도**
        
        정확히 목표 수익률의 50%에서 첫 번째 부분 매도가 실행되어야 한다
        **검증: 요구사항 9.1**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 정확히 목표 수익률의 50%에 도달
        current_pnl = target_profit * 0.5
        sell_ratio = manager.should_partial_sell(current_pnl)
        
        # Then: 30% 매도 비율이 반환되어야 함
        assert sell_ratio == 0.3
        
        # And: 매도 수량 계산이 정확해야 함
        sell_quantity = manager.calculate_sell_quantity(total_quantity, sell_ratio)
        expected_quantity = total_quantity * 0.3
        
        # 부동소수점 오차 허용
        assert abs(sell_quantity - expected_quantity) < 0.000001
    
    @given(
        target_profit=st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False),
        total_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
        pnl_ratio=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False)
    )
    def test_first_partial_sell_quantity_never_exceeds_total(self, target_profit, total_quantity, pnl_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 37: 첫 번째 부분 매도**
        
        첫 번째 부분 매도 수량이 총 보유 수량을 초과하지 않아야 한다
        **검증: 요구사항 9.1**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 목표 수익률의 50% 이상에 도달
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
    def test_get_next_sell_level_shows_first_partial_sell(self, target_profit):
        """
        **Feature: stop-loss-averaging-strategy, Property 37: 첫 번째 부분 매도**
        
        초기 상태에서 다음 매도 레벨이 첫 번째 부분 매도를 가리켜야 한다
        **검증: 요구사항 9.1**
        """
        # Given: 부분 매도 관리자 생성
        manager = PartialSellManager(target_profit)
        
        # When: 다음 매도 레벨 조회
        next_level = manager.get_next_sell_level()
        
        # Then: 첫 번째 부분 매도 정보가 반환되어야 함
        assert next_level is not None
        assert next_level['threshold_percent'] == target_profit * 0.5
        assert next_level['sell_ratio'] == 0.3
        assert "50%" in next_level['description']
        assert "30%" in next_level['description']