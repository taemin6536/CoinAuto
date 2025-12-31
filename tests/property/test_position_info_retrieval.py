"""
Property-based test for position information retrieval functionality.

**Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**

Tests that when position information is requested, the PositionManager
returns current average price and total quantity correctly according to requirement 4.5.
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime
from decimal import Decimal

from upbit_trading_bot.strategy.position_manager import PositionManager
from upbit_trading_bot.data.models import StopLossPosition, PositionEntry


# 테스트용 마켓 코드 전략
MARKET_STRATEGY = st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT', 'KRW-LINK', 'KRW-MATIC', 'KRW-SOL', 'KRW-AVAX'])


class TestPositionInfoRetrieval:
    """포지션 정보 반환 속성 테스트"""
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_get_position_returns_current_info(self, market, buy_price, buy_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        WHEN 포지션 정보가 요청되면 
        THE Position_Manager SHALL 현재 평균 단가와 총 수량을 반환한다
        
        검증: 요구사항 4.5
        """
        # Given: 포지션이 있는 포지션 관리자
        manager = PositionManager()
        original_position = manager.add_initial_position(market, buy_price, buy_quantity)
        
        # When: 포지션 정보 요청
        retrieved_position = manager.get_position(market)
        
        # Then: 현재 평균 단가와 총 수량이 정확히 반환되어야 함
        assert retrieved_position is not None
        assert retrieved_position.market == market
        assert retrieved_position.average_price == buy_price
        assert retrieved_position.total_quantity == buy_quantity
        assert abs(retrieved_position.total_cost - (buy_price * buy_quantity)) < 0.01
        
        # 원본 포지션과 동일한 정보인지 확인
        assert retrieved_position.market == original_position.market
        assert retrieved_position.average_price == original_position.average_price
        assert retrieved_position.total_quantity == original_position.total_quantity
        assert retrieved_position.total_cost == original_position.total_cost
    
    @given(
        market=MARKET_STRATEGY,
        prices=st.lists(
            st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=4
        ),
        quantities=st.lists(
            st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=4
        )
    )
    def test_get_position_with_averaging_returns_updated_info(self, market, prices, quantities):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        물타기 후 포지션 정보 요청 시 업데이트된 평균 단가와 총 수량을 반환하는지 검증
        """
        assume(len(prices) == len(quantities))
        
        # Given: 물타기 포지션이 있는 포지션 관리자
        manager = PositionManager()
        position = manager.add_initial_position(market, prices[0], quantities[0])
        
        for i in range(1, len(prices)):
            position = manager.add_averaging_position(market, prices[i], quantities[i])
        
        # 예상 값 계산
        total_cost = sum(price * quantity for price, quantity in zip(prices, quantities))
        total_quantity = sum(quantities)
        expected_avg_price = total_cost / total_quantity
        
        # When: 포지션 정보 요청
        retrieved_position = manager.get_position(market)
        
        # Then: 업데이트된 정보가 정확히 반환되어야 함
        assert retrieved_position is not None
        assert abs(retrieved_position.total_quantity - total_quantity) < 0.00001
        assert abs(retrieved_position.total_cost - total_cost) < 0.01
        assert abs(retrieved_position.average_price - expected_avg_price) < 0.01
        assert len(retrieved_position.entries) == len(prices)
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        sell_ratio=st.floats(min_value=0.1, max_value=0.8, allow_nan=False, allow_infinity=False),
        sell_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_get_position_after_partial_sell_returns_remaining_info(self, market, buy_price, buy_quantity, 
                                                                  sell_ratio, sell_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        부분 매도 후 포지션 정보 요청 시 남은 수량과 평균 단가를 반환하는지 검증
        """
        # Given: 포지션이 있고 부분 매도가 실행된 포지션 관리자
        manager = PositionManager()
        manager.add_initial_position(market, buy_price, buy_quantity)
        
        sell_quantity = buy_quantity * sell_ratio
        manager.partial_sell(market, sell_quantity, sell_price)
        
        expected_remaining_quantity = buy_quantity - sell_quantity
        
        # When: 포지션 정보 요청
        retrieved_position = manager.get_position(market)
        
        # Then: 남은 수량과 평균 단가가 정확히 반환되어야 함
        assert retrieved_position is not None
        assert abs(retrieved_position.total_quantity - expected_remaining_quantity) < 0.00001
        assert retrieved_position.average_price == buy_price  # 평균 단가는 변하지 않음
        assert abs(retrieved_position.total_cost - (expected_remaining_quantity * buy_price)) < 0.01
    
    @given(market=MARKET_STRATEGY)
    def test_get_nonexistent_position_returns_none(self, market):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        존재하지 않는 포지션 정보 요청 시 None을 반환하는지 검증
        """
        # Given: 빈 포지션 관리자
        manager = PositionManager()
        
        # When: 존재하지 않는 포지션 정보 요청
        retrieved_position = manager.get_position(market)
        
        # Then: None 반환
        assert retrieved_position is None
    
    @given(
        markets=st.lists(MARKET_STRATEGY, min_size=1, max_size=5, unique=True),
        prices=st.lists(
            st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=5
        ),
        quantities=st.lists(
            st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=5
        )
    )
    def test_get_all_positions_returns_complete_info(self, markets, prices, quantities):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        모든 포지션 정보 요청 시 완전한 정보를 반환하는지 검증
        """
        assume(len(markets) == len(prices) == len(quantities))
        
        # Given: 여러 포지션이 있는 포지션 관리자
        manager = PositionManager()
        
        for market, price, quantity in zip(markets, prices, quantities):
            manager.add_initial_position(market, price, quantity)
        
        # When: 모든 포지션 정보 요청
        all_positions = manager.get_all_positions()
        
        # Then: 모든 포지션 정보가 정확히 반환되어야 함
        assert len(all_positions) == len(markets)
        assert isinstance(all_positions, dict)
        
        for i, market in enumerate(markets):
            position = all_positions[market]
            assert position is not None
            assert position.market == market
            assert position.average_price == prices[i]
            assert position.total_quantity == quantities[i]
            assert abs(position.total_cost - (prices[i] * quantities[i])) < 0.01
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_get_position_pnl_returns_correct_calculation(self, market, buy_price, buy_quantity, current_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        포지션 손익 정보 요청 시 정확한 계산 결과를 반환하는지 검증
        """
        # Given: 포지션이 있는 포지션 관리자
        manager = PositionManager()
        manager.add_initial_position(market, buy_price, buy_quantity)
        
        # When: 포지션 손익 정보 요청
        pnl_info = manager.get_position_pnl(market, current_price)
        
        # Then: 정확한 손익 계산 결과가 반환되어야 함
        assert pnl_info is not None
        
        expected_current_value = current_price * buy_quantity
        expected_total_cost = buy_price * buy_quantity
        expected_pnl = expected_current_value - expected_total_cost
        expected_pnl_rate = (expected_pnl / expected_total_cost) * 100
        
        assert abs(pnl_info['current_value'] - expected_current_value) < 0.01
        assert abs(pnl_info['total_cost'] - expected_total_cost) < 0.01
        assert abs(pnl_info['pnl'] - expected_pnl) < 0.01
        assert abs(pnl_info['pnl_rate'] - expected_pnl_rate) < 0.01
        assert pnl_info['average_price'] == buy_price
        assert pnl_info['current_price'] == current_price
    
    @given(
        market=MARKET_STRATEGY,
        current_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
    )
    def test_get_pnl_for_nonexistent_position_returns_none(self, market, current_price):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        존재하지 않는 포지션의 손익 정보 요청 시 None을 반환하는지 검증
        """
        # Given: 빈 포지션 관리자
        manager = PositionManager()
        
        # When: 존재하지 않는 포지션의 손익 정보 요청
        pnl_info = manager.get_position_pnl(market, current_price)
        
        # Then: None 반환
        assert pnl_info is None
    
    @given(
        market=MARKET_STRATEGY,
        buy_price=st.floats(min_value=10.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        buy_quantity=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    def test_has_position_returns_correct_status(self, market, buy_price, buy_quantity):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        포지션 존재 여부 확인이 정확한 결과를 반환하는지 검증
        """
        # Given: 포지션 관리자
        manager = PositionManager()
        
        # When & Then: 포지션 생성 전에는 False
        assert manager.has_position(market) is False
        
        # When: 포지션 생성
        manager.add_initial_position(market, buy_price, buy_quantity)
        
        # Then: 포지션 생성 후에는 True
        assert manager.has_position(market) is True
        
        # When: 포지션 청산
        manager.close_position(market)
        
        # Then: 포지션 청산 후에는 False
        assert manager.has_position(market) is False
    
    @given(
        count=st.integers(min_value=0, max_value=3)
    )
    def test_get_position_count_returns_correct_number(self, count):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        포지션 개수 조회가 정확한 결과를 반환하는지 검증
        """
        # Given: 포지션 관리자
        manager = PositionManager()
        
        # When & Then: 초기에는 0개
        assert manager.get_position_count() == 0
        
        # When: 지정된 개수만큼 포지션들 생성
        markets = ['KRW-BTC', 'KRW-ETH', 'KRW-ADA'][:count]
        for i, market in enumerate(markets):
            manager.add_initial_position(market, 10000.0 * (i + 1), 1.0)
        
        # Then: 생성된 포지션 수와 일치
        assert manager.get_position_count() == count
        
        # When: 일부 포지션 청산
        if count > 0:
            manager.close_position(markets[0])
            expected_count = count - 1
            assert manager.get_position_count() == expected_count
    
    def test_get_position_invalid_inputs(self):
        """
        **Feature: stop-loss-averaging-strategy, Property 18: 포지션 정보 반환**
        
        잘못된 입력값에 대해 적절히 처리하는지 검증
        """
        manager = PositionManager()
        manager.add_initial_position("KRW-BTC", 100.0, 1.0)
        
        # 빈 마켓 코드
        assert manager.get_position("") is None
        assert manager.has_position("") is False
        
        # None 마켓 코드
        assert manager.get_position(None) is None
        assert manager.has_position(None) is False
        
        # 손익 계산 시 잘못된 현재 가격
        assert manager.get_position_pnl("KRW-BTC", -100.0) is None
        assert manager.get_position_pnl("KRW-BTC", 0.0) is None