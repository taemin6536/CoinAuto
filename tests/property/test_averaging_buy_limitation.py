"""
Property-based tests for stop-loss averaging strategy averaging buy limitation.

**Feature: stop-loss-averaging-strategy, Property 4: 물타기 후 추가 매수 제한**
**Validates: Requirements 1.4**

Tests that after averaging down, no additional buy signals should be generated
when the price continues to decline.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings, HealthCheck
from datetime import datetime, timedelta
from decimal import Decimal

from upbit_trading_bot.strategy.stop_loss_averaging import StopLossAveragingStrategy
from upbit_trading_bot.strategy.base import MarketData
from upbit_trading_bot.data.models import Ticker, StopLossAveragingSignal


# Test data generators
@st.composite
def generate_market_data(draw):
    """Generate realistic market data for testing."""
    market = draw(st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA']))
    
    # Generate base price
    base_price = draw(st.floats(min_value=1000, max_value=100000, allow_nan=False, allow_infinity=False))
    
    # Generate price history with realistic variations
    history_length = draw(st.integers(min_value=50, max_value=100))
    price_history = []
    current_price = base_price
    
    for _ in range(history_length):
        # Small random variations (-2% to +2%)
        variation = draw(st.floats(min_value=-0.02, max_value=0.02, allow_nan=False, allow_infinity=False))
        current_price = current_price * (1 + variation)
        current_price = max(current_price, 100)  # Minimum price
        price_history.append(current_price)
    
    # Generate volume data
    volume_history = [
        draw(st.floats(min_value=1000, max_value=1000000, allow_nan=False, allow_infinity=False))
        for _ in range(history_length)
    ]
    
    # Generate timestamps
    base_time = datetime.now() - timedelta(minutes=history_length)
    timestamps = [base_time + timedelta(minutes=i) for i in range(history_length)]
    
    # Create current ticker
    current_ticker = Ticker(
        market=market,
        trade_price=price_history[-1],
        trade_volume=volume_history[-1],
        timestamp=timestamps[-1],
        change_rate=draw(st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False))
    )
    
    return MarketData(
        current_ticker=current_ticker,
        price_history=price_history,
        volume_history=volume_history,
        timestamps=timestamps
    )


@st.composite
def generate_strategy_config(draw):
    """Generate valid strategy configuration."""
    # Ensure stop_loss_level is more negative than averaging_trigger
    averaging_trigger = draw(st.floats(min_value=-2.0, max_value=-0.5))
    stop_loss_level = draw(st.floats(min_value=-5.0, max_value=averaging_trigger - 0.5))  # Always more negative
    
    return {
        'parameters': {
            'stop_loss_level': stop_loss_level,
            'averaging_trigger': averaging_trigger,
            'target_profit': draw(st.floats(min_value=0.2, max_value=2.0)),
            'max_averaging_count': draw(st.integers(min_value=1, max_value=3)),
            'trading_fee': 0.0005,
            'monitoring_interval': draw(st.integers(min_value=5, max_value=60)),
            'market_analyzer': {
                'volatility_threshold': 5.0,
                'volume_ratio_threshold': 1.5,
                'rapid_decline_threshold': -2.0,
                'rsi_oversold_threshold': 30,
                'market_decline_threshold': -3.0
            },
            'risk_controller': {
                'daily_loss_limit': 10000.0,
                'consecutive_loss_limit': 3,
                'min_balance_threshold': 5000.0
            }
        }
    }


class TestAveragingBuyLimitation:
    """Property-based tests for averaging buy limitation."""
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_averaging_buy_limitation_property(self, market_data, config):
        """
        **Feature: stop-loss-averaging-strategy, Property 4: 물타기 후 추가 매수 제한**
        **Validates: Requirements 1.4**
        
        Property: After averaging down, no additional buy signals should be generated
        when the price continues to decline.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create initial position by simulating first buy
        initial_price = market_data.price_history[-1]
        initial_quantity = 0.1
        
        # Add initial position to strategy
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        # Verify position was added
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position is not None)
        assume(position.total_quantity > 0)
        
        # Calculate averaging trigger price
        averaging_price = initial_price * (1 + strategy.averaging_trigger / 100)
        
        # Ensure averaging price is lower than initial price
        assume(averaging_price < initial_price * 0.995)  # At least 0.5% drop
        
        # Add averaging position to simulate first averaging down
        strategy.position_manager.add_averaging_position(
            market_data.current_ticker.market,
            averaging_price,
            initial_quantity
        )
        
        # Verify averaging position was added
        position_after_averaging = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position_after_averaging is not None)
        assume(len(position_after_averaging.entries) >= 2)  # Initial + averaging
        
        # Check that we've reached the max averaging count
        averaging_entries = [entry for entry in position_after_averaging.entries if entry.order_type == 'averaging']
        assume(len(averaging_entries) >= strategy.max_averaging_count)
        
        # Create market data with price continuing to decline (further averaging trigger)
        further_decline_price = averaging_price * 0.98  # Additional 2% decline
        
        # Ensure this price would normally trigger averaging but shouldn't due to limit
        assume(further_decline_price < position_after_averaging.average_price)
        
        further_decline_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=further_decline_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=((further_decline_price - initial_price) / initial_price)
            ),
            price_history=market_data.price_history + [averaging_price, further_decline_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume] * 2,
            timestamps=market_data.timestamps + [datetime.now()] * 2
        )
        
        # Act
        signal = strategy.evaluate(further_decline_market_data)
        
        # Assert
        if signal is not None:
            # If a signal is generated, it should NOT be an averaging buy signal
            assert isinstance(signal, StopLossAveragingSignal)
            assert signal.signal_reason != 'averaging', \
                f"Should not generate averaging signal after max averaging count reached. Got: {signal.signal_reason}"
            
            # It could be a stop loss signal if the decline is severe enough
            if signal.action == 'buy':
                assert False, f"Should not generate any buy signal after max averaging count reached"
        
        # Additional verification: Check averaging logic directly
        current_pnl_info = strategy._calculate_position_pnl(further_decline_price, position_after_averaging)
        if current_pnl_info:
            current_pnl_percent = current_pnl_info['pnl_rate']
            
            # Even if the price decline would normally trigger averaging, it should be blocked
            should_average = strategy._should_average_down(current_pnl_percent, position_after_averaging)
            assert not should_average, \
                "Should not allow averaging down after max averaging count reached"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_averaging_allowed_before_limit(self, market_data, config):
        """
        Test that averaging is allowed before reaching the maximum count.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        assume(strategy.max_averaging_count > 1)  # Need room for averaging
        
        # Create initial position
        initial_price = market_data.price_history[-1]
        initial_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        # Verify position was added
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position is not None)
        
        # Calculate averaging trigger price
        averaging_price = initial_price * (1 + strategy.averaging_trigger / 100)
        assume(averaging_price < initial_price * 0.995)  # At least 0.5% drop
        
        # Test averaging logic before reaching limit
        current_pnl_percent = ((averaging_price - initial_price) / initial_price) * 100
        
        # Should allow averaging when under the limit
        should_average = strategy._should_average_down(current_pnl_percent, position)
        
        # If the PnL triggers averaging and we're under the limit, it should be allowed
        if current_pnl_percent <= strategy.averaging_trigger:
            assert should_average, \
                "Should allow averaging down when under max averaging count and trigger conditions are met"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_max_averaging_count_enforcement(self, market_data, config):
        """
        Test that the max averaging count is properly enforced.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create initial position
        initial_price = market_data.price_history[-1]
        initial_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position is not None)
        
        # Add averaging positions up to the maximum count
        current_price = initial_price
        for i in range(strategy.max_averaging_count):
            current_price = current_price * 0.99  # 1% decline each time
            strategy.position_manager.add_averaging_position(
                market_data.current_ticker.market,
                current_price,
                initial_quantity
            )
        
        # Verify we've reached the maximum
        final_position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(final_position is not None)
        
        averaging_entries = [entry for entry in final_position.entries if entry.order_type == 'averaging']
        assert len(averaging_entries) == strategy.max_averaging_count, \
            f"Should have exactly {strategy.max_averaging_count} averaging entries"
        
        # Test that further averaging is blocked
        further_decline_price = current_price * 0.99  # Another 1% decline
        further_decline_pnl = ((further_decline_price - final_position.average_price) / final_position.average_price) * 100
        
        should_average = strategy._should_average_down(further_decline_pnl, final_position)
        assert not should_average, \
            "Should not allow averaging down after reaching max averaging count"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_averaging_count_reset_after_position_close(self, market_data, config):
        """
        Test that averaging count is reset after position is closed.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create and close a position with averaging
        initial_price = market_data.price_history[-1]
        initial_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        # Add one averaging position
        averaging_price = initial_price * 0.99
        strategy.position_manager.add_averaging_position(
            market_data.current_ticker.market,
            averaging_price,
            initial_quantity
        )
        
        # Close the position (simulate sell)
        strategy.position_manager.close_position(market_data.current_ticker.market)
        
        # Verify position is closed
        closed_position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assert closed_position is None, "Position should be closed"
        
        # Create new position
        new_initial_price = market_data.price_history[-1] * 1.01  # Slightly higher price
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            new_initial_price,
            initial_quantity
        )
        
        new_position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(new_position is not None)
        
        # Test that averaging is allowed again (count was reset)
        new_averaging_price = new_initial_price * (1 + strategy.averaging_trigger / 100)
        new_pnl_percent = ((new_averaging_price - new_initial_price) / new_initial_price) * 100
        
        should_average = strategy._should_average_down(new_pnl_percent, new_position)
        
        # If conditions are met, averaging should be allowed again
        if new_pnl_percent <= strategy.averaging_trigger:
            assert should_average, \
                "Should allow averaging down for new position (count should be reset)"