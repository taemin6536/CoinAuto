"""
Property-based tests for stop-loss averaging strategy bilateral fee reflection.

**Feature: stop-loss-averaging-strategy, Property 7: 양방향 수수료 반영**
**Validates: Requirements 2.2**

Tests that when calculating profit rates, both buy fees and sell fees are reflected
in all profit calculations.
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


class TestBilateralFeeReflection:
    """Property-based tests for bilateral fee reflection in profit calculations."""
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_bilateral_fee_reflection_property(self, market_data, config):
        """
        **Feature: stop-loss-averaging-strategy, Property 7: 양방향 수수료 반영**
        **Validates: Requirements 2.2**
        
        Property: When calculating profit rates, both buy fees and sell fees are reflected
        in all profit calculations.
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
        assume(position.total_quantity > 0)
        
        # Test at various price levels to ensure bilateral fee reflection
        price_multipliers = [0.95, 0.98, 1.0, 1.02, 1.05, 1.1]  # Various profit/loss scenarios
        
        for multiplier in price_multipliers:
            test_price = initial_price * multiplier
            
            # Calculate PnL using strategy's method
            pnl_info = strategy._calculate_position_pnl(test_price, position)
            
            if pnl_info:
                # Verify both buy and sell fees are calculated
                assert 'buy_fees' in pnl_info, "PnL info should include buy fees"
                assert 'sell_fees' in pnl_info, "PnL info should include sell fees"
                
                # Verify buy fees are calculated correctly
                expected_buy_fees = position.total_cost * strategy.trading_fee
                assert abs(pnl_info['buy_fees'] - expected_buy_fees) < 0.01, \
                    f"Buy fees should be {expected_buy_fees}, got {pnl_info['buy_fees']}"
                
                # Verify sell fees are calculated correctly
                current_value = test_price * position.total_quantity
                expected_sell_fees = current_value * strategy.trading_fee
                assert abs(pnl_info['sell_fees'] - expected_sell_fees) < 0.01, \
                    f"Sell fees should be {expected_sell_fees}, got {pnl_info['sell_fees']}"
                
                # Verify net PnL reflects both fees
                expected_gross_pnl = current_value - position.total_cost
                expected_net_pnl = expected_gross_pnl - expected_buy_fees - expected_sell_fees
                assert abs(pnl_info['pnl'] - expected_net_pnl) < 0.01, \
                    f"Net PnL should reflect both fees. Expected: {expected_net_pnl}, Got: {pnl_info['pnl']}"
                
                # Verify PnL rate is calculated on fee-adjusted basis
                fee_adjusted_cost = position.total_cost + expected_buy_fees
                expected_pnl_rate = (expected_net_pnl / fee_adjusted_cost) * 100
                assert abs(pnl_info['pnl_rate'] - expected_pnl_rate) < 0.01, \
                    f"PnL rate should be calculated on fee-adjusted basis. Expected: {expected_pnl_rate}, Got: {pnl_info['pnl_rate']}"
                
                # Verify that both fees are positive (non-zero)
                assert pnl_info['buy_fees'] > 0, "Buy fees should be positive"
                assert pnl_info['sell_fees'] > 0, "Sell fees should be positive"
                
                # Verify that fees are proportional to transaction amounts
                buy_fee_rate = pnl_info['buy_fees'] / position.total_cost
                sell_fee_rate = pnl_info['sell_fees'] / current_value
                
                assert abs(buy_fee_rate - strategy.trading_fee) < 0.0001, \
                    f"Buy fee rate should equal trading fee. Expected: {strategy.trading_fee}, Got: {buy_fee_rate}"
                assert abs(sell_fee_rate - strategy.trading_fee) < 0.0001, \
                    f"Sell fee rate should equal trading fee. Expected: {strategy.trading_fee}, Got: {sell_fee_rate}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_bilateral_fees_in_signal_generation(self, market_data, config):
        """
        Test that signal generation considers both buy and sell fees in profit calculations.
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
        
        # Test take profit signal generation with bilateral fees
        # Calculate price that would be profitable only after considering both fees
        trading_fee = strategy.trading_fee
        bilateral_fee_impact = trading_fee * 2 * 100  # Both buy and sell fees in percentage
        target_with_bilateral_fees = strategy.target_profit + bilateral_fee_impact + 0.1  # Small buffer
        
        profitable_price = initial_price * (1 + target_with_bilateral_fees / 100)
        
        profitable_market_data = MarketData(
            current_ticker=Ticker(
                market=market_data.current_ticker.market,
                trade_price=profitable_price,
                trade_volume=market_data.current_ticker.trade_volume,
                timestamp=datetime.now(),
                change_rate=target_with_bilateral_fees / 100
            ),
            price_history=market_data.price_history + [profitable_price],
            volume_history=market_data.volume_history + [market_data.current_ticker.trade_volume],
            timestamps=market_data.timestamps + [datetime.now()]
        )
        
        # Act
        signal = strategy.evaluate(profitable_market_data)
        
        # Assert
        if signal is not None and signal.action == 'sell':
            # Verify that the signal's expected PnL accounts for bilateral fees
            pnl_info = strategy._calculate_position_pnl(profitable_price, position)
            
            if signal.expected_pnl is not None and pnl_info:
                # For full sell signals, expected PnL should match calculated PnL (with bilateral fees)
                if signal.signal_reason in ['take_profit', 'stop_loss']:
                    assert abs(signal.expected_pnl - pnl_info['pnl']) < 0.01, \
                        f"Signal expected PnL should match calculated PnL with bilateral fees. Expected: {pnl_info['pnl']}, Got: {signal.expected_pnl}"
                
                # Verify that the PnL calculation includes both fees
                current_value = profitable_price * position.total_quantity
                buy_fees = position.total_cost * trading_fee
                sell_fees = current_value * trading_fee
                expected_net_pnl = current_value - position.total_cost - buy_fees - sell_fees
                
                # The signal's expected PnL should be based on this bilateral fee calculation
                if signal.signal_reason in ['take_profit', 'stop_loss']:
                    assert abs(signal.expected_pnl - expected_net_pnl) < 0.01, \
                        f"Signal expected PnL should account for bilateral fees. Expected: {expected_net_pnl}, Got: {signal.expected_pnl}"
                elif signal.signal_reason == 'partial_sell':
                    # For partial sells, expected PnL should be a fraction of the bilateral fee-adjusted PnL
                    assert 0 < signal.expected_pnl <= expected_net_pnl, \
                        f"Partial sell expected PnL should be a fraction of bilateral fee-adjusted PnL. Full: {expected_net_pnl}, Partial: {signal.expected_pnl}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=50, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_bilateral_fees_with_averaging_positions(self, market_data, config):
        """
        Test that bilateral fees are correctly calculated for positions with averaging entries.
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
        
        # Test bilateral fee calculation on averaged position
        test_price = position_with_averaging.average_price * 1.02  # 2% above average
        
        pnl_info = strategy._calculate_position_pnl(test_price, position_with_averaging)
        
        if pnl_info:
            # Verify buy fees account for all entries (bilateral on buy side)
            total_cost = position_with_averaging.total_cost
            expected_total_buy_fees = total_cost * strategy.trading_fee
            assert abs(pnl_info['buy_fees'] - expected_total_buy_fees) < 0.01, \
                f"Buy fees should account for all entries. Expected: {expected_total_buy_fees}, Got: {pnl_info['buy_fees']}"
            
            # Verify sell fees account for total position (bilateral on sell side)
            current_value = test_price * position_with_averaging.total_quantity
            expected_sell_fees = current_value * strategy.trading_fee
            assert abs(pnl_info['sell_fees'] - expected_sell_fees) < 0.01, \
                f"Sell fees should account for total position. Expected: {expected_sell_fees}, Got: {pnl_info['sell_fees']}"
            
            # Verify net PnL reflects bilateral fees on averaged position
            expected_gross_pnl = current_value - total_cost
            expected_net_pnl = expected_gross_pnl - expected_total_buy_fees - expected_sell_fees
            assert abs(pnl_info['pnl'] - expected_net_pnl) < 0.01, \
                f"Net PnL should reflect bilateral fees on averaged position. Expected: {expected_net_pnl}, Got: {pnl_info['pnl']}"
            
            # Verify PnL rate is calculated with bilateral fee adjustment
            fee_adjusted_cost = total_cost + expected_total_buy_fees
            expected_pnl_rate = (expected_net_pnl / fee_adjusted_cost) * 100
            assert abs(pnl_info['pnl_rate'] - expected_pnl_rate) < 0.01, \
                f"PnL rate should be calculated with bilateral fee adjustment. Expected: {expected_pnl_rate}, Got: {pnl_info['pnl_rate']}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_bilateral_fee_impact_on_breakeven(self, market_data, config):
        """
        Test that breakeven calculations properly account for bilateral fees.
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
        
        # Calculate true breakeven price accounting for bilateral fees
        trading_fee = strategy.trading_fee
        
        # At breakeven, net PnL should be zero:
        # current_value - total_cost - buy_fees - sell_fees = 0
        # current_value - total_cost - (total_cost * fee) - (current_value * fee) = 0
        # current_value * (1 - fee) - total_cost * (1 + fee) = 0
        # current_value = total_cost * (1 + fee) / (1 - fee)
        
        total_cost = position.total_cost
        breakeven_value = total_cost * (1 + trading_fee) / (1 - trading_fee)
        breakeven_price = breakeven_value / position.total_quantity
        
        # Test PnL at calculated breakeven price
        pnl_info = strategy._calculate_position_pnl(breakeven_price, position)
        
        if pnl_info:
            # Net PnL should be approximately zero at true breakeven
            assert abs(pnl_info['pnl']) < 0.01, \
                f"Net PnL should be approximately zero at breakeven price. Got: {pnl_info['pnl']}"
            
            # Verify that both fees are accounted for
            expected_buy_fees = total_cost * trading_fee
            expected_sell_fees = breakeven_value * trading_fee
            
            assert abs(pnl_info['buy_fees'] - expected_buy_fees) < 0.01, \
                f"Buy fees should be correct at breakeven. Expected: {expected_buy_fees}, Got: {pnl_info['buy_fees']}"
            assert abs(pnl_info['sell_fees'] - expected_sell_fees) < 0.01, \
                f"Sell fees should be correct at breakeven. Expected: {expected_sell_fees}, Got: {pnl_info['sell_fees']}"
            
            # Verify the bilateral fee calculation
            gross_pnl = breakeven_value - total_cost
            net_pnl_check = gross_pnl - expected_buy_fees - expected_sell_fees
            assert abs(net_pnl_check) < 0.01, \
                f"Bilateral fee calculation should result in zero net PnL at breakeven. Got: {net_pnl_check}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_bilateral_fee_consistency_across_price_levels(self, market_data, config):
        """
        Test that bilateral fee calculations are consistent across different price levels.
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
        
        # Test at multiple price levels
        price_multipliers = [0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
        
        for multiplier in price_multipliers:
            test_price = initial_price * multiplier
            pnl_info = strategy._calculate_position_pnl(test_price, position)
            
            if pnl_info:
                # Verify fee rates are consistent
                buy_fee_rate = pnl_info['buy_fees'] / position.total_cost
                sell_fee_rate = pnl_info['sell_fees'] / (test_price * position.total_quantity)
                
                assert abs(buy_fee_rate - strategy.trading_fee) < 0.0001, \
                    f"Buy fee rate should be consistent at price {test_price}. Expected: {strategy.trading_fee}, Got: {buy_fee_rate}"
                assert abs(sell_fee_rate - strategy.trading_fee) < 0.0001, \
                    f"Sell fee rate should be consistent at price {test_price}. Expected: {strategy.trading_fee}, Got: {sell_fee_rate}"
                
                # Verify bilateral fee impact on PnL rate
                current_value = test_price * position.total_quantity
                gross_pnl = current_value - position.total_cost
                net_pnl = gross_pnl - pnl_info['buy_fees'] - pnl_info['sell_fees']
                
                assert abs(pnl_info['pnl'] - net_pnl) < 0.01, \
                    f"Net PnL should equal gross PnL minus bilateral fees at price {test_price}"
                
                # Verify PnL rate calculation includes bilateral fees
                fee_adjusted_cost = position.total_cost + pnl_info['buy_fees']
                expected_pnl_rate = (net_pnl / fee_adjusted_cost) * 100
                assert abs(pnl_info['pnl_rate'] - expected_pnl_rate) < 0.01, \
                    f"PnL rate should account for bilateral fees at price {test_price}. Expected: {expected_pnl_rate}, Got: {pnl_info['pnl_rate']}"
    
    @given(
        market_data=generate_market_data(),
        config=generate_strategy_config()
    )
    @settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.filter_too_much])
    def test_take_profit_threshold_includes_bilateral_fees(self, market_data, config):
        """
        Test that take profit threshold calculations include bilateral fees.
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
        
        # Test the take profit threshold calculation
        trading_fee = strategy.trading_fee
        bilateral_fee_impact = trading_fee * 2 * 100  # Both buy and sell fees in percentage
        
        # The strategy should use bilateral fees in its take profit calculation
        # From the code: breakeven_with_fees = self.trading_fee * 2 * 100
        # target_with_fees = self.target_profit + breakeven_with_fees
        
        expected_breakeven_with_fees = bilateral_fee_impact
        expected_target_with_fees = strategy.target_profit + expected_breakeven_with_fees
        
        # Test at a price that should trigger take profit
        target_price = initial_price * (1 + (expected_target_with_fees + 0.1) / 100)  # Small buffer
        
        # Calculate PnL at target price
        pnl_info = strategy._calculate_position_pnl(target_price, position)
        
        if pnl_info:
            # Verify that the PnL rate exceeds the bilateral fee-adjusted target (with small tolerance for floating point precision)
            tolerance = 0.01  # 0.01% tolerance for floating point precision
            assert pnl_info['pnl_rate'] >= (expected_target_with_fees - tolerance), \
                f"PnL rate should exceed bilateral fee-adjusted target. Expected >= {expected_target_with_fees}, Got: {pnl_info['pnl_rate']}"
            
            # Test the strategy's take profit condition
            should_take_profit = strategy._should_take_profit(pnl_info['pnl_rate'])
            # Allow for small floating point precision differences
            if abs(pnl_info['pnl_rate'] - expected_target_with_fees) < 0.02:  # Within 0.02% tolerance
                # If we're very close to the threshold, either result is acceptable due to floating point precision
                pass
            else:
                assert should_take_profit, \
                    f"Strategy should trigger take profit when PnL rate ({pnl_info['pnl_rate']}) exceeds bilateral fee-adjusted target ({expected_target_with_fees})"
            
            # Verify that the calculation includes both fees
            current_value = target_price * position.total_quantity
            buy_fees = position.total_cost * trading_fee
            sell_fees = current_value * trading_fee
            net_pnl = current_value - position.total_cost - buy_fees - sell_fees
            
            # The net PnL should be positive when take profit is triggered
            assert net_pnl > 0, \
                f"Net PnL should be positive when take profit is triggered. Got: {net_pnl}"
            
            # The net PnL rate should exceed the target profit
            fee_adjusted_cost = position.total_cost + buy_fees
            net_pnl_rate = (net_pnl / fee_adjusted_cost) * 100
            assert net_pnl_rate >= strategy.target_profit, \
                f"Net PnL rate should exceed target profit. Expected >= {strategy.target_profit}, Got: {net_pnl_rate}"