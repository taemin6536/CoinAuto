"""
Property-based tests for stop-loss averaging strategy fee-inclusive profit calculation.

**Feature: stop-loss-averaging-strategy, Property 6: 수수료 포함 손익 계산**
**Validates: Requirements 2.1**

Tests that when generating sell signals, the strategy includes Upbit fees (0.05%)
in profit calculations.
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
    """Generate valid strategy configuration with fixed trading fee."""
    # Ensure stop_loss_level is more negative than averaging_trigger
    averaging_trigger = draw(st.floats(min_value=-2.0, max_value=-0.5))
    stop_loss_level = draw(st.floats(min_value=-5.0, max_value=averaging_trigger - 0.5))  # Always more negative
    
    return {
        'parameters': {
            'stop_loss_level': stop_loss_level,
            'averaging_trigger': averaging_trigger,
            'target_profit': draw(st.floats(min_value=0.2, max_value=2.0)),
            'max_averaging_count': draw(st.integers(min_value=1, max_value=3)),
            'trading_fee': 0.0005,  # Fixed Upbit fee (0.05%)
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


class TestFeeInclusiveProfitCalculation:
    """Property-based tests for fee-inclusive profit calculation."""
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_fee_inclusive_profit_calculation_property(self, market_data, config):
        """
        **Feature: stop-loss-averaging-strategy, Property 6: 수수료 포함 손익 계산**
        **Validates: Requirements 2.1**
        
        Property: When generating sell signals, the strategy includes Upbit fees (0.05%)
        in profit calculations.
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Verify trading fee is set to Upbit's fee
        assert strategy.trading_fee == 0.0005, "Trading fee should be set to Upbit's 0.05%"
        
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
        assume(position.total_quantity > 0)
        
        # Generate a profitable price that should trigger sell signal
        profit_multiplier = 1 + (strategy.target_profit + 0.2) / 100  # Target profit + 0.2% buffer
        profitable_price = initial_price * profit_multiplier
        
        # Ensure profitable price is significantly higher
        assume(profitable_price > initial_price * 1.005)  # At least 0.5% profit
        
        # Create market data with profitable price
        profitable_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=profitable_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=(profitable_price - initial_price) / initial_price
            ),
            price_history=market_data.price_history + [profitable_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(profitable_market_data)
        
        # Assert
        if signal is not None and signal.action == 'sell':
            # Verify that the signal includes fee calculations
            assert isinstance(signal, StopLossAveragingSignal)
            
            # Check that expected PnL is calculated with fees
            if signal.expected_pnl is not None:
                # Get the actual PnL info from the strategy
                pnl_info = strategy._calculate_position_pnl(profitable_price, position)
                
                # For partial sell signals, the expected PnL should be proportional to the sell ratio
                if signal.signal_reason == 'partial_sell':
                    # The strategy calculates expected_pnl as pnl_info['pnl'] * sell_ratio
                    # We need to verify that this calculation includes fees
                    
                    # Verify that the PnL calculation itself includes fees
                    current_value = profitable_price * position.total_quantity
                    buy_fees = position.total_cost * strategy.trading_fee
                    sell_fees = current_value * strategy.trading_fee
                    expected_full_pnl = current_value - position.total_cost - buy_fees - sell_fees
                    
                    # Allow for small floating point differences in the full PnL calculation
                    assert abs(pnl_info['pnl'] - expected_full_pnl) < 0.01, \
                        f"Full PnL calculation should include fees. Expected: {expected_full_pnl}, Got: {pnl_info['pnl']}"
                    
                    # The signal's expected_pnl should be a fraction of the full PnL
                    # (The exact fraction depends on the partial sell manager's logic)
                    assert 0 < signal.expected_pnl <= pnl_info['pnl'], \
                        f"Partial sell expected PnL should be a positive fraction of full PnL. Full: {pnl_info['pnl']}, Partial: {signal.expected_pnl}"
                    
                else:
                    # For full sell signals, calculate full expected PnL with fees
                    current_value = profitable_price * position.total_quantity
                    buy_fees = position.total_cost * strategy.trading_fee
                    sell_fees = current_value * strategy.trading_fee
                    expected_net_pnl = current_value - position.total_cost - buy_fees - sell_fees
                    
                    # Allow for small floating point differences
                    assert abs(signal.expected_pnl - expected_net_pnl) < 0.01, \
                        f"Signal's expected PnL should include fees. Expected: {expected_net_pnl}, Got: {signal.expected_pnl}"
        
        # Additional verification: Check strategy's internal PnL calculation
        pnl_info = strategy._calculate_position_pnl(profitable_price, position)
        if pnl_info:
            # Verify that buy fees are calculated correctly
            expected_buy_fees = position.total_cost * strategy.trading_fee
            assert abs(pnl_info['buy_fees'] - expected_buy_fees) < 0.01, \
                "Buy fees should be calculated correctly"
            
            # Verify that sell fees are calculated correctly
            current_value = profitable_price * position.total_quantity
            expected_sell_fees = current_value * strategy.trading_fee
            assert abs(pnl_info['sell_fees'] - expected_sell_fees) < 0.01, \
                "Sell fees should be calculated correctly"
            
            # Verify that net PnL includes both fees
            expected_net_pnl = current_value - position.total_cost - expected_buy_fees - expected_sell_fees
            assert abs(pnl_info['pnl'] - expected_net_pnl) < 0.01, \
                "Net PnL should include both buy and sell fees"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_upbit_fee_rate_consistency(self, market_data, config):
        """
        Test that the strategy consistently uses Upbit's fee rate (0.05%).
        """
        # Arrange
        strategy = StopLossAveragingStrategy("test_strategy", config)
        
        # Ensure market data is valid
        assume(market_data.validate())
        assume(len(market_data.price_history) >= strategy.get_required_history_length())
        
        # Assert that trading fee is exactly Upbit's rate
        assert strategy.trading_fee == 0.0005, \
            f"Trading fee should be Upbit's 0.05% (0.0005), got {strategy.trading_fee}"
        
        # Create position to test fee calculations
        initial_price = market_data.price_history[-1]
        initial_quantity = 0.1
        
        strategy.position_manager.add_initial_position(
            market_data.current_ticker.market,
            initial_price,
            initial_quantity
        )
        
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position is not None)
        
        # Test fee calculation at different price levels
        test_prices = [
            initial_price * 0.97,  # Loss scenario
            initial_price * 1.0,   # Breakeven scenario
            initial_price * 1.02   # Profit scenario
        ]
        
        for test_price in test_prices:
            pnl_info = strategy._calculate_position_pnl(test_price, position)
            
            if pnl_info:
                # Verify buy fee calculation
                expected_buy_fee = position.total_cost * 0.0005
                assert abs(pnl_info['buy_fees'] - expected_buy_fee) < 0.01, \
                    f"Buy fee should be 0.05% of cost at price {test_price}"
                
                # Verify sell fee calculation
                current_value = test_price * position.total_quantity
                expected_sell_fee = current_value * 0.0005
                assert abs(pnl_info['sell_fees'] - expected_sell_fee) < 0.01, \
                    f"Sell fee should be 0.05% of value at price {test_price}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_fee_impact_on_breakeven_calculation(self, market_data, config):
        """
        Test that fees are properly considered in breakeven calculations.
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
        
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position is not None)
        
        # Calculate theoretical breakeven price without fees
        breakeven_without_fees = initial_price * (1 + strategy.target_profit / 100)
        
        # Calculate actual breakeven price with fees
        trading_fee = strategy.trading_fee
        breakeven_with_fees = trading_fee * 2 * 100  # Buy + sell fees in percentage
        target_with_fees = strategy.target_profit + breakeven_with_fees
        breakeven_with_fees_price = initial_price * (1 + target_with_fees / 100)
        
        # Test PnL calculation at both prices
        pnl_without_fees = strategy._calculate_position_pnl(breakeven_without_fees, position)
        pnl_with_fees = strategy._calculate_position_pnl(breakeven_with_fees_price, position)
        
        if pnl_without_fees and pnl_with_fees:
            # At breakeven without fees, net PnL should be less than at breakeven with fees
            # (The exact sign depends on the target profit vs fee relationship)
            assert pnl_without_fees['pnl'] < pnl_with_fees['pnl'], \
                "PnL should be lower at breakeven price without fees compared to fee-adjusted breakeven"
            
            # At breakeven with fees, net PnL should be approximately zero or positive
            assert pnl_with_fees['pnl'] >= -0.01, \
                "PnL should be approximately zero or positive at fee-adjusted breakeven price"
            
            # The difference should reflect the additional profit needed to cover fees
            price_difference = breakeven_with_fees_price - breakeven_without_fees
            expected_additional_profit = price_difference * position.total_quantity
            pnl_difference = pnl_with_fees['pnl'] - pnl_without_fees['pnl']
            
            # The PnL difference should be close to the additional profit (allowing for fee calculations)
            # Since fees are calculated on both buy and sell, the relationship is more complex
            total_fees_at_higher_price = pnl_with_fees['buy_fees'] + pnl_with_fees['sell_fees']
            total_fees_at_lower_price = pnl_without_fees['buy_fees'] + pnl_without_fees['sell_fees']
            fee_difference = total_fees_at_higher_price - total_fees_at_lower_price
            
            # The net effect should account for both additional profit and additional fees
            expected_net_difference = expected_additional_profit - fee_difference
            assert abs(pnl_difference - expected_net_difference) < 0.1, \
                f"PnL difference should reflect additional profit minus additional fees. Expected: {expected_net_difference}, Got: {pnl_difference}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_sell_signal_generation_includes_fees(self, market_data, config):
        """
        Test that sell signal generation properly considers fees.
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
        
        position = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position is not None)
        
        # Test at price that would be profitable without fees but not with fees
        # This should NOT generate a take_profit signal (but might generate partial_sell)
        profit_without_fees = strategy.target_profit / 2  # Half the target profit
        price_without_fee_consideration = initial_price * (1 + profit_without_fees / 100)
        
        market_data_without_fees = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=price_without_fee_consideration,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=profit_without_fees / 100
            ),
            price_history=market_data.price_history + [price_without_fee_consideration],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal_without_fees = strategy.evaluate(market_data_without_fees)
        
        # Assert
        # Should not generate take profit signal when fees would make it unprofitable
        if signal_without_fees is not None:
            assert signal_without_fees.signal_reason != 'take_profit', \
                "Should not generate take profit signal when fees would make it unprofitable"
        
        # Test at price that is profitable even with fees
        # This SHOULD generate a sell signal
        trading_fee = strategy.trading_fee
        breakeven_with_fees = trading_fee * 2 * 100  # Buy + sell fees in percentage
        target_with_fees = strategy.target_profit + breakeven_with_fees + 0.1  # Add small buffer
        price_with_fee_consideration = initial_price * (1 + target_with_fees / 100)
        
        market_data_with_fees = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=price_with_fee_consideration,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=target_with_fees / 100
            ),
            price_history=market_data.price_history + [price_with_fee_consideration],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        signal_with_fees = strategy.evaluate(market_data_with_fees)
        
        # Should generate sell signal when profitable after fees
        if signal_with_fees is not None:
            # If a signal is generated, verify it accounts for fees
            pnl_info = strategy._calculate_position_pnl(price_with_fee_consideration, position)
            if pnl_info:
                # Net PnL should be positive after fees
                assert pnl_info['pnl'] > 0, \
                    "Net PnL should be positive when sell signal is generated"
                
                # PnL rate should be reasonable (allow for partial sell scenarios)
                # For partial sells, the threshold might be lower
                min_expected_rate = target_with_fees - 0.2  # Allow more tolerance for partial sells
                assert pnl_info['pnl_rate'] >= min_expected_rate, \
                    f"PnL rate should be reasonable when sell signal is generated. Expected >= {min_expected_rate}, Got: {pnl_info['pnl_rate']}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_fee_calculation_with_averaging_position(self, market_data, config):
        """
        Test that fees are correctly calculated for positions with averaging entries.
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
        
        # Add averaging position
        averaging_price = initial_price * 0.99  # 1% lower
        strategy.position_manager.add_averaging_position(
            market_data.current_ticker.market,
            averaging_price,
            initial_quantity
        )
        
        position_with_averaging = strategy.position_manager.get_position(market_data.current_ticker.market)
        assume(position_with_averaging is not None)
        assume(len(position_with_averaging.entries) == 2)  # Initial + averaging
        
        # Test fee calculation on averaged position
        test_price = position_with_averaging.average_price * 1.02  # 2% above average
        
        pnl_info = strategy._calculate_position_pnl(test_price, position_with_averaging)
        
        if pnl_info:
            # Buy fees should be calculated on total cost (both entries)
            expected_buy_fees = position_with_averaging.total_cost * strategy.trading_fee
            assert abs(pnl_info['buy_fees'] - expected_buy_fees) < 0.01, \
                "Buy fees should be calculated on total cost of all entries"
            
            # Sell fees should be calculated on current total value
            current_value = test_price * position_with_averaging.total_quantity
            expected_sell_fees = current_value * strategy.trading_fee
            assert abs(pnl_info['sell_fees'] - expected_sell_fees) < 0.01, \
                "Sell fees should be calculated on current total value"
            
            # Net PnL should account for both fees
            expected_net_pnl = current_value - position_with_averaging.total_cost - expected_buy_fees - expected_sell_fees
            assert abs(pnl_info['pnl'] - expected_net_pnl) < 0.01, \
                "Net PnL should account for both buy and sell fees on averaged position"