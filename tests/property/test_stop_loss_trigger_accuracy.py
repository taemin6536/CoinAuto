"""Property-based tests for stop-loss trigger accuracy.

**Feature: upbit-trading-bot, Property 15: Stop Loss Trigger Accuracy**
**Validates: Requirements 5.1**
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.risk.manager import RiskManager, PortfolioSnapshot, RiskEvent
from upbit_trading_bot.data.models import Position, Ticker, Account
from upbit_trading_bot.api.client import UpbitAPIClient
from upbit_trading_bot.config.manager import ConfigManager


@composite
def valid_positions(draw):
    """Generate valid positions for testing."""
    # Generate realistic market currencies (excluding KRW)
    currencies = ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'XRP', 'LTC', 'BCH', 'EOS', 'TRX']
    
    market = draw(st.sampled_from(currencies))
    
    # Generate position parameters
    avg_buy_price = draw(st.floats(min_value=100.0, max_value=100000.0, allow_nan=False, allow_infinity=False))
    balance = draw(st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False))
    locked = draw(st.floats(min_value=0.0, max_value=balance * 0.5, allow_nan=False, allow_infinity=False))
    
    return Position(
        market=market,
        avg_buy_price=avg_buy_price,
        balance=balance,
        locked=locked,
        unit_currency='KRW'
    )


@composite
def portfolio_with_positions(draw):
    """Generate portfolio snapshot with positions."""
    # Generate 1-5 positions
    num_positions = draw(st.integers(min_value=1, max_value=5))
    positions = {}
    
    # Always include KRW position
    krw_balance = draw(st.floats(min_value=10000.0, max_value=10000000.0, allow_nan=False, allow_infinity=False))
    krw_locked = draw(st.floats(min_value=0.0, max_value=krw_balance * 0.3, allow_nan=False, allow_infinity=False))
    
    positions['KRW'] = Position(
        market='KRW',
        avg_buy_price=1.0,
        balance=krw_balance,
        locked=krw_locked,
        unit_currency='KRW'
    )
    
    # Add other positions
    used_currencies = {'KRW'}
    for _ in range(num_positions):
        position = draw(valid_positions())
        if position.market not in used_currencies:
            positions[position.market] = position
            used_currencies.add(position.market)
    
    # Calculate total values
    total_krw_value = krw_balance
    for market, pos in positions.items():
        if market != 'KRW':
            total_krw_value += pos.balance * pos.avg_buy_price
    
    total_btc_value = draw(st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False))
    daily_pnl = draw(st.floats(min_value=-total_krw_value * 0.5, max_value=total_krw_value * 0.5, allow_nan=False, allow_infinity=False))
    daily_pnl_percentage = daily_pnl / total_krw_value if total_krw_value > 0 else 0.0
    
    return PortfolioSnapshot(
        total_krw_value=total_krw_value,
        total_btc_value=total_btc_value,
        positions=positions,
        timestamp=datetime.now(),
        daily_pnl=daily_pnl,
        daily_pnl_percentage=daily_pnl_percentage
    )


@composite
def stop_loss_config(draw):
    """Generate stop-loss configuration."""
    return {
        'stop_loss_percentage': draw(st.floats(min_value=0.01, max_value=0.20, allow_nan=False, allow_infinity=False)),  # 1-20%
        'daily_loss_limit': draw(st.floats(min_value=0.05, max_value=0.50, allow_nan=False, allow_infinity=False)),  # 5-50%
        'max_daily_trades': draw(st.integers(min_value=10, max_value=200)),
        'min_balance_threshold': draw(st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False)),
        'position_size_limit': draw(st.floats(min_value=0.05, max_value=0.50, allow_nan=False, allow_infinity=False))
    }


@composite
def current_prices_triggering_stop_loss(draw, positions, stop_loss_percentage):
    """Generate current prices that should trigger stop-loss."""
    prices = {}
    
    for market, position in positions.items():
        if market == 'KRW' or position.balance <= 0:
            continue
        
        # Calculate stop-loss price
        stop_loss_price = position.avg_buy_price * (1 - stop_loss_percentage)
        
        # Generate current price that triggers stop-loss (below stop-loss price)
        trigger_multiplier = draw(st.floats(min_value=0.5, max_value=0.99, allow_nan=False, allow_infinity=False))
        current_price = stop_loss_price * trigger_multiplier
        
        # Ensure current price is actually below stop-loss price
        assume(current_price <= stop_loss_price)
        
        prices[f"KRW-{market}"] = Ticker(
            market=f"KRW-{market}",
            trade_price=current_price,
            trade_volume=draw(st.floats(min_value=1.0, max_value=1000000.0, allow_nan=False, allow_infinity=False)),
            timestamp=datetime.now(),
            change_rate=draw(st.floats(min_value=-0.30, max_value=0.30, allow_nan=False, allow_infinity=False))
        )
    
    return prices


@composite
def current_prices_not_triggering_stop_loss(draw, positions, stop_loss_percentage):
    """Generate current prices that should NOT trigger stop-loss."""
    prices = {}
    
    for market, position in positions.items():
        if market == 'KRW' or position.balance <= 0:
            continue
        
        # Calculate stop-loss price
        stop_loss_price = position.avg_buy_price * (1 - stop_loss_percentage)
        
        # Generate current price that does NOT trigger stop-loss (above stop-loss price)
        safe_multiplier = draw(st.floats(min_value=1.01, max_value=2.0, allow_nan=False, allow_infinity=False))
        current_price = stop_loss_price * safe_multiplier
        
        # Ensure current price is actually above stop-loss price
        assume(current_price > stop_loss_price)
        
        prices[f"KRW-{market}"] = Ticker(
            market=f"KRW-{market}",
            trade_price=current_price,
            trade_volume=draw(st.floats(min_value=1.0, max_value=1000000.0, allow_nan=False, allow_infinity=False)),
            timestamp=datetime.now(),
            change_rate=draw(st.floats(min_value=-0.30, max_value=0.30, allow_nan=False, allow_infinity=False))
        )
    
    return prices


class TestStopLossTriggerAccuracy:
    """Property-based tests for stop-loss trigger accuracy."""
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_15_stop_loss_trigger_accuracy_should_trigger(self, data):
        """
        **Feature: upbit-trading-bot, Property 15: Stop Loss Trigger Accuracy**
        **Validates: Requirements 5.1**
        
        Property: For any portfolio state where losses exceed the configured stop-loss percentage,
        emergency sell orders should be triggered.
        """
        # Generate portfolio and configuration
        portfolio = data.draw(portfolio_with_positions())
        config = data.draw(stop_loss_config())
        
        # Filter out positions with zero balance
        active_positions = {k: v for k, v in portfolio.positions.items() 
                          if k != 'KRW' and v.balance > 0}
        
        # Skip if no active positions
        assume(len(active_positions) > 0)
        
        # Generate current prices that should trigger stop-loss
        current_prices = data.draw(current_prices_triggering_stop_loss(active_positions, config['stop_loss_percentage']))
        
        # Skip if no prices generated
        assume(len(current_prices) > 0)
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        def mock_get_ticker(market):
            if market in current_prices:
                return current_prices[market]
            else:
                # Return a default ticker for markets not in our test data
                return Ticker(
                    market=market,
                    trade_price=50000.0,
                    trade_volume=1000.0,
                    timestamp=datetime.now(),
                    change_rate=0.0
                )
        
        mock_api_client.get_ticker.side_effect = mock_get_ticker
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        risk_manager.last_portfolio_snapshot = portfolio
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check stop-loss triggers
        should_stop = risk_manager._check_stop_loss_triggers()
        
        # Property 1: Should trigger stop-loss when current price is below stop-loss price
        assert should_stop, "Stop-loss should be triggered when current prices are below stop-loss thresholds"
        
        # Property 2: Risk events should be generated for triggered positions
        assert len(triggered_events) > 0, "Risk events should be generated when stop-loss is triggered"
        
        # Property 3: All triggered events should be stop-loss events
        for event in triggered_events:
            assert event.event_type == 'stop_loss', f"Event type should be 'stop_loss', got {event.event_type}"
            assert event.severity == 'critical', f"Stop-loss events should have 'critical' severity, got {event.severity}"
            assert event.market is not None, "Stop-loss events should specify the market"
            assert event.current_value is not None, "Stop-loss events should include current price"
            assert event.threshold_value is not None, "Stop-loss events should include stop-loss threshold"
            assert "손절매 트리거" in event.message, "Event message should indicate stop-loss trigger"
        
        # Property 4: Current price should be at or below stop-loss price for triggered positions
        for event in triggered_events:
            if event.market:
                market_currency = event.market.split('-')[1]  # KRW-BTC -> BTC
                if market_currency in active_positions:
                    position = active_positions[market_currency]
                    expected_stop_loss = position.avg_buy_price * (1 - config['stop_loss_percentage'])
                    
                    assert event.current_value <= expected_stop_loss, \
                        f"Current price {event.current_value} should be <= stop-loss price {expected_stop_loss}"
                    assert abs(event.threshold_value - expected_stop_loss) < 0.01, \
                        f"Threshold value {event.threshold_value} should match calculated stop-loss {expected_stop_loss}"
    
    @given(data=st.data())
    @settings(max_examples=100)
    def test_property_15_stop_loss_trigger_accuracy_should_not_trigger(self, data):
        """
        **Feature: upbit-trading-bot, Property 15: Stop Loss Trigger Accuracy**
        **Validates: Requirements 5.1**
        
        Property: For any portfolio state where current prices are above stop-loss thresholds,
        stop-loss should NOT be triggered.
        """
        # Generate portfolio and configuration
        portfolio = data.draw(portfolio_with_positions())
        config = data.draw(stop_loss_config())
        
        # Filter out positions with zero balance
        active_positions = {k: v for k, v in portfolio.positions.items() 
                          if k != 'KRW' and v.balance > 0}
        
        # Skip if no active positions
        assume(len(active_positions) > 0)
        
        # Generate current prices that should NOT trigger stop-loss
        current_prices = data.draw(current_prices_not_triggering_stop_loss(active_positions, config['stop_loss_percentage']))
        
        # Skip if no prices generated
        assume(len(current_prices) > 0)
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        def mock_get_ticker(market):
            if market in current_prices:
                return current_prices[market]
            else:
                # Return a safe default ticker
                return Ticker(
                    market=market,
                    trade_price=100000.0,  # High price that won't trigger stop-loss
                    trade_volume=1000.0,
                    timestamp=datetime.now(),
                    change_rate=0.0
                )
        
        mock_api_client.get_ticker.side_effect = mock_get_ticker
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        risk_manager.last_portfolio_snapshot = portfolio
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Check stop-loss triggers
        should_stop = risk_manager._check_stop_loss_triggers()
        
        # Property 1: Should NOT trigger stop-loss when current prices are above stop-loss thresholds
        assert not should_stop, "Stop-loss should NOT be triggered when current prices are above stop-loss thresholds"
        
        # Property 2: No stop-loss risk events should be generated
        stop_loss_events = [e for e in triggered_events if e.event_type == 'stop_loss']
        assert len(stop_loss_events) == 0, f"No stop-loss events should be generated, but got {len(stop_loss_events)}"
        
        # Property 3: Current price should be above stop-loss price for all positions
        for market, ticker in current_prices.items():
            market_currency = market.split('-')[1]  # KRW-BTC -> BTC
            if market_currency in active_positions:
                position = active_positions[market_currency]
                expected_stop_loss = position.avg_buy_price * (1 - config['stop_loss_percentage'])
                
                assert ticker.trade_price > expected_stop_loss, \
                    f"Current price {ticker.trade_price} should be > stop-loss price {expected_stop_loss} for {market}"
    
    @given(position=valid_positions(), config=stop_loss_config())
    @settings(max_examples=50)
    def test_stop_loss_calculation_accuracy(self, position, config):
        """Test that stop-loss price calculation is accurate."""
        # Skip positions with zero balance
        assume(position.balance > 0)
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager)
        
        # Calculate stop-loss price
        stop_loss_price = risk_manager.calculate_stop_loss(position)
        
        # Property 1: Stop-loss price should be calculated correctly
        expected_stop_loss = position.avg_buy_price * (1 - config['stop_loss_percentage'])
        assert abs(stop_loss_price - expected_stop_loss) < 0.0001, \
            f"Stop-loss calculation incorrect: expected {expected_stop_loss}, got {stop_loss_price}"
        
        # Property 2: Stop-loss price should be less than average buy price
        assert stop_loss_price < position.avg_buy_price, \
            f"Stop-loss price {stop_loss_price} should be less than avg buy price {position.avg_buy_price}"
        
        # Property 3: Stop-loss price should be positive
        assert stop_loss_price > 0, f"Stop-loss price should be positive, got {stop_loss_price}"
        
        # Property 4: Stop-loss percentage should be applied correctly
        actual_percentage = (position.avg_buy_price - stop_loss_price) / position.avg_buy_price
        assert abs(actual_percentage - config['stop_loss_percentage']) < 0.0001, \
            f"Stop-loss percentage incorrect: expected {config['stop_loss_percentage']}, got {actual_percentage}"
    
    def test_stop_loss_zero_balance_position(self):
        """Test stop-loss calculation for positions with zero balance."""
        # Create position with zero balance
        position = Position(
            market='BTC',
            avg_buy_price=50000.0,
            balance=0.0,
            locked=0.0,
            unit_currency='KRW'
        )
        
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
        
        # Calculate stop-loss price
        stop_loss_price = risk_manager.calculate_stop_loss(position)
        
        # Property: Should return 0 for zero balance positions
        assert stop_loss_price == 0.0, f"Stop-loss price should be 0 for zero balance positions, got {stop_loss_price}"
    
    def test_stop_loss_api_error_handling(self):
        """Test stop-loss trigger behavior when API calls fail."""
        # Create portfolio with positions
        positions = {
            'KRW': Position(market='KRW', avg_buy_price=1.0, balance=1000000.0, locked=0.0, unit_currency='KRW'),
            'BTC': Position(market='BTC', avg_buy_price=50000.0, balance=1.0, locked=0.0, unit_currency='KRW')
        }
        
        portfolio = PortfolioSnapshot(
            total_krw_value=1050000.0,
            total_btc_value=1.0,
            positions=positions,
            timestamp=datetime.now(),
            daily_pnl=0.0,
            daily_pnl_percentage=0.0
        )
        
        # Create mock API client that raises exception
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_ticker.side_effect = Exception("API connection failed")
        
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
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        risk_manager.last_portfolio_snapshot = portfolio
        
        # Check stop-loss triggers
        should_stop = risk_manager._check_stop_loss_triggers()
        
        # Property: Should handle API errors gracefully and not trigger stop-loss
        assert not should_stop, "Should not trigger stop-loss when API calls fail"
    
    def test_stop_loss_no_portfolio_snapshot(self):
        """Test stop-loss trigger behavior when no portfolio snapshot is available."""
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create RiskManager without portfolio snapshot
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        risk_manager.last_portfolio_snapshot = None
        
        # Check stop-loss triggers
        should_stop = risk_manager._check_stop_loss_triggers()
        
        # Property: Should not trigger stop-loss when no portfolio snapshot is available
        assert not should_stop, "Should not trigger stop-loss when no portfolio snapshot is available"
    
    def test_stop_loss_no_api_client(self):
        """Test stop-loss trigger behavior when no API client is available."""
        # Create portfolio with positions
        positions = {
            'KRW': Position(market='KRW', avg_buy_price=1.0, balance=1000000.0, locked=0.0, unit_currency='KRW'),
            'BTC': Position(market='BTC', avg_buy_price=50000.0, balance=1.0, locked=0.0, unit_currency='KRW')
        }
        
        portfolio = PortfolioSnapshot(
            total_krw_value=1050000.0,
            total_btc_value=1.0,
            positions=positions,
            timestamp=datetime.now(),
            daily_pnl=0.0,
            daily_pnl_percentage=0.0
        )
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create RiskManager without API client
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=None)
        risk_manager.last_portfolio_snapshot = portfolio
        
        # Check stop-loss triggers
        should_stop = risk_manager._check_stop_loss_triggers()
        
        # Property: Should not trigger stop-loss when no API client is available
        assert not should_stop, "Should not trigger stop-loss when no API client is available"
    
    @given(data=st.data())
    @settings(max_examples=30)
    def test_stop_loss_trigger_consistency(self, data):
        """Test that stop-loss trigger results are consistent across multiple calls."""
        # Generate portfolio and configuration
        portfolio = data.draw(portfolio_with_positions())
        config = data.draw(stop_loss_config())
        
        # Filter out positions with zero balance
        active_positions = {k: v for k, v in portfolio.positions.items() 
                          if k != 'KRW' and v.balance > 0}
        
        # Skip if no active positions
        assume(len(active_positions) > 0)
        
        # Generate consistent current prices
        current_prices = data.draw(current_prices_triggering_stop_loss(active_positions, config['stop_loss_percentage']))
        assume(len(current_prices) > 0)
        
        # Create mock API client with consistent responses
        mock_api_client = Mock(spec=UpbitAPIClient)
        
        def mock_get_ticker(market):
            if market in current_prices:
                return current_prices[market]
            else:
                return Ticker(market=market, trade_price=50000.0, trade_volume=1000.0, 
                            timestamp=datetime.now(), change_rate=0.0)
        
        mock_api_client.get_ticker.side_effect = mock_get_ticker
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = config
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        risk_manager.last_portfolio_snapshot = portfolio
        
        # Check stop-loss triggers multiple times
        results = []
        for _ in range(3):
            results.append(risk_manager._check_stop_loss_triggers())
        
        # Property: All results should be consistent
        first_result = results[0]
        for i, result in enumerate(results[1:], 1):
            assert result == first_result, f"Stop-loss trigger result {i+1} should match first result"
    
    def test_stop_loss_event_details(self):
        """Test that stop-loss events contain correct details."""
        # Create specific test case
        position = Position(
            market='BTC',
            avg_buy_price=50000.0,
            balance=1.0,
            locked=0.0,
            unit_currency='KRW'
        )
        
        positions = {
            'KRW': Position(market='KRW', avg_buy_price=1.0, balance=1000000.0, locked=0.0, unit_currency='KRW'),
            'BTC': position
        }
        
        portfolio = PortfolioSnapshot(
            total_krw_value=1050000.0,
            total_btc_value=1.0,
            positions=positions,
            timestamp=datetime.now(),
            daily_pnl=0.0,
            daily_pnl_percentage=0.0
        )
        
        # Create current price that triggers stop-loss
        stop_loss_percentage = 0.05
        stop_loss_price = position.avg_buy_price * (1 - stop_loss_percentage)  # 47,500
        current_price = stop_loss_price * 0.9  # 42,750 (below stop-loss)
        
        current_ticker = Ticker(
            market='KRW-BTC',
            trade_price=current_price,
            trade_volume=1000.0,
            timestamp=datetime.now(),
            change_rate=-0.15
        )
        
        # Create mock API client
        mock_api_client = Mock(spec=UpbitAPIClient)
        mock_api_client.get_ticker.return_value = current_ticker
        
        # Create mock config manager
        mock_config_manager = Mock(spec=ConfigManager)
        mock_config_manager.get_section.return_value = {
            'stop_loss_percentage': stop_loss_percentage,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        
        # Create RiskManager
        risk_manager = RiskManager(config_manager=mock_config_manager, api_client=mock_api_client)
        risk_manager.last_portfolio_snapshot = portfolio
        
        # Mock notification service to capture events
        triggered_events = []
        def mock_send_notification(event):
            triggered_events.append(event)
            return True
        
        risk_manager.notification_service.send_notification = mock_send_notification
        
        # Trigger stop-loss check
        should_stop = risk_manager._check_stop_loss_triggers()
        
        # Verify results
        assert should_stop, "Stop-loss should be triggered"
        assert len(triggered_events) == 1, "Exactly one stop-loss event should be generated"
        
        event = triggered_events[0]
        
        # Property: Event should contain correct details
        assert event.event_type == 'stop_loss', f"Event type should be 'stop_loss', got {event.event_type}"
        assert event.severity == 'critical', f"Severity should be 'critical', got {event.severity}"
        assert event.market == 'KRW-BTC', f"Market should be 'KRW-BTC', got {event.market}"
        assert event.current_value == current_price, f"Current value should be {current_price}, got {event.current_value}"
        assert abs(event.threshold_value - stop_loss_price) < 0.01, f"Threshold should be {stop_loss_price}, got {event.threshold_value}"
        assert "손절매 트리거" in event.message, f"Message should contain '손절매 트리거', got {event.message}"
        assert "긴급 매도 주문 생성" in event.action_taken, f"Action should mention emergency sell order, got {event.action_taken}"
        assert isinstance(event.timestamp, datetime), "Timestamp should be datetime object"