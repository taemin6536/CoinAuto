"""
Unit tests for MarketAnalyzer class.

Tests specific examples, edge cases, and integration points for the market analyzer
that supports the stop-loss averaging strategy.
"""

import pytest
from datetime import datetime
from typing import List

from upbit_trading_bot.strategy.market_analyzer import MarketAnalyzer
from upbit_trading_bot.data.models import MarketConditions, Ticker
from upbit_trading_bot.data.market_data import MarketData


class TestMarketAnalyzer:
    """Test suite for MarketAnalyzer class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.analyzer = MarketAnalyzer()
        self.base_price = 50000000.0
        
    def create_test_market_data(self, 
                               trade_price: float = None,
                               trade_volume: float = 1.5,
                               change_rate: float = 0.01,
                               price_history: List[float] = None) -> MarketData:
        """Create test market data with specified parameters."""
        if trade_price is None:
            trade_price = self.base_price
            
        if price_history is None:
            price_history = [self.base_price + i * 1000 for i in range(20)]
        
        ticker = Ticker(
            market="KRW-BTC",
            trade_price=trade_price,
            trade_volume=trade_volume,
            timestamp=datetime.now(),
            change_rate=change_rate
        )
        
        return MarketData(
            ticker=ticker,
            orderbook=None,
            timestamp=datetime.now(),
            price_history=price_history
        )
    
    def test_initialization_with_default_config(self):
        """Test MarketAnalyzer initialization with default configuration."""
        analyzer = MarketAnalyzer()
        
        assert analyzer.volatility_threshold == 5.0
        assert analyzer.volume_ratio_threshold == 1.5
        assert analyzer.rapid_decline_threshold == -2.0
        assert analyzer.rsi_oversold_threshold == 30
        assert analyzer.market_decline_threshold == -3.0
        assert analyzer.rsi_period == 14
    
    def test_initialization_with_custom_config(self):
        """Test MarketAnalyzer initialization with custom configuration."""
        config = {
            'volatility_threshold': 7.0,
            'volume_ratio_threshold': 2.0,
            'rapid_decline_threshold': -1.5,
            'rsi_oversold_threshold': 25,
            'market_decline_threshold': -4.0,
            'rsi_period': 21
        }
        analyzer = MarketAnalyzer(config)
        
        assert analyzer.volatility_threshold == 7.0
        assert analyzer.volume_ratio_threshold == 2.0
        assert analyzer.rapid_decline_threshold == -1.5
        assert analyzer.rsi_oversold_threshold == 25
        assert analyzer.market_decline_threshold == -4.0
        assert analyzer.rsi_period == 21
    
    def test_calculate_24h_volatility_positive_change(self):
        """Test 24-hour volatility calculation with positive change rate."""
        market_data = self.create_test_market_data(change_rate=0.05)  # 5% positive
        
        volatility = self.analyzer.calculate_24h_volatility(market_data)
        
        assert volatility == 5.0  # Should return absolute value as percentage
    
    def test_calculate_24h_volatility_negative_change(self):
        """Test 24-hour volatility calculation with negative change rate."""
        market_data = self.create_test_market_data(change_rate=-0.03)  # -3% negative
        
        volatility = self.analyzer.calculate_24h_volatility(market_data)
        
        assert volatility == 3.0  # Should return absolute value as percentage
    
    def test_calculate_24h_volatility_no_ticker(self):
        """Test 24-hour volatility calculation with no ticker data."""
        market_data = MarketData(ticker=None, orderbook=None, timestamp=datetime.now())
        
        volatility = self.analyzer.calculate_24h_volatility(market_data)
        
        assert volatility == 0.0
    
    def test_calculate_volume_ratio_normal(self):
        """Test volume ratio calculation with normal volume."""
        market_data = self.create_test_market_data(trade_volume=2.0)
        
        volume_ratio = self.analyzer.calculate_volume_ratio(market_data)
        
        assert volume_ratio == 2.0  # Current volume / base volume (1.0)
    
    def test_calculate_volume_ratio_no_ticker(self):
        """Test volume ratio calculation with no ticker data."""
        market_data = MarketData(ticker=None, orderbook=None, timestamp=datetime.now())
        
        volume_ratio = self.analyzer.calculate_volume_ratio(market_data)
        
        assert volume_ratio == 1.0  # Default ratio
    
    def test_calculate_rsi_insufficient_data(self):
        """Test RSI calculation with insufficient price data."""
        short_prices = [100.0, 101.0, 102.0]  # Less than required period
        
        rsi = self.analyzer.calculate_rsi(short_prices, 14)
        
        assert rsi == 50.0  # Should return neutral value
    
    def test_calculate_rsi_all_gains(self):
        """Test RSI calculation with all price gains."""
        rising_prices = [100.0 + i for i in range(20)]  # Continuous rise
        
        rsi = self.analyzer.calculate_rsi(rising_prices, 14)
        
        assert rsi == 100.0  # Should return maximum RSI
    
    def test_calculate_rsi_mixed_pattern(self):
        """Test RSI calculation with mixed price pattern."""
        mixed_prices = []
        base = 100.0
        for i in range(20):
            if i % 2 == 0:
                mixed_prices.append(base + i * 0.5)
            else:
                mixed_prices.append(base - i * 0.3)
        
        rsi = self.analyzer.calculate_rsi(mixed_prices, 14)
        
        assert 0 <= rsi <= 100  # Should be within valid range
        assert 40 <= rsi <= 60  # Should be near neutral for mixed pattern
    
    def test_calculate_price_change_1m_normal(self):
        """Test 1-minute price change calculation with normal data."""
        price_history = [100.0] * 18 + [100.0, 102.0]  # 2% increase
        market_data = self.create_test_market_data(price_history=price_history)
        
        price_change = self.analyzer.calculate_price_change_1m(market_data)
        
        assert abs(price_change - 2.0) < 0.01  # Should be approximately 2%
    
    def test_calculate_price_change_1m_insufficient_data(self):
        """Test 1-minute price change calculation with insufficient data."""
        price_history = [100.0]  # Only one price point
        market_data = self.create_test_market_data(price_history=price_history)
        
        price_change = self.analyzer.calculate_price_change_1m(market_data)
        
        assert price_change == 0.0
    
    def test_calculate_price_change_1m_zero_previous_price(self):
        """Test 1-minute price change calculation with zero previous price."""
        price_history = [100.0] * 18 + [0.0, 100.0]  # Zero previous price
        market_data = self.create_test_market_data(price_history=price_history)
        
        price_change = self.analyzer.calculate_price_change_1m(market_data)
        
        assert price_change == 0.0
    
    def test_detect_rapid_decline_true(self):
        """Test rapid decline detection when decline exceeds threshold."""
        # Create price history with 3% decline
        price_history = [100.0] * 18 + [100.0, 97.0]
        market_data = self.create_test_market_data(price_history=price_history)
        
        is_rapid_decline = self.analyzer.detect_rapid_decline(market_data)
        
        assert is_rapid_decline is True
    
    def test_detect_rapid_decline_false(self):
        """Test rapid decline detection when decline is within threshold."""
        # Create price history with 1% decline
        price_history = [100.0] * 18 + [100.0, 99.0]
        market_data = self.create_test_market_data(price_history=price_history)
        
        is_rapid_decline = self.analyzer.detect_rapid_decline(market_data)
        
        assert is_rapid_decline is False
    
    def test_check_market_trend_bullish(self):
        """Test market trend analysis for bullish trend."""
        # Create rising price pattern
        price_history = [100.0 + i * 2 for i in range(20)]  # Strong upward trend
        market_data = self.create_test_market_data(price_history=price_history)
        
        trend = self.analyzer.check_market_trend(market_data)
        
        assert trend == 'bullish'
    
    def test_check_market_trend_bearish(self):
        """Test market trend analysis for bearish trend."""
        # Create falling price pattern
        price_history = [100.0 - i * 2 for i in range(20)]  # Strong downward trend
        market_data = self.create_test_market_data(price_history=price_history)
        
        trend = self.analyzer.check_market_trend(market_data)
        
        assert trend == 'bearish'
    
    def test_check_market_trend_neutral(self):
        """Test market trend analysis for neutral trend."""
        # Create sideways price pattern
        price_history = [100.0 + (i % 2) * 0.5 for i in range(20)]  # Small oscillations
        market_data = self.create_test_market_data(price_history=price_history)
        
        trend = self.analyzer.check_market_trend(market_data)
        
        assert trend == 'neutral'
    
    def test_check_market_trend_insufficient_data(self):
        """Test market trend analysis with insufficient data."""
        price_history = [100.0, 101.0]  # Less than 5 data points
        market_data = self.create_test_market_data(price_history=price_history)
        
        trend = self.analyzer.check_market_trend(market_data)
        
        assert trend == 'neutral'
    
    def test_should_select_high_volatility_coin_true(self):
        """Test high volatility coin selection when volatility exceeds threshold."""
        conditions = MarketConditions(
            volatility_24h=6.0,  # Above default threshold of 5%
            volume_ratio=1.0,
            rsi=50.0,
            price_change_1m=0.0,
            market_trend='neutral',
            is_rapid_decline=False
        )
        
        should_select = self.analyzer.should_select_high_volatility_coin(conditions)
        
        assert should_select is True
    
    def test_should_select_high_volatility_coin_false(self):
        """Test high volatility coin selection when volatility is below threshold."""
        conditions = MarketConditions(
            volatility_24h=3.0,  # Below default threshold of 5%
            volume_ratio=1.0,
            rsi=50.0,
            price_change_1m=0.0,
            market_trend='neutral',
            is_rapid_decline=False
        )
        
        should_select = self.analyzer.should_select_high_volatility_coin(conditions)
        
        assert should_select is False
    
    def test_should_allow_buy_signal_all_conditions_met(self):
        """Test buy signal allowance when all conditions are met."""
        conditions = MarketConditions(
            volatility_24h=6.0,
            volume_ratio=2.0,  # Above threshold
            rsi=50.0,
            price_change_1m=-1.0,  # Above market decline threshold
            market_trend='neutral',
            is_rapid_decline=False  # No rapid decline
        )
        
        should_allow = self.analyzer.should_allow_buy_signal(conditions)
        
        assert should_allow is True
    
    def test_should_allow_buy_signal_low_volume(self):
        """Test buy signal allowance when volume condition is not met."""
        conditions = MarketConditions(
            volatility_24h=6.0,
            volume_ratio=1.0,  # Below threshold of 1.5
            rsi=50.0,
            price_change_1m=-1.0,
            market_trend='neutral',
            is_rapid_decline=False
        )
        
        should_allow = self.analyzer.should_allow_buy_signal(conditions)
        
        assert should_allow is False
    
    def test_should_allow_buy_signal_rapid_decline(self):
        """Test buy signal allowance when rapid decline is detected."""
        conditions = MarketConditions(
            volatility_24h=6.0,
            volume_ratio=2.0,
            rsi=50.0,
            price_change_1m=-1.0,
            market_trend='neutral',
            is_rapid_decline=True  # Rapid decline detected
        )
        
        should_allow = self.analyzer.should_allow_buy_signal(conditions)
        
        assert should_allow is False
    
    def test_should_allow_buy_signal_market_decline(self):
        """Test buy signal allowance when market decline exceeds threshold."""
        conditions = MarketConditions(
            volatility_24h=6.0,
            volume_ratio=2.0,
            rsi=50.0,
            price_change_1m=-4.0,  # Below market decline threshold of -3%
            market_trend='neutral',
            is_rapid_decline=False
        )
        
        should_allow = self.analyzer.should_allow_buy_signal(conditions)
        
        assert should_allow is False
    
    def test_should_suspend_strategy_true(self):
        """Test strategy suspension when market decline exceeds threshold."""
        conditions = MarketConditions(
            volatility_24h=6.0,
            volume_ratio=2.0,
            rsi=50.0,
            price_change_1m=-4.0,  # Below threshold of -3%
            market_trend='bearish',
            is_rapid_decline=False
        )
        
        should_suspend = self.analyzer.should_suspend_strategy(conditions)
        
        assert should_suspend is True
    
    def test_should_suspend_strategy_false(self):
        """Test strategy suspension when market decline is within threshold."""
        conditions = MarketConditions(
            volatility_24h=6.0,
            volume_ratio=2.0,
            rsi=50.0,
            price_change_1m=-2.0,  # Above threshold of -3%
            market_trend='neutral',
            is_rapid_decline=False
        )
        
        should_suspend = self.analyzer.should_suspend_strategy(conditions)
        
        assert should_suspend is False
    
    def test_get_buy_signal_confidence_base_case(self):
        """Test buy signal confidence calculation for base case."""
        conditions = MarketConditions(
            volatility_24h=3.0,  # Below volatility threshold
            volume_ratio=1.0,    # Below volume threshold
            rsi=50.0,           # Neutral RSI
            price_change_1m=0.0,
            market_trend='neutral',
            is_rapid_decline=False
        )
        
        confidence = self.analyzer.get_buy_signal_confidence(conditions)
        
        assert confidence == 0.5  # Base confidence
    
    def test_get_buy_signal_confidence_all_boosts(self):
        """Test buy signal confidence calculation with all confidence boosts."""
        conditions = MarketConditions(
            volatility_24h=6.0,  # Above volatility threshold (+0.1)
            volume_ratio=2.0,    # Above volume threshold (+0.1)
            rsi=25.0,           # Oversold RSI (+0.2)
            price_change_1m=0.0,
            market_trend='bullish',  # Bullish trend (+0.1)
            is_rapid_decline=False
        )
        
        confidence = self.analyzer.get_buy_signal_confidence(conditions)
        
        # Use approximate comparison for floating point
        assert abs(confidence - 1.0) < 0.001  # Maximum confidence (0.5 + 0.1 + 0.1 + 0.2 + 0.1)
    
    def test_get_buy_signal_confidence_clamped(self):
        """Test buy signal confidence calculation is clamped to valid range."""
        # Test with conditions that would exceed 1.0
        conditions = MarketConditions(
            volatility_24h=10.0,  # High volatility
            volume_ratio=5.0,     # High volume
            rsi=10.0,            # Very oversold
            price_change_1m=0.0,
            market_trend='bullish',
            is_rapid_decline=False
        )
        
        confidence = self.analyzer.get_buy_signal_confidence(conditions)
        
        assert 0.0 <= confidence <= 1.0  # Should be clamped to valid range
    
    def test_update_config(self):
        """Test configuration update functionality."""
        new_config = {
            'volatility_threshold': 8.0,
            'rsi_oversold_threshold': 25
        }
        
        self.analyzer.update_config(new_config)
        
        assert self.analyzer.volatility_threshold == 8.0
        assert self.analyzer.rsi_oversold_threshold == 25
        # Other values should remain unchanged
        assert self.analyzer.volume_ratio_threshold == 1.5
    
    def test_analyze_market_conditions_integration(self):
        """Test complete market conditions analysis integration."""
        market_data = self.create_test_market_data(
            trade_price=51000000.0,
            trade_volume=2.0,
            change_rate=0.06  # 6% volatility
        )
        
        conditions = self.analyzer.analyze_market_conditions(market_data)
        
        # Verify all fields are populated
        assert isinstance(conditions, MarketConditions)
        assert conditions.validate()
        assert conditions.volatility_24h == 6.0
        assert conditions.volume_ratio == 2.0
        assert 0 <= conditions.rsi <= 100
        assert isinstance(conditions.price_change_1m, float)
        assert conditions.market_trend in ['bullish', 'bearish', 'neutral']
        assert isinstance(conditions.is_rapid_decline, bool)
    
    def test_analyze_market_conditions_invalid_data(self):
        """Test market conditions analysis with invalid data."""
        # ticker가 있지만 유효하지 않은 MarketData 생성
        invalid_ticker = Ticker(
            market="",  # 빈 문자열 (유효하지 않음)
            trade_price=0,  # 0 이하 (유효하지 않음)
            trade_volume=-1,  # 음수 (유효하지 않음)
            timestamp=datetime.now(),
            change_rate=0.0
        )
        
        invalid_market_data = MarketData(
            ticker=invalid_ticker,
            orderbook=None,
            timestamp=datetime.now(),
            price_history=[100.0, 101.0]
        )
        
        # MarketData.validate()가 False를 반환하는지 확인
        assert not invalid_market_data.validate()
        
        # analyze_market_conditions가 ValueError를 발생시키는지 확인
        with pytest.raises(ValueError, match="Invalid market data provided"):
            self.analyzer.analyze_market_conditions(invalid_market_data)