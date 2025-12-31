"""Property-based tests for volume limit enforcement.

**Feature: upbit-trading-bot, Property 16: Volume Limit Enforcement**
**Validates: Requirements 5.2**
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.risk.manager import RiskManager, PortfolioSnapshot, RiskEvent
from upbit_trading_bot.data.models import Position, Account
from upbit_trading_bot.api.client import UpbitAPIClient
from upbit_trading_bot.config.manager import ConfigManager


@composite
def daily_trading_config(draw):
    """Generate daily trading configuration."""
    return {
        'stop_loss_percentage': draw(st.floats(min_value=0.01, max_value=0.20, allow_nan=False, allow_infinity=False)),
        'daily_loss_limit': draw(st.floats(min_value=0.05, max_value=0.50, allow_nan=False, allow_infinity=False)),
        'max_daily_trades': draw(st.integers(min_value=5, max_value=200)),
        'min_balance_threshold': draw(st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)),
        'position_size_limit': draw(st.floats(min_value=0.05, max_value=0.50, allow_nan=False, allow_infinity=False))
    }


@composite
def portfolio_snapshot_with_loss(draw):
    """Generate portfolio snapshot with daily loss."""
    total_krw_value = draw(st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False))
    total_btc_value = draw(st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False))
    
    # Generate daily loss that exceeds limit
    daily_loss_percentage = draw(st.floats(min_value=0.05, max_value=0.50, allow_nan=False, allow_infinity=False))
    daily_pnl = -total_krw_value * daily_loss_percentage  # Negative for loss
    
    positions = {
        'KRW': Position(
            market='KRW',
            avg_buy_price=1.0,
            balance=total_krw_value * 0.5,
            locked=0.0,
            unit_currency='KRW'
        )
    }
    
    return PortfolioSnapshot(
        total_krw_value=total_krw_value,
        total_btc_value=total_btc_value,
        positions=positions,
        timestamp=datetime.now(),
        daily_pnl=daily_pnl,
        daily_pnl_percentage=-daily_loss_percentage
    ), daily_loss_percentage


@composite
def trade_count_exceeding_limit(draw, max_daily_trades):
    """Generate trade count that exceeds the daily limit."""
    return draw(st.integers(min_value=max_daily_trades, max_value=max_daily_trades + 100))


@composite
def trade_count_within_limit(draw, max_daily_trades):
    """Generate trade count that is within the daily limit."""
    return draw(st.integers(min_value=0, max_value=max_daily_trades - 1))


class TestVolumeLimitEnforcement:
    """Property-based tests for volume limit enforcement."""
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_16_volume_limit_enforcement_trade_count_exceeded(self, data):
        """
        **Feature: upbit-trading-bot, Property 16: Volume Limit Enforcement**
        **Validates: Requirements 5.2**
        
        Property: For any trading session where daily volume exceeds configured limits,
        trading operations should be paused.
        """
        # Generate configuration
        config = data.draw(daily_trading_config())
        
        # Generate trade count that exceeds limit
        excessive_trade_count = data.draw(trade_count_exceeding_limit(config['max_daily_trades']))
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        
        # Set daily trade count to exceed limit
        risk_manager.daily_trade_count = excessive_trade_count
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check daily limits
        within_limits = risk_manager.check_daily_limits()
        
        # Property 1: Should return False when trade count exceeds limit
        assert not within_limits, f"Should return False when daily trades ({excessive_trade_count}) exceed limit ({config['max_daily_trades']})"
        
        # Property 2: Trading should be paused
        assert risk_manager.trading_paused, "Trading should be paused when daily trade limit is exceeded"
        
        # Property 3: Pause reason should be set
        assert "일일 거래 횟수 한도 초과" in risk_manager.pause_reason, f"Pause reason should mention trade count limit, got: {risk_manager.pause_reason}"
        
        # Property 4: Risk event should be triggered
        assert len(triggered_events) > 0, "Risk event should be triggered when trade limit is exceeded"
        
        # Property 5: Event should have correct details
        daily_limit_events = [e for e in triggered_events if e.event_type == 'daily_limit']
        assert len(daily_limit_events) > 0, "Should have daily_limit risk events"
        
        event = daily_limit_events[0]
        assert event.severity == 'critical', f"Event severity should be 'critical', got {event.severity}"
        assert event.current_value == excessive_trade_count, f"Current value should be {excessive_trade_count}, got {event.current_value}"
        assert event.threshold_value == config['max_daily_trades'], f"Threshold should be {config['max_daily_trades']}, got {event.threshold_value}"
        assert "일일 거래 횟수 한도 초과" in event.message, f"Event message should mention trade count limit, got: {event.message}"
        assert "거래 중단" in event.action_taken, f"Action should mention trading pause, got: {event.action_taken}"
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_16_volume_limit_enforcement_daily_loss_exceeded(self, data):
        """
        **Feature: upbit-trading-bot, Property 16: Volume Limit Enforcement**
        **Validates: Requirements 5.2**
        
        Property: For any trading session where daily loss exceeds configured limits,
        trading operations should be paused.
        """
        # Generate configuration and portfolio with excessive loss
        config = data.draw(daily_trading_config())
        portfolio, actual_loss_percentage = data.draw(portfolio_snapshot_with_loss())
        
        # Ensure the loss exceeds the configured limit
        assume(actual_loss_percentage > config['daily_loss_limit'])
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        risk_manager.last_portfolio_snapshot = portfolio
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check daily limits
        within_limits = risk_manager.check_daily_limits()
        
        # Property 1: Should return False when daily loss exceeds limit
        assert not within_limits, f"Should return False when daily loss ({actual_loss_percentage:.2%}) exceeds limit ({config['daily_loss_limit']:.2%})"
        
        # Property 2: Trading should be paused
        assert risk_manager.trading_paused, "Trading should be paused when daily loss limit is exceeded"
        
        # Property 3: Pause reason should be set
        assert "일일 손실 한도 초과" in risk_manager.pause_reason, f"Pause reason should mention loss limit, got: {risk_manager.pause_reason}"
        
        # Property 4: Risk event should be triggered
        assert len(triggered_events) > 0, "Risk event should be triggered when loss limit is exceeded"
        
        # Property 5: Event should have correct details
        daily_limit_events = [e for e in triggered_events if e.event_type == 'daily_limit']
        assert len(daily_limit_events) > 0, "Should have daily_limit risk events"
        
        event = daily_limit_events[0]
        assert event.severity == 'critical', f"Event severity should be 'critical', got {event.severity}"
        assert abs(event.current_value - actual_loss_percentage) < 0.001, f"Current value should be {actual_loss_percentage}, got {event.current_value}"
        assert event.threshold_value == config['daily_loss_limit'], f"Threshold should be {config['daily_loss_limit']}, got {event.threshold_value}"
        assert "일일 손실 한도 초과" in event.message, f"Event message should mention loss limit, got: {event.message}"
        assert "거래 중단" in event.action_taken, f"Action should mention trading pause, got: {event.action_taken}"
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_16_volume_limit_enforcement_within_limits(self, data):
        """
        **Feature: upbit-trading-bot, Property 16: Volume Limit Enforcement**
        **Validates: Requirements 5.2**
        
        Property: For any trading session where daily volume is within configured limits,
        trading operations should continue normally.
        """
        # Generate configuration
        config = data.draw(daily_trading_config())
        
        # Generate trade count within limit
        safe_trade_count = data.draw(trade_count_within_limit(config['max_daily_trades']))
        
        # Generate portfolio with acceptable loss
        total_krw_value = data.draw(st.floats(min_value=100000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False))
        safe_loss_percentage = data.draw(st.floats(min_value=0.0, max_value=config['daily_loss_limit'] * 0.9, allow_nan=False, allow_infinity=False))
        
        portfolio = PortfolioSnapshot(
            total_krw_value=total_krw_value,
            total_btc_value=data.draw(st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)),
            positions={'KRW': Position(market='KRW', avg_buy_price=1.0, balance=total_krw_value, locked=0.0, unit_currency='KRW')},
            timestamp=datetime.now(),
            daily_pnl=-total_krw_value * safe_loss_percentage,
            daily_pnl_percentage=-safe_loss_percentage
        )
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        risk_manager.daily_trade_count = safe_trade_count
        risk_manager.last_portfolio_snapshot = portfolio
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check daily limits
        within_limits = risk_manager.check_daily_limits()
        
        # Property 1: Should return True when within limits
        assert within_limits, f"Should return True when trade count ({safe_trade_count}) and loss ({safe_loss_percentage:.2%}) are within limits"
        
        # Property 2: Trading should not be paused
        assert not risk_manager.trading_paused, "Trading should not be paused when within limits"
        
        # Property 3: No daily limit events should be triggered
        daily_limit_events = [e for e in triggered_events if e.event_type == 'daily_limit']
        assert len(daily_limit_events) == 0, f"No daily_limit events should be triggered when within limits, got {len(daily_limit_events)}"
    
    @given(config=daily_trading_config())
    @settings(max_examples=50)
    def test_should_stop_trading_when_daily_limits_exceeded(self, config):
        """Test that should_stop_trading returns True when daily limits are exceeded."""
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        
        # Set trade count to exceed limit
        risk_manager.daily_trade_count = config['max_daily_trades'] + 1
        
        # Mock notification service
        risk_manager.notification_service.send_notification = Mock(return_value=True)
        
        # Check if trading should stop
        should_stop = risk_manager.should_stop_trading()
        
        # Property: Should stop trading when daily limits are exceeded
        assert should_stop, "Should stop trading when daily trade limit is exceeded"
        assert risk_manager.trading_paused, "Trading should be paused"
    
    def test_daily_stats_reset_resumes_trading(self):
        """Test that resetting daily stats resumes trading."""
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        
        # Set up state that would pause trading
        risk_manager.daily_trade_count = 100  # Exceeds limit
        risk_manager.trading_paused = True
        risk_manager.pause_reason = "일일 거래 횟수 한도 초과"
        
        # Reset daily stats
        risk_manager.reset_daily_stats()
        
        # Property 1: Daily trade count should be reset
        assert risk_manager.daily_trade_count == 0, "Daily trade count should be reset to 0"
        
        # Property 2: Daily trade volume should be reset
        assert risk_manager.daily_trade_volume == 0.0, "Daily trade volume should be reset to 0"
        
        # Property 3: Trading should be resumed
        assert not risk_manager.trading_paused, "Trading should be resumed after daily stats reset"
        
        # Property 4: Pause reason should be cleared
        assert risk_manager.pause_reason == "", "Pause reason should be cleared"
        
        # Property 5: Daily start time should be updated
        assert risk_manager.daily_start_time.date() == datetime.now().date(), "Daily start time should be updated to today"
    
    @given(data=st.data())
    @settings(max_examples=50)
    def test_record_trade_updates_daily_stats(self, data):
        """Test that recording trades updates daily statistics correctly."""
        # Generate trade data
        market = data.draw(st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA']))
        side = data.draw(st.sampled_from(['bid', 'ask']))
        volume = data.draw(st.floats(min_value=0.001, max_value=100.0, allow_nan=False, allow_infinity=False))
        price = data.draw(st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False))
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        
        # Record initial state
        initial_trade_count = risk_manager.daily_trade_count
        initial_trade_volume = risk_manager.daily_trade_volume
        
        # Record trade
        risk_manager.record_trade(market, side, volume, price)
        
        # Calculate expected trade value
        expected_trade_value = volume * price
        
        # Property 1: Daily trade count should increase by 1
        assert risk_manager.daily_trade_count == initial_trade_count + 1, \
            f"Daily trade count should increase by 1, expected {initial_trade_count + 1}, got {risk_manager.daily_trade_count}"
        
        # Property 2: Daily trade volume should increase by trade value
        expected_volume = initial_trade_volume + expected_trade_value
        assert abs(risk_manager.daily_trade_volume - expected_volume) < 0.01, \
            f"Daily trade volume should be {expected_volume}, got {risk_manager.daily_trade_volume}"
    
    def test_multiple_limit_checks_consistency(self):
        """Test that multiple calls to check_daily_limits return consistent results."""
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create RiskManager with trade count exceeding limit
        risk_manager = RiskManager(config_manager=mock_config_manager)
        risk_manager.daily_trade_count = 60  # Exceeds limit of 50
        
        # Mock notification service
        risk_manager.notification_service.send_notification = Mock(return_value=True)
        
        # Check limits multiple times
        results = []
        for _ in range(3):
            results.append(risk_manager.check_daily_limits())
        
        # Property: All results should be consistent
        first_result = results[0]
        for i, result in enumerate(results[1:], 1):
            assert result == first_result, f"Daily limit check result {i+1} should match first result"
        
        # Property: All results should be False (exceeds limit)
        for result in results:
            assert not result, "All results should be False when limit is exceeded"
    
    def test_pause_and_resume_trading_functionality(self):
        """Test pause and resume trading functionality."""
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        
        # Initially trading should not be paused
        assert not risk_manager.trading_paused, "Trading should not be paused initially"
        assert risk_manager.pause_reason == "", "Pause reason should be empty initially"
        
        # Pause trading
        test_reason = "테스트 목적으로 거래 중단"
        risk_manager.pause_trading(test_reason)
        
        # Property 1: Trading should be paused
        assert risk_manager.trading_paused, "Trading should be paused after pause_trading call"
        
        # Property 2: Pause reason should be set
        assert risk_manager.pause_reason == test_reason, f"Pause reason should be '{test_reason}', got '{risk_manager.pause_reason}'"
        
        # Resume trading
        risk_manager.resume_trading()
        
        # Property 3: Trading should be resumed
        assert not risk_manager.trading_paused, "Trading should be resumed after resume_trading call"
        
        # Property 4: Pause reason should be cleared
        assert risk_manager.pause_reason == "", "Pause reason should be cleared after resume"
    
    @given(data=st.data())
    @settings(max_examples=30)
    def test_get_risk_status_includes_volume_limits(self, data):
        """Test that get_risk_status includes volume limit information."""
        # Generate configuration and state
        config = data.draw(daily_trading_config())
        trade_count = data.draw(st.integers(min_value=0, max_value=300))
        trade_volume = data.draw(st.floats(min_value=0.0, max_value=10000000.0, allow_nan=False, allow_infinity=False))
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        risk_manager.daily_trade_count = trade_count
        risk_manager.daily_trade_volume = trade_volume
        
        # Get risk status
        status = risk_manager.get_risk_status()
        
        # Property 1: Status should include daily trade count
        assert 'daily_trade_count' in status, "Risk status should include daily_trade_count"
        assert status['daily_trade_count'] == trade_count, f"Daily trade count should be {trade_count}, got {status['daily_trade_count']}"
        
        # Property 2: Status should include max daily trades
        assert 'max_daily_trades' in status, "Risk status should include max_daily_trades"
        assert status['max_daily_trades'] == config['max_daily_trades'], f"Max daily trades should be {config['max_daily_trades']}, got {status['max_daily_trades']}"
        
        # Property 3: Status should include daily trade volume
        assert 'daily_trade_volume' in status, "Risk status should include daily_trade_volume"
        assert abs(status['daily_trade_volume'] - trade_volume) < 0.01, f"Daily trade volume should be {trade_volume}, got {status['daily_trade_volume']}"
        
        # Property 4: Status should include daily loss limit
        assert 'daily_loss_limit' in status, "Risk status should include daily_loss_limit"
        assert status['daily_loss_limit'] == config['daily_loss_limit'], f"Daily loss limit should be {config['daily_loss_limit']}, got {status['daily_loss_limit']}"
        
        # Property 5: Status should include trading pause state
        assert 'trading_paused' in status, "Risk status should include trading_paused"
        assert isinstance(status['trading_paused'], bool), "Trading paused should be boolean"
    
    def test_volume_limit_enforcement_edge_cases(self):
        """Test volume limit enforcement edge cases."""
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 0,  # Edge case: zero trades allowed
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        
        # Mock notification service
        risk_manager.notification_service.send_notification = Mock(return_value=True)
        
        # Property 1: Should immediately pause when max_daily_trades is 0
        within_limits = risk_manager.check_daily_limits()
        assert not within_limits, "Should not be within limits when max_daily_trades is 0"
        assert risk_manager.trading_paused, "Trading should be paused when max_daily_trades is 0"
        
        # Test with exactly at limit
        mock_config_manager.get_section.return_value['max_daily_trades'] = 10
        risk_manager2 = RiskManager(config_manager=mock_config_manager)
        risk_manager2.daily_trade_count = 10  # Exactly at limit
        risk_manager2.notification_service.send_notification = Mock(return_value=True)
        
        # Property 2: Should pause when exactly at limit
        within_limits2 = risk_manager2.check_daily_limits()
        assert not within_limits2, "Should not be within limits when exactly at max_daily_trades"
        assert risk_manager2.trading_paused, "Trading should be paused when exactly at max_daily_trades"