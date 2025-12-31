#!/usr/bin/env python3
"""
Demo script showing configuration hot reload functionality.

This script demonstrates how the ConfigManager can automatically reload
configuration changes without restarting the application.
"""

import time
import logging
from pathlib import Path
import sys

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from upbit_trading_bot.config import ConfigManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def on_config_change(config_type: str, new_config: dict):
    """Callback function called when configuration changes."""
    logger.info(f"Configuration changed: {config_type}")
    
    if config_type == "main":
        # Main configuration changed
        trading_enabled = new_config.get('trading', {}).get('enabled', False)
        logger.info(f"Trading is now: {'ENABLED' if trading_enabled else 'DISABLED'}")
        
        strategies = new_config.get('strategies', {}).get('enabled', [])
        logger.info(f"Active strategies: {', '.join(strategies) if strategies else 'None'}")
        
    elif config_type.startswith("strategy."):
        # Strategy configuration changed
        strategy_name = config_type.split(".", 1)[1]
        strategy_info = new_config.get('strategy', {})
        enabled = strategy_info.get('enabled', False)
        logger.info(f"Strategy '{strategy_name}' is now: {'ENABLED' if enabled else 'DISABLED'}")


def main():
    """Main demo function."""
    logger.info("Starting configuration hot reload demo")
    
    # Create config manager with hot reload enabled
    config_manager = ConfigManager("config/default.yaml", enable_hot_reload=True)
    
    # Add our callback to be notified of changes
    config_manager.add_change_callback(on_config_change)
    
    try:
        # Load initial configuration
        config = config_manager.load_config()
        logger.info("Initial configuration loaded")
        
        # Show initial status
        trading_enabled = config.get('trading', {}).get('enabled', False)
        logger.info(f"Initial trading status: {'ENABLED' if trading_enabled else 'DISABLED'}")
        
        strategies = config.get('strategies', {}).get('enabled', [])
        logger.info(f"Initial strategies: {', '.join(strategies) if strategies else 'None'}")
        
        # Monitor for changes
        logger.info("Monitoring for configuration changes...")
        logger.info("Try editing config/default.yaml or files in config/strategies/")
        logger.info("Press Ctrl+C to exit")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Stopping configuration monitor...")
        config_manager.stop_hot_reload()
        logger.info("Demo completed")


if __name__ == "__main__":
    main()