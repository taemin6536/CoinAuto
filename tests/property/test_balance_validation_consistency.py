"""Property-based tests for balance validation consistency.

**Feature: upbit-trading-bot, Property 12: Balance Validation Consistency**
**Validates: Requirements 4.2**
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.order.manager import OrderManager, OrderValidationResult
from upbit_trading_bot.data.models import Order, Position
from upbit_trading_bot.api.client import UpbitAPIClient


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
        
        # 충분한 KRW 잔고 생성 (필요 금액의 1.1~3배)
        multiplier = draw(st.floats(min_value=1.1, max_value=3.0))
        krw_balance = required_balance * multiplier
        krw_locked = draw(st.floats(min_value=0.0, max_value=krw_balance * 0.3))
        
        # 사용 가능한 잔고가 필요 금액보다 많은지 확인
        available_balance = krw_balance - krw_locked
        assume(available_balance >= required_balance)
        
        positions.append(Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=krw_balance,
            locked=krw_locked,
            unit_currency='KRW'
        ))
        
    else:  # 매도 주문 - 해당 코인 잔고 필요
        market_currency = order.market.split('-')[1]  # KRW-BTC -> BTC
        
        # 충분한 코인 잔고 생성 (필요 수량의 1.1~3배)
        multiplier = draw(st.floats(min_value=1.1, max_value=3.0))
        coin_balance = order.volume * multiplier
        coin_locked = draw(st.floats(min_value=0.0, max_value=coin_balance * 0.3))
        
        # 사용 가능한 잔고가 필요 수량보다 많은지 확인
        available_balance = coin_balance - coin_locked
        assume(available_balance >= order.volume)
        
        avg_buy_price = draw(st.floats(min_value=1000.0, max_value=100000.0))
        
        positions.append(Position(
            market=market_currency,
            avg_buy_price=avg_buy_price,
            balance=coin_balance,
            locked=coin_locked,
            unit_currency='KRW'
        ))
        
        # KRW 포지션도 추가 (항상 존재해야 함)
        krw_balance = draw(st.floats(min_value=0.0, max_value=1000000.0))
        krw_locked = draw(st.floats(min_value=0.0, max_value=krw_balance))
        
        positions.append(Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=krw_balance,
            locked=krw_locked,
            unit_currency='KRW'
        ))
    
    return positions


@composite
def mock_positions_with_insufficient_balance(draw, order):
    """Generate mock positions with insufficient balance for the given order."""
    positions = []
    
    if order.side == 'bid':  # 매수 주문 - KRW 잔고 부족
        # 필요한 금액 계산
        if order.ord_type == 'market':
            required_balance = order.volume
        else:
            required_balance = order.price * order.volume
        
        # 부족한 KRW 잔고 생성 (필요 금액의 0.1~0.9배)
        multiplier = draw(st.floats(min_value=0.1, max_value=0.9))
        krw_balance = required_balance * multiplier
        krw_locked = draw(st.floats(min_value=0.0, max_value=krw_balance))
        
        # 사용 가능한 잔고가 필요 금액보다 적은지 확인
        available_balance = krw_balance - krw_locked
        assume(available_balance < required_balance)
        
        positions.append(Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=krw_balance,
            locked=krw_locked,
            unit_currency='KRW'
        ))
        
    else:  # 매도 주문 - 해당 코인 잔고 부족
        market_currency = order.market.split('-')[1]
        
        # 부족한 코인 잔고 생성 (필요 수량의 0.1~0.9배)
        multiplier = draw(st.floats(min_value=0.1, max_value=0.9))
        coin_balance = order.volume * multiplier
        coin_locked = draw(st.floats(min_value=0.0, max_value=coin_balance))
        
        # 사용 가능한 잔고가 필요 수량보다 적은지 확인
        available_balance = coin_balance - coin_locked
        assume(available_balance < order.volume)
        
        avg_buy_price = draw(st.floats(min_value=1000.0, max_value=100000.0))
        
        positions.append(Position(
            market=market_currency,
            avg_buy_price=avg_buy_price,
            balance=coin_balance,
            locked=coin_locked,
            unit_currency='KRW'
        ))
        
        # KRW 포지션도 추가
        krw_balance = draw(st.floats(min_value=0.0, max_value=1000000.0))
        krw_locked = draw(st.floats(min_value=0.0, max_value=krw_balance))
        
        positions.append(Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=krw_balance,
            locked=krw_locked,
            unit_currency='KRW'
        ))
    
    return positions


class TestBalanceValidationConsistency:
    """Property-based tests for balance validation consistency."""
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_12_balance_validation_consistency_sufficient_balance(self, data):
        """
        **Feature: upbit-trading-bot, Property 12: Balance Validation Consistency**
        **Validates: Requirements 4.2**
        
        Property: For any order placement attempt with sufficient balance,
        the system should validate and approve the order.
        """
        # Generate a valid order
        order = data.draw(valid_orders())
        
        # Generate positions with sufficient balance for this order
        positions = data.draw(mock_positions_with_sufficient_balance(order))
        
        # Create mock API client that returns the positions
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Validate the order
        validation_result = order_manager.validate_order(order)
        
        # Property 1: Order with sufficient balance should be valid
        assert validation_result.is_valid, f"Order should be valid when sufficient balance is available. Error: {validation_result.error_message}"
        
        # Property 2: No error message should be present for valid orders
        assert validation_result.error_message is None, "Valid orders should not have error messages"
        
        # Property 3: API should be called to get account information
        mock_api_client.get_accounts.assert_called_once()
        
        # Property 4: Validation should be consistent for the same order and positions
        validation_result2 = order_manager.validate_order(order)
        assert validation_result2.is_valid == validation_result.is_valid, "Validation should be consistent"
        assert validation_result2.error_message == validation_result.error_message, "Error messages should be consistent"
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_12_balance_validation_consistency_insufficient_balance(self, data):
        """
        **Feature: upbit-trading-bot, Property 12: Balance Validation Consistency**
        **Validates: Requirements 4.2**
        
        Property: For any order placement attempt with insufficient balance,
        the system should validate and reject the order with appropriate error message.
        """
        # Generate a valid order
        order = data.draw(valid_orders())
        
        # Generate positions with insufficient balance for this order
        positions = data.draw(mock_positions_with_insufficient_balance(order))
        
        # Create mock API client that returns the positions
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Validate the order
        validation_result = order_manager.validate_order(order)
        
        # Property 1: Order with insufficient balance should be invalid
        assert not validation_result.is_valid, "Order should be invalid when insufficient balance"
        
        # Property 2: Error message should be present for invalid orders
        assert validation_result.error_message is not None, "Invalid orders should have error messages"
        assert isinstance(validation_result.error_message, str), "Error message should be a string"
        assert len(validation_result.error_message) > 0, "Error message should not be empty"
        
        # Property 3: Error message should indicate balance issue
        error_msg = validation_result.error_message.lower()
        balance_keywords = ['잔고', '부족', 'balance', 'insufficient']
        assert any(keyword in error_msg for keyword in balance_keywords), f"Error message should indicate balance issue: {validation_result.error_message}"
        
        # Property 4: Required and available balance should be provided when relevant
        if order.side == 'bid':
            # For buy orders, we should have balance information
            assert validation_result.required_balance is not None, "Required balance should be provided for buy orders"
            assert validation_result.available_balance is not None, "Available balance should be provided for buy orders"
            assert validation_result.required_balance > validation_result.available_balance, "Required balance should exceed available balance"
        else:
            # For sell orders, we should also have balance information
            assert validation_result.required_balance is not None, "Required balance should be provided for sell orders"
            assert validation_result.available_balance is not None, "Available balance should be provided for sell orders"
            assert validation_result.required_balance > validation_result.available_balance, "Required volume should exceed available volume"
        
        # Property 5: API should be called to get account information
        mock_api_client.get_accounts.assert_called_once()
    
    @given(order=valid_orders())
    @settings(max_examples=50)
    def test_balance_validation_buy_order_krw_calculation(self, order):
        """Test that buy order balance validation correctly calculates required KRW."""
        # Only test buy orders
        assume(order.side == 'bid')
        
        # Calculate expected required balance
        if order.ord_type == 'market':
            expected_required = order.volume  # Market buy: volume is KRW amount
        else:
            expected_required = order.price * order.volume  # Limit buy: price * volume
        
        # Create sufficient KRW balance
        krw_balance = expected_required * 2.0
        krw_locked = 0.0
        
        positions = [Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=krw_balance,
            locked=krw_locked,
            unit_currency='KRW'
        )]
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager and validate
        order_manager = OrderManager(api_client=mock_api_client)
        validation_result = order_manager.validate_order(order)
        
        # Property: Buy order should be valid with sufficient KRW
        assert validation_result.is_valid, f"Buy order should be valid with sufficient KRW balance"
        
        # Test with insufficient balance
        insufficient_balance = expected_required * 0.5
        positions[0].balance = insufficient_balance
        
        validation_result2 = order_manager.validate_order(order)
        
        # Property: Buy order should be invalid with insufficient KRW
        assert not validation_result2.is_valid, "Buy order should be invalid with insufficient KRW balance"
        assert validation_result2.required_balance == expected_required, f"Required balance should match calculation: expected {expected_required}, got {validation_result2.required_balance}"
    
    @given(order=valid_orders())
    @settings(max_examples=50)
    def test_balance_validation_sell_order_coin_calculation(self, order):
        """Test that sell order balance validation correctly calculates required coin amount."""
        # Only test sell orders
        assume(order.side == 'ask')
        
        market_currency = order.market.split('-')[1]  # KRW-BTC -> BTC
        expected_required = order.volume  # Sell orders require volume amount of the coin
        
        # Create sufficient coin balance
        coin_balance = expected_required * 2.0
        coin_locked = 0.0
        
        positions = [
            Position(
                market=market_currency,
                avg_buy_price=50000.0,
                balance=coin_balance,
                locked=coin_locked,
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
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager and validate
        order_manager = OrderManager(api_client=mock_api_client)
        validation_result = order_manager.validate_order(order)
        
        # Property: Sell order should be valid with sufficient coin balance
        assert validation_result.is_valid, f"Sell order should be valid with sufficient {market_currency} balance"
        
        # Test with insufficient balance
        insufficient_balance = expected_required * 0.5
        positions[0].balance = insufficient_balance
        
        validation_result2 = order_manager.validate_order(order)
        
        # Property: Sell order should be invalid with insufficient coin balance
        assert not validation_result2.is_valid, f"Sell order should be invalid with insufficient {market_currency} balance"
        assert validation_result2.required_balance == expected_required, f"Required balance should match order volume: expected {expected_required}, got {validation_result2.required_balance}"
    
    def test_balance_validation_missing_krw_position(self):
        """Test validation behavior when KRW position is missing."""
        # Create buy order
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=0.1,
            identifier='test_order'
        )
        
        # Create positions without KRW
        positions = [
            Position(
                market='BTC',
                avg_buy_price=50000.0,
                balance=1.0,
                locked=0.0,
                unit_currency='KRW'
            )
        ]
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager and validate
        order_manager = OrderManager(api_client=mock_api_client)
        validation_result = order_manager.validate_order(order)
        
        # Property: Should be invalid when KRW position is missing
        assert not validation_result.is_valid, "Order should be invalid when KRW position is missing"
        assert "KRW 잔고 정보를 찾을 수 없습니다" in validation_result.error_message, "Error should indicate missing KRW position"
    
    def test_balance_validation_missing_coin_position(self):
        """Test validation behavior when required coin position is missing."""
        # Create sell order
        order = Order(
            market='KRW-BTC',
            side='ask',
            ord_type='limit',
            price=50000.0,
            volume=0.1,
            identifier='test_order'
        )
        
        # Create positions without BTC
        positions = [
            Position(
                market='KRW',
                avg_buy_price=1.0,
                balance=1000000.0,
                locked=0.0,
                unit_currency='KRW'
            )
        ]
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager and validate
        order_manager = OrderManager(api_client=mock_api_client)
        validation_result = order_manager.validate_order(order)
        
        # Property: Should be invalid when required coin position is missing
        assert not validation_result.is_valid, "Order should be invalid when required coin position is missing"
        assert "BTC 잔고 정보를 찾을 수 없습니다" in validation_result.error_message, "Error should indicate missing BTC position"
    
    def test_balance_validation_locked_balance_consideration(self):
        """Test that locked balance is properly considered in validation."""
        # Create buy order requiring 100,000 KRW
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=2.0,  # 50000 * 2 = 100,000 KRW needed
            identifier='test_order'
        )
        
        # Create KRW position with total balance but high locked amount
        positions = [
            Position(
                market='KRW',
                avg_buy_price=1.0,
                balance=150000.0,  # Total balance
                locked=80000.0,    # Locked amount
                unit_currency='KRW'
            )
        ]
        # Available balance = 150,000 - 80,000 = 70,000 KRW (insufficient for 100,000 KRW order)
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager and validate
        order_manager = OrderManager(api_client=mock_api_client)
        validation_result = order_manager.validate_order(order)
        
        # Property: Should be invalid when available balance (total - locked) is insufficient
        assert not validation_result.is_valid, "Order should be invalid when available balance is insufficient due to locked funds"
        assert validation_result.required_balance == 100000.0, "Required balance should be correctly calculated"
        assert validation_result.available_balance == 70000.0, "Available balance should exclude locked funds"
        
        # Test with sufficient available balance
        positions[0].locked = 30000.0  # Available = 150,000 - 30,000 = 120,000 KRW (sufficient)
        
        validation_result2 = order_manager.validate_order(order)
        
        # Property: Should be valid when available balance is sufficient
        assert validation_result2.is_valid, "Order should be valid when available balance is sufficient"
    
    def test_balance_validation_api_error_handling(self):
        """Test validation behavior when API call fails."""
        # Create valid order
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=0.1,
            identifier='test_order'
        )
        
        # Create mock API client that raises exception
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.side_effect = Exception("API connection failed")
        
        # Create OrderManager and validate
        order_manager = OrderManager(api_client=mock_api_client)
        validation_result = order_manager.validate_order(order)
        
        # Property: Should handle API errors gracefully
        assert not validation_result.is_valid, "Order should be invalid when API call fails"
        assert validation_result.error_message is not None, "Error message should be provided"
        assert "검증 중 오류 발생" in validation_result.error_message, "Error message should indicate validation error"
    
    def test_balance_validation_invalid_order_handling(self):
        """Test validation behavior with invalid order data."""
        # Create invalid order (negative volume)
        order = Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000.0,
            volume=-0.1,  # Invalid negative volume
            identifier='test_order'
        )
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create OrderManager and validate
        order_manager = OrderManager(api_client=mock_api_client)
        validation_result = order_manager.validate_order(order)
        
        # Property: Should reject invalid orders before checking balance
        assert not validation_result.is_valid, "Invalid orders should be rejected"
        assert "주문 데이터가 유효하지 않습니다" in validation_result.error_message, "Error should indicate invalid order data"
        
        # Property: API should not be called for invalid orders
        mock_api_client.get_accounts.assert_not_called()
    
    @given(order=valid_orders())
    @settings(max_examples=30)
    def test_balance_validation_consistency_multiple_calls(self, order):
        """Test that validation results are consistent across multiple calls."""
        # Generate consistent positions
        if order.side == 'bid':
            required_balance = order.volume if order.ord_type == 'market' else order.price * order.volume
            positions = [Position(
                market='KRW',
                avg_buy_price=1.0,
                balance=required_balance * 1.5,  # Sufficient balance
                locked=0.0,
                unit_currency='KRW'
            )]
        else:
            market_currency = order.market.split('-')[1]
            positions = [
                Position(
                    market=market_currency,
                    avg_buy_price=50000.0,
                    balance=order.volume * 1.5,  # Sufficient balance
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
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = positions
        
        # Create OrderManager
        order_manager = OrderManager(api_client=mock_api_client)
        
        # Validate multiple times
        results = []
        for _ in range(3):
            results.append(order_manager.validate_order(order))
        
        # Property: All validation results should be consistent
        first_result = results[0]
        for i, result in enumerate(results[1:], 1):
            assert result.is_valid == first_result.is_valid, f"Validation result {i+1} validity should match first result"
            assert result.error_message == first_result.error_message, f"Validation result {i+1} error message should match first result"
            
            if result.required_balance is not None and first_result.required_balance is not None:
                assert result.required_balance == first_result.required_balance, f"Required balance should be consistent"
            
            if result.available_balance is not None and first_result.available_balance is not None:
                assert result.available_balance == first_result.available_balance, f"Available balance should be consistent"