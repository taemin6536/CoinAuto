"""Configuration management with hot-reload functionality."""

import yaml
import os
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)


@dataclass
class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    message: str
    config_path: Optional[str] = None
    field_path: Optional[str] = None
    expected_type: Optional[str] = None
    actual_value: Optional[Any] = None


class ConfigChangeHandler(FileSystemEventHandler):
    """Handles file system events for configuration hot reload."""
    
    def __init__(self, config_manager: 'ConfigManager'):
        self.config_manager = config_manager
        self.last_modified = {}
        
    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
            
        file_path = event.src_path
        if not file_path.endswith(('.yaml', '.yml')):
            return
            
        # Debounce rapid file changes
        current_time = time.time()
        if file_path in self.last_modified:
            if current_time - self.last_modified[file_path] < 1.0:  # 1 second debounce
                return
                
        self.last_modified[file_path] = current_time
        
        try:
            self.config_manager._handle_config_change(file_path)
        except Exception as e:
            logger.error(f"Error handling config change for {file_path}: {e}")


class ConfigManager:
    """Manages YAML configuration loading, validation, and hot-reload functionality."""
    
    def __init__(self, config_path: Optional[str] = None, enable_hot_reload: bool = True):
        """Initialize ConfigManager with optional config path and hot reload.
        
        Args:
            config_path: Optional path to main config file
            enable_hot_reload: Whether to enable hot reload functionality
        """
        self.config_path = config_path or "config/default.yaml"
        self.enable_hot_reload = enable_hot_reload
        self._config: Dict[str, Any] = {}
        self._strategy_configs: Dict[str, Dict[str, Any]] = {}
        self._loaded = False
        self._change_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        
        # Hot reload setup
        self._observer: Optional[Observer] = None
        self._file_handler: Optional[ConfigChangeHandler] = None
        self._watched_paths: set = set()
        
        if self.enable_hot_reload:
            self._setup_hot_reload()
    
    def _setup_hot_reload(self):
        """Set up file system watching for hot reload."""
        try:
            self._observer = Observer()
            self._file_handler = ConfigChangeHandler(self)
            
            # Watch main config directory
            config_dir = Path(self.config_path).parent
            if config_dir.exists():
                self._observer.schedule(self._file_handler, str(config_dir), recursive=True)
                self._watched_paths.add(str(config_dir))
                
            # Watch strategy config directory
            strategy_dir = Path("config/strategies")
            if strategy_dir.exists():
                self._observer.schedule(self._file_handler, str(strategy_dir), recursive=True)
                self._watched_paths.add(str(strategy_dir))
                
            self._observer.start()
            logger.info("Hot reload enabled for configuration files")
            
        except Exception as e:
            logger.warning(f"Failed to setup hot reload: {e}")
            self.enable_hot_reload = False
    
    def _handle_config_change(self, file_path: str):
        """Handle configuration file changes."""
        logger.info(f"Configuration file changed: {file_path}")
        
        try:
            # Determine if this is main config or strategy config
            if Path(file_path).name == Path(self.config_path).name:
                # Main config changed
                old_config = self._config.copy()
                self.load_config()
                self._notify_change_callbacks("main", self._config)
                logger.info("Main configuration reloaded successfully")
                
            elif "strategies" in file_path and file_path.endswith(('.yaml', '.yml')):
                # Strategy config changed
                strategy_name = Path(file_path).stem
                old_strategy_config = self._strategy_configs.get(strategy_name, {}).copy()
                
                try:
                    new_strategy_config = self._load_strategy_config(file_path)
                    self._strategy_configs[strategy_name] = new_strategy_config
                    self._notify_change_callbacks(f"strategy.{strategy_name}", new_strategy_config)
                    logger.info(f"Strategy configuration '{strategy_name}' reloaded successfully")
                    
                except Exception as e:
                    logger.error(f"Failed to reload strategy config '{strategy_name}': {e}")
                    # Keep old config on error
                    if strategy_name in self._strategy_configs:
                        self._strategy_configs[strategy_name] = old_strategy_config
                        
        except Exception as e:
            logger.error(f"Failed to handle config change for {file_path}: {e}")
    
    def add_change_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Add callback to be notified of configuration changes.
        
        Args:
            callback: Function to call when config changes. 
                     Receives (config_type, new_config) as arguments.
        """
        self._change_callbacks.append(callback)
    
    def remove_change_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Remove a change callback."""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)
    
    def _notify_change_callbacks(self, config_type: str, new_config: Dict[str, Any]):
        """Notify all registered callbacks of configuration changes."""
        for callback in self._change_callbacks:
            try:
                callback(config_type, new_config)
            except Exception as e:
                logger.error(f"Error in config change callback: {e}")
    
    def load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from YAML file.
        
        Args:
            config_path: Optional path to config file. Uses instance path if not provided.
            
        Returns:
            Dictionary containing loaded configuration
            
        Raises:
            ConfigValidationError: If config file is invalid or missing
        """
        path = config_path or self.config_path
        
        try:
            config_file = Path(path)
            if not config_file.exists():
                raise ConfigValidationError(
                    f"Configuration file not found: {path}",
                    config_path=path
                )
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if config_data is None:
                raise ConfigValidationError(
                    f"Configuration file is empty: {path}",
                    config_path=path
                )
            
            if not isinstance(config_data, dict):
                raise ConfigValidationError(
                    f"Configuration must be a dictionary, got {type(config_data).__name__}",
                    config_path=path,
                    expected_type="dict",
                    actual_value=type(config_data).__name__
                )
            
            # Validate required sections
            self._validate_config_structure(config_data, path)
            
            # Validate individual sections
            self._validate_api_config(config_data.get('api', {}), path)
            self._validate_trading_config(config_data.get('trading', {}), path)
            self._validate_risk_config(config_data.get('risk', {}), path)
            self._validate_strategies_config(config_data.get('strategies', {}), path)
            
            self._config = config_data
            self._loaded = True
            
            # Load strategy configurations
            self._load_all_strategy_configs()
            
            logger.info(f"Successfully loaded configuration from {path}")
            return config_data.copy()
            
        except yaml.YAMLError as e:
            raise ConfigValidationError(
                f"Invalid YAML syntax in {path}: {str(e)}",
                config_path=path
            )
        except Exception as e:
            if isinstance(e, ConfigValidationError):
                raise
            raise ConfigValidationError(
                f"Failed to load configuration from {path}: {str(e)}",
                config_path=path
            )
    
    def _validate_config_structure(self, config: Dict[str, Any], path: str) -> None:
        """Validate that config has required structure."""
        required_sections = ['api', 'trading', 'risk', 'strategies']
        
        for section in required_sections:
            if section not in config:
                raise ConfigValidationError(
                    f"Missing required configuration section '{section}' in {path}",
                    config_path=path,
                    field_path=section
                )
            
            if not isinstance(config[section], dict):
                raise ConfigValidationError(
                    f"Configuration section '{section}' must be a dictionary in {path}",
                    config_path=path,
                    field_path=section,
                    expected_type="dict",
                    actual_value=type(config[section]).__name__
                )
    
    def _validate_api_config(self, api_config: Dict[str, Any], path: str) -> None:
        """Validate API configuration section."""
        required_fields = {
            'base_url': str,
            'websocket_url': str,
            'timeout': (int, float),
            'max_retries': int,
            'retry_delay': (int, float)
        }
        
        for field, expected_type in required_fields.items():
            if field not in api_config:
                raise ConfigValidationError(
                    f"Missing required API config field '{field}' in {path}",
                    config_path=path,
                    field_path=f"api.{field}"
                )
            
            if not isinstance(api_config[field], expected_type):
                raise ConfigValidationError(
                    f"API config field '{field}' must be of type {expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type)} in {path}",
                    config_path=path,
                    field_path=f"api.{field}",
                    expected_type=expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type),
                    actual_value=type(api_config[field]).__name__
                )
    
    def _validate_trading_config(self, trading_config: Dict[str, Any], path: str) -> None:
        """Validate trading configuration section."""
        required_fields = {
            'enabled': bool,
            'default_market': str,
            'order_type': str,
            'min_order_amount': (int, float),
            'max_position_size': (int, float)
        }
        
        for field, expected_type in required_fields.items():
            if field not in trading_config:
                raise ConfigValidationError(
                    f"Missing required trading config field '{field}' in {path}",
                    config_path=path,
                    field_path=f"trading.{field}"
                )
            
            if not isinstance(trading_config[field], expected_type):
                raise ConfigValidationError(
                    f"Trading config field '{field}' must be of type {expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type)} in {path}",
                    config_path=path,
                    field_path=f"trading.{field}",
                    expected_type=expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type),
                    actual_value=type(trading_config[field]).__name__
                )
        
        # Validate order_type values
        valid_order_types = ['limit', 'market']
        if trading_config['order_type'] not in valid_order_types:
            raise ConfigValidationError(
                f"Trading config 'order_type' must be one of {valid_order_types} in {path}",
                config_path=path,
                field_path="trading.order_type",
                expected_type=f"one of {valid_order_types}",
                actual_value=trading_config['order_type']
            )
    
    def _validate_risk_config(self, risk_config: Dict[str, Any], path: str) -> None:
        """Validate risk management configuration section."""
        required_fields = {
            'stop_loss_percentage': (int, float),
            'daily_loss_limit': (int, float),
            'max_daily_trades': int,
            'min_balance_threshold': (int, float),
            'position_size_limit': (int, float)
        }
        
        for field, expected_type in required_fields.items():
            if field not in risk_config:
                raise ConfigValidationError(
                    f"Missing required risk config field '{field}' in {path}",
                    config_path=path,
                    field_path=f"risk.{field}"
                )
            
            if not isinstance(risk_config[field], expected_type):
                raise ConfigValidationError(
                    f"Risk config field '{field}' must be of type {expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type)} in {path}",
                    config_path=path,
                    field_path=f"risk.{field}",
                    expected_type=expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type),
                    actual_value=type(risk_config[field]).__name__
                )
        
        # Validate percentage values are between 0 and 1
        percentage_fields = ['stop_loss_percentage', 'daily_loss_limit', 'position_size_limit']
        for field in percentage_fields:
            if field in risk_config:
                value = risk_config[field]
                if not (0 <= value <= 1):
                    raise ConfigValidationError(
                        f"Risk config '{field}' must be between 0 and 1 (percentage) in {path}",
                        config_path=path,
                        field_path=f"risk.{field}",
                        expected_type="float between 0 and 1",
                        actual_value=value
                    )
    
    def _validate_strategies_config(self, strategies_config: Dict[str, Any], path: str) -> None:
        """Validate strategies configuration section."""
        required_fields = {
            'enabled': list,
            'evaluation_interval': (int, float),
            'signal_threshold': (int, float)
        }
        
        for field, expected_type in required_fields.items():
            if field not in strategies_config:
                raise ConfigValidationError(
                    f"Missing required strategies config field '{field}' in {path}",
                    config_path=path,
                    field_path=f"strategies.{field}"
                )
            
            if not isinstance(strategies_config[field], expected_type):
                raise ConfigValidationError(
                    f"Strategies config field '{field}' must be of type {expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type)} in {path}",
                    config_path=path,
                    field_path=f"strategies.{field}",
                    expected_type=expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type),
                    actual_value=type(strategies_config[field]).__name__
                )
        
        # Validate signal_threshold is between 0 and 1
        signal_threshold = strategies_config.get('signal_threshold', 0)
        if not (0 <= signal_threshold <= 1):
            raise ConfigValidationError(
                f"Strategies config 'signal_threshold' must be between 0 and 1 in {path}",
                config_path=path,
                field_path="strategies.signal_threshold",
                expected_type="float between 0 and 1",
                actual_value=signal_threshold
            )
    
    def _load_all_strategy_configs(self):
        """Load all strategy configuration files."""
        strategy_dir = Path("config/strategies")
        if not strategy_dir.exists():
            logger.warning("Strategy configuration directory not found: config/strategies")
            return
        
        for strategy_file in strategy_dir.glob("*.yaml"):
            try:
                strategy_name = strategy_file.stem
                strategy_config = self._load_strategy_config(str(strategy_file))
                self._strategy_configs[strategy_name] = strategy_config
                logger.debug(f"Loaded strategy config: {strategy_name}")
            except Exception as e:
                logger.error(f"Failed to load strategy config {strategy_file}: {e}")
    
    def _load_strategy_config(self, strategy_path: str) -> Dict[str, Any]:
        """Load a single strategy configuration file."""
        try:
            with open(strategy_path, 'r', encoding='utf-8') as f:
                strategy_data = yaml.safe_load(f)
            
            if strategy_data is None:
                raise ConfigValidationError(
                    f"Strategy configuration file is empty: {strategy_path}",
                    config_path=strategy_path
                )
            
            if not isinstance(strategy_data, dict):
                raise ConfigValidationError(
                    f"Strategy configuration must be a dictionary: {strategy_path}",
                    config_path=strategy_path,
                    expected_type="dict",
                    actual_value=type(strategy_data).__name__
                )
            
            # Validate strategy structure
            self._validate_strategy_structure(strategy_data, strategy_path)
            
            return strategy_data
            
        except yaml.YAMLError as e:
            raise ConfigValidationError(
                f"Invalid YAML syntax in strategy config {strategy_path}: {str(e)}",
                config_path=strategy_path
            )
    
    def _validate_strategy_structure(self, strategy_data: Dict[str, Any], path: str) -> None:
        """Validate strategy configuration structure."""
        if 'strategy' not in strategy_data:
            raise ConfigValidationError(
                f"Missing 'strategy' section in {path}",
                config_path=path,
                field_path="strategy"
            )
        
        strategy_info = strategy_data['strategy']
        required_strategy_fields = {
            'name': str,
            'description': str,
            'enabled': bool
        }
        
        for field, expected_type in required_strategy_fields.items():
            if field not in strategy_info:
                raise ConfigValidationError(
                    f"Missing required strategy field '{field}' in {path}",
                    config_path=path,
                    field_path=f"strategy.{field}"
                )
            
            if not isinstance(strategy_info[field], expected_type):
                raise ConfigValidationError(
                    f"Strategy field '{field}' must be of type {expected_type.__name__} in {path}",
                    config_path=path,
                    field_path=f"strategy.{field}",
                    expected_type=expected_type.__name__,
                    actual_value=type(strategy_info[field]).__name__
                )
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration. Loads if not already loaded."""
        if not self._loaded:
            self.load_config()
        return self._config.copy()
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get specific configuration section."""
        config = self.get_config()
        if section not in config:
            raise ConfigValidationError(f"Configuration section '{section}' not found")
        return config[section].copy()
    
    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any]:
        """Get configuration for a specific strategy.
        
        Strategy configurations can be loaded from two sources:
        1. Embedded in main config file under strategies section
        2. Separate files in config/strategies/ directory
        
        Separate files take precedence over embedded configurations.
        """
        # First check if we have a separate strategy file
        if strategy_name not in self._strategy_configs:
            # Try to load strategy config from separate file
            strategy_path = Path(f"config/strategies/{strategy_name}.yaml")
            if strategy_path.exists():
                try:
                    strategy_config = self._load_strategy_config(str(strategy_path))
                    self._strategy_configs[strategy_name] = strategy_config
                except Exception as e:
                    logger.error(f"Failed to load strategy config '{strategy_name}': {e}")
                    # Fall through to check embedded config
        
        # If we have loaded strategy config from file, return it
        if strategy_name in self._strategy_configs:
            return self._strategy_configs[strategy_name].copy()
        
        # Otherwise, check if strategy config is embedded in main config
        if self._loaded:
            strategies_config = self._config.get('strategies', {})
            if strategy_name in strategies_config and isinstance(strategies_config[strategy_name], dict):
                # Return embedded strategy configuration
                return strategies_config[strategy_name].copy()
        
        # If no configuration found anywhere, return empty dict
        logger.warning(f"No configuration found for strategy '{strategy_name}'")
        return {}
    
    def get_enabled_strategies(self) -> List[str]:
        """Get list of enabled strategy names."""
        strategies_config = self.get_section('strategies')
        return strategies_config.get('enabled', [])
    
    def is_strategy_enabled(self, strategy_name: str) -> bool:
        """Check if a strategy is enabled."""
        enabled_strategies = self.get_enabled_strategies()
        return strategy_name in enabled_strategies
    
    def validate_config_file(self, config_path: str) -> bool:
        """Validate a configuration file without loading it permanently.
        
        Args:
            config_path: Path to configuration file to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Create temporary instance to validate
            temp_manager = ConfigManager(config_path, enable_hot_reload=False)
            temp_manager.load_config()
            return True
        except ConfigValidationError:
            return False
    
    def reload_config(self) -> bool:
        """Manually reload configuration.
        
        Returns:
            True if reload successful, False otherwise
        """
        try:
            self.load_config()
            return True
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            return False
    
    def reload_strategy_config(self, strategy_name: str) -> bool:
        """Manually reload a specific strategy configuration.
        
        Args:
            strategy_name: Name of strategy to reload
            
        Returns:
            True if reload successful, False otherwise
        """
        try:
            strategy_path = Path(f"config/strategies/{strategy_name}.yaml")
            if not strategy_path.exists():
                logger.error(f"Strategy config file not found: {strategy_path}")
                return False
            
            strategy_config = self._load_strategy_config(str(strategy_path))
            self._strategy_configs[strategy_name] = strategy_config
            self._notify_change_callbacks(f"strategy.{strategy_name}", strategy_config)
            logger.info(f"Successfully reloaded strategy config: {strategy_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reload strategy config '{strategy_name}': {e}")
            return False
    
    def stop_hot_reload(self):
        """Stop hot reload file watching."""
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()
            logger.info("Hot reload stopped")
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        if hasattr(self, '_observer') and self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()