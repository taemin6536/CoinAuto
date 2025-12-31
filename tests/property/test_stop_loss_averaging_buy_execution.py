"""
Property-based tests for stop-loss averaging strategy buy execution.

**Feature: stop-loss-averaging-strategy, Property 1: 물타기 매수 실행**
**Validates: Requirements 1.1**

Tests that for any initial buy position, when price drops by -1%, 
an additional buy with the same amount should be executed.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
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


class TestStopLossAveragingBuyExecution:
    """Property-based tests for averaging down buy execution."""
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=100, deadline=5000)
    def test_averaging_buy_execution_property(self, market_data, config):
        """
        **Feature: stop-loss-averaging-strategy, Property 1: 물타기 매수 실행**
        **Validates: Requirements 1.1**
        
        Property: For any initial buy position, when price drops by -1% (averaging trigger),
        an additional buy with the same amount should be executed.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create initial position by simulating first buy
        initial_price = market_data.current_ticker.trade_price
        initial_quantity = 0.1
        
        # Add initial position to strategy
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        # Calculate price that triggers averaging (averaging_trigger% drop)
        averaging_trigger_price = initial_price * (1 + strategy.averaging_trigger / 100)
        
        # Create market data with price at averaging trigger level
        triggered_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=averaging_trigger_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=strategy.averaging_trigger / 100
            ),
            price_history=market_data.price_history + [averaging_trigger_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(triggered_market_data)
        
        # Assert
        if signal is not None:
            # If a signal is generated, it should be a buy signal for averaging
            assert isinstance(signal, StopLossAveragingSignal)
            assert signal.action == 'buy'
            assert signal.signal_reason == 'averaging'
            
            # The volume should be similar to initial quantity (same amount)
            # Allow for small differences due to floating point precision
            volume_ratio = signal.volume / initial_quantity
            assert 0.9 <= volume_ratio <= 1.1, f"Averaging volume should be similar to initial quantity"
            
            # Price should be at or near the averaging trigger price
            price_diff_percent = abs(signal.price - averaging_trigger_price) / averaging_trigger_price * 100
            assert price_diff_percent < 1.0, f"Signal price should be close to current market price"
        
        # Additional verification: Check that position allows averaging
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        if position:
            # Calculate current PnL
            pnl_info = strategy.position_manager.get_position_pnl(
                market_data.current_ticker.market, 
                averaging_trigger_price
            )
            
            if pnl_info:
                current_pnl_percent = pnl_info['pnl_rate']
                
                # If PnL is at averaging trigger level and max averaging not reached,
                # averaging should be allowed
                averaging_entries = [e for e in position.entries if e.order_type == 'averaging']
                max_averaging_not_reached = len(averaging_entries) < strategy.max_averaging_count
                
                if (current_pnl_percent <= strategy.averaging_trigger and 
                    max_averaging_not_reached and 
                    not strategy.strategy_state.is_suspended):
                    
                    # Strategy should generate averaging signal
                    assert signal is not None, "Strategy should generate averaging signal when conditions are met"
                    assert signal.action == 'buy', "Signal should be a buy signal"
                    assert signal.signal_reason == 'averaging', "Signal reason should be averaging"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000)
    def test_no_averaging_when_max_count_reached(self, market_data, config):
        """
        Test that no averaging signal is generated when max averaging count is reached.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create initial position
        initial_price = market_data.current_ticker.trade_price
        initial_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        # Add maximum number of averaging positions
        for i in range(strategy.max_averaging_count):
            averaging_price = initial_price * (1 - 0.01 * (i + 1))  # Each 1% lower
            strategy.position_manager.add_averaging_position(
                market_data.current_ticker.market,
                averaging_price,
                initial_quantity
            )
        
        # Create market data with price that would normally trigger averaging
        averaging_trigger_price = initial_price * (1 + strategy.averaging_trigger / 100)
        
        triggered_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=averaging_trigger_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=strategy.averaging_trigger / 100
            ),
            price_history=market_data.price_history + [averaging_trigger_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(triggered_market_data)
        
        # Assert
        # Should not generate averaging signal when max count is reached
        if signal is not None:
            assert signal.signal_reason != 'averaging', "Should not generate averaging signal when max count reached"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000)
    def test_no_averaging_above_trigger_level(self, market_data, config):
        """
        Test that no averaging signal is generated when price is above averaging trigger level.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create initial position
        initial_price = market_data.current_ticker.trade_price
        initial_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        # Create market data with price above averaging trigger (less loss than trigger)
        above_trigger_price = initial_price * (1 + (strategy.averaging_trigger / 100) + 0.005)  # 0.5% above trigger
        
        above_trigger_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=above_trigger_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=(above_trigger_price - initial_price) / initial_price
            ),
            price_history=market_data.price_history + [above_trigger_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(above_trigger_market_data)
        
        # Assert
        # Should not generate averaging signal when price is above trigger level
        if signal is not None:
            assert signal.signal_reason != 'averaging', "Should not generate averaging signal above trigger level"