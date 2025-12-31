"""
Unit tests for core data models.

Tests the validation, serialization, and deserialization functionality
of the core data models used throughout the trading system.
"""

import pytest
from datetime import datetime
import json

from upbit_trading_bot.data import (
    Ticker, Order, TradingSignal, Position, OrderResult, OrderStatus
)


class TestTicker:
    """Test cases for Ticker data model."""
    
    def test_valid_ticker_creation(self):
        """Test creating a valid ticker."""
        ticker = Ticker(
            market="KRW-BTC",
            trade_price=50000000.0,
            trade_volume=1.5,
            timestamp=datetime.now(),
            change_rate=0.05
        )
        assert ticker.validate() is True
    
    def test_ticker_validation_invalid_market(self):
        """Test ticker validation with invalid market."""
        ticker = Ticker(
            market="",
            trade_price=50000000.0,
            trade_volume=1.5,
            timestamp=datetime.now(),
            change_rate=0.05
        )
        assert ticker.validate() is False
    
    def test_ticker_validation_invalid_price(self):
        """Test ticker validation with invalid price."""
        ticker = Ticker(
            market="KRW-BTC",
            trade_price=-1000.0,
            trade_volume=1.5,
            timestamp=datetime.now(),
            change_rate=0.05
        )
        assert ticker.validate() is False
    
    def test_ticker_serialization_round_trip(self):
        """Test ticker serialization and deserialization."""
        original = Ticker(
            market="KRW-BTC",
            trade_price=50000000.0,
            trade_volume=1.5,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            change_rate=0.05
        )
        
        # Test dict round trip
        data = original.to_dict()
        restored = Ticker.from_dict(data)
        
        assert restored.market == original.market
        assert restored.trade_price == original.trade_price
        assert restored.trade_volume == original.trade_volume
        assert restored.timestamp == original.timestamp
        assert restored.change_rate == original.change_rate
    
    def test_ticker_json_round_trip(self):
        """Test ticker JSON serialization and deserialization."""
        original = Ticker(
            market="KRW-BTC",
            trade_price=50000000.0,
            trade_volume=1.5,
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            change_rate=0.05
        )
        
        json_str = original.to_json()
        restored = Ticker.from_json(json_str)
        
        assert restored.market == original.market
        assert restored.trade_price == original.trade_price
        assert restored.trade_volume == original.trade_volume
        assert restored.timestamp == original.timestamp
        assert restored.change_rate == original.change_rate


class TestOrder:
    """Test cases for Order data model."""
    
    def test_valid_limit_order_creation(self):
        """Test creating a valid limit order."""
        order = Order(
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=50000000.0,
            volume=0.001,
            identifier="test-order-1"
        )
        assert order.validate() is True
    
    def test_valid_market_order_creation(self):
        """Test creating a valid market order."""
        order = Order(
            market="KRW-BTC",
            side="ask",
            ord_type="market",
            price=None,
            volume=0.001
        )
        assert order.validate() is True
    
    def test_order_validation_invalid_side(self):
        """Test order validation with invalid side."""
        order = Order(
            market="KRW-BTC",
            side="invalid",
            ord_type="limit",
            price=50000000.0,
            volume=0.001
        )
        assert order.validate() is False
    
    def test_order_validation_limit_without_price(self):
        """Test order validation for limit order without price."""
        order = Order(
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=None,
            volume=0.001
        )
        assert order.validate() is False
    
    def test_order_serialization_round_trip(self):
        """Test order serialization and deserialization."""
        original = Order(
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=50000000.0,
            volume=0.001,
            identifier="test-order-1"
        )
        
        data = original.to_dict()
        restored = Order.from_dict(data)
        
        assert restored.market == original.market
        assert restored.side == original.side
        assert restored.ord_type == original.ord_type
        assert restored.price == original.price
        assert restored.volume == original.volume
        assert restored.identifier == original.identifier


class TestTradingSignal:
    """Test cases for TradingSignal data model."""
    
    def test_valid_trading_signal_creation(self):
        """Test creating a valid trading signal."""
        signal = TradingSignal(
            market="KRW-BTC",
            action="buy",
            confidence=0.8,
            price=50000000.0,
            volume=0.001,
            strategy_id="sma_crossover",
            timestamp=datetime.now()
        )
        assert signal.validate() is True
    
    def test_trading_signal_validation_invalid_action(self):
        """Test trading signal validation with invalid action."""
        signal = TradingSignal(
            market="KRW-BTC",
            action="hold",
            confidence=0.8,
            price=50000000.0,
            volume=0.001,
            strategy_id="sma_crossover",
            timestamp=datetime.now()
        )
        assert signal.validate() is False
    
    def test_trading_signal_validation_invalid_confidence(self):
        """Test trading signal validation with invalid confidence."""
        signal = TradingSignal(
            market="KRW-BTC",
            action="buy",
            confidence=1.5,  # > 1.0
            price=50000000.0,
            volume=0.001,
            strategy_id="sma_crossover",
            timestamp=datetime.now()
        )
        assert signal.validate() is False
    
    def test_trading_signal_serialization_round_trip(self):
        """Test trading signal serialization and deserialization."""
        original = TradingSignal(
            market="KRW-BTC",
            action="buy",
            confidence=0.8,
            price=50000000.0,
            volume=0.001,
            strategy_id="sma_crossover",
            timestamp=datetime(2023, 1, 1, 12, 0, 0)
        )
        
        data = original.to_dict()
        restored = TradingSignal.from_dict(data)
        
        assert restored.market == original.market
        assert restored.action == original.action
        assert restored.confidence == original.confidence
        assert restored.price == original.price
        assert restored.volume == original.volume
        assert restored.strategy_id == original.strategy_id
        assert restored.timestamp == original.timestamp


class TestPosition:
    """Test cases for Position data model."""
    
    def test_valid_position_creation(self):
        """Test creating a valid position."""
        position = Position(
            market="KRW-BTC",
            avg_buy_price=50000000.0,
            balance=0.001,
            locked=0.0,
            unit_currency="BTC"
        )
        assert position.validate() is True
    
    def test_position_validation_negative_balance(self):
        """Test position validation with negative balance."""
        position = Position(
            market="KRW-BTC",
            avg_buy_price=50000000.0,
            balance=-0.001,
            locked=0.0,
            unit_currency="BTC"
        )
        assert position.validate() is False
    
    def test_position_serialization_round_trip(self):
        """Test position serialization and deserialization."""
        original = Position(
            market="KRW-BTC",
            avg_buy_price=50000000.0,
            balance=0.001,
            locked=0.0,
            unit_currency="BTC"
        )
        
        data = original.to_dict()
        restored = Position.from_dict(data)
        
        assert restored.market == original.market
        assert restored.avg_buy_price == original.avg_buy_price
        assert restored.balance == original.balance
        assert restored.locked == original.locked
        assert restored.unit_currency == original.unit_currency


class TestOrderResult:
    """Test cases for OrderResult data model."""
    
    def test_valid_order_result_creation(self):
        """Test creating a valid order result."""
        result = OrderResult(
            order_id="test-order-123",
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=50000000.0,
            volume=0.001,
            remaining_volume=0.0,
            reserved_fee=500.0,
            remaining_fee=0.0,
            paid_fee=500.0,
            locked=50000.0,
            executed_volume=0.001,
            trades_count=1
        )
        assert result.validate() is True
    
    def test_order_result_validation_negative_volume(self):
        """Test order result validation with negative volume."""
        result = OrderResult(
            order_id="test-order-123",
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=50000000.0,
            volume=-0.001,  # negative
            remaining_volume=0.0,
            reserved_fee=500.0,
            remaining_fee=0.0,
            paid_fee=500.0,
            locked=50000.0,
            executed_volume=0.001,
            trades_count=1
        )
        assert result.validate() is False


class TestOrderStatus:
    """Test cases for OrderStatus data model."""
    
    def test_valid_order_status_creation(self):
        """Test creating a valid order status."""
        status = OrderStatus(
            order_id="test-order-123",
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=50000000.0,
            state="wait",
            volume=0.001,
            remaining_volume=0.001,
            executed_volume=0.0,
            created_at=datetime.now()
        )
        assert status.validate() is True
    
    def test_order_status_validation_invalid_state(self):
        """Test order status validation with invalid state."""
        status = OrderStatus(
            order_id="test-order-123",
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=50000000.0,
            state="invalid",
            volume=0.001,
            remaining_volume=0.001,
            executed_volume=0.0,
            created_at=datetime.now()
        )
        assert status.validate() is False
    
    def test_order_status_serialization_round_trip(self):
        """Test order status serialization and deserialization."""
        original = OrderStatus(
            order_id="test-order-123",
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=50000000.0,
            state="wait",
            volume=0.001,
            remaining_volume=0.001,
            executed_volume=0.0,
            created_at=datetime(2023, 1, 1, 12, 0, 0)
        )
        
        data = original.to_dict()
        restored = OrderStatus.from_dict(data)
        
        assert restored.order_id == original.order_id
        assert restored.market == original.market
        assert restored.side == original.side
        assert restored.ord_type == original.ord_type
        assert restored.price == original.price
        assert restored.state == original.state
        assert restored.volume == original.volume
        assert restored.remaining_volume == original.remaining_volume
        assert restored.executed_volume == original.executed_volume
        assert restored.created_at == original.created_at