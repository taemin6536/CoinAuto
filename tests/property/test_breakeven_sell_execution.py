"""
Property-based tests for stop-loss averaging strategy breakeven sell execution.

**Feature: stop-loss-averaging-strategy, Property 3: 손익분기점 매도**
**Validates: Requirements 1.3**

Tests that for any position, when it exceeds the breakeven point including fees,
a sell signal should be generated.
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


class TestBreakevenSellExecution:
    """Property-based tests for breakeven sell execution."""
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_breakeven_sell_execution_property(self, market_data, config):
        """
        **Feature: stop-loss-averaging-strategy, Property 3: 손익분기점 매도**
        **Validates: Requirements 1.3**
        
        Property: For any position, when it exceeds the breakeven point including fees,
        a sell signal should be generated.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Create initial position by simulating first buy
        # Use a consistent price from the price history to avoid discrepancies
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
        
        # Calculate breakeven price including fees
        # Breakeven = initial_price * (1 + buy_fee + sell_fee + target_profit)
        trading_fee = strategy.trading_fee
        breakeven_with_fees = trading_fee * 2 * 100  # Buy + sell fees in percentage
        target_with_fees = strategy.target_profit + breakeven_with_fees
        breakeven_price = initial_price * (1 + target_with_fees / 100)
        
        # Ensure breakeven price is significantly higher than initial price
        assume(breakeven_price > initial_price * 1.005)  # At least 0.5% profit
        
        # Verify that this price would actually trigger take profit
        test_pnl_rate = ((breakeven_price - initial_price) / initial_price) * 100
        assume(test_pnl_rate >= target_with_fees)
        
        # Create market data with price at breakeven level
        breakeven_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=breakeven_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=test_pnl_rate / 100
            ),
            price_history=market_data.price_history + [breakeven_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(breakeven_market_data)
        
        # Assert
        if signal is not None:
            # If a signal is generated, it should be a sell signal for take profit
            assert isinstance(signal, StopLossAveragingSignal)
            assert signal.action == 'sell'
            
            # The signal reason should be related to profit taking
            assert signal.signal_reason in ['take_profit', 'partial_sell'], \
                f"Expected take_profit or partial_sell, got {signal.signal_reason}"
            
            # The volume should be positive
            assert signal.volume > 0, "Sell volume should be positive"
            
            # Confidence should be reasonable for profit taking
            assert 0.5 <= signal.confidence <= 1.0, \
                f"Take profit signal should have reasonable confidence, got {signal.confidence}"
        
        # Additional verification: Check that position triggers take profit
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        if position:
            # Calculate current PnL
            pnl_info = strategy.position_manager.get_position_pnl(
                market_data.current_ticker.market, 
                breakeven_price
            )
            
            if pnl_info:
                current_pnl_percent = pnl_info['pnl_rate']
                
                # If PnL is at breakeven level, take profit should be triggered
                if (current_pnl_percent >= target_with_fees and 
                    not strategy.strategy_state.is_suspended):
                    
                    # Strategy should generate take profit signal
                    assert signal is not None, \
                        "Strategy should generate take profit signal when breakeven conditions are met"
                    assert signal.action == 'sell', "Signal should be a sell signal"
                    assert signal.signal_reason in ['take_profit', 'partial_sell'], \
                        "Signal reason should be related to profit taking"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_no_take_profit_below_breakeven(self, market_data, config):
        """
        Test that no take profit signal is generated when profit is below breakeven threshold.
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
        
        # Create market data with price below breakeven threshold
        trading_fee = strategy.trading_fee
        breakeven_with_fees = trading_fee * 2 * 100  # Buy + sell fees in percentage
        target_with_fees = strategy.target_profit + breakeven_with_fees
        
        # Price that's profitable but below breakeven threshold (half of target)
        below_breakeven_price = initial_price * (1 + (target_with_fees / 2) / 100)
        
        below_breakeven_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=below_breakeven_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=(below_breakeven_price - initial_price) / initial_price
            ),
            price_history=market_data.price_history + [below_breakeven_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(below_breakeven_market_data)
        
        # Assert
        # Should not generate take profit signal when price is below breakeven threshold
        if signal is not None:
            assert signal.signal_reason != 'take_profit', \
                "Should not generate take profit signal below breakeven threshold"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_fee_calculation_accuracy(self, market_data, config):
        """
        Test that fee calculations are accurate in breakeven determination.
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
        
        # Calculate exact breakeven price
        trading_fee = strategy.trading_fee
        breakeven_with_fees = trading_fee * 2 * 100  # Buy + sell fees in percentage
        target_with_fees = strategy.target_profit + breakeven_with_fees
        exact_breakeven_price = initial_price * (1 + target_with_fees / 100)
        
        # Test with price exactly at breakeven
        exact_breakeven_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=exact_breakeven_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=target_with_fees / 100
            ),
            price_history=market_data.price_history + [exact_breakeven_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(exact_breakeven_market_data)
        
        # Assert
        # Verify that the strategy correctly calculates fees
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        if position:
            # Use the strategy's fee-inclusive PnL calculation
            pnl_info = strategy._calculate_position_pnl(exact_breakeven_price, position)
            
            if pnl_info:
                # The calculated PnL should account for both buy and sell fees
                current_value = exact_breakeven_price * position.total_quantity
                buy_fees = position.total_cost * trading_fee
                sell_fees = current_value * trading_fee
                expected_net_pnl = current_value - position.total_cost - buy_fees - sell_fees
                
                # Allow for small floating point differences
                actual_pnl = pnl_info['pnl']
                assert abs(actual_pnl - expected_net_pnl) < 0.01, \
                    f"PnL calculation should account for fees correctly. Expected: {expected_net_pnl}, Got: {actual_pnl}"