"""Property-based tests for order retry behavior.

**Feature: upbit-trading-bot, Property 13: Order Retry Behavior**
**Validates: Requirements 4.3**
"""

import pytest
import time
from datetime import datetime
from unittest.mock import Mock, patch, call
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.order.manager import OrderManager
from upbit_trading_bot.data.models import Order, OrderResult, Position
from upbit_trading_bot.api.client import UpbitAPIClient, UpbitAPIError


@composite
def valid_orders(draw):
    """Generate valid orders for testing."""
    # Generate realistic market names
    base_currencies = ['KRW']
    quote_currencies = ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'XRP', 'LTC']
    
    base = draw(st.sampled_from(base_currencies))
    quote = draw(st.sampled_from(quote_currencies))
    market = f"{base}-{quote}"
    
    # Generate order parameters
    side = draw(st.sampled_from(['bid', 'ask']))
    ord_type = draw(st.sampled_from(['limit', 'market']))
    
    # Price is required for limit orders, None for market orders
    if ord_type == 'limit':
        price = draw(st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False))
    else:
        price = None
    
    volume = draw(st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False))
    
    # Generate identifier
    identifier = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_-'),
        min_size=5, max_size=30
    ))
    assume(len(identifier.strip()) >= 5)
    
    return Order(
        market=market,
        side=side,
        ord_type=ord_type,
        price=price,
        volume=volume,
        identifier=identifier
    )


@composite
def mock_positions_with_sufficient_balance(draw, order):
    """Generate mock positions with sufficient balance for the given order."""
    positions = []
    
    if order.side == 'bid':  # 매수 주문 - KRW 잔고 필요
        # 필요한 금액 계산
        if order.ord_type == 'market':
            required_balance = order.volume  # 시장가 매수는 volume이 KRW 금액
        else:
            required_balance = order.price * order.volume  # 지정가 매수
        
        # 충분한 KRW 잔고 생성 (필요 금액의 2~5배)
        multiplier = draw(st.floats(min_value=2.0, max_value=5.0))
        krw_balance = required_balance * multiplier
        krw_locked = draw(st.floats(min_value=0.0, max_value=krw_balance * 0.1))
        
        positions.append(Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=krw_balance,
            locked=krw_locked,
            unit_currency='KRW'
        ))
        
    else:  # 매도 주문 - 해당 코인 잔고 필요
        market_currency = order.market.split('-')[1]  # KRW-BTC -> BTC
        
        # 충분한 코인 잔고 생성 (필요 수량의 2~5배)
        multiplier = draw(st.floats(min_value=2.0, max_value=5.0))
        coin_balance = order.volume * multiplier
        coin_locked = draw(st.floats(min_value=0.0, max_value=coin_balance * 0.1))
        
        avg_buy_price = draw(st.floats(min_value=1000.0, max_value=100000.0))
        
        positions.append(Position(
            market=market_currency,
            avg_buy_price=avg_buy_price,
            balance=coin_balance,
            locked=coin_locked,
            unit_currency='KRW'
        ))
        
        # KRW 포지션도 추가 (항상 존재해야 함)
        krw_balance = draw(st.floats(min_value=100000.0, max_value=1000000.0))
        krw_locked = draw(st.floats(min_value=0.0, max_value=krw_balance * 0.1))
        
        positions.append(Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=krw_balance,
            locked=krw_locked,
            unit_currency='KRW'
        ))
    
    return positions


@composite
def api_error_types(draw):
    """Generate different types of API errors for testing."""
    error_types = [
        "Network connection failed",
        "API rate limit exceeded",
        "Server temporarily unavailable",
        "Request timeout",
        "Internal server error",
        "Service unavailable",
        "Connection reset by peer"
    ]
    
    error_message = draw(st.sampled_from(error_types))
    return UpbitAPIError(error_message)


