"""
Property-based test for average price recalculation functionality.

**Feature: stop-loss-averaging-strategy, Property 15: 평균 단가 재계산**

Tests that when averaging down buy orders are executed, the PositionManager
recalculates the average price correctly according to requirement 4.2.
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime
from decimal import Decimal

from upbit_trading_bot.strategy.position_manager import PositionManager
from upbit_trading_bot.data.models import StopLossPosition, PositionEntry


# 테스트용 마켓 코드 전략
MARKET_STRATEGY = st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT', 'KRW-LINK', 'KRW-MATIC', 'KRW-SOL', 'KRW-AVAX'])


class TestAveragePriceRecalculation:
    """평균 단가 재계산 속성 테스트"""
    
    @given(
        market=MARKET_STRATEGY,
        initial_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        initial_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
        avg_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        avg_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_averaging_down_recalculates_average_price(self, market, initial_price, initial_quantity, 
                                                     avg_price, avg_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 15: 평균 단가 재계산**
        
        WHEN 물타기 매수가 체결되면 
        THE Position_Manager SHALL 평균 단가를 재계산한다
        
        검증: 요구사항 4.2
        """
        # Given: 최초 포지션이 있는 포지션 관리자
        manager = PositionManager()
        initial_position = manager.add_initial_position(market, initial_price, initial_quantity)
        
        # When: 물타기 매수 추가
        updated_position = manager.add_averaging_position(market, avg_price, avg_quantity)
        
        # Then: 평균 단가가 정확히 재계산되어야 함
        total_cost = (initial_price * initial_quantity) + (avg_price * avg_quantity)
        total_quantity = initial_quantity + avg_quantity
        expected_avg_price = total_cost / total_quantity
        
        assert updated_position is not None
        assert len(updated_position.entries) == 2
        assert updated_position.total_quantity == total_quantity
        assert abs(updated_position.total_cost - total_cost) < 0.01
        assert abs(updated_position.average_price - expected_avg_price) < 0.01
        
        # 첫 번째 진입 정보 확인
        first_entry = updated_position.entries[0]
        assert first_entry.order_type == 'initial'
        assert first_entry.price == initial_price
        assert first_entry.quantity == initial_quantity
        
        # 두 번째 진입 정보 확인
        second_entry = updated_position.entries[1]
        assert second_entry.order_type == 'averaging'
        assert second_entry.price == avg_price
        assert second_entry.quantity == avg_quantity
        
        # 포지션이 업데이트되었는지 확인
        retrieved_position = manager.get_position(market)
        assert retrieved_position.total_quantity == total_quantity
        assert abs(retrieved_position.average_price - expected_avg_price) < 0.01
    
    @given(
        market=MARKET_STRATEGY,
        prices=st.lists(
            st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=5
        ),
        quantities=st.lists(
            st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=5
        )
    )
    def test_multiple_averaging_positions_calculate_correctly(self, market, prices, quantities):
        """
        **Feature: stop-loss-averaging-strategy, Property 15: 평균 단가 재계산**
        
        여러 번의 물타기 매수 시 평균 단가가 정확히 계산되는지 검증
        """
        assume(len(prices) == len(quantities))
        
        # Given: 포지션 관리자
        manager = PositionManager()
        
        # When: 최초 매수 후 여러 번의 물타기 매수
        position = manager.add_initial_position(market, prices[0], quantities[0])
        
        for i in range(1, len(prices)):
            position = manager.add_averaging_position(market, prices[i], quantities[i])
        
        # Then: 최종 평균 단가가 정확해야 함
        total_cost = sum(price * quantity for price, quantity in zip(prices, quantities))
        total_quantity = sum(quantities)
        expected_avg_price = total_cost / total_quantity
        
        assert len(position.entries) == len(prices)
        assert abs(position.total_quantity - total_quantity) < 0.00001
        assert abs(position.total_cost - total_cost) < 0.01
        assert abs(position.average_price - expected_avg_price) < 0.01
        
        # 각 진입 정보 검증
        for i, (price, quantity) in enumerate(zip(prices, quantities)):
            entry = position.entries[i]
            assert entry.price == price
            assert entry.quantity == quantity
            assert entry.order_type == ('initial' if i == 0 else 'averaging')
    
    @given(
        market=MARKET_STRATEGY,
        price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_averaging_without_initial_position_raises_error(self, market, price, quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 15: 평균 단가 재계산**
        
        최초 포지션 없이 물타기 매수를 시도할 때 오류가 발생하는지 검증
        """
        # Given: 빈 포지션 관리자
        manager = PositionManager()
        
        # When & Then: 최초 포지션 없이 물타기 매수 시 오류 발생
        with pytest.raises(ValueError, match="No existing position found"):
            manager.add_averaging_position(market, price, quantity)
    
    @given(
        market=MARKET_STRATEGY,
        initial_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        initial_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False),
        avg_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        avg_quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_averaging_position_entry_is_valid(self, market, initial_price, initial_quantity, 
                                              avg_price, avg_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 15: 평균 단가 재계산**
        
        물타기 매수로 생성되는 PositionEntry가 유효한 데이터를 포함하는지 검증
        """
        # Given: 최초 포지션이 있는 포지션 관리자
        manager = PositionManager()
        manager.add_initial_position(market, initial_price, initial_quantity)
        
        # When: 물타기 매수 추가
        position = manager.add_averaging_position(market, avg_price, avg_quantity)
        
        # Then: 물타기 진입 정보가 유효해야 함
        avg_entry = position.entries[1]  # 두 번째 진입 정보
        assert avg_entry.validate() is True
        assert avg_entry.order_type == 'averaging'
        
        # 직렬화/역직렬화 테스트
        entry_dict = avg_entry.to_dict()
        restored_entry = PositionEntry.from_dict(entry_dict)
        assert restored_entry.price == avg_entry.price
        assert restored_entry.quantity == avg_entry.quantity
        assert restored_entry.order_type == avg_entry.order_type
    
    def test_averaging_invalid_inputs_raise_errors(self):
        """
        **Feature: stop-loss-averaging-strategy, Property 15: 평균 단가 재계산**
        
        물타기 매수 시 잘못된 입력값에 대해 적절한 오류가 발생하는지 검증
        """
        manager = PositionManager()
        manager.add_initial_position("KRW-BTC", 100.0, 1.0)
        
        # 빈 마켓 코드
        with pytest.raises(ValueError, match="Market must be a non-empty string"):
            manager.add_averaging_position("", 90.0, 1.0)
        
        # 음수 가격
        with pytest.raises(ValueError, match="Price must be a positive number"):
            manager.add_averaging_position("KRW-BTC", -90.0, 1.0)
        
        # 0 가격
        with pytest.raises(ValueError, match="Price must be a positive number"):
            manager.add_averaging_position("KRW-BTC", 0.0, 1.0)
        
        # 음수 수량
        with pytest.raises(ValueError, match="Quantity must be a positive number"):
            manager.add_averaging_position("KRW-BTC", 90.0, -1.0)
        
        # 0 수량
        with pytest.raises(ValueError, match="Quantity must be a positive number"):
            manager.add_averaging_position("KRW-BTC", 90.0, 0.0)