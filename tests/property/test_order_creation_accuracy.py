"""Property-based tests for order creation accuracy.

**Feature: upbit-trading-bot, Property 11: Order Creation Accuracy**
**Validates: Requirements 4.1**
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.order.manager import OrderManager
from upbit_trading_bot.data.models import TradingSignal, Order, Position
from upbit_trading_bot.api.client import UpbitAPIClient


@composite
def valid_trading_signals(draw):
    """Generate valid trading signals for testing."""
    # Generate realistic market names
    base_currencies = ['KRW']
    quote_currencies = ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'XRP', 'LTC']
    
    base = draw(st.sampled_from(base_currencies))
    quote = draw(st.sampled_from(quote_currencies))
    market = f"{base}-{quote}"
    
    # Generate trading signal parameters
    action = draw(st.sampled_from(['buy', 'sell']))
    confidence = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    price = draw(st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False))
    volume = draw(st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False))
    
    # Generate strategy ID
    strategy_id = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_-'),
        min_size=3, max_size=20
    ))
    assume(len(strategy_id.strip()) >= 3)
    
    # Use fixed timestamp to avoid flaky tests
    timestamp = datetime(2025, 1, 1, 12, 0, 0)
    
    return TradingSignal(
        market=market,
        action=action,
        confidence=confidence,
        price=price,
        volume=volume,
        strategy_id=strategy_id,
        timestamp=timestamp
    )


@composite
def invalid_trading_signals(draw):
    """Generate invalid trading signals for negative testing."""
    invalid_type = draw(st.sampled_from([
        'empty_market',
        'invalid_action',
        'negative_confidence',
        'confidence_over_one',
        'negative_price',
        'zero_price',
        'negative_volume',
        'zero_volume',
        'empty_strategy_id'
    ]))
    
    # Start with a valid signal and then break one field
    base_signal = {
        'market': 'KRW-BTC',
        'action': 'buy',
        'confidence': 0.5,
        'price': 50000.0,
        'volume': 0.1,
        'strategy_id': 'test_strategy',
        'timestamp': datetime(2025, 1, 1, 12, 0, 0)  # Fixed timestamp
    }
    
    if invalid_type == 'empty_market':
        base_signal['market'] = ''
    elif invalid_type == 'invalid_action':
        base_signal['action'] = 'invalid_action'
    elif invalid_type == 'negative_confidence':
        base_signal['confidence'] = -0.1
    elif invalid_type == 'confidence_over_one':
        base_signal['confidence'] = 1.1
    elif invalid_type == 'negative_price':
        base_signal['price'] = -100.0
    elif invalid_type == 'zero_price':
        base_signal['price'] = 0.0
    elif invalid_type == 'negative_volume':
        base_signal['volume'] = -0.1
    elif invalid_type == 'zero_volume':
        base_signal['volume'] = 0.0
    elif invalid_type == 'empty_strategy_id':
        base_signal['strategy_id'] = ''
    
    return TradingSignal(**base_signal)


@composite
def mock_account_positions(draw):
    """Generate mock account positions for balance validation."""
    positions = []
    
    # Always include KRW position for buy orders
    krw_balance = draw(st.floats(min_value=0.0, max_value=10000000.0, allow_nan=False, allow_infinity=False))
    krw_locked = draw(st.floats(min_value=0.0, max_value=krw_balance, allow_nan=False, allow_infinity=False))
    
    positions.append(Position(
        market='KRW',
        avg_buy_price=1.0,
        balance=krw_balance,
        locked=krw_locked,
        unit_currency='KRW'
    ))
    
    # Add some crypto positions for sell orders
    crypto_currencies = ['BTC', 'ETH', 'ADA', 'DOT']
    num_cryptos = draw(st.integers(min_value=1, max_value=3))
    
    for _ in range(num_cryptos):
        currency = draw(st.sampled_from(crypto_currencies))
        balance = draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False))
        locked = draw(st.floats(min_value=0.0, max_value=balance, allow_nan=False, allow_infinity=False))
        avg_buy_price = draw(st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False))
        
        positions.append(Position(
            market=currency,
            avg_buy_price=avg_buy_price,
            balance=balance,
            locked=locked,
            unit_currency='KRW'
        ))
    
    return positions


class TestOrderCreationAccuracy:
    """Property-based tests for order creation accuracy."""
    
    @given(signal=valid_trading_signals())
    @settings(max_examples=100)
    def test_property_11_order_creation_accuracy(self, signal):
        """
        **Feature: upbit-trading-bot, Property 11: Order Creation Accuracy**
        **Validates: Requirements 4.1**
        
        Property: For any valid trading signal, the created order should match 
        the signal's market, side, and volume specifications.
        """
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create order from signal
        order = order_manager.create_order(signal)
        
        # Property 1: Order should be created successfully for valid signals
        assert order is not None, "Order should be created for valid trading signal"
        
        # Property 2: Order market should match signal market
        assert order.market == signal.market, f"Order market '{order.market}' should match signal market '{signal.market}'"
        
        # Property 3: Order side should correctly map from signal action
        expected_side = 'bid' if signal.action == 'buy' else 'ask'
        assert order.side == expected_side, f"Order side '{order.side}' should match expected side '{expected_side}' for action '{signal.action}'"
        
        # Property 4: Order volume should match signal volume
        assert order.volume == signal.volume, f"Order volume '{order.volume}' should match signal volume '{signal.volume}'"
        
        # Property 5: Order type should be determined by confidence level
        if signal.confidence > 0.8:
            assert order.ord_type == 'market', f"High confidence signal (confidence={signal.confidence}) should create market order"
            assert order.price is None, "Market orders should not have a price"
        else:
            assert order.ord_type == 'limit', f"Low confidence signal (confidence={signal.confidence}) should create limit order"
            assert order.price == signal.price, f"Limit order price '{order.price}' should match signal price '{signal.price}'"
        
        # Property 6: Order should have valid identifier
        assert order.identifier is not None, "Order should have an identifier"
        assert isinstance(order.identifier, str), "Order identifier should be a string"
        assert signal.strategy_id in order.identifier, "Order identifier should contain strategy ID"
        
        # Property 7: Created order should be valid
        assert order.validate(), "Created order should pass validation"
        
        # Property 8: Order should preserve all required fields from signal
        assert order.market.startswith('KRW-'), "Order should be for KRW market pairs"
        assert order.side in ['bid', 'ask'], "Order side should be valid"
        assert order.ord_type in ['limit', 'market'], "Order type should be valid"
        assert order.volume > 0, "Order volume should be positive"
    
    @given(signal=invalid_trading_signals())
    @settings(max_examples=50)
    def test_invalid_signal_handling(self, signal):
        """Test that invalid trading signals are properly rejected."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Attempt to create order from invalid signal
        order = order_manager.create_order(signal)
        
        # Property: Invalid signals should not create orders
        assert order is None, "Invalid trading signals should not create orders"
    
    @given(signal=valid_trading_signals())
    @settings(max_examples=30)
    def test_order_creation_consistency(self, signal):
        """Test that order creation is consistent for the same signal."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create multiple orders from the same signal
        order1 = order_manager.create_order(signal)
        order2 = order_manager.create_order(signal)
        
        # Property: Both orders should be created successfully
        assert order1 is not None, "First order should be created"
        assert order2 is not None, "Second order should be created"
        
        # Property: Core order properties should be consistent
        assert order1.market == order2.market, "Market should be consistent"
        assert order1.side == order2.side, "Side should be consistent"
        assert order1.ord_type == order2.ord_type, "Order type should be consistent"
        assert order1.volume == order2.volume, "Volume should be consistent"
        
        # Property: Price should be consistent for limit orders
        if order1.ord_type == 'limit':
            assert order1.price == order2.price, "Price should be consistent for limit orders"
        
        # Property: Identifiers should be consistent for same signal (same timestamp)
        # Note: This is expected behavior since identifiers are based on strategy_id + timestamp
        assert order1.identifier == order2.identifier, "Order identifiers should be consistent for same signal"
    
    def test_buy_signal_creates_bid_order(self):
        """Test that buy signals create bid orders."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create buy signal
        buy_signal = TradingSignal(
            market='KRW-BTC',
            action='buy',
            confidence=0.5,
            price=50000.0,
            volume=0.1,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
        
        # Create order
        order = order_manager.create_order(buy_signal)
        
        # Property: Buy signal should create bid order
        assert order is not None, "Buy signal should create an order"
        assert order.side == 'bid', "Buy signal should create bid order"
    
    def test_sell_signal_creates_ask_order(self):
        """Test that sell signals create ask orders."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create sell signal
        sell_signal = TradingSignal(
            market='KRW-BTC',
            action='sell',
            confidence=0.5,
            price=50000.0,
            volume=0.1,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
        
        # Create order
        order = order_manager.create_order(sell_signal)
        
        # Property: Sell signal should create ask order
        assert order is not None, "Sell signal should create an order"
        assert order.side == 'ask', "Sell signal should create ask order"
    
    def test_high_confidence_creates_market_order(self):
        """Test that high confidence signals create market orders."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create high confidence signal
        high_confidence_signal = TradingSignal(
            market='KRW-BTC',
            action='buy',
            confidence=0.9,  # High confidence
            price=50000.0,
            volume=0.1,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
        
        # Create order
        order = order_manager.create_order(high_confidence_signal)
        
        # Property: High confidence should create market order
        assert order is not None, "High confidence signal should create an order"
        assert order.ord_type == 'market', "High confidence signal should create market order"
        assert order.price is None, "Market order should not have price"
    
    def test_low_confidence_creates_limit_order(self):
        """Test that low confidence signals create limit orders."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create low confidence signal
        low_confidence_signal = TradingSignal(
            market='KRW-BTC',
            action='buy',
            confidence=0.3,  # Low confidence
            price=50000.0,
            volume=0.1,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
        
        # Create order
        order = order_manager.create_order(low_confidence_signal)
        
        # Property: Low confidence should create limit order
        assert order is not None, "Low confidence signal should create an order"
        assert order.ord_type == 'limit', "Low confidence signal should create limit order"
        assert order.price == low_confidence_signal.price, "Limit order should have signal price"
    
    @given(signal=valid_trading_signals())
    @settings(max_examples=20)
    def test_order_identifier_format(self, signal):
        """Test that order identifiers follow expected format."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create order
        order = order_manager.create_order(signal)
        
        # Property: Order should have identifier
        assert order is not None, "Order should be created"
        assert order.identifier is not None, "Order should have identifier"
        
        # Property: Identifier should contain strategy ID
        assert signal.strategy_id in order.identifier, "Identifier should contain strategy ID"
        
        # Property: Identifier should contain timestamp component
        identifier_parts = order.identifier.split('_')
        assert len(identifier_parts) >= 2, "Identifier should have at least strategy and timestamp parts"
        
        # Property: Last part should be numeric (timestamp)
        try:
            timestamp_part = int(identifier_parts[-1])
            assert timestamp_part > 0, "Timestamp part should be positive"
        except ValueError:
            pytest.fail("Last part of identifier should be numeric timestamp")
    
    def test_order_creation_exception_handling(self):
        """Test order creation behavior when exceptions occur."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create signal that will cause validation to fail
        invalid_signal = TradingSignal(
            market='',  # Invalid empty market
            action='buy',
            confidence=0.5,
            price=50000.0,
            volume=0.1,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
        
        # Attempt to create order
        order = order_manager.create_order(invalid_signal)
        
        # Property: Exception should be handled gracefully
        assert order is None, "Invalid signal should return None instead of raising exception"
    
    @given(signal=valid_trading_signals())
    @settings(max_examples=20)
    def test_order_validation_after_creation(self, signal):
        """Test that created orders pass validation."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Create order
        order = order_manager.create_order(signal)
        
        # Property: Created order should be valid
        assert order is not None, "Order should be created"
        assert order.validate(), "Created order should pass validation"
        
        # Property: All required fields should be present and valid
        assert order.market, "Order should have market"
        assert order.side in ['bid', 'ask'], "Order should have valid side"
        assert order.ord_type in ['limit', 'market'], "Order should have valid type"
        assert order.volume > 0, "Order should have positive volume"
        
        # Property: Conditional fields should be valid
        if order.ord_type == 'limit':
            assert order.price is not None, "Limit order should have price"
            assert order.price > 0, "Limit order price should be positive"
        else:
            assert order.price is None, "Market order should not have price"