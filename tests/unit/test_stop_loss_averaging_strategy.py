"""
Unit tests for StopLossAveragingStrategy main strategy class.

Tests signal generation logic and entry condition checking for the stop-loss
averaging strategy implementation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal

from upbit_trading_bot.strategy.stop_loss_averaging import StopLossAveragingStrategy
from upbit_trading_bot.strategy.base import MarketData, StrategyEvaluationError
from upbit_trading_bot.data.models import (
    Ticker, 
    StopLossAveragingSignal, 
    MarketConditions, 
    StopLossPosition,
    PositionEntry
)


class TestStopLossAveragingStrategy:
    """Unit tests for StopLossAveragingStrategy."""
    
    @pytest.fixture
    def valid_config(self):
        """Valid strategy configuration for testing."""
        return {
            'parameters': {
                'stop_loss_level': -3.0,
                'averaging_trigger': -1.0,
                'target_profit': 0.5,
                'max_averaging_count': 1,
                'trading_fee': 0.0005,
                'monitoring_interval': 10,
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
    
    @pytest.fixture
    def sample_market_data(self):
        """Sample market data for testing."""
        base_time = datetime.now() - timedelta(minutes=60)
        price_history = [50000.0 + i * 100 for i in range(60)]  # Gradual price increase
        volume_history = [1000000.0] * 60
        timestamps = [base_time + timedelta(minutes=i) for i in range(60)]
        
        current_ticker = Ticker(
            market='KRW-BTC',
            trade_price=price_history[-1],
            trade_volume=volume_history[-1],
            timestamp=timestamps[-1],
            change_rate=0.02
        )
        
        return MarketData(
            current_ticker=current_ticker,
            price_history=price_history,
            volume_history=volume_history,
            timestamps=timestamps
        )
    
    def test_strategy_initialization(self, valid_config):
        """Test strategy initialization with valid configuration."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        assert strategy.strategy_id == "test_strategy"
        assert strategy.stop_loss_level == -3.0
        assert strategy.averaging_trigger == -1.0
        assert strategy.target_profit == 0.5
        assert strategy.max_averaging_count == 1
        assert strategy.trading_fee == 0.0005
        assert strategy.monitoring_interval == 10
        
        # Check that components are initialized
        assert strategy.market_analyzer is not None
        assert strategy.position_manager is not None
        assert strategy.risk_controller is not None
        assert strategy.partial_sell_manager is not None
        assert strategy.trailing_stop_manager is not None
    
    def test_invalid_config_validation(self):
        """Test that invalid configurations raise errors."""
        # Test invalid stop loss level
        invalid_config = {
            'parameters': {
                'stop_loss_level': -6.0,  # Too negative
                'averaging_trigger': -1.0,
                'target_profit': 0.5,
                'max_averaging_count': 1,
                'trading_fee': 0.0005,
                'monitoring_interval': 10,
                'market_analyzer': {},
                'risk_controller': {}
            }
        }
        
        with pytest.raises(StrategyEvaluationError, match="Stop loss level"):
            StopLossAveragingStrategy("test_strategy", invalid_config)
        
        # Test invalid averaging trigger
        invalid_config['parameters']['stop_loss_level'] = -3.0
        invalid_config['parameters']['averaging_trigger'] = -3.0  # Too negative
        
        with pytest.raises(StrategyEvaluationError, match="Averaging trigger"):
            StopLossAveragingStrategy("test_strategy", invalid_config)
        
        # Test invalid target profit
        invalid_config['parameters']['averaging_trigger'] = -1.0
        invalid_config['parameters']['target_profit'] = 3.0  # Too high
        
        with pytest.raises(StrategyEvaluationError, match="Target profit"):
            StopLossAveragingStrategy("test_strategy", invalid_config)
    
    def test_get_required_history_length(self, valid_config):
        """Test required history length."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        assert strategy.get_required_history_length() == 50
    
    def test_can_evaluate_basic_conditions(self, valid_config, sample_market_data):
        """Test basic evaluation conditions."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Should be able to evaluate with valid market data
        assert strategy.can_evaluate(sample_market_data) is True
        
        # Should not evaluate when disabled
        strategy.enabled = False
        assert strategy.can_evaluate(sample_market_data) is False
        
        # Should not evaluate with insufficient history
        strategy.enabled = True
        short_market_data = MarketData(
            current_ticker=sample_market_data.current_ticker,
            price_history=[50000.0] * 10,  # Too short
            volume_history=[1000000.0] * 10,
            timestamps=[datetime.now()] * 10
        )
        assert strategy.can_evaluate(short_market_data) is False
    
    @patch('upbit_trading_bot.strategy.stop_loss_averaging.StopLossAveragingStrategy._check_entry_conditions')
    def test_evaluate_no_position_calls_entry_conditions(self, mock_entry_check, valid_config, sample_market_data):
        """Test that evaluate calls entry conditions when no position exists."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        mock_entry_check.return_value = None
        
        # Mock market analyzer to return favorable conditions
        strategy.market_analyzer.analyze_market_conditions = Mock(return_value=MarketConditions(
            volatility_24h=6.0,
            volume_ratio=2.0,
            rsi=25.0,
            price_change_1m=0.5,
            market_trend='bullish',
            is_rapid_decline=False
        ))
        
        result = strategy.evaluate(sample_market_data)
        
        mock_entry_check.assert_called_once()
        assert result is None  # Since mock returns None
    
    def test_evaluate_with_position_checks_stop_loss_first(self, valid_config, sample_market_data):
        """Test that evaluate checks stop loss conditions first when position exists."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Create a position with significant loss
        initial_price = 55000.0
        current_price = 52000.0  # About -5.5% loss
        
        position = StopLossPosition(
            market='KRW-BTC',
            entries=[PositionEntry(
                price=initial_price,
                quantity=0.1,
                cost=initial_price * 0.1,
                order_type='initial',
                timestamp=datetime.now()
            )],
            average_price=initial_price,
            total_quantity=0.1,
            total_cost=initial_price * 0.1,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Mock position manager to return the position
        strategy.position_manager.get_position = Mock(return_value=position)
        
        # Update market data with loss-inducing price
        market_data_with_loss = MarketData(
            current_ticker=Ticker(
                market='KRW-BTC',
                trade_price=current_price,
                trade_volume=1000000.0,
                timestamp=datetime.now(),
                change_rate=-0.055
            ),
            price_history=sample_market_data.price_history + [current_price],
            volume_history=sample_market_data.volume_history + [1000000.0],
            timestamps=sample_market_data.timestamps + [datetime.now()]
        )
        
        # Mock market analyzer
        strategy.market_analyzer.analyze_market_conditions = Mock(return_value=MarketConditions(
            volatility_24h=6.0,
            volume_ratio=2.0,
            rsi=25.0,
            price_change_1m=-2.0,
            market_trend='bearish',
            is_rapid_decline=True
        ))
        
        result = strategy.evaluate(market_data_with_loss)
        
        # Should generate stop loss signal
        assert result is not None
        assert isinstance(result, StopLossAveragingSignal)
        assert result.action == 'sell'
        assert result.signal_reason == 'stop_loss'
        assert result.confidence == 1.0
    
    def test_check_entry_conditions_with_favorable_market(self, valid_config, sample_market_data):
        """Test entry condition checking with favorable market conditions."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Mock favorable market conditions
        favorable_conditions = MarketConditions(
            volatility_24h=6.0,  # Above threshold
            volume_ratio=2.0,    # Above threshold
            rsi=25.0,           # Oversold
            price_change_1m=0.5,
            market_trend='bullish',
            is_rapid_decline=False
        )
        
        # Mock market analyzer methods
        strategy.market_analyzer.should_allow_buy_signal = Mock(return_value=True)
        strategy.market_analyzer.should_select_high_volatility_coin = Mock(return_value=True)
        strategy.market_analyzer.get_buy_signal_confidence = Mock(return_value=0.8)
        
        # Mock risk controller
        strategy.risk_controller.should_suspend_strategy = Mock(return_value=False)
        
        result = strategy._check_entry_conditions(sample_market_data, favorable_conditions)
        
        assert result is not None
        assert isinstance(result, StopLossAveragingSignal)
        assert result.action == 'buy'
        assert result.signal_reason == 'initial_buy'
        assert result.confidence == 0.8
        assert result.market_conditions == favorable_conditions
    
    def test_check_entry_conditions_with_unfavorable_market(self, valid_config, sample_market_data):
        """Test entry condition checking with unfavorable market conditions."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        unfavorable_conditions = MarketConditions(
            volatility_24h=3.0,  # Below threshold
            volume_ratio=1.0,    # Below threshold
            rsi=70.0,           # Overbought
            price_change_1m=-3.0,
            market_trend='bearish',
            is_rapid_decline=True
        )
        
        # Mock market analyzer to reject entry
        strategy.market_analyzer.should_allow_buy_signal = Mock(return_value=False)
        
        result = strategy._check_entry_conditions(sample_market_data, unfavorable_conditions)
        
        assert result is None
    
    def test_should_average_down_conditions(self, valid_config):
        """Test averaging down condition logic."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Create position with initial entry only
        position = StopLossPosition(
            market='KRW-BTC',
            entries=[PositionEntry(
                price=50000.0,
                quantity=0.1,
                cost=5000.0,
                order_type='initial',
                timestamp=datetime.now()
            )],
            average_price=50000.0,
            total_quantity=0.1,
            total_cost=5000.0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Should average down at -1.5% (below trigger)
        assert strategy._should_average_down(-1.5, position) is True
        
        # Should not average down at -0.5% (above trigger)
        assert strategy._should_average_down(-0.5, position) is False
        
        # Add averaging entry to test max count limit
        position.entries.append(PositionEntry(
            price=49000.0,
            quantity=0.1,
            cost=4900.0,
            order_type='averaging',
            timestamp=datetime.now()
        ))
        
        # Should not average down when max count reached
        assert strategy._should_average_down(-2.0, position) is False
    
    def test_should_stop_loss_conditions(self, valid_config):
        """Test stop loss condition logic."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Should trigger stop loss at -3.1%
        assert strategy._should_stop_loss(-3.1) is True
        
        # Should trigger stop loss exactly at -3.0% (with tolerance)
        assert strategy._should_stop_loss(-3.0) is True
        
        # Should not trigger stop loss at -2.9%
        assert strategy._should_stop_loss(-2.9) is False
        
        # Test tolerance - should trigger at -2.99% (within 0.01% tolerance)
        assert strategy._should_stop_loss(-2.99) is True
    
    def test_should_take_profit_conditions(self, valid_config):
        """Test take profit condition logic."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Calculate expected threshold
        # trading_fee = 0.0005, bilateral fees = 0.1%, target_profit = 0.5%
        # threshold = 0.5 + 0.1 = 0.6%
        
        # Should take profit at 0.7%
        assert strategy._should_take_profit(0.7) is True
        
        # Should take profit at exactly 0.6%
        assert strategy._should_take_profit(0.6) is True
        
        # Should not take profit at 0.5%
        assert strategy._should_take_profit(0.5) is False
    
    def test_calculate_position_pnl_accuracy(self, valid_config):
        """Test PnL calculation accuracy."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        position = StopLossPosition(
            market='KRW-BTC',
            entries=[PositionEntry(
                price=50000.0,
                quantity=0.1,
                cost=5000.0,
                order_type='initial',
                timestamp=datetime.now()
            )],
            average_price=50000.0,
            total_quantity=0.1,
            total_cost=5000.0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        current_price = 51000.0  # 2% profit
        pnl_info = strategy._calculate_position_pnl(current_price, position)
        
        assert pnl_info is not None
        
        # Expected calculations
        current_value = 51000.0 * 0.1  # 5100.0
        buy_fees = 5000.0 * 0.0005     # 2.5
        sell_fees = 5100.0 * 0.0005    # 2.55
        expected_net_pnl = 5100.0 - 5000.0 - 2.5 - 2.55  # 94.95
        expected_pnl_rate = (94.95 / (5000.0 + 2.5)) * 100  # ~1.898%
        
        assert abs(pnl_info['pnl'] - expected_net_pnl) < 0.01
        assert abs(pnl_info['pnl_rate'] - expected_pnl_rate) < 0.01
        assert abs(pnl_info['buy_fees'] - buy_fees) < 0.01
        assert abs(pnl_info['sell_fees'] - sell_fees) < 0.01
        assert abs(pnl_info['current_value'] - current_value) < 0.01
    
    def test_strategy_suspension_and_resumption(self, valid_config):
        """Test strategy suspension and resumption."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Initially not suspended
        assert strategy.strategy_state.is_suspended is False
        assert strategy.strategy_state.suspension_reason is None
        
        # Suspend strategy
        strategy._suspend_strategy("Test suspension")
        assert strategy.strategy_state.is_suspended is True
        assert strategy.strategy_state.suspension_reason == "Test suspension"
        
        # Resume strategy
        strategy._resume_strategy()
        assert strategy.strategy_state.is_suspended is False
        assert strategy.strategy_state.suspension_reason is None
    
    def test_get_strategy_info(self, valid_config):
        """Test strategy information retrieval."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        info = strategy.get_strategy_info()
        
        assert info['strategy_id'] == "test_strategy"
        assert info['strategy_type'] == 'stop_loss_averaging'
        assert info['stop_loss_level'] == -3.0
        assert info['averaging_trigger'] == -1.0
        assert info['target_profit'] == 0.5
        assert info['max_averaging_count'] == 1
        assert info['trading_fee'] == 0.0005
        assert info['monitoring_interval'] == 10
        assert 'strategy_state' in info
        assert 'position_count' in info
        assert 'risk_status' in info
    
    def test_update_position_after_initial_buy(self, valid_config):
        """Test position update after initial buy trade."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Mock position manager
        strategy.position_manager.has_position = Mock(return_value=False)
        strategy.position_manager.add_initial_position = Mock()
        
        # Mock risk controller
        strategy.risk_controller.record_trade = Mock()
        
        # Execute initial buy
        strategy.update_position_after_trade(
            market='KRW-BTC',
            action='buy',
            price=50000.0,
            quantity=0.1
        )
        
        # Verify calls
        strategy.position_manager.add_initial_position.assert_called_once_with(
            'KRW-BTC', 50000.0, 0.1, None
        )
        strategy.risk_controller.record_trade.assert_called_once()
    
    def test_update_position_after_averaging_buy(self, valid_config):
        """Test position update after averaging buy trade."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Mock position manager
        strategy.position_manager.has_position = Mock(return_value=True)
        strategy.position_manager.add_averaging_position = Mock()
        
        # Mock risk controller
        strategy.risk_controller.record_trade = Mock()
        
        # Execute averaging buy
        strategy.update_position_after_trade(
            market='KRW-BTC',
            action='buy',
            price=49000.0,
            quantity=0.1
        )
        
        # Verify calls
        strategy.position_manager.add_averaging_position.assert_called_once_with(
            'KRW-BTC', 49000.0, 0.1, None
        )
        strategy.risk_controller.record_trade.assert_called_once()
    
    def test_update_position_after_full_sell(self, valid_config):
        """Test position update after full sell trade."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Create mock position
        mock_position = Mock()
        mock_position.total_quantity = 0.1
        
        # Mock position manager
        strategy.position_manager.has_position = Mock(return_value=True)
        strategy.position_manager.get_position = Mock(return_value=mock_position)
        strategy.position_manager.close_position = Mock()
        strategy.position_manager.get_position_pnl = Mock(return_value={'pnl_rate': -2.0})
        
        # Mock risk controller
        strategy.risk_controller.record_trade = Mock()
        
        # Mock managers reset
        strategy.partial_sell_manager.reset = Mock()
        strategy.trailing_stop_manager.reset = Mock()
        
        # Execute full sell
        strategy.update_position_after_trade(
            market='KRW-BTC',
            action='sell',
            price=51000.0,
            quantity=0.1  # Full quantity
        )
        
        # Verify calls
        strategy.position_manager.close_position.assert_called_once_with('KRW-BTC')
        strategy.partial_sell_manager.reset.assert_called_once()
        strategy.trailing_stop_manager.reset.assert_called_once()
        strategy.risk_controller.record_trade.assert_called_once()
    
    def test_update_position_after_partial_sell(self, valid_config):
        """Test position update after partial sell trade."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Create mock position
        mock_position = Mock()
        mock_position.total_quantity = 0.1
        
        # Mock position manager
        strategy.position_manager.has_position = Mock(return_value=True)
        strategy.position_manager.get_position = Mock(return_value=mock_position)
        strategy.position_manager.partial_sell = Mock()
        strategy.position_manager.get_position_pnl = Mock(return_value={'pnl_rate': 1.0})
        
        # Mock risk controller
        strategy.risk_controller.record_trade = Mock()
        
        # Execute partial sell
        strategy.update_position_after_trade(
            market='KRW-BTC',
            action='sell',
            price=51000.0,
            quantity=0.05  # Partial quantity
        )
        
        # Verify calls
        strategy.position_manager.partial_sell.assert_called_once_with(
            'KRW-BTC', 0.05, 51000.0, None
        )
        strategy.risk_controller.record_trade.assert_called_once()
    
    def test_evaluate_handles_exceptions(self, valid_config, sample_market_data):
        """Test that evaluate method handles exceptions properly."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Mock market analyzer to raise exception
        strategy.market_analyzer.analyze_market_conditions = Mock(
            side_effect=Exception("Test exception")
        )
        
        with pytest.raises(StrategyEvaluationError, match="Strategy evaluation failed"):
            strategy.evaluate(sample_market_data)
    
    def test_evaluate_suspended_strategy_returns_none(self, valid_config, sample_market_data):
        """Test that suspended strategy returns None from evaluate."""
        strategy = StopLossAveragingStrategy("test_strategy", valid_config)
        
        # Suspend strategy
        strategy._suspend_strategy("Test suspension")
        
        result = strategy.evaluate(sample_market_data)
        assert result is None