class TestOrderRetryBehavior:
    """Property-based tests for order retry behavior."""
    
    @given(data=st.data())
    @settings(max_examples=50)
    def test_property_13_order_retry_behavior_success_after_retries(self, data):
        """
        **Feature: upbit-trading-bot, Property 13: Order Retry Behavior**
        **Validates: Requirements 4.3**
        
        Property: For any failed order placement, the system should retry exactly 3 times 
        with exponential backoff delays before giving up.
        """
        # Generate a valid order
        order = data.draw(valid_orders())
        
        # Generate positions with sufficient balance
        positions = data.draw(mock_positions_with_sufficient_balance(order))
        
        # Generate the number of failures before success (0-3)
        failures_before_success = data.draw(st.integers(min_value=0, max_value=3))
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create expected successful result
        expected_result = OrderResult(
            order_id=f"order_{int(time.time())}",
            market=order.market,
            side=order.side,
            ord_type=order.ord_type,
            price=order.price,
            volume=order.volume,
            remaining_volume=order.volume,
            reserved_fee=0.0,
            remaining_fee=0.0,
            paid_fee=0.0,
            locked=0.0,
            executed_volume=0.0,
            trades_count=0
        )
        
        # Setup place_order to fail N times then succeed
        api_error = data.draw(api_error_types())
        side_effects = [api_error] * failures_before_success + [expected_result]
        mock_api_client.place_order.side_effect = side_effects
        
        # Create OrderManager with default retry settings
        order_manager = OrderManager(api_client=mock_api_client, max_retries=3)
        
        # Mock time.sleep to avoid actual delays in tests
        with patch('time.sleep') as mock_sleep:
            # Execute order
            result = order_manager.execute_order(order)
        
        # Property 1: Order should succeed if it succeeds within retry limit
        if failures_before_success <= 3:
            assert result is not None, f"Order should succeed after {failures_before_success} failures"
            assert result.order_id == expected_result.order_id, "Result should match expected result"
            
            # Property 2: place_order should be called exactly (failures + 1) times
            expected_calls = failures_before_success + 1
            assert mock_api_client.place_order.call_count == expected_calls, f"place_order should be called {expected_calls} times"
            
            # Property 3: Sleep should be called for each retry (not for first attempt or final success)
            expected_sleep_calls = failures_before_success
            assert mock_sleep.call_count == expected_sleep_calls, f"sleep should be called {expected_sleep_calls} times"
            
            # Property 4: Sleep delays should follow exponential backoff pattern
            if expected_sleep_calls > 0:
                expected_delays = [1.0, 2.0, 4.0][:expected_sleep_calls]
                actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
                assert actual_delays == expected_delays, f"Sleep delays should follow exponential backoff: expected {expected_delays}, got {actual_delays}"
        
        else:
            # This case shouldn't happen with our test data, but included for completeness
            assert result is None, "Order should fail if failures exceed retry limit"
    
    @given(data=st.data())
    @settings(max_examples=30)
    def test_property_13_order_retry_behavior_max_retries_exceeded(self, data):
        """
        **Feature: upbit-trading-bot, Property 13: Order Retry Behavior**
        **Validates: Requirements 4.3**
        
        Property: For any order that fails more than 3 times, the system should give up 
        and return None after exactly 3 retry attempts.
        """
        # Generate a valid order
        order = data.draw(valid_orders())
        
        # Generate positions with sufficient balance
        positions = data.draw(mock_positions_with_sufficient_balance(order))
        
        # Create mock API client that always fails
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Generate API error
        api_error = data.draw(api_error_types())
        mock_api_client.place_order.side_effect = api_error
        
        # Create OrderManager with default retry settings
        order_manager = OrderManager(api_client=mock_api_client, max_retries=3)
        
        # Mock time.sleep to avoid actual delays in tests
        with patch('time.sleep') as mock_sleep:
            # Execute order
            result = order_manager.execute_order(order)
        
        # Property 1: Order should fail when all retries are exhausted
        assert result is None, "Order should fail when all retries are exhausted"
        
        # Property 2: place_order should be called exactly 4 times (1 initial + 3 retries)
        assert mock_api_client.place_order.call_count == 4, "place_order should be called 4 times (1 initial + 3 retries)"
        
        # Property 3: Sleep should be called exactly 3 times (for each retry)
        assert mock_sleep.call_count == 3, "sleep should be called 3 times for retries"
        
        # Property 4: Sleep delays should follow exponential backoff pattern
        expected_delays = [1.0, 2.0, 4.0]
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays, f"Sleep delays should follow exponential backoff: expected {expected_delays}, got {actual_delays}"
        
        # Property 5: All place_order calls should use the same order
        for call_args in mock_api_client.place_order.call_args_list:
            called_order = call_args[0][0]  # First positional argument
            assert called_order == order, "All retry attempts should use the same order"
    
    @given(order=valid_orders())
    @settings(max_examples=20)
    def test_order_retry_behavior_first_attempt_success(self, order):
        """Test retry behavior when first attempt succeeds."""
        # Create sufficient balance positions
        if order.side == 'bid':
            required_balance = order.volume if order.ord_type == 'market' else order.price * order.volume
            positions = [Position(
                market='KRW',
                avg_buy_price=1.0,
                balance=required_balance * 3.0,
                locked=0.0,
                unit_currency='KRW'
            )]
        else:
            market_currency = order.market.split('-')[1]
            positions = [
                Position(
                    market=market_currency,
                    avg_buy_price=50000.0,
                    balance=order.volume * 3.0,
                    locked=0.0,
                    unit_currency='KRW'
                ),
                Position(
                    market='KRW',
                    avg_buy_price=1.0,
                    balance=1000000.0,
                    locked=0.0,
                    unit_currency='KRW'
                )
            ]
        
        # Create mock API client that succeeds immediately
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        expected_result = OrderResult(
            order_id=f"order_{int(time.time())}",
            market=order.market,
            side=order.side,
            ord_type=order.ord_type,
            price=order.price,
            volume=order.volume,
            remaining_volume=order.volume,
            reserved_fee=0.0,
            remaining_fee=0.0,
            paid_fee=0.0,
            locked=0.0,
            executed_volume=0.0,
            trades_count=0
        )
        mock_api_client.place_order.return_value = expected_result
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client, max_retries=3)
        
        # Mock time.sleep
        with patch('time.sleep') as mock_sleep:
            # Execute order
            result = order_manager.execute_order(order)
        
        # Property: Should succeed immediately without retries
        assert result is not None, "Order should succeed on first attempt"
        assert result.order_id == expected_result.order_id, "Result should match expected result"
        
        # Property: place_order should be called exactly once
        assert mock_api_client.place_order.call_count == 1, "place_order should be called exactly once"
        
        # Property: No sleep calls should be made
        assert mock_sleep.call_count == 0, "No sleep calls should be made for immediate success"
    
    def test_order_retry_behavior_validation_failure_no_retry(self):
        """Test that validation failures don't trigger retries."""
        # Create order that will fail validation (insufficient balance)
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=100.0,  # Requires 5,000,000 KRW
            identifier='test_order'
        )
        
        # Create insufficient balance
        positions = [Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=1000.0,  # Only 1,000 KRW available
            locked=0.0,
            unit_currency='KRW'
        )]
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client, max_retries=3)
        
        # Mock time.sleep
        with patch('time.sleep') as mock_sleep:
            # Execute order
            result = order_manager.execute_order(order)
        
        # Property: Should fail immediately without retries for validation failures
        assert result is None, "Order should fail immediately for validation failures"
        
        # Property: place_order should not be called at all
        assert mock_api_client.place_order.call_count == 0, "place_order should not be called for validation failures"
        
        # Property: No sleep calls should be made
        assert mock_sleep.call_count == 0, "No sleep calls should be made for validation failures"
    
    def test_order_retry_behavior_non_api_error_no_retry(self):
        """Test that non-API errors don't trigger retries."""
        # Create valid order with sufficient balance
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=0.1,
            identifier='test_order'
        )
        
        positions = [Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=100000.0,
            locked=0.0,
            unit_currency='KRW'
        )]
        
        # Create mock API client that raises non-API exception
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        mock_api_client.place_order.side_effect = ValueError("Invalid order data")  # Non-API error
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client, max_retries=3)
        
        # Mock time.sleep
        with patch('time.sleep') as mock_sleep:
            # Execute order
            result = order_manager.execute_order(order)
        
        # Property: Should fail immediately without retries for non-API errors
        assert result is None, "Order should fail immediately for non-API errors"
        
        # Property: place_order should be called exactly once
        assert mock_api_client.place_order.call_count == 1, "place_order should be called exactly once"
        
        # Property: No sleep calls should be made
        assert mock_sleep.call_count == 0, "No sleep calls should be made for non-API errors"
    
    @given(max_retries=st.integers(min_value=0, max_value=10))
    @settings(max_examples=20)
    def test_order_retry_behavior_configurable_max_retries(self, max_retries):
        """Test that max_retries parameter is respected."""
        # Create valid order
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=0.1,
            identifier='test_order'
        )
        
        positions = [Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=100000.0,
            locked=0.0,
            unit_currency='KRW'
        )]
        
        # Create mock API client that always fails
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        mock_api_client.place_order.side_effect = UpbitAPIError("API error")
        
        # Create OrderManager with custom max_retries
        order_manager = OrderManager(api_client=mock_api_client, max_retries=max_retries)
        
        # Mock time.sleep
        with patch('time.sleep') as mock_sleep:
            # Execute order
            result = order_manager.execute_order(order)
        
        # Property: Should fail after exhausting retries
        assert result is None, "Order should fail after exhausting retries"
        
        # Property: place_order should be called exactly (max_retries + 1) times
        expected_calls = max_retries + 1
        assert mock_api_client.place_order.call_count == expected_calls, f"place_order should be called {expected_calls} times"
        
        # Property: Sleep should be called exactly max_retries times
        assert mock_sleep.call_count == max_retries, f"sleep should be called {max_retries} times"
        
        # Property: Sleep delays should follow exponential backoff pattern (up to available delays)
        if max_retries > 0:
            expected_delays = [1.0, 2.0, 4.0]
            # Use the pattern, repeating the last delay if needed
            actual_expected_delays = []
            for i in range(max_retries):
                if i < len(expected_delays):
                    actual_expected_delays.append(expected_delays[i])
                else:
                    actual_expected_delays.append(expected_delays[-1])  # Repeat last delay
            
            actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert actual_delays == actual_expected_delays, f"Sleep delays should follow pattern: expected {actual_expected_delays}, got {actual_delays}"
    
    def test_order_retry_behavior_exponential_backoff_pattern(self):
        """Test that exponential backoff delays follow the expected pattern."""
        # Create valid order
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=0.1,
            identifier='test_order'
        )
        
        positions = [Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=100000.0,
            locked=0.0,
            unit_currency='KRW'
        )]
        
        # Create mock API client that always fails
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        mock_api_client.place_order.side_effect = UpbitAPIError("API error")
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client, max_retries=3)
        
        # Verify the retry_delays configuration
        assert order_manager.retry_delays == [1.0, 2.0, 4.0], "Retry delays should be configured as [1.0, 2.0, 4.0]"
        
        # Mock time.sleep to capture delays
        with patch('time.sleep') as mock_sleep:
            # Execute order
            result = order_manager.execute_order(order)
        
        # Property: Delays should follow exponential backoff pattern
        expected_delays = [1.0, 2.0, 4.0]
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays, f"Sleep delays should be {expected_delays}, got {actual_delays}"
        
        # Property: Each delay should be called exactly once
        assert len(actual_delays) == 3, "Should have exactly 3 delay calls"
        assert all(isinstance(delay, float) for delay in actual_delays), "All delays should be floats"
        assert all(delay > 0 for delay in actual_delays), "All delays should be positive"
    
    def test_order_retry_behavior_database_operations(self):
        """Test that database operations are only performed on successful orders."""
        # Create valid order
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=0.1,
            identifier='test_order'
        )
        
        positions = [Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=100000.0,
            locked=0.0,
            unit_currency='KRW'
        )]
        
        # Create mock API client that fails twice then succeeds
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        expected_result = OrderResult(
            order_id="successful_order_123",
            market=order.market,
            side=order.side,
            ord_type=order.ord_type,
            price=order.price,
            volume=order.volume,
            remaining_volume=order.volume,
            reserved_fee=0.0,
            remaining_fee=0.0,
            paid_fee=0.0,
            locked=0.0,
            executed_volume=0.0,
            trades_count=0
        )
        
        mock_api_client.place_order.side_effect = [
            UpbitAPIError("First failure"),
            UpbitAPIError("Second failure"),
            expected_result  # Success on third attempt
        ]
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client, max_retries=3)
        
        # Mock database operations
        with patch.object(order_manager, '_save_order_to_db') as mock_save_db:
            with patch('time.sleep'):
                # Execute order
                result = order_manager.execute_order(order)
        
        # Property: Order should succeed after retries
        assert result is not None, "Order should succeed after retries"
        assert result.order_id == expected_result.order_id, "Result should match expected result"
        
        # Property: Database save should be called exactly once (only on success)
        assert mock_save_db.call_count == 1, "Database save should be called exactly once"
        mock_save_db.assert_called_with(order, expected_result)
        
        # Property: Active orders should be updated exactly once
        assert expected_result.order_id in order_manager.active_orders, "Successful order should be added to active orders"
        assert len(order_manager.active_orders) == 1, "Should have exactly one active order"
    
    def test_order_retry_behavior_active_orders_management(self):
        """Test that active orders are only updated on successful execution."""
        # Create valid order
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=0.1,
            identifier='test_order'
        )
        
        positions = [Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=100000.0,
            locked=0.0,
            unit_currency='KRW'
        )]
        
        # Create mock API client that always fails
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        mock_api_client.place_order.side_effect = UpbitAPIError("Always fails")
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client, max_retries=3)
        
        # Verify initial state
        assert len(order_manager.active_orders) == 0, "Should start with no active orders"
        
        # Mock time.sleep
        with patch('time.sleep'):
            # Execute order (should fail)
            result = order_manager.execute_order(order)
        
        # Property: Failed order should not be added to active orders
        assert result is None, "Order should fail"
        assert len(order_manager.active_orders) == 0, "Failed order should not be added to active orders"
        
        # Now test successful case
        expected_result = OrderResult(
            order_id="successful_order_456",
            market=order.market,
            side=order.side,
            ord_type=order.ord_type,
            price=order.price,
            volume=order.volume,
            remaining_volume=order.volume,
            reserved_fee=0.0,
            remaining_fee=0.0,
            paid_fee=0.0,
            locked=0.0,
            executed_volume=0.0,
            trades_count=0
        )
        mock_api_client.place_order.side_effect = None
        mock_api_client.place_order.return_value = expected_result
        
        with patch('time.sleep'):
            # Execute order (should succeed)
            result = order_manager.execute_order(order)
        
        # Property: Successful order should be added to active orders
        assert result is not None, "Order should succeed"
        assert len(order_manager.active_orders) == 1, "Successful order should be added to active orders"
        assert expected_result.order_id in order_manager.active_orders, "Order ID should be in active orders"