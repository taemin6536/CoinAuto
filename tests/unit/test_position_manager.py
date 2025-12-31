"""
Unit tests for PositionManager class.

Tests the core functionality of position management including average price calculation,
partial sell processing, and position initialization for the stop-loss averaging strategy.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from upbit_trading_bot.strategy.position_manager import PositionManager
from upbit_trading_bot.data.models import StopLossPosition, PositionEntry, OrderResult


class TestPositionManager:
    """포지션 관리자 단위 테스트"""
    
    def setup_method(self):
        """각 테스트 메서드 실행 전 초기화"""
        self.manager = PositionManager()
    
    def test_initial_position_creation(self):
        """최초 포지션 생성 테스트"""
        # Given
        market = "KRW-BTC"
        price = 50000.0
        quantity = 0.1
        
        # When
        position = self.manager.add_initial_position(market, price, quantity)
        
        # Then
        assert position.market == market
        assert position.average_price == price
        assert position.total_quantity == quantity
        assert position.total_cost == price * quantity
        assert len(position.entries) == 1
        assert position.entries[0].order_type == 'initial'
        assert position.entries[0].price == price
        assert position.entries[0].quantity == quantity
    
    def test_averaging_position_calculation(self):
        """물타기 포지션 평균 단가 계산 테스트"""
        # Given
        market = "KRW-ETH"
        initial_price = 3000000.0
        initial_quantity = 0.5
        avg_price = 2700000.0
        avg_quantity = 0.5
        
        self.manager.add_initial_position(market, initial_price, initial_quantity)
        
        # When
        position = self.manager.add_averaging_position(market, avg_price, avg_quantity)
        
        # Then
        expected_total_cost = (initial_price * initial_quantity) + (avg_price * avg_quantity)
        expected_total_quantity = initial_quantity + avg_quantity
        expected_avg_price = expected_total_cost / expected_total_quantity
        
        assert abs(position.total_cost - expected_total_cost) < 0.01
        assert abs(position.total_quantity - expected_total_quantity) < 0.00001
        assert abs(position.average_price - expected_avg_price) < 0.01
        assert len(position.entries) == 2
        assert position.entries[1].order_type == 'averaging'
    
    def test_multiple_averaging_positions(self):
        """여러 번의 물타기 매수 테스트"""
        # Given
        market = "KRW-ADA"
        prices = [1000.0, 900.0, 800.0, 750.0]
        quantities = [100.0, 100.0, 100.0, 100.0]
        
        # When
        position = self.manager.add_initial_position(market, prices[0], quantities[0])
        for i in range(1, len(prices)):
            position = self.manager.add_averaging_position(market, prices[i], quantities[i])
        
        # Then
        expected_total_cost = sum(p * q for p, q in zip(prices, quantities))
        expected_total_quantity = sum(quantities)
        expected_avg_price = expected_total_cost / expected_total_quantity
        
        assert abs(position.total_cost - expected_total_cost) < 0.01
        assert abs(position.total_quantity - expected_total_quantity) < 0.00001
        assert abs(position.average_price - expected_avg_price) < 0.01
        assert len(position.entries) == len(prices)
    
    def test_partial_sell_processing(self):
        """부분 매도 처리 테스트"""
        # Given
        market = "KRW-DOT"
        buy_price = 20000.0
        buy_quantity = 10.0
        sell_quantity = 3.0
        sell_price = 22000.0
        
        self.manager.add_initial_position(market, buy_price, buy_quantity)
        
        # When
        position = self.manager.partial_sell(market, sell_quantity, sell_price)
        
        # Then
        expected_remaining_quantity = buy_quantity - sell_quantity
        expected_remaining_cost = expected_remaining_quantity * buy_price
        
        assert abs(position.total_quantity - expected_remaining_quantity) < 0.00001
        assert abs(position.total_cost - expected_remaining_cost) < 0.01
        assert position.average_price == buy_price  # 평균 단가는 변하지 않음
    
    def test_complete_position_liquidation(self):
        """완전 포지션 청산 테스트"""
        # Given
        market = "KRW-LINK"
        buy_price = 15000.0
        buy_quantity = 5.0
        
        self.manager.add_initial_position(market, buy_price, buy_quantity)
        
        # When
        position = self.manager.partial_sell(market, buy_quantity, buy_price * 1.1)
        
        # Then
        assert position.total_quantity == 0
        assert position.total_cost == 0
        assert position.average_price == 0
        assert self.manager.get_position(market) is None
        assert not self.manager.has_position(market)
    
    def test_position_close_method(self):
        """포지션 강제 청산 메서드 테스트"""
        # Given
        market = "KRW-MATIC"
        self.manager.add_initial_position(market, 1000.0, 100.0)
        
        # When
        result = self.manager.close_position(market)
        
        # Then
        assert result is True
        assert self.manager.get_position(market) is None
        assert not self.manager.has_position(market)
    
    def test_position_pnl_calculation(self):
        """포지션 손익 계산 테스트"""
        # Given
        market = "KRW-SOL"
        buy_price = 100000.0
        buy_quantity = 1.0
        current_price = 110000.0
        
        self.manager.add_initial_position(market, buy_price, buy_quantity)
        
        # When
        pnl_info = self.manager.get_position_pnl(market, current_price)
        
        # Then
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
    
    def test_multiple_positions_management(self):
        """다중 포지션 관리 테스트"""
        # Given
        positions_data = [
            ("KRW-BTC", 50000000.0, 0.1),
            ("KRW-ETH", 3000000.0, 1.0),
            ("KRW-ADA", 1000.0, 1000.0)
        ]
        
        # When
        for market, price, quantity in positions_data:
            self.manager.add_initial_position(market, price, quantity)
        
        # Then
        assert self.manager.get_position_count() == len(positions_data)
        
        all_positions = self.manager.get_all_positions()
        assert len(all_positions) == len(positions_data)
        
        for market, price, quantity in positions_data:
            position = self.manager.get_position(market)
            assert position is not None
            assert position.average_price == price
            assert position.total_quantity == quantity
            assert self.manager.has_position(market)
    
    def test_clear_all_positions(self):
        """모든 포지션 일괄 청산 테스트"""
        # Given
        markets = ["KRW-BTC", "KRW-ETH", "KRW-ADA"]
        for market in markets:
            self.manager.add_initial_position(market, 10000.0, 1.0)
        
        # When
        self.manager.clear_all_positions()
        
        # Then
        assert self.manager.get_position_count() == 0
        for market in markets:
            assert self.manager.get_position(market) is None
            assert not self.manager.has_position(market)
    
    def test_precision_handling(self):
        """소수점 정밀도 처리 테스트"""
        # Given
        market = "KRW-XRP"
        price = 123.456789
        quantity = 0.123456789
        
        # When
        position = self.manager.add_initial_position(market, price, quantity)
        
        # Then
        expected_cost = float(Decimal(str(price)) * Decimal(str(quantity)))
        assert abs(position.total_cost - expected_cost) < 0.01
        assert position.entries[0].validate()
    
    def test_edge_cases(self):
        """엣지 케이스 테스트"""
        # 매우 작은 수량
        position = self.manager.add_initial_position("KRW-TEST1", 1000000.0, 0.00001)
        assert position.total_quantity == 0.00001
        
        # 매우 큰 가격
        position = self.manager.add_initial_position("KRW-TEST2", 999999999.0, 1.0)
        assert position.average_price == 999999999.0
        
        # 매우 작은 부분 매도
        self.manager.add_initial_position("KRW-TEST3", 1000.0, 100.0)
        position = self.manager.partial_sell("KRW-TEST3", 0.00001, 1100.0)
        assert abs(position.total_quantity - 99.99999) < 0.00001
    
    def test_error_conditions(self):
        """오류 조건 테스트"""
        # 중복 최초 포지션 생성
        self.manager.add_initial_position("KRW-BTC", 50000000.0, 0.1)
        with pytest.raises(ValueError, match="Position already exists"):
            self.manager.add_initial_position("KRW-BTC", 51000000.0, 0.1)
        
        # 존재하지 않는 포지션에 물타기
        with pytest.raises(ValueError, match="No existing position found"):
            self.manager.add_averaging_position("KRW-ETH", 3000000.0, 1.0)
        
        # 존재하지 않는 포지션 매도
        with pytest.raises(ValueError, match="No existing position found"):
            self.manager.partial_sell("KRW-ADA", 100.0, 1100.0)
        
        # 보유 수량 초과 매도
        self.manager.add_initial_position("KRW-DOT", 20000.0, 10.0)
        with pytest.raises(ValueError, match="Sell quantity .* exceeds position quantity"):
            self.manager.partial_sell("KRW-DOT", 15.0, 22000.0)
        
        # 잘못된 입력값들
        with pytest.raises(ValueError, match="Market must be a non-empty string"):
            self.manager.add_initial_position("", 10000.0, 1.0)
        
        with pytest.raises(ValueError, match="Price must be a positive number"):
            self.manager.add_initial_position("KRW-TEST", -10000.0, 1.0)
        
        with pytest.raises(ValueError, match="Quantity must be a positive number"):
            self.manager.add_initial_position("KRW-TEST", 10000.0, 0.0)
    
    def test_position_entry_validation(self):
        """포지션 진입 정보 검증 테스트"""
        # Given
        market = "KRW-AVAX"
        price = 25000.0
        quantity = 4.0
        
        # When
        position = self.manager.add_initial_position(market, price, quantity)
        
        # Then
        entry = position.entries[0]
        assert entry.validate()
        assert isinstance(entry.timestamp, datetime)
        assert entry.cost == price * quantity
        
        # 직렬화/역직렬화 테스트
        entry_dict = entry.to_dict()
        restored_entry = PositionEntry.from_dict(entry_dict)
        assert restored_entry.price == entry.price
        assert restored_entry.quantity == entry.quantity
        assert restored_entry.order_type == entry.order_type
    
    def test_position_validation(self):
        """포지션 검증 테스트"""
        # Given
        market = "KRW-ATOM"
        price = 12000.0
        quantity = 8.0
        
        # When
        position = self.manager.add_initial_position(market, price, quantity)
        
        # Then
        assert position.validate()
        
        # 직렬화/역직렬화 테스트
        position_dict = position.to_dict()
        restored_position = StopLossPosition.from_dict(position_dict)
        assert restored_position.market == position.market
        assert restored_position.average_price == position.average_price
        assert restored_position.total_quantity == position.total_quantity
        assert restored_position.validate()
    
    def test_concurrent_operations_simulation(self):
        """동시 작업 시뮬레이션 테스트"""
        # Given
        market = "KRW-NEAR"
        
        # When: 빠른 연속 작업
        self.manager.add_initial_position(market, 5000.0, 10.0)
        self.manager.add_averaging_position(market, 4500.0, 10.0)
        self.manager.partial_sell(market, 5.0, 5500.0)
        self.manager.add_averaging_position(market, 4000.0, 5.0)
        
        # Then
        position = self.manager.get_position(market)
        assert position is not None
        assert len(position.entries) == 3  # 초기 + 2번의 물타기
        assert position.total_quantity == 20.0  # 10 + 10 - 5 + 5
        
        # 평균 단가 검증
        total_cost = (5000.0 * 10.0) + (4500.0 * 10.0) + (4000.0 * 5.0) - (5.0 * ((5000.0 * 10.0 + 4500.0 * 10.0) / 20.0))
        expected_avg_price = total_cost / 20.0
        assert abs(position.average_price - expected_avg_price) < 0.01