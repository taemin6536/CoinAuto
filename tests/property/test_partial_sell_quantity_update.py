"""
Property-based test for partial sell quantity update functionality.

**Feature: stop-loss-averaging-strategy, Property 16: 부분 매도 수량 업데이트**

Tests that when partial sell orders are executed, the PositionManager
updates the remaining position quantity correctly according to requirement 4.3.
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime
from decimal import Decimal

from upbit_trading_bot.strategy.position_manager import PositionManager
from upbit_trading_bot.data.models import StopLossPosition, PositionEntry


# 테스트용 마켓 코드 전략
MARKET_STRATEGY = st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT', 'KRW-LINK', 'KRW-MATIC', 'KRW-SOL', 'KRW-AVAX'])


class TestPartialSellQuantityUpdate:
    """부분 매도 수량 업데이트 속성 테스트"""
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        sell_ratio=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False)
    )
    def test_partial_sell_updates_remaining_quantity(self, market, buy_price, buy_quantity, 
                                                   sell_price, sell_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 16: 부분 매도 수량 업데이트**
        
        WHEN 부분 매도가 발생하면 
        THE Position_Manager SHALL 남은 포지션 수량을 업데이트한다
        
        검증: 요구사항 4.3
        """
        # Given: 포지션이 있는 포지션 관리자
        manager = PositionManager()
        initial_position = manager.add_initial_position(market, buy_price, buy_quantity)
        
        # When: 부분 매도 실행
        sell_quantity = buy_quantity * sell_ratio
        updated_position = manager.partial_sell(market, sell_quantity, sell_price)
        
        # Then: 남은 수량이 정확히 업데이트되어야 함
        expected_remaining_quantity = buy_quantity - sell_quantity
        expected_remaining_cost = expected_remaining_quantity * buy_price
        
        assert updated_position is not None
        assert abs(updated_position.total_quantity - expected_remaining_quantity) < 0.00001
        assert abs(updated_position.total_cost - expected_remaining_cost) < 0.01
        assert updated_position.average_price == buy_price  # 평균 단가는 변하지 않음
        
        # 포지션이 여전히 존재하는지 확인
        retrieved_position = manager.get_position(market)
        assert retrieved_position is not None
        assert abs(retrieved_position.total_quantity - expected_remaining_quantity) < 0.00001
        assert manager.has_position(market) is True
    
    @given(
        market=MARKET_STRATEGY,
        prices=st.lists(
            st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=3
        ),
        quantities=st.lists(
            st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=3
        ),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        sell_ratio=st.floats(min_value=0.1, max_value=0.8, allow_nan=False, allow_infinity=False)
    )
    def test_partial_sell_with_averaging_positions(self, market, prices, quantities, sell_price, sell_ratio):
        """
        **Feature: stop-loss-averaging-strategy, Property 16: 부분 매도 수량 업데이트**
        
        물타기 포지션이 있는 상태에서 부분 매도 시 수량이 정확히 업데이트되는지 검증
        """
        assume(len(prices) == len(quantities))
        
        # Given: 물타기 포지션이 있는 포지션 관리자
        manager = PositionManager()
        position = manager.add_initial_position(market, prices[0], quantities[0])
        
        for i in range(1, len(prices)):
            position = manager.add_averaging_position(market, prices[i], quantities[i])
        
        total_quantity_before = position.total_quantity
        average_price_before = position.average_price
        
        # When: 부분 매도 실행
        sell_quantity = total_quantity_before * sell_ratio
        updated_position = manager.partial_sell(market, sell_quantity, sell_price)
        
        # Then: 남은 수량과 비용이 정확히 계산되어야 함
        expected_remaining_quantity = total_quantity_before - sell_quantity
        expected_remaining_cost = expected_remaining_quantity * average_price_before
        
        assert abs(updated_position.total_quantity - expected_remaining_quantity) < 0.00001
        assert abs(updated_position.total_cost - expected_remaining_cost) < 0.01
        assert abs(updated_position.average_price - average_price_before) < 0.01
        
        # 진입 정보는 변하지 않아야 함
        assert len(updated_position.entries) == len(prices)
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_complete_sell_removes_position(self, market, buy_price, buy_quantity, sell_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 16: 부분 매도 수량 업데이트**
        
        전체 수량을 매도할 때 포지션이 제거되는지 검증
        """
        # Given: 포지션이 있는 포지션 관리자
        manager = PositionManager()
        manager.add_initial_position(market, buy_price, buy_quantity)
        
        # When: 전체 수량 매도
        updated_position = manager.partial_sell(market, buy_quantity, sell_price)
        
        # Then: 포지션이 제거되어야 함
        assert updated_position.total_quantity == 0
        assert updated_position.total_cost == 0
        assert updated_position.average_price == 0
        
        # 포지션이 관리자에서 제거되었는지 확인
        assert manager.get_position(market) is None
        assert manager.has_position(market) is False
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_oversell_raises_error(self, market, buy_price, buy_quantity, sell_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 16: 부분 매도 수량 업데이트**
        
        보유 수량보다 많은 수량을 매도하려 할 때 오류가 발생하는지 검증
        """
        # Given: 포지션이 있는 포지션 관리자
        manager = PositionManager()
        manager.add_initial_position(market, buy_price, buy_quantity)
        
        # When & Then: 보유 수량을 초과하는 매도 시 오류 발생
        oversell_quantity = buy_quantity * 1.1
        with pytest.raises(ValueError, match="Sell quantity .* exceeds position quantity"):
            manager.partial_sell(market, oversell_quantity, sell_price)
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_partial_sell_without_position_raises_error(self, market, buy_price, buy_quantity, sell_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 16: 부분 매도 수량 업데이트**
        
        포지션이 없는 상태에서 매도를 시도할 때 오류가 발생하는지 검증
        """
        # Given: 빈 포지션 관리자
        manager = PositionManager()
        
        # When & Then: 포지션 없이 매도 시 오류 발생
        with pytest.raises(ValueError, match="No existing position found"):
            manager.partial_sell(market, buy_quantity, sell_price)
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        sell_ratios=st.lists(
            st.floats(min_value=0.1, max_value=0.3, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=4
        ),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_multiple_partial_sells_update_correctly(self, market, buy_price, buy_quantity, 
                                                   sell_ratios, sell_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 16: 부분 매도 수량 업데이트**
        
        여러 번의 부분 매도가 정확히 처리되는지 검증
        """
        assume(sum(sell_ratios) < 0.9)  # 전체 매도를 방지
        
        # Given: 포지션이 있는 포지션 관리자
        manager = PositionManager()
        manager.add_initial_position(market, buy_price, buy_quantity)
        
        remaining_quantity = buy_quantity
        
        # When: 여러 번의 부분 매도 실행
        for sell_ratio in sell_ratios:
            sell_quantity = buy_quantity * sell_ratio
            position = manager.partial_sell(market, sell_quantity, sell_price)
            remaining_quantity -= sell_quantity
            
            # Then: 각 매도 후 수량이 정확해야 함
            assert abs(position.total_quantity - remaining_quantity) < 0.00001
            assert position.average_price == buy_price
        
        # 최종 포지션 확인
        final_position = manager.get_position(market)
        assert final_position is not None
        assert abs(final_position.total_quantity - remaining_quantity) < 0.00001
    
    def test_partial_sell_invalid_inputs_raise_errors(self):
        """
        **Feature: stop-loss-averaging-strategy, Property 16: 부분 매도 수량 업데이트**
        
        부분 매도 시 잘못된 입력값에 대해 적절한 오류가 발생하는지 검증
        """
        manager = PositionManager()
        manager.add_initial_position("KRW-BTC", 100.0, 10.0)
        
        # 빈 마켓 코드
        with pytest.raises(ValueError, match="Market must be a non-empty string"):
            manager.partial_sell("", 5.0, 110.0)
        
        # 음수 매도 수량
        with pytest.raises(ValueError, match="Sell quantity must be a positive number"):
            manager.partial_sell("KRW-BTC", -5.0, 110.0)
        
        # 0 매도 수량
        with pytest.raises(ValueError, match="Sell quantity must be a positive number"):
            manager.partial_sell("KRW-BTC", 0.0, 110.0)
        
        # 음수 매도 가격
        with pytest.raises(ValueError, match="Sell price must be a positive number"):
            manager.partial_sell("KRW-BTC", 5.0, -110.0)
        
        # 0 매도 가격
        with pytest.raises(ValueError, match="Sell price must be a positive number"):
            manager.partial_sell("KRW-BTC", 5.0, 0.0)