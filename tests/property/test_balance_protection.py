"""Property-based tests for balance protection.

**Feature: upbit-trading-bot, Property 17: Balance Protection**
**Validates: Requirements 5.3**
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.risk.manager import RiskManager, RiskEvent
from upbit_trading_bot.data.models import Account, Order
from upbit_trading_bot.api.client import UpbitAPIClient
from upbit_trading_bot.config.manager import ConfigManager


@composite
def balance_protection_config(draw):
    """Generate balance protection configuration."""
    return {
        'stop_loss_percentage': draw(st.floats(min_value=0.01, max_value=0.20, allow_nan=False, allow_infinity=False)),
        'daily_loss_limit': draw(st.floats(min_value=0.05, max_value=0.50, allow_nan=False, allow_infinity=False)),
        'max_daily_trades': draw(st.integers(min_value=5, max_value=200)),
        'min_balance_threshold': draw(st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)),
        'position_size_limit': draw(st.floats(min_value=0.05, max_value=0.50, allow_nan=False, allow_infinity=False))
    }


@composite
def account_below_threshold(draw, min_threshold):
    """Generate account with balance below minimum threshold."""
    # Generate balance below threshold
    balance = draw(st.floats(min_value=0.0, max_value=min_threshold * 0.99, allow_nan=False, allow_infinity=False))
    locked = draw(st.floats(min_value=0.0, max_value=balance * 0.5, allow_nan=False, allow_infinity=False))
    
    return Account(
        currency='KRW',
        balance=balance,
        locked=locked,
        avg_buy_price=1.0,
        avg_buy_price_modified=False,
        unit_currency='KRW'
    )


@composite
def account_above_threshold(draw, min_threshold):
    """Generate account with balance above minimum threshold."""
    # Generate balance above threshold
    balance = draw(st.floats(min_value=min_threshold * 1.1, max_value=min_threshold * 10.0, allow_nan=False, allow_infinity=False))
    locked = draw(st.floats(min_value=0.0, max_value=balance * 0.3, allow_nan=False, allow_infinity=False))
    
    return Account(
        currency='KRW',
        balance=balance,
        locked=locked,
        avg_buy_price=1.0,
        avg_buy_price_modified=False,
        unit_currency='KRW'
    )


@composite
def buy_order(draw):
    """Generate a buy order."""
    return Order(
        market=draw(st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT'])),
        side='bid',  # Buy order
        ord_type=draw(st.sampled_from(['market', 'limit'])),
        price=draw(st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)),
        volume=draw(st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False)),
        identifier=None
    )


@composite
def sell_order(draw):
    """Generate a sell order."""
    return Order(
        market=draw(st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT'])),
        side='ask',  # Sell order
        ord_type=draw(st.sampled_from(['market', 'limit'])),
        price=draw(st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)),
        volume=draw(st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False)),
        identifier=None
    )


class TestBalanceProtection:
    """Property-based tests for balance protection."""
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_17_balance_protection_below_threshold(self, data):
        """
        **Feature: upbit-trading-bot, Property 17: Balance Protection**
        **Validates: Requirements 5.3**
        
        Property: For any account state where balance falls below minimum threshold,
        new buy orders should be prevented.
        """
        # Generate configuration
        config = data.draw(balance_protection_config())
        
        # Generate account with balance below threshold
        krw_account = data.draw(account_below_threshold(config['min_balance_threshold']))
        
        # Calculate available balance
        available_balance = krw_account.balance - krw_account.locked
        
        # Ensure available balance is actually below threshold
        assume(available_balance < config['min_balance_threshold'])
        
        # Generate a buy order
        order = data.draw(buy_order())
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = [krw_account]
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check balance protection
        balance_ok = risk_manager._check_balance_protection()
        
        # Property 1: Should return False when balance is below threshold
        assert not balance_ok, f"Should return False when available balance ({available_balance:,.0f}) is below threshold ({config['min_balance_threshold']:,.0f})"
        
        # Property 2: Risk event should be triggered
        assert len(triggered_events) > 0, "Risk event should be triggered when balance is below threshold"
        
        # Property 3: Event should have correct details
        balance_events = [e for e in triggered_events if e.event_type == 'balance_protection']
        assert len(balance_events) > 0, "Should have balance_protection risk events"
        
        event = balance_events[0]
        assert event.severity == 'critical', f"Event severity should be 'critical', got {event.severity}"
        assert abs(event.current_value - available_balance) < 0.01, f"Current value should be {available_balance}, got {event.current_value}"
        assert event.threshold_value == config['min_balance_threshold'], f"Threshold should be {config['min_balance_threshold']}, got {event.threshold_value}"
        assert "최소 잔고 임계값 미달" in event.message, f"Event message should mention balance threshold, got: {event.message}"
        assert "신규 매수 주문 차단" in event.action_taken, f"Action should mention buy order blocking, got: {event.action_taken}"
        
        # Property 4: should_stop_trading should return True for buy orders
        should_stop = risk_manager.should_stop_trading()
        assert should_stop, "should_stop_trading should return True when balance is below threshold"
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_17_balance_protection_above_threshold(self, data):
        """
        **Feature: upbit-trading-bot, Property 17: Balance Protection**
        **Validates: Requirements 5.3**
        
        Property: For any account state where balance is above minimum threshold,
        new buy orders should be allowed.
        """
        # Generate configuration
        config = data.draw(balance_protection_config())
        
        # Generate account with balance above threshold
        krw_account = data.draw(account_above_threshold(config['min_balance_threshold']))
        
        # Calculate available balance
        available_balance = krw_account.balance - krw_account.locked
        
        # Ensure available balance is actually above threshold
        assume(available_balance >= config['min_balance_threshold'])
        
        # Generate a buy order
        order = data.draw(buy_order())
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = [krw_account]
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check balance protection
        balance_ok = risk_manager._check_balance_protection()
        
        # Property 1: Should return True when balance is above threshold
        assert balance_ok, f"Should return True when available balance ({available_balance:,.0f}) is above threshold ({config['min_balance_threshold']:,.0f})"
        
        # Property 2: No balance protection events should be triggered
        balance_events = [e for e in triggered_events if e.event_type == 'balance_protection']
        assert len(balance_events) == 0, f"No balance_protection events should be triggered when above threshold, got {len(balance_events)}"
    
    @given(data=st.data())
    @settings(max_examples=50)
    def test_property_17_balance_protection_sell_orders_unaffected(self, data):
        """
        **Feature: upbit-trading-bot, Property 17: Balance Protection**
        **Validates: Requirements 5.3**
        
        Property: Balance protection should not affect sell orders, only buy orders.
        """
        # Generate configuration
        config = data.draw(balance_protection_config())
        
        # Generate account with balance below threshold
        krw_account = data.draw(account_below_threshold(config['min_balance_threshold']))
        
        # Generate a sell order
        order = data.draw(sell_order())
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = [krw_account]
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Check position limits for sell order (should not be affected by balance protection)
        position_ok = risk_manager.check_position_limits(order)
        
        # Property: Sell orders should not be affected by balance protection
        # (check_position_limits returns True for sell orders regardless of balance)
        assert position_ok, "Sell orders should not be affected by balance protection"
    
    @given(data=st.data())
    @settings(max_examples=50)
    def test_property_17_balance_protection_no_api_client(self, data):
        """
        **Feature: upbit-trading-bot, Property 17: Balance Protection**
        **Validates: Requirements 5.3**
        
        Property: When API client is not available, balance protection should default to allowing operations.
        """
        # Generate configuration
        config = data.draw(balance_protection_config())
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager without API client
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=None)
        
        # Check balance protection
        balance_ok = risk_manager._check_balance_protection()
        
        # Property: Should return True when API client is not available
        assert balance_ok, "Should return True when API client is not available (fail-safe behavior)"
    
    @given(data=st.data())
    @settings(max_examples=50)
    def test_property_17_balance_protection_no_krw_account(self, data):
        """
        **Feature: upbit-trading-bot, Property 17: Balance Protection**
        **Validates: Requirements 5.3**
        
        Property: When no KRW account is found, balance protection should default to allowing operations.
        """
        # Generate configuration
        config = data.draw(balance_protection_config())
        
        # Create accounts without KRW
        btc_account = Account(
            currency='BTC',
            balance=data.draw(st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False)),
            locked=0.0,
            avg_buy_price=data.draw(st.floats(min_value=30000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)),
            avg_buy_price_modified=False,
            unit_currency='KRW'
        )
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = [btc_account]  # No KRW account
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Check balance protection
        balance_ok = risk_manager._check_balance_protection()
        
        # Property: Should return True when no KRW account is found
        assert balance_ok, "Should return True when no KRW account is found (fail-safe behavior)"
    
    @given(data=st.data())
    @settings(max_examples=50)
    def test_property_17_balance_protection_exactly_at_threshold(self, data):
        """
        **Feature: upbit-trading-bot, Property 17: Balance Protection**
        **Validates: Requirements 5.3**
        
        Property: When balance is exactly at the threshold, it should be considered acceptable.
        """
        # Generate configuration
        config = data.draw(balance_protection_config())
        
        # Create account with balance exactly at threshold
        krw_account = Account(
            currency='KRW',
            balance=config['min_balance_threshold'],
            locked=0.0,
            avg_buy_price=1.0,
            avg_buy_price_modified=False,
            unit_currency='KRW'
        )
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = [krw_account]
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check balance protection
        balance_ok = risk_manager._check_balance_protection()
        
        # Property: Should return True when balance is exactly at threshold
        assert balance_ok, f"Should return True when balance ({config['min_balance_threshold']}) is exactly at threshold"
        
        # Property: No balance protection events should be triggered
        balance_events = [e for e in triggered_events if e.event_type == 'balance_protection']
        assert len(balance_events) == 0, f"No balance_protection events should be triggered when exactly at threshold, got {len(balance_events)}"
    
    @given(data=st.data())
    @settings(max_examples=50)
    def test_property_17_balance_protection_with_locked_funds(self, data):
        """
        **Feature: upbit-trading-bot, Property 17: Balance Protection**
        **Validates: Requirements 5.3**
        
        Property: Balance protection should consider locked funds when calculating available balance.
        """
        # Generate configuration
        config = data.draw(balance_protection_config())
        
        # Generate account where total balance is above threshold but available balance is below
        total_balance = data.draw(st.floats(min_value=config['min_balance_threshold'] * 1.1, 
                                          max_value=config['min_balance_threshold'] * 2.0, 
                                          allow_nan=False, allow_infinity=False))
        
        # Set locked amount so that available balance is below threshold
        locked_amount = total_balance - (config['min_balance_threshold'] * 0.9)
        
        krw_account = Account(
            currency='KRW',
            balance=total_balance,
            locked=locked_amount,
            avg_buy_price=1.0,
            avg_buy_price_modified=False,
            unit_currency='KRW'
        )
        
        available_balance = total_balance - locked_amount
        
        # Ensure available balance is actually below threshold
        assume(available_balance < config['min_balance_threshold'])
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = [krw_account]
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check balance protection
        balance_ok = risk_manager._check_balance_protection()
        
        # Property 1: Should return False when available balance (after locked funds) is below threshold
        assert not balance_ok, f"Should return False when available balance ({available_balance:,.0f}) is below threshold ({config['min_balance_threshold']:,.0f}), even if total balance ({total_balance:,.0f}) is above"
        
        # Property 2: Risk event should be triggered
        assert len(triggered_events) > 0, "Risk event should be triggered when available balance is below threshold"
        
        # Property 3: Event should reflect available balance, not total balance
        balance_events = [e for e in triggered_events if e.event_type == 'balance_protection']
        assert len(balance_events) > 0, "Should have balance_protection risk events"
        
        event = balance_events[0]
        assert abs(event.current_value - available_balance) < 0.01, f"Event current_value should reflect available balance ({available_balance}), got {event.current_value}"
    
    def test_balance_protection_integration_with_should_stop_trading(self):
        """Test that balance protection integrates correctly with should_stop_trading."""
        # Create configuration with specific threshold
        config = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create account with balance below threshold
        krw_account = Account(
            currency='KRW',
            balance=5000.0,  # Below threshold
            locked=0.0,
            avg_buy_price=1.0,
            avg_buy_price_modified=False,
            unit_currency='KRW'
        )
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = [krw_account]
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Mock notification service
        risk_manager.notification_service.send_notification = Mock(return_value=True)
        
        # Check if trading should stop
        should_stop = risk_manager.should_stop_trading()
        
        # Property: should_stop_trading should return True when balance protection is triggered
        assert should_stop, "should_stop_trading should return True when balance is below threshold"
    
    def test_balance_protection_error_handling(self):
        """Test balance protection error handling."""
        # Create configuration
        config = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create mock API client that raises exception
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.side_effect = Exception("API connection failed")
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Check balance protection (should handle exception gracefully)
        balance_ok = risk_manager._check_balance_protection()
        
        # Property: Should return True (fail-safe) when exception occurs
        assert balance_ok, "Should return True (fail-safe behavior) when exception occurs during balance check"
    
    @given(config=balance_protection_config())
    @settings(max_examples=30)
    def test_balance_protection_consistency_across_calls(self, config):
        """Test that balance protection returns consistent results across multiple calls."""
        # Create account with balance below threshold
        krw_account = Account(
            currency='KRW',
            balance=config['min_balance_threshold'] * 0.5,  # Half of threshold
            locked=0.0,
            avg_buy_price=1.0,
            avg_buy_price_modified=False,
            unit_currency='KRW'
        )
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_accounts.return_value = [krw_account]
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        
        # Mock notification service
        risk_manager.notification_service.send_notification = Mock(return_value=True)
        
        # Check balance protection multiple times
        results = []
        for _ in range(3):
            results.append(risk_manager._check_balance_protection())
        
        # Property: All results should be consistent
        first_result = results[0]
        for i, result in enumerate(results[1:], 1):
            assert result == first_result, f"Balance protection check result {i+1} should match first result"
        
        # Property: All results should be False (below threshold)
        for result in results:
            assert not result, "All results should be False when balance is below threshold"