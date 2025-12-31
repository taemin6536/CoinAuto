"""
Property-based tests for stop-loss averaging strategy state reset after sell.

**Feature: stop-loss-averaging-strategy, Property 5: 매도 후 상태 초기화**
**Validates: Requirements 1.5**

Tests that after a sell is completed, the strategy transitions to a state
where it can explore new buy opportunities.
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


class TestStateResetAfterSell:
    """Property-based tests for state reset after sell."""
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_state_reset_after_sell_property(self, market_data, config):
        """
        **Feature: stop-loss-averaging-strategy, Property 5: 매도 후 상태 초기화**
        **Validates: Requirements 1.5**
        
        Property: After a sell is completed, the strategy transitions to a state
        where it can explore new buy opportunities.
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
        position_before = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position_before is not None)
        assume(position_before.total_quantity > 0)
        
        # Simulate a complete sell by closing the position
        strategy.position_manager.close_position(market_data.current_ticker.market)
        
        # Verify position is closed
        position_after_sell = strategy.position_manager.get_position(market_data.current_ticker.market)
        assert position_after_sell is None, "Position should be closed after sell"
        
        # Reset any managers that might have state
        strategy._reset_managers()
        
        # Create new market data for potential new buy opportunity
        new_buy_price = initial_price * 1.02  # 2% higher than original
        
        new_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=new_buy_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=0.02  # 2% positive change
            ),
            price_history=market_data.price_history + [new_buy_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act - Evaluate strategy for new buy opportunity
        signal = strategy.evaluate(new_market_data)
        
        # Assert - Strategy should be able to explore new buy opportunities
        # The strategy should not be blocked by previous position state
        
        # Verify that the strategy can evaluate without errors
        # (This tests that internal state has been properly reset)
        
        # Check that position manager is clean
        assert strategy.position_manager.get_position_count() == 0, \
            "Position manager should have no positions after sell"
        
        # Check that partial sell manager is reset
        next_sell_level = strategy.partial_sell_manager.get_next_sell_level()
        assert next_sell_level is not None, \
            "Partial sell manager should be reset to initial state"
        
        # Check that trailing stop manager is reset
        assert not strategy.trailing_stop_manager.is_activated(), \
            "Trailing stop manager should be reset (not activated)"
        
        # If a signal is generated, it should be for a new opportunity, not related to old position
        if signal is not None:
            assert isinstance(signal, StopLossAveragingSignal)
            # Should not reference old position
            if signal.position_info is not None:
                # If position_info exists, it should be for a new position, not the old one
                assert signal.position_info != position_before.to_dict(), \
                    "Signal should not reference old position after sell"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_managers_reset_after_position_close(self, market_data, config):
        """
        Test that all managers are properly reset after position close.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create position and simulate some activity
        initial_price = market_data.price_history[-1]
        initial_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        # Simulate partial sell activity
        profit_price = initial_price * 1.01  # 1% profit
        strategy.partial_sell_manager.should_partial_sell(1.0)  # Trigger some activity
        
        # Simulate trailing stop activity
        high_profit_price = initial_price * 1.05  # 5% profit
        strategy.trailing_stop_manager.update_high_price(high_profit_price)
        
        # Close position
        strategy.position_manager.close_position(market_data.current_ticker.market)
        
        # Reset managers
        strategy._reset_managers()
        
        # Assert managers are reset
        # Partial sell manager should be reset
        assert strategy.partial_sell_manager.get_next_sell_level() is not None, \
            "Partial sell manager should be reset"
        
        # Trailing stop manager should be reset
        assert not strategy.trailing_stop_manager.is_activated(), \
            "Trailing stop manager should be deactivated"
        assert strategy.trailing_stop_manager.get_stop_price() is None, \
            "Trailing stop price should be reset to None"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_new_position_independent_of_old(self, market_data, config):
        """
        Test that new positions are independent of old positions.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create and close first position
        first_price = market_data.price_history[-1]
        first_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            first_price,
            first_quantity
        )
        
        first_position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(first_position is not None)
        
        # Close first position
        strategy.position_manager.close_position(market_data.current_ticker.market)
        strategy._reset_managers()
        
        # Create second position with different parameters
        second_price = first_price * 1.1  # 10% higher
        second_quantity = 0.2  # Different quantity
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            second_price,
            second_quantity
        )
        
        second_position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(second_position is not None)
        
        # Assert new position is independent
        assert second_position.average_price == second_price, \
            "New position should have its own average price"
        assert second_position.total_quantity == second_quantity, \
            "New position should have its own quantity"
        assert len(second_position.entries) == 1, \
            "New position should start with one entry"
        assert second_position.entries[0].order_type == 'initial', \
            "New position should start with initial entry type"
        
        # Verify no remnants of old position (allow for floating point precision)
        expected_cost = second_price * second_quantity
        assert abs(second_position.total_cost - expected_cost) < 0.01, \
            f"New position cost should be calculated independently. Expected: {expected_cost}, Got: {second_position.total_cost}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_strategy_state_clean_after_sell(self, market_data, config):
        """
        Test that strategy state is clean after sell completion.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create position
        initial_price = market_data.price_history[-1]
        initial_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        # Simulate trade completion (this would normally be called by the trading system)
        strategy.update_position_after_trade(
            market_data.current_ticker.market,
            'sell',
            initial_price * 1.01,  # Sell at 1% profit
            initial_quantity
        )
        
        # Assert strategy state is clean
        position_after_trade = strategy.position_manager.get_position(market_data.current_ticker.market)
        assert position_after_trade is None, \
            "Position should be None after complete sell"
        
        # Check that position count is zero
        assert strategy.position_manager.get_position_count() == 0, \
            "Position count should be zero after sell"
        
        # Verify managers are reset
        assert not strategy.trailing_stop_manager.is_activated(), \
            "Trailing stop should be deactivated after sell"
        
        # Strategy should be ready for new opportunities
        strategy_info = strategy.get_strategy_info()
        assert strategy_info['position_count'] == 0, \
            "Strategy info should show zero positions"