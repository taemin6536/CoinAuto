"""
Property-based tests for stop-loss averaging strategy sell execution.

**Feature: stop-loss-averaging-strategy, Property 2: 손절 매도 실행**
**Validates: Requirements 1.2**

Tests that for any position, when average loss reaches -3% (stop loss level),
all positions should be immediately sold.
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


class TestStopLossSellExecution:
    """Property-based tests for stop loss sell execution."""
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_stop_loss_sell_execution_property(self, market_data, config):
        """
        **Feature: stop-loss-averaging-strategy, Property 2: 손절 매도 실행**
        **Validates: Requirements 1.2**
        
        Property: For any position, when average loss reaches -3% (stop loss level),
        all positions should be immediately sold.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create initial position by simulating first buy
        # Use a consistent price from the price history to avoid discrepancies
        initial_price = market_data.price_history[-1]  # Use the last price from history
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
        
        # Calculate price that triggers stop loss (stop_loss_level% drop)
        stop_loss_price = initial_price * (1 + strategy.stop_loss_level / 100)
        
        # Ensure stop loss price is significantly lower than initial price
        assume(stop_loss_price < initial_price * 0.98)  # At least 2% drop
        
        # Verify that this price would actually trigger stop loss
        test_pnl_rate = ((stop_loss_price - initial_price) / initial_price) * 100
        assume(test_pnl_rate <= strategy.stop_loss_level)
        
        # Create market data with price at stop loss level
        stop_loss_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=stop_loss_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=strategy.stop_loss_level / 100
            ),
            price_history=market_data.price_history + [stop_loss_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(stop_loss_market_data)
        
        # Assert
        if signal is not None:
            # If a signal is generated, it should be a sell signal for stop loss
            assert isinstance(signal, StopLossAveragingSignal)
            assert signal.action == 'sell'
            assert signal.signal_reason == 'stop_loss'
            
            # The volume should be the entire position (all positions sold)
            position = strategy.position_manager.get_position(market_data.current_ticker.market)
            if position:
                # Allow for small differences due to floating point precision
                volume_ratio = signal.volume / position.total_quantity
                assert 0.99 <= volume_ratio <= 1.01, f"Stop loss should sell entire position"
            
            # Confidence should be high for stop loss (1.0)
            assert signal.confidence == 1.0, f"Stop loss signal should have maximum confidence"
        
        # Additional verification: Check that position triggers stop loss
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        if position:
            # Calculate current PnL
            pnl_info = strategy.position_manager.get_position_pnl(
                market_data.current_ticker.market, 
                stop_loss_price
            )
            
            if pnl_info:
                current_pnl_percent = pnl_info['pnl_rate']
                
                # If PnL is at stop loss level, stop loss should be triggered
                if (current_pnl_percent <= strategy.stop_loss_level and 
                    not strategy.strategy_state.is_suspended):
                    
                    # Strategy should generate stop loss signal
                    assert signal is not None, "Strategy should generate stop loss signal when conditions are met"
                    assert signal.action == 'sell', "Signal should be a sell signal"
                    assert signal.signal_reason == 'stop_loss', "Signal reason should be stop_loss"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000)
    def test_no_stop_loss_above_threshold(self, market_data, config):
        """
        Test that no stop loss signal is generated when loss is above stop loss threshold.
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
        
        # Create market data with price above stop loss threshold (less loss than threshold)
        above_threshold_price = initial_price * (1 + (strategy.stop_loss_level / 100) + 0.005)  # 0.5% above threshold
        
        above_threshold_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=above_threshold_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=(above_threshold_price - initial_price) / initial_price
            ),
            price_history=market_data.price_history + [above_threshold_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(above_threshold_market_data)
        
        # Assert
        # Should not generate stop loss signal when price is above threshold
        if signal is not None:
            assert signal.signal_reason != 'stop_loss', "Should not generate stop loss signal above threshold"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_stop_loss_with_averaging_position(self, market_data, config):
        """
        Test that stop loss works correctly with positions that have averaging entries.
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
        
        # Add averaging position (at lower price)
        averaging_price = initial_price * 0.99  # 1% lower
        strategy.position_manager.add_averaging_position(
            market_data.current_ticker.market,
            averaging_price,
            initial_quantity
        )
        
        # Get the position to calculate average price
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position is not None)
        
        # Calculate price that triggers stop loss based on average price
        stop_loss_price = position.average_price * (1 + strategy.stop_loss_level / 100)
        
        # Ensure stop loss price is significantly lower
        assume(stop_loss_price < position.average_price * 0.98)
        
        # Create market data with price at stop loss level
        stop_loss_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=stop_loss_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=(stop_loss_price - position.average_price) / position.average_price
            ),
            price_history=market_data.price_history + [stop_loss_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(stop_loss_market_data)
        
        # Assert
        if signal is not None:
            assert signal.action == 'sell'
            assert signal.signal_reason == 'stop_loss'
            
            # Should sell entire position (both initial and averaging entries)
            volume_ratio = signal.volume / position.total_quantity
            assert 0.99 <= volume_ratio <= 1.01, "Should sell entire position including averaging entries"