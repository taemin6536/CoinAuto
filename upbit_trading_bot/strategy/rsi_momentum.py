"""
RSI Momentum Strategy Implementation.

This strategy uses the Relative Strength Index (RSI) to identify oversold and overbought
conditions, generating buy signals in oversold conditions and sell signals in overbought conditions.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import statistics

from .base import TradingStrategy, MarketData, StrategyEvaluationError
from ..data.models import TradingSignal


class RSIStrategy(TradingStrategy):
    """RSI-based Momentum Trading Strategy."""
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        """Initialize RSI strategy with configuration."""
        super().__init__(strategy_id, config)
        
        # Extract strategy parameters
        params = config.get('parameters', {})
        self.rsi_period = params.get('rsi_period', 14)
        self.oversold_threshold = params.get('oversold_threshold', 30)
        self.overbought_threshold = params.get('overbought_threshold', 70)
        self.signal_threshold = params.get('signal_threshold', 0.75)
        
        # Risk management parameters
        risk_params = params.get('risk', {})
        self.max_position_size = risk_params.get('max_position_size', 0.1)
        self.stop_loss = risk_params.get('stop_loss', 0.04)
        self.take_profit = risk_params.get('take_profit', 0.08)
        self.trailing_stop = risk_params.get('trailing_stop', True)
        self.trailing_stop_percentage = risk_params.get('trailing_stop_percentage', 0.02)
        
        # Timing parameters
        self.evaluation_frequency = params.get('evaluation_frequency', 180)
        self.min_volume_threshold = params.get('min_volume_threshold', 500000)
        
        # Technical indicator parameters
        indicators = params.get('indicators', {})
        self.volume_sma_period = indicators.get('volume_sma_period', 20)
        self.price_sma_period = indicators.get('price_sma_period', 50)
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate strategy configuration parameters."""
        if not (0 < self.oversold_threshold < self.overbought_threshold < 100):
            raise StrategyEvaluationError(
                f"Invalid RSI thresholds: oversold={self.oversold_threshold}, overbought={self.overbought_threshold}"
            )
        
        if not (0 < self.signal_threshold <= 1):
            raise StrategyEvaluationError(
                f"Signal threshold ({self.signal_threshold}) must be between 0 and 1"
            )
        
        if self.rsi_period < 2:
            raise StrategyEvaluationError(f"RSI period ({self.rsi_period}) must be at least 2")
    
    def get_required_history_length(self) -> int:
        """Return minimum history length needed for RSI calculation."""
        return max(self.rsi_period + 10, self.volume_sma_period, self.price_sma_period) + 5
    
    def _calculate_rsi(self, prices: List[float]) -> float:
        """
        Calculate Relative Strength Index (RSI).
        
        Args:
            prices: List of price values
            
        Returns:
            RSI value between 0 and 100
        """
        if len(prices) < self.rsi_period + 1:
            raise StrategyEvaluationError(
                f"Insufficient data for RSI calculation: need {self.rsi_period + 1}, got {len(prices)}"
            )
        
        # Calculate price changes
        price_changes = []
        for i in range(1, len(prices)):
            price_changes.append(prices[i] - prices[i-1])
        
        # Separate gains and losses
        gains = [max(change, 0) for change in price_changes]
        losses = [abs(min(change, 0)) for change in price_changes]
        
        # Calculate average gains and losses
        if len(gains) < self.rsi_period or len(losses) < self.rsi_period:
            raise StrategyEvaluationError("Insufficient data for RSI calculation")
        
        avg_gain = statistics.mean(gains[-self.rsi_period:])
        avg_loss = statistics.mean(losses[-self.rsi_period:])
        
        # Calculate RSI
        if avg_loss == 0:
            return 100.0  # No losses, RSI = 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_volume_sma(self, volumes: List[float]) -> float:
        """Calculate Simple Moving Average for volume."""
        if len(volumes) < self.volume_sma_period:
            raise StrategyEvaluationError(
                f"Insufficient volume data for SMA: need {self.volume_sma_period}, got {len(volumes)}"
            )
        
        return statistics.mean(volumes[-self.volume_sma_period:])
    
    def _check_volume_condition(self, market_data: MarketData, multiplier: float = 1.5) -> bool:
        """Check if current volume meets the specified multiplier of average volume."""
        try:
            avg_volume = self._calculate_volume_sma(market_data.volume_history)
            current_volume = market_data.current_ticker.trade_volume
            return current_volume > avg_volume * multiplier
        except StrategyEvaluationError:
            # If we can't calculate average volume, use absolute threshold
            current_volume_krw = (market_data.current_ticker.trade_volume * 
                                market_data.current_ticker.trade_price)
            return current_volume_krw >= self.min_volume_threshold
    
    def _check_price_change_condition(self, market_data: MarketData, max_decline: float = -0.02) -> bool:
        """Check if price is not falling too fast."""
        if len(market_data.price_history) < 2:
            return True  # Can't determine, assume OK
        
        current_price = market_data.current_ticker.trade_price
        previous_price = market_data.price_history[-2]
        price_change = (current_price - previous_price) / previous_price
        
        return price_change > max_decline
    
    def _calculate_confidence(self, rsi: float, market_data: MarketData, signal_type: str) -> float:
        """
        Calculate signal confidence based on RSI value and additional factors.
        
        Args:
            rsi: Current RSI value
            market_data: Current market data
            signal_type: 'buy' or 'sell'
            
        Returns:
            Confidence score between 0 and 1
        """
        # Base confidence from RSI extremity
        if signal_type == 'buy':
            # More oversold = higher confidence
            base_confidence = max(0, (self.oversold_threshold - rsi) / self.oversold_threshold)
        else:  # sell
            # More overbought = higher confidence
            base_confidence = max(0, (rsi - self.overbought_threshold) / (100 - self.overbought_threshold))
        
        # Volume confirmation boost
        volume_boost = 0.0
        try:
            if signal_type == 'buy' and self._check_volume_condition(market_data, 1.5):
                volume_boost = 0.2
            elif signal_type == 'sell' and self._check_volume_condition(market_data, 1.2):
                volume_boost = 0.15
        except StrategyEvaluationError:
            pass  # Skip volume boost if can't calculate
        
        # Price change confirmation (for buy signals)
        price_boost = 0.0
        if signal_type == 'buy' and self._check_price_change_condition(market_data):
            price_boost = 0.1
        
        total_confidence = min(base_confidence + volume_boost + price_boost, 1.0)
        return total_confidence
    
    def evaluate(self, market_data: MarketData) -> Optional[TradingSignal]:
        """
        Evaluate RSI momentum strategy and generate trading signals.
        
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
            
            # Calculate RSI
            rsi = self._calculate_rsi(prices)
            
            # Determine signal type based on RSI thresholds
            signal_type = None
            if rsi < self.oversold_threshold:
                signal_type = 'buy'
            elif rsi > self.overbought_threshold:
                signal_type = 'sell'
            else:
                return None  # RSI in neutral zone
            
            # Check additional filters based on signal type
            if signal_type == 'buy':
                # Check buy signal filters
                if not self._check_volume_condition(market_data, 1.5):
                    return None
                if not self._check_price_change_condition(market_data, -0.02):
                    return None
            elif signal_type == 'sell':
                # Check sell signal filters
                if not self._check_volume_condition(market_data, 1.2):
                    return None
            
            # Calculate confidence
            confidence = self._calculate_confidence(rsi, market_data, signal_type)
            
            # Check if confidence meets threshold
            if confidence < self.signal_threshold:
                return None
            
            # Generate signal
            current_price = market_data.current_ticker.trade_price
            
            # Calculate volume based on position size
            volume = self.max_position_size  # This will be adjusted by order manager
            
            signal = TradingSignal(
                market=market_data.current_ticker.market,
                action=signal_type,
                confidence=confidence,
                price=current_price,
                volume=volume,
                strategy_id=self.strategy_id,
                timestamp=datetime.now()
            )
            
            return signal
            
        except Exception as e:
            raise StrategyEvaluationError(f"RSI strategy evaluation failed: {str(e)}") from e
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get extended strategy information including RSI-specific data."""
        base_info = super().get_strategy_info()
        base_info.update({
            'strategy_type': 'rsi_momentum',
            'rsi_period': self.rsi_period,
            'oversold_threshold': self.oversold_threshold,
            'overbought_threshold': self.overbought_threshold,
            'signal_threshold': self.signal_threshold
        })
        return base_info