"""
Trading strategy management module.

This module provides the core infrastructure for implementing and managing
trading strategies in the Upbit trading bot. It includes:

- Base strategy interface and abstract classes
- Concrete strategy implementations (SMA, RSI)
- Strategy manager for loading and coordinating multiple strategies
- Conflict resolution and signal generation

Key Components:
- TradingStrategy: Abstract base class for all strategies
- StrategyManager: Central coordinator for multiple strategies
- MarketData: Data container for strategy evaluation
- Strategy implementations: SMAStrategy, RSIStrategy

Usage:
    from upbit_trading_bot.strategy import StrategyManager, MarketData
    
    manager = StrategyManager("config/strategies")
    manager.load_strategies()
    
    # Evaluate strategies with market data
    signals = manager.evaluate_strategies(market_data)
"""

from .base import TradingStrategy, MarketData, StrategyError, StrategyEvaluationError, StrategyConfigurationError
from .manager import StrategyManager
from .sma_crossover import SMAStrategy
from .rsi_momentum import RSIStrategy

__all__ = [
    'TradingStrategy',
    'MarketData', 
    'StrategyError',
    'StrategyEvaluationError',
    'StrategyConfigurationError',
    'StrategyManager',
    'SMAStrategy',
    'RSIStrategy'
]