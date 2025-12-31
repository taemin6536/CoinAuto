"""
Simple Moving Average Crossover Strategy Implementation.

This strategy generates buy signals when the short-term SMA crosses above the long-term SMA
and sell signals when the short-term SMA crosses below the long-term SMA.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import statistics

from .base import TradingStrategy, MarketData, StrategyEvaluationError
from ..data.models import TradingSignal


class SMAStrategy(TradingStrategy):
    """Simple Moving Average Crossover Strategy."""
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        """Initialize SMA strategy with configuration."""
        super().__init__(strategy_id, config)
        
        # Extract strategy parameters
        params = config.get('parameters', {})
        self.short_period = params.get('short_period', 10)
        self.long_period = params.get('long_period', 30)
        self.signal_threshold = params.get('signal_threshold', 0.8)
        self.confirmation_periods = params.get('buy_signal', {}).get('confirmation_periods', 2)
        
        # Risk management parameters
        risk_params = params.get('risk', {})
        self.max_position_size = risk_params.get('max_position_size', 0.15)
        self.stop_loss = risk_params.get('stop_loss', 0.03)
        self.take_profit = risk_params.get('take_profit', 0.06)
        
        # Timing parameters
        self.evaluation_frequency = params.get('evaluation_frequency', 300)
        self.min_volume_threshold = params.get('min_volume_threshold', 1000000)
        
        # State tracking for confirmation
        self.crossover_count = 0
        self.last_signal_type = None
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate strategy configuration parameters."""
        if self.short_period >= self.long_period:
            raise StrategyEvaluationError(
                f"Short period ({self.short_period}) must be less than long period ({self.long_period})"
            )
        
        if not (0 < self.signal_threshold <= 1):
            raise StrategyEvaluationError(
                f"Signal threshold ({self.signal_threshold}) must be between 0 and 1"
            )
    
    def get_required_history_length(self) -> int:
        """Return minimum history length needed for SMA calculation."""
        return max(self.long_period, 50)  # Extra buffer for stability
    
    def _calculate_sma(self, prices: List[float], period: int) -> float:
        """Calculate Simple Moving Average for given period."""
        if len(prices) < period:
            raise StrategyEvaluationError(f"Insufficient data for SMA calculation: need {period}, got {len(prices)}")
        
        return statistics.mean(prices[-period:])
    
    def _check_volume_condition(self, market_data: MarketData) -> bool:
        """Check if current volume meets minimum threshold."""
        current_volume_krw = market_data.current_ticker.trade_volume * market_data.current_ticker.trade_price
        return current_volume_krw >= self.min_volume_threshold
    
    def _detect_crossover(self, short_sma: float, long_sma: float, 
                         prev_short_sma: float, prev_long_sma: float) -> Optional[str]:
        """
        Detect SMA crossover events.
        
        Returns:
            'bullish' for upward crossover, 'bearish' for downward crossover, None for no crossover
        """
        # Current state
        current_above = short_sma > long_sma
        # Previous state
        previous_above = prev_short_sma > prev_long_sma
        
        if not current_above and previous_above:
            return 'bearish'  # Short SMA crossed below long SMA
        elif current_above and not previous_above:
            return 'bullish'  # Short SMA crossed above long SMA
        
        return None
    
    def _calculate_confidence(self, short_sma: float, long_sma: float, 
                            market_data: MarketData) -> float:
        """
        Calculate signal confidence based on various factors.
        
        Args:
            short_sma: Short-term SMA value
            long_sma: Long-term SMA value
            market_data: Current market data
            
        Returns:
            Confidence score between 0 and 1
        """
        # Base confidence from SMA separation
        price_diff_ratio = abs(short_sma - long_sma) / long_sma
        base_confidence = min(price_diff_ratio * 10, 0.8)  # Cap at 0.8
        
        # Volume confirmation
        volume_boost = 0.0
        if self._check_volume_condition(market_data):
            volume_boost = 0.2
        
        # Trend strength (based on recent price movement)
        if len(market_data.price_history) >= 5:
            recent_trend = (market_data.price_history[-1] - market_data.price_history[-5]) / market_data.price_history[-5]
            trend_boost = min(abs(recent_trend) * 2, 0.1)
        else:
            trend_boost = 0.0
        
        total_confidence = min(base_confidence + volume_boost + trend_boost, 1.0)
        return total_confidence
    
    def evaluate(self, market_data: MarketData) -> Optional[TradingSignal]:
        """
        Evaluate SMA crossover strategy and generate trading signals.
        
        Args:
            market_data: Current market data
            
        Returns:
            TradingSignal if conditions are met, None otherwise
        """
        try:
            self.last_evaluation = datetime.now()
            
            # Check if we can evaluate
            if not self.can_evaluate(market_data):
                return None
            
            prices = market_data.price_history
            
            # Calculate current SMAs
            short_sma = self._calculate_sma(prices, self.short_period)
            long_sma = self._calculate_sma(prices, self.long_period)
            
            # Calculate previous SMAs for crossover detection
            if len(prices) > self.long_period:
                prev_short_sma = self._calculate_sma(prices[:-1], self.short_period)
                prev_long_sma = self._calculate_sma(prices[:-1], self.long_period)
            else:
                # Not enough data for crossover detection
                return None
            
            # Detect crossover
            crossover_type = self._detect_crossover(short_sma, long_sma, prev_short_sma, prev_long_sma)
            
            if crossover_type is None:
                # No crossover, check if we're continuing a trend
                if self.last_signal_type == crossover_type:
                    self.crossover_count = 0
                return None
            
            # Handle confirmation periods
            if crossover_type == self.last_signal_type:
                self.crossover_count += 1
            else:
                self.crossover_count = 1
                self.last_signal_type = crossover_type
            
            # Check if we have enough confirmation
            if self.crossover_count < self.confirmation_periods:
                return None
            
            # Calculate confidence
            confidence = self._calculate_confidence(short_sma, long_sma, market_data)
            
            # Check if confidence meets threshold
            if confidence < self.signal_threshold:
                return None
            
            # Generate signal
            action = 'buy' if crossover_type == 'bullish' else 'sell'
            current_price = market_data.current_ticker.trade_price
            
            # Calculate volume based on position size
            volume = self.max_position_size  # This will be adjusted by order manager
            
            signal = TradingSignal(
                market=market_data.current_ticker.market,
                action=action,
                confidence=confidence,
                price=current_price,
                volume=volume,
                strategy_id=self.strategy_id,
                timestamp=datetime.now()
            )
            
            # Reset confirmation counter after generating signal
            self.crossover_count = 0
            
            return signal
            
        except Exception as e:
            raise StrategyEvaluationError(f"SMA strategy evaluation failed: {str(e)}") from e
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get extended strategy information including SMA-specific data."""
        base_info = super().get_strategy_info()
        base_info.update({
            'strategy_type': 'sma_crossover',
            'short_period': self.short_period,
            'long_period': self.long_period,
            'signal_threshold': self.signal_threshold,
            'crossover_count': self.crossover_count,
            'last_signal_type': self.last_signal_type
        })
        return base_info