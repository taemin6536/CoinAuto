"""
Strategy Manager for loading, managing, and evaluating trading strategies.

This module provides centralized management of trading strategies, including
loading from configuration files, strategy evaluation, signal generation,
and conflict resolution between multiple strategies.
"""

import os
import yaml
import logging
from typing import Dict, Any, List, Optional, Type
from datetime import datetime, timedelta
from pathlib import Path

from .base import TradingStrategy, StrategyError, StrategyConfigurationError
from .sma_crossover import SMAStrategy
from .rsi_momentum import RSIStrategy
from .simple_test import SimpleTestStrategy
from .aggressive_test import AggressiveTestStrategy
from .instant_test import InstantTestStrategy
from ..data.models import TradingSignal
from ..data.market_data import MarketData


class StrategyManager:
    """
    Manages multiple trading strategies and handles signal generation.
    
    This class is responsible for:
    - Loading strategies from configuration files
    - Evaluating strategies independently
    - Resolving conflicts between multiple signals
    - Supporting hot-reload of strategy configurations
    """
    
    # Registry of available strategy classes
    STRATEGY_REGISTRY: Dict[str, Type[TradingStrategy]] = {
        'sma_crossover': SMAStrategy,
        'rsi_momentum': RSIStrategy,
        'simple_test': SimpleTestStrategy,
        'aggressive_test': AggressiveTestStrategy,
        'instant_test': InstantTestStrategy,
    }
    
    def __init__(self, config_dir: str = "config/strategies"):
        """
        Initialize strategy manager.
        
        Args:
            config_dir: Directory containing strategy configuration files
        """
        self.config_dir = Path(config_dir)
        self.strategies: Dict[str, TradingStrategy] = {}
        self.strategy_configs: Dict[str, Dict[str, Any]] = {}
        self.last_config_check = datetime.now()
        self.config_check_interval = timedelta(seconds=5)  # Check for config changes every 5 seconds
        self.api_client = None  # API 클라이언트 저장
        
        self.logger = logging.getLogger(__name__)
        
        # Priority rules for conflict resolution
        self.priority_rules = {
            'default': 'confidence',  # Use highest confidence signal
            'strategy_priority': {
                'rsi_momentum': 1,
                'sma_crossover': 2
            }
        }
        
        self.logger.info(f"StrategyManager initialized with config directory: {self.config_dir}")
    
    def set_api_client(self, api_client):
        """
        API 클라이언트를 설정하고 모든 전략에 전달합니다.
        
        Args:
            api_client: API 클라이언트 인스턴스
        """
        self.api_client = api_client
        
        # 모든 전략에 API 클라이언트 설정
        for strategy in self.strategies.values():
            if hasattr(strategy, 'set_api_client'):
                strategy.set_api_client(api_client)
        
        self.logger.info("API 클라이언트가 전략 매니저와 모든 전략에 설정되었습니다")
    
    def load_strategies(self, config_path: Optional[str] = None) -> None:
        """
        Load strategies from configuration files.
        
        Args:
            config_path: Specific config file path, or None to load all from config_dir
        """
        try:
            if config_path:
                # Load single strategy from specific file
                self._load_single_strategy(config_path)
            else:
                # Load all strategies from config directory
                self._load_all_strategies()
                
            self.logger.info(f"Loaded {len(self.strategies)} strategies")
            
        except Exception as e:
            raise StrategyConfigurationError(f"Failed to load strategies: {str(e)}") from e
    
    def _load_all_strategies(self) -> None:
        """Load all strategy configuration files from the config directory."""
        if not self.config_dir.exists():
            self.logger.warning(f"Strategy config directory does not exist: {self.config_dir}")
            return
        
        # Find all YAML files in the config directory
        config_files = list(self.config_dir.glob("*.yaml")) + list(self.config_dir.glob("*.yml"))
        
        for config_file in config_files:
            try:
                self._load_single_strategy(str(config_file))
            except Exception as e:
                self.logger.error(f"Failed to load strategy from {config_file}: {str(e)}")
                continue
    
    def _load_single_strategy(self, config_path: str) -> None:
        """
        Load a single strategy from configuration file.
        
        Args:
            config_path: Path to strategy configuration file
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise StrategyConfigurationError(f"Strategy config file not found: {config_path}")
        
        # Load YAML configuration
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Validate configuration structure
        if 'strategy' not in config:
            raise StrategyConfigurationError(f"Missing 'strategy' section in {config_path}")
        
        strategy_info = config['strategy']
        strategy_name = strategy_info.get('name')
        
        if not strategy_name:
            raise StrategyConfigurationError(f"Missing strategy name in {config_path}")
        
        # Check if strategy is enabled
        if not strategy_info.get('enabled', True):
            self.logger.info(f"Strategy {strategy_name} is disabled, skipping")
            return
        
        # Get strategy class from registry
        strategy_class = self.STRATEGY_REGISTRY.get(strategy_name)
        if not strategy_class:
            raise StrategyConfigurationError(
                f"Unknown strategy type: {strategy_name}. Available: {list(self.STRATEGY_REGISTRY.keys())}"
            )
        
        # Create unique strategy ID
        strategy_id = f"{strategy_name}_{config_file.stem}"
        
        # Create strategy instance
        try:
            strategy = strategy_class(strategy_id, config)
            
            # API 클라이언트가 있으면 전략에 설정
            if self.api_client and hasattr(strategy, 'set_api_client'):
                strategy.set_api_client(self.api_client)
            
            self.strategies[strategy_id] = strategy
            self.strategy_configs[strategy_id] = config
            
            self.logger.info(f"Loaded strategy: {strategy_id} ({strategy_name})")
            
        except Exception as e:
            raise StrategyConfigurationError(
                f"Failed to create strategy {strategy_name}: {str(e)}"
            ) from e
    
    def add_strategy(self, strategy: TradingStrategy) -> None:
        """
        Add a strategy instance directly.
        
        Args:
            strategy: TradingStrategy instance to add
        """
        if strategy.strategy_id in self.strategies:
            self.logger.warning(f"Strategy {strategy.strategy_id} already exists, replacing")
        
        self.strategies[strategy.strategy_id] = strategy
        self.logger.info(f"Added strategy: {strategy.strategy_id}")
    
    def remove_strategy(self, strategy_id: str) -> None:
        """
        Remove a strategy by ID.
        
        Args:
            strategy_id: ID of strategy to remove
        """
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            if strategy_id in self.strategy_configs:
                del self.strategy_configs[strategy_id]
            self.logger.info(f"Removed strategy: {strategy_id}")
        else:
            self.logger.warning(f"Strategy not found for removal: {strategy_id}")
    
    def evaluate_strategies(self, market_data: MarketData) -> List[TradingSignal]:
        """
        Evaluate all strategies and return generated signals.
        
        This method ensures strategy independence by evaluating each strategy
        separately and collecting all generated signals.
        
        Args:
            market_data: Current market data for evaluation
            
        Returns:
            List of TradingSignal objects from all strategies
        """
        signals = []
        
        # Check for configuration changes (hot reload support)
        self._check_config_changes()
        
        for strategy_id, strategy in self.strategies.items():
            try:
                # Evaluate strategy independently
                signal = strategy.evaluate(market_data)
                
                if signal:
                    # Validate signal
                    if signal.validate():
                        signals.append(signal)
                        self.logger.debug(f"Strategy {strategy_id} generated signal: {signal.action} for {signal.market}")
                    else:
                        self.logger.warning(f"Strategy {strategy_id} generated invalid signal")
                
            except Exception as e:
                self.logger.error(f"Strategy {strategy_id} evaluation failed: {str(e)}")
                continue
        
        # Resolve conflicts if multiple signals exist
        if len(signals) > 1:
            signals = self._resolve_conflicts(signals)
        
        return signals
    
    def _resolve_conflicts(self, signals: List[TradingSignal]) -> List[TradingSignal]:
        """
        Resolve conflicts between multiple trading signals.
        
        Args:
            signals: List of conflicting signals
            
        Returns:
            List of resolved signals (may be filtered or prioritized)
        """
        if not signals:
            return signals
        
        # Group signals by market
        market_signals: Dict[str, List[TradingSignal]] = {}
        for signal in signals:
            if signal.market not in market_signals:
                market_signals[signal.market] = []
            market_signals[signal.market].append(signal)
        
        resolved_signals = []
        
        for market, market_signal_list in market_signals.items():
            if len(market_signal_list) == 1:
                # No conflict for this market
                resolved_signals.extend(market_signal_list)
                continue
            
            # Resolve conflicts for this market
            resolved_signal = self._resolve_market_conflicts(market_signal_list)
            if resolved_signal:
                resolved_signals.append(resolved_signal)
        
        return resolved_signals
    
    def _resolve_market_conflicts(self, signals: List[TradingSignal]) -> Optional[TradingSignal]:
        """
        Resolve conflicts for a specific market.
        
        Args:
            signals: List of signals for the same market
            
        Returns:
            Single resolved signal or None
        """
        if not signals:
            return None
        
        if len(signals) == 1:
            return signals[0]
        
        # Check for opposing signals (buy vs sell)
        buy_signals = [s for s in signals if s.action == 'buy']
        sell_signals = [s for s in signals if s.action == 'sell']
        
        if buy_signals and sell_signals:
            # Opposing signals - use priority rules
            self.logger.warning(f"Opposing signals detected for {signals[0].market}")
            
            # Use strategy priority if configured
            if 'strategy_priority' in self.priority_rules:
                all_signals_with_priority = []
                for signal in signals:
                    strategy_name = signal.strategy_id.split('_')[0]  # Extract strategy name
                    priority = self.priority_rules['strategy_priority'].get(strategy_name, 999)
                    all_signals_with_priority.append((priority, signal))
                
                # Sort by priority (lower number = higher priority)
                all_signals_with_priority.sort(key=lambda x: x[0])
                return all_signals_with_priority[0][1]
        
        # Same action signals - use confidence-based resolution
        if self.priority_rules['default'] == 'confidence':
            # Return signal with highest confidence
            return max(signals, key=lambda s: s.confidence)
        
        # Fallback: return first signal
        return signals[0]
    
    def _check_config_changes(self) -> None:
        """Check for configuration file changes and reload if necessary."""
        now = datetime.now()
        if now - self.last_config_check < self.config_check_interval:
            return
        
        self.last_config_check = now
        
        # Check if any config files have been modified
        config_files = list(self.config_dir.glob("*.yaml")) + list(self.config_dir.glob("*.yml"))
        
        for config_file in config_files:
            try:
                # Get file modification time
                mtime = datetime.fromtimestamp(config_file.stat().st_mtime)
                
                # Check if file was modified recently
                if now - mtime < self.config_check_interval * 2:
                    self.logger.info(f"Configuration file changed: {config_file}")
                    self._reload_strategy_config(str(config_file))
                    
            except Exception as e:
                self.logger.error(f"Error checking config file {config_file}: {str(e)}")
    
    def _reload_strategy_config(self, config_path: str) -> None:
        """
        Reload a specific strategy configuration.
        
        Args:
            config_path: Path to configuration file to reload
        """
        try:
            config_file = Path(config_path)
            
            # Load new configuration
            with open(config_file, 'r', encoding='utf-8') as f:
                new_config = yaml.safe_load(f)
            
            strategy_info = new_config.get('strategy', {})
            strategy_name = strategy_info.get('name')
            
            if not strategy_name:
                return
            
            strategy_id = f"{strategy_name}_{config_file.stem}"
            
            # Update existing strategy or create new one
            if strategy_id in self.strategies:
                # Update existing strategy configuration
                self.strategies[strategy_id].update_config(new_config)
                self.strategy_configs[strategy_id] = new_config
                self.logger.info(f"Reloaded strategy configuration: {strategy_id}")
            else:
                # Load as new strategy
                self._load_single_strategy(config_path)
                
        except Exception as e:
            self.logger.error(f"Failed to reload strategy config {config_path}: {str(e)}")
    
    def get_strategy_info(self, strategy_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about strategies.
        
        Args:
            strategy_id: Specific strategy ID, or None for all strategies
            
        Returns:
            Dictionary containing strategy information
        """
        if strategy_id:
            if strategy_id in self.strategies:
                return self.strategies[strategy_id].get_strategy_info()
            else:
                return {}
        
        # Return info for all strategies
        return {
            sid: strategy.get_strategy_info() 
            for sid, strategy in self.strategies.items()
        }
    
    def get_enabled_strategies(self) -> List[str]:
        """
        Get list of enabled strategy IDs.
        
        Returns:
            List of enabled strategy IDs
        """
        return [
            strategy_id for strategy_id, strategy in self.strategies.items()
            if strategy.enabled
        ]
    
    def set_priority_rules(self, priority_rules: Dict[str, Any]) -> None:
        """
        Update priority rules for conflict resolution.
        
        Args:
            priority_rules: New priority rules configuration
        """
        self.priority_rules.update(priority_rules)
        self.logger.info("Updated priority rules for conflict resolution")
    
    def get_strategy_count(self) -> int:
        """Get total number of loaded strategies."""
        return len(self.strategies)
    
    def get_active_strategy_count(self) -> int:
        """Get number of enabled strategies."""
        return len(self.get_enabled_strategies())