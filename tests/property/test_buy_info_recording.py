"""
Property-based test for buy information recording functionality.

**Feature: stop-loss-averaging-strategy, Property 14: 매수 정보 기록**

Tests that when an initial buy order is executed, the PositionManager records
the buy price and quantity correctly according to requirement 4.1.
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime
from decimal import Decimal

from upbit_trading_bot.strategy.position_manager import PositionManager
from upbit_trading_bot.data.models import StopLossPosition, PositionEntry


# 테스트용 마켓 코드 전략
MARKET_STRATEGY = st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT', 'KRW-LINK', 'KRW-MATIC', 'KRW-SOL', 'KRW-AVAX'])


class TestBuyInfoRecording:
    """매수 정보 기록 속성 테스트"""
    
    @given(
        market=MARKET_STRATEGY,
        price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_initial_buy_records_price_and_quantity(self, market, price, quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 14: 매수 정보 기록**
        
        WHEN 최초 매수가 체결되면 
        THE Position_Manager SHALL 매수 가격과 수량을 기록한다
        
        검증: 요구사항 4.1
        """
        # Given: 포지션 관리자 초기화
        manager = PositionManager()
        
        # When: 최초 매수 포지션 추가
        position = manager.add_initial_position(market, price, quantity)
        
        # Then: 매수 정보가 정확히 기록되어야 함
        assert position is not None
        assert position.market == market
        assert len(position.entries) == 1
        
        entry = position.entries[0]
        assert entry.price == price
        assert entry.quantity == quantity
        assert entry.order_type == 'initial'
        assert isinstance(entry.timestamp, datetime)
        
        # 비용 계산 검증 (소수점 정밀도 고려)
        expected_cost = float(Decimal(str(price)) * Decimal(str(quantity)))
        assert abs(entry.cost - expected_cost) < 0.01
        
        # 포지션 총계 검증
        assert position.total_quantity == quantity
        assert abs(position.total_cost - expected_cost) < 0.01
        assert position.average_price == price
        
        # 포지션이 관리자에 저장되었는지 확인
        retrieved_position = manager.get_position(market)
        assert retrieved_position is not None
        assert retrieved_position.market == market
        assert retrieved_position.total_quantity == quantity
        assert abs(retrieved_position.average_price - price) < 0.01
    
    @given(
        market=MARKET_STRATEGY,
        price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_initial_buy_creates_valid_position_entry(self, market, price, quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 14: 매수 정보 기록**
        
        최초 매수 시 생성되는 PositionEntry가 유효한 데이터를 포함하는지 검증
        """
        # Given: 포지션 관리자 초기화
        manager = PositionManager()
        
        # When: 최초 매수 포지션 추가
        position = manager.add_initial_position(market, price, quantity)
        
        # Then: PositionEntry가 유효해야 함
        entry = position.entries[0]
        assert entry.validate() is True
        
        # 직렬화/역직렬화 테스트
        entry_dict = entry.to_dict()
        restored_entry = PositionEntry.from_dict(entry_dict)
        assert restored_entry.price == entry.price
        assert restored_entry.quantity == entry.quantity
        assert restored_entry.cost == entry.cost
        assert restored_entry.order_type == entry.order_type
    
    @given(
        market=MARKET_STRATEGY,
        price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        quantity=st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_duplicate_initial_position_raises_error(self, market, price, quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 14: 매수 정보 기록**
        
        동일한 마켓에 대해 중복으로 최초 포지션을 생성하려 할 때 오류가 발생하는지 검증
        """
        # Given: 포지션 관리자와 기존 포지션
        manager = PositionManager()
        manager.add_initial_position(market, price, quantity)
        
        # When & Then: 동일한 마켓에 다시 최초 포지션 생성 시 오류 발생
        with pytest.raises(ValueError, match="Position already exists"):
            manager.add_initial_position(market, price * 1.1, quantity * 0.9)
    
    def test_invalid_inputs_raise_errors(self):
        """
        **Feature: stop-loss-averaging-strategy, Property 14: 매수 정보 기록**
        
        잘못된 입력값에 대해 적절한 오류가 발생하는지 검증
        """
        manager = PositionManager()
        
        # 빈 마켓 코드
        with pytest.raises(ValueError, match="Market must be a non-empty string"):
            manager.add_initial_position("", 100.0, 1.0)
        
        # 음수 가격
        with pytest.raises(ValueError, match="Price must be a positive number"):
            manager.add_initial_position("KRW-BTC", -100.0, 1.0)
        
        # 0 가격
        with pytest.raises(ValueError, match="Price must be a positive number"):
            manager.add_initial_position("KRW-BTC", 0.0, 1.0)
        
        # 음수 수량
        with pytest.raises(ValueError, match="Quantity must be a positive number"):
            manager.add_initial_position("KRW-BTC", 100.0, -1.0)
        
        # 0 수량
        with pytest.raises(ValueError, match="Quantity must be a positive number"):
            manager.add_initial_position("KRW-BTC", 100.0, 0.0)