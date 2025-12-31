"""
Base trading strategy interface and abstract classes.

This module defines the core interfaces and abstract classes that all trading strategies
must implement. It provides the foundation for strategy independence and consistent
signal generation across different trading algorithms.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

from ..data.models import TradingSignal, Ticker


@dataclass
class MarketData:
    """Market data container for strategy evaluation."""
    
    current_ticker: Ticker
    price_history: List[float]
    volume_history: List[float]
    timestamps: List[datetime]
    
    def validate(self) -> bool:
        """Validate market data consistency."""
        if not self.current_ticker or not self.current_ticker.validate():
            return False
        
        # All history lists should have the same length
        history_lengths = [
            len(self.price_history),
            len(self.volume_history),
            len(self.timestamps)
        ]
        
        if len(set(history_lengths)) > 1:
            return False
            
        return True


class TradingStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    This interface ensures strategy independence by providing a consistent
    evaluation method that all strategies must implement. Each strategy
    operates independently and generates signals based solely on market data.
    """
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        """
        Initialize trading strategy.
        
        Args:
            strategy_id: Unique identifier for this strategy instance
            config: Strategy configuration parameters
        """
        self.strategy_id = strategy_id
        self.config = config
        self.enabled = config.get('enabled', True)
        self.markets = config.get('markets', [])
        self.last_evaluation = None
        
    @abstractmethod
    def evaluate(self, market_data: MarketData) -> Optional[TradingSignal]:
        """
        Evaluate market conditions and generate trading signal if criteria are met.
        
        This method must be implemented by all concrete strategy classes.
        It should analyze the provided market data and return a trading signal
        if the strategy's conditions are satisfied.
        
        Args:
            market_data: Current market data for evaluation
            
        Returns:
            TradingSignal if conditions are met, None otherwise
        """
        pass
    
    @abstractmethod
    def get_required_history_length(self) -> int:
        """
        Return the minimum number of historical data points required for evaluation.
        
        Returns:
            int: Minimum history length needed
        """
        pass
    
    def can_evaluate(self, market_data: MarketData) -> bool:
        """
        Check if strategy can evaluate given market data.
        
        Args:
            market_data: Market data to check
            
        Returns:
            bool: True if evaluation is possible
        """
        if not self.enabled:
            return False
            
        if not market_data.validate():
            return False
            
        if len(market_data.price_history) < self.get_required_history_length():
            return False
            
        # Check if this strategy applies to the current market
        if self.markets and market_data.current_ticker.market not in self.markets:
            return False
            
        return True
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """
        Get strategy information and current configuration.
        
        Returns:
            Dict containing strategy metadata
        """
        return {
            'strategy_id': self.strategy_id,
            'enabled': self.enabled,
            'markets': self.markets,
            'last_evaluation': self.last_evaluation.isoformat() if self.last_evaluation else None,
            'config': self.config
        }
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """
        Update strategy configuration (for hot reload support).
        
        Args:
            new_config: New configuration parameters
        """
        self.config.update(new_config)
        self.enabled = self.config.get('enabled', True)
        self.markets = self.config.get('markets', [])


class StrategyError(Exception):
    """Base exception for strategy-related errors."""
    pass


class StrategyEvaluationError(StrategyError):
    """Exception raised when strategy evaluation fails."""
    pass


class StrategyConfigurationError(StrategyError):
    """Exception raised when strategy configuration is invalid."""
    pass