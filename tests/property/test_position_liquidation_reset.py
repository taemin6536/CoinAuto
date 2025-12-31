"""
Property-based test for position liquidation and reset functionality.

**Feature: stop-loss-averaging-strategy, Property 17: 포지션 청산 후 초기화**

Tests that when all positions are liquidated, the PositionManager
initializes the position state correctly according to requirement 4.4.
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime
from decimal import Decimal

from upbit_trading_bot.strategy.position_manager import PositionManager
from upbit_trading_bot.data.models import StopLossPosition, PositionEntry


# 테스트용 마켓 코드 전략
MARKET_STRATEGY = st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT', 'KRW-LINK', 'KRW-MATIC', 'KRW-SOL', 'KRW-AVAX'])


class TestPositionLiquidationReset:
    """포지션 청산 후 초기화 속성 테스트"""
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_complete_liquidation_initializes_position(self, market, buy_price, buy_quantity, sell_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 17: 포지션 청산 후 초기화**
        
        WHEN 모든 포지션이 청산되면 
        THE Position_Manager SHALL 포지션 상태를 초기화한다
        
        검증: 요구사항 4.4
        """
        # Given: 포지션이 있는 포지션 관리자
        manager = PositionManager()
        manager.add_initial_position(market, buy_price, buy_quantity)
        
        # 포지션이 존재하는지 확인
        assert manager.has_position(market) is True
        assert manager.get_position_count() == 1
        
        # When: 전체 수량 매도 (완전 청산)
        liquidated_position = manager.partial_sell(market, buy_quantity, sell_price)
        
        # Then: 포지션이 초기화되어야 함
        assert liquidated_position.total_quantity == 0
        assert liquidated_position.total_cost == 0
        assert liquidated_position.average_price == 0
        
        # 포지션이 관리자에서 제거되었는지 확인
        assert manager.get_position(market) is None
        assert manager.has_position(market) is False
        assert manager.get_position_count() == 0
        
        # 새로운 포지션을 다시 생성할 수 있는지 확인
        new_position = manager.add_initial_position(market, buy_price * 1.1, buy_quantity * 0.9)
        assert new_position is not None
        assert manager.has_position(market) is True
    
    @given(
        market=MARKET_STRATEGY,
        prices=st.lists(
            st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=4
        ),
        quantities=st.lists(
            st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=4
        ),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_averaging_position_complete_liquidation(self, market, prices, quantities, sell_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 17: 포지션 청산 후 초기화**
        
        물타기 포지션이 있는 상태에서 완전 청산 시 초기화되는지 검증
        """
        assume(len(prices) == len(quantities))
        
        # Given: 물타기 포지션이 있는 포지션 관리자
        manager = PositionManager()
        position = manager.add_initial_position(market, prices[0], quantities[0])
        
        for i in range(1, len(prices)):
            position = manager.add_averaging_position(market, prices[i], quantities[i])
        
        total_quantity = position.total_quantity
        entry_count = len(position.entries)
        
        # 포지션이 복잡한 상태인지 확인
        assert entry_count >= 2
        assert total_quantity > 0
        
        # When: 전체 수량 매도
        liquidated_position = manager.partial_sell(market, total_quantity, sell_price)
        
        # Then: 포지션이 완전히 초기화되어야 함
        assert liquidated_position.total_quantity == 0
        assert liquidated_position.total_cost == 0
        assert liquidated_position.average_price == 0
        
        assert manager.get_position(market) is None
        assert manager.has_position(market) is False
        assert manager.get_position_count() == 0
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_close_position_method_initializes_state(self, market, buy_price, buy_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 17: 포지션 청산 후 초기화**
        
        close_position 메서드를 통한 강제 청산 시 초기화되는지 검증
        """
        # Given: 포지션이 있는 포지션 관리자
        manager = PositionManager()
        manager.add_initial_position(market, buy_price, buy_quantity)
        
        assert manager.has_position(market) is True
        assert manager.get_position_count() == 1
        
        # When: 포지션 강제 청산
        result = manager.close_position(market)
        
        # Then: 포지션이 초기화되어야 함
        assert result is True
        assert manager.get_position(market) is None
        assert manager.has_position(market) is False
        assert manager.get_position_count() == 0
    
    @given(
        markets=st.lists(MARKET_STRATEGY, min_size=2, max_size=5, unique=True),
        prices=st.lists(
            st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=5
        ),
        quantities=st.lists(
            st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=5
        )
    )
    def test_multiple_positions_individual_liquidation(self, markets, prices, quantities):
        """
        **Feature: stop-loss-averaging-strategy, Property 17: 포지션 청산 후 초기화**
        
        여러 포지션 중 개별 포지션 청산 시 해당 포지션만 초기화되는지 검증
        """
        assume(len(markets) == len(prices) == len(quantities))
        
        # Given: 여러 포지션이 있는 포지션 관리자
        manager = PositionManager()
        
        for market, price, quantity in zip(markets, prices, quantities):
            manager.add_initial_position(market, price, quantity)
        
        initial_count = len(markets)
        assert manager.get_position_count() == initial_count
        
        # When: 첫 번째 포지션만 청산
        target_market = markets[0]
        target_quantity = quantities[0]
        sell_price = prices[0] * 1.1
        
        liquidated_position = manager.partial_sell(target_market, target_quantity, sell_price)
        
        # Then: 해당 포지션만 초기화되고 다른 포지션은 유지되어야 함
        assert liquidated_position.total_quantity == 0
        assert manager.get_position(target_market) is None
        assert manager.has_position(target_market) is False
        assert manager.get_position_count() == initial_count - 1
        
        # 다른 포지션들은 여전히 존재해야 함
        for i, market in enumerate(markets[1:], 1):
            position = manager.get_position(market)
            assert position is not None
            assert position.total_quantity == quantities[i]
            assert position.average_price == prices[i]
    
    @given(market=MARKET_STRATEGY)
    def test_close_nonexistent_position_returns_false(self, market):
        """
        **Feature: stop-loss-averaging-strategy, Property 17: 포지션 청산 후 초기화**
        
        존재하지 않는 포지션을 청산하려 할 때 False를 반환하는지 검증
        """
        # Given: 빈 포지션 관리자
        manager = PositionManager()
        
        # When: 존재하지 않는 포지션 청산 시도
        result = manager.close_position(market)
        
        # Then: False 반환
        assert result is False
        assert manager.get_position_count() == 0
    
    @given(
        markets=st.lists(MARKET_STRATEGY, min_size=1, max_size=3, unique=True),
        prices=st.lists(
            st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=3
        ),
        quantities=st.lists(
            st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=3
        )
    )
    def test_clear_all_positions_initializes_everything(self, markets, prices, quantities):
        """
        **Feature: stop-loss-averaging-strategy, Property 17: 포지션 청산 후 초기화**
        
        모든 포지션 일괄 청산 시 완전히 초기화되는지 검증
        """
        assume(len(markets) == len(prices) == len(quantities))
        
        # Given: 여러 포지션이 있는 포지션 관리자
        manager = PositionManager()
        
        for market, price, quantity in zip(markets, prices, quantities):
            manager.add_initial_position(market, price, quantity)
        
        assert manager.get_position_count() == len(markets)
        
        # When: 모든 포지션 일괄 청산
        manager.clear_all_positions()
        
        # Then: 모든 포지션이 초기화되어야 함
        assert manager.get_position_count() == 0
        
        for market in markets:
            assert manager.get_position(market) is None
            assert manager.has_position(market) is False
        
        # 빈 딕셔너리 반환 확인
        all_positions = manager.get_all_positions()
        assert len(all_positions) == 0
        assert isinstance(all_positions, dict)
    
    def test_close_position_invalid_inputs(self):
        """
        **Feature: stop-loss-averaging-strategy, Property 17: 포지션 청산 후 초기화**
        
        잘못된 입력값에 대해 적절히 처리하는지 검증
        """
        manager = PositionManager()
        
        # 빈 마켓 코드
        result = manager.close_position("")
        assert result is False
        
        # None 마켓 코드
        result = manager.close_position(None)
        assert result is False