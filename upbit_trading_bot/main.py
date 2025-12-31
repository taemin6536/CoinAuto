"""
Main entry point for the Upbit Trading Bot.

This module provides the main function to start the trading bot with
comprehensive logging, monitoring, and alerting capabilities.
"""

import sys
import os
import signal
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from upbit_trading_bot.logging import (
    LoggerManager, 
    HealthMonitor, 
    SystemMonitor, 
    NotificationService,
    get_logger
)
from upbit_trading_bot.config.manager import ConfigManager, ConfigValidationError
from upbit_trading_bot.api.client import UpbitAPIClient, UpbitAPIError
from upbit_trading_bot.data.market_data import MarketDataHandler, MarketData
from upbit_trading_bot.strategy.manager import StrategyManager
from upbit_trading_bot.order.manager import OrderManager
from upbit_trading_bot.risk.manager import RiskManager
from upbit_trading_bot.portfolio.manager import PortfolioManager
from upbit_trading_bot.data.database import get_db_manager


class TradingBotApplication:
    """
    Main trading bot application with integrated logging and monitoring.
    
    Manages all bot components including logging, monitoring, alerting,
    and graceful shutdown procedures.
    """
    
    def __init__(self):
        """Initialize the trading bot application."""
        # Initialize logging system first
        self.logger_manager = self._setup_logging()
        self.logger = get_logger(__name__)
        
        # Initialize monitoring and alerting
        self.health_monitor: Optional[HealthMonitor] = None
        self.system_monitor: Optional[SystemMonitor] = None
        self.notification_service: Optional[NotificationService] = None
        
        # Trading components
        self.config_manager: Optional[ConfigManager] = None
        self.api_client: Optional[UpbitAPIClient] = None
        self.market_data_handler: Optional[MarketDataHandler] = None
        self.strategy_manager: Optional[StrategyManager] = None
        self.order_manager: Optional[OrderManager] = None
        self.risk_manager: Optional[RiskManager] = None
        self.portfolio_manager: Optional[PortfolioManager] = None
        self.db_manager = None
        
        # Application state
        self.running = False
        self.shutdown_requested = False
        self.main_loop_thread: Optional[threading.Thread] = None
        
        # Configuration
        self.config: Dict[str, Any] = {}
        self.trading_enabled = False
        self.dry_run_mode = os.getenv('DRY_RUN', 'false').lower() == 'true'
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        self.logger.info("TradingBotApplication initialized")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.shutdown_requested = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def _setup_logging(self) -> LoggerManager:
        """Setup comprehensive logging system."""
        # Get log level from environment or default to INFO
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        
        # Create logs directory
        Path("logs").mkdir(exist_ok=True)
        
        # Initialize logger manager with structured logging
        logger_manager = LoggerManager(
            log_dir="logs",
            log_level=log_level,
            max_file_size=10 * 1024 * 1024,  # 10MB
            backup_count=30,  # 30 days retention
            console_output=True,
            structured_format=True
        )
        
        return logger_manager
    
    def _setup_monitoring(self) -> None:
        """Setup health and system monitoring."""
        try:
            # Initialize health monitor
            self.health_monitor = HealthMonitor(check_interval=30)
            
            # Initialize system monitor
            self.system_monitor = SystemMonitor(
                collection_interval=60,
                max_metrics_history=1440  # 24 hours
            )
            
            # Initialize notification service
            notification_config = Path("config/notifications.json")
            self.notification_service = NotificationService(
                config_file=str(notification_config) if notification_config.exists() else None
            )
            
            self.logger.info("Monitoring systems initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to setup monitoring: {e}", exc_info=True)
            # Continue without monitoring if setup fails
    
    def _initialize_components(self) -> bool:
        """Initialize all trading components."""
        try:
            self.logger.info("Initializing trading components...")
            
            # 1. Initialize configuration manager
            config_path = os.getenv('CONFIG_PATH', 'config/default.yaml')
            self.config_manager = ConfigManager(config_path, enable_hot_reload=True)
            self.config = self.config_manager.load_config()
            self.trading_enabled = self.config.get('trading', {}).get('enabled', False)
            
            self.logger.info(f"Configuration loaded from {config_path}")
            self.logger.info(f"Trading enabled: {self.trading_enabled}")
            self.logger.info(f"Dry run mode: {self.dry_run_mode}")
            
            # 2. Initialize database manager
            self.db_manager = get_db_manager()
            self.logger.info("Database manager initialized")
            
            # 3. Initialize API client
            self.api_client = UpbitAPIClient()
            
            # Load API credentials from environment variables or encrypted file
            access_key = os.getenv('UPBIT_ACCESS_KEY')
            secret_key = os.getenv('UPBIT_SECRET_KEY')
            
            if access_key and secret_key:
                # Use environment variables
                if self.api_client.authenticate(access_key, secret_key):
                    self.logger.info("API authentication successful (from environment variables)")
                else:
                    self.logger.warning("API authentication failed")
                    if not self.dry_run_mode:
                        return False
            else:
                # Try to load from encrypted credentials file
                credentials_path = os.getenv('CREDENTIALS_PATH', 'credentials.json')
                if Path(credentials_path).exists():
                    if self.api_client.load_encrypted_credentials(credentials_path):
                        if self.api_client.authenticate(self.api_client.access_key, self.api_client.secret_key):
                            self.logger.info("API authentication successful (from encrypted file)")
                        else:
                            self.logger.warning("API authentication failed")
                            if not self.dry_run_mode:
                                return False
                    else:
                        self.logger.warning("Failed to load API credentials")
                        if not self.dry_run_mode:
                            return False
                else:
                    self.logger.warning(f"No API credentials found (env vars or {credentials_path})")
                    if not self.dry_run_mode:
                        self.logger.error("Cannot run without API credentials (use DRY_RUN=true for testing)")
                        return False
            
            # 4. Initialize market data handler
            self.market_data_handler = MarketDataHandler(window_size=1000)
            
            # Subscribe to market data updates
            self.market_data_handler.subscribe_to_ticker(self._on_market_data_update)
            
            # 5. Initialize strategy manager
            self.strategy_manager = StrategyManager()
            self.strategy_manager.set_api_client(self.api_client)  # API 클라이언트 설정
            self.strategy_manager.load_strategies()
            
            enabled_strategies = self.strategy_manager.get_enabled_strategies()
            self.logger.info(f"Loaded {len(enabled_strategies)} enabled strategies: {enabled_strategies}")
            
            # 6. Initialize order manager
            self.order_manager = OrderManager(self.api_client, max_retries=3)
            
            # 7. Initialize risk manager
            self.risk_manager = RiskManager(self.config_manager, self.api_client)
            
            # 8. Initialize portfolio manager
            self.portfolio_manager = PortfolioManager(self.db_manager)
            
            # Update initial portfolio state
            if self.api_client.authenticated:
                try:
                    accounts = self.api_client.get_accounts()
                    self.portfolio_manager.update_positions(accounts)
                    self.risk_manager.update_portfolio_snapshot(accounts)
                    self.logger.info("Initial portfolio state updated")
                except Exception as e:
                    self.logger.warning(f"Failed to update initial portfolio state: {e}")
            
            self.logger.info("All trading components initialized successfully")
            return True
            
        except ConfigValidationError as e:
            self.logger.error(f"Configuration validation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}", exc_info=True)
            return False
    
    def _start_market_data(self) -> bool:
        """Start market data collection."""
        try:
            # Get markets to monitor from config
            trading_config = self.config.get('trading', {})
            default_market = trading_config.get('default_market', 'KRW-BTC')
            
            # For now, monitor the default market
            # In a full implementation, this would be configurable
            markets = [default_market]
            
            self.market_data_handler.start_websocket_connection(markets)
            self.logger.info(f"Market data collection started for: {markets}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start market data collection: {e}")
            return False
    
    def _on_market_data_update(self, market_data: MarketData) -> None:
        """Handle market data updates."""
        try:
            if not market_data.ticker:
                return
            
            # Log market data (debug level to avoid spam)
            self.logger.debug(f"Market data update: {market_data.ticker.market} "
                            f"price={market_data.ticker.trade_price:,.0f}")
            
            # Trigger strategy evaluation in main loop
            # This is handled by the main trading loop
            
        except Exception as e:
            self.logger.error(f"Error handling market data update: {e}")
    
    def _main_trading_loop(self) -> None:
        """Main trading loop that runs continuously."""
        self.logger.info("Starting main trading loop")
        
        last_strategy_evaluation = 0
        strategy_interval = self.config.get('strategies', {}).get('evaluation_interval', 3)  # 3초로 단축
        
        last_portfolio_update = 0
        portfolio_update_interval = 10  # 10초로 단축
        
        last_order_tracking = 0
        order_tracking_interval = 3  # 3초로 단축
        
        while self.running and not self.shutdown_requested:
            try:
                current_time = time.time()
                
                # 1. Check if trading should be stopped (risk management)
                if self.risk_manager.should_stop_trading():
                    if self.trading_enabled:
                        self.logger.warning("Trading stopped by risk manager")
                        self.trading_enabled = False
                    time.sleep(5)
                    continue
                
                # 2. Track active orders
                if current_time - last_order_tracking >= order_tracking_interval:
                    try:
                        active_orders = self.order_manager.track_orders()
                        if active_orders:
                            self.logger.debug(f"Tracking {len(active_orders)} active orders")
                        last_order_tracking = current_time
                    except Exception as e:
                        self.logger.error(f"Error tracking orders: {e}")
                
                # 3. Update portfolio periodically
                if current_time - last_portfolio_update >= portfolio_update_interval:
                    try:
                        if self.api_client.authenticated:
                            accounts = self.api_client.get_accounts()
                            self.portfolio_manager.update_positions(accounts)
                            self.risk_manager.update_portfolio_snapshot(accounts)
                            self.logger.debug("Portfolio updated")
                        last_portfolio_update = current_time
                    except Exception as e:
                        self.logger.error(f"Error updating portfolio: {e}")
                
                # 4. Evaluate strategies and generate signals
                if current_time - last_strategy_evaluation >= strategy_interval:
                    try:
                        self._evaluate_strategies()
                        last_strategy_evaluation = current_time
                    except Exception as e:
                        self.logger.error(f"Error evaluating strategies: {e}")
                
                # Sleep briefly to prevent excessive CPU usage
                time.sleep(0.5)  # 0.5초로 단축
                
            except Exception as e:
                self.logger.error(f"Error in main trading loop: {e}", exc_info=True)
                time.sleep(5)  # Wait longer on error
        
        self.logger.info("Main trading loop stopped")
    
    def _evaluate_strategies(self) -> None:
        """Evaluate all strategies and process signals."""
        try:
            # Get current market data for all subscribed markets
            subscribed_markets = self.market_data_handler.get_subscribed_markets()
            
            for market in subscribed_markets:
                # Get latest ticker data
                latest_ticker = None
                if self.market_data_handler.get_rolling_window_size(market) > 0:
                    price_history = self.market_data_handler.get_price_history(market, 60)
                    if price_history:
                        latest_ticker = price_history[-1]
                
                if not latest_ticker:
                    continue
                
                # Create market data object with price history
                price_history_values = [ticker.trade_price for ticker in price_history] if price_history else []
                market_data = MarketData(
                    ticker=latest_ticker,
                    timestamp=latest_ticker.timestamp,
                    price_history=price_history_values
                )
                
                # Evaluate strategies
                signals = self.strategy_manager.evaluate_strategies(market_data)
                
                if signals:
                    self.logger.info(f"Generated {len(signals)} trading signals for {market}")
                    
                    # Process each signal
                    for signal in signals:
                        self._process_trading_signal(signal)
        
        except Exception as e:
            self.logger.error(f"Error evaluating strategies: {e}")
    
    def _process_trading_signal(self, signal) -> None:
        """Process a trading signal and execute orders if appropriate."""
        try:
            self.logger.info(f"Processing trading signal: {signal.market} {signal.action} "
                           f"confidence={signal.confidence:.2f}")
            
            # Check if trading is enabled
            if not self.trading_enabled:
                self.logger.info("Trading disabled, skipping signal execution")
                return
            
            # Check signal threshold
            signal_threshold = self.config.get('strategies', {}).get('signal_threshold', 0.7)
            if signal.confidence < signal_threshold:
                self.logger.info(f"Signal confidence {signal.confidence:.2f} below threshold {signal_threshold}")
                return
            
            # Create order from signal
            order = self.order_manager.create_order(signal)
            if not order:
                self.logger.error("Failed to create order from signal")
                return
            
            # Check risk limits
            if not self.risk_manager.check_position_limits(order):
                self.logger.warning("Order rejected by position limits")
                return
            
            if not self.risk_manager.check_daily_limits():
                self.logger.warning("Order rejected by daily limits")
                return
            
            # Execute order (or simulate in dry run mode)
            if self.dry_run_mode:
                self.logger.info(f"DRY RUN: Would execute order: {order.market} {order.side} {order.volume}")
                return
            
            # Execute the order
            result = self.order_manager.execute_order(order)
            if result:
                self.logger.info(f"Order executed successfully: {result.order_id}")
                
                # Record trade
                self.portfolio_manager.record_trade(result, signal.strategy_id)
                
                # Update risk manager
                self.risk_manager.record_trade(
                    result.market, 
                    result.side, 
                    result.executed_volume, 
                    result.price or 0
                )
            else:
                self.logger.error("Order execution failed")
        
        except Exception as e:
            self.logger.error(f"Error processing trading signal: {e}")
    
    def _start_monitoring(self) -> None:
        """Start monitoring services."""
        try:
            if self.health_monitor:
                self.health_monitor.start_monitoring()
            
            if self.system_monitor:
                self.system_monitor.start_monitoring()
            
            if self.notification_service:
                self.notification_service.start_processing()
            
            self.logger.info("Monitoring services started")
            
        except Exception as e:
            self.logger.error(f"Failed to start monitoring: {e}", exc_info=True)
    
    def _stop_monitoring(self) -> None:
        """Stop monitoring services."""
        try:
            if self.health_monitor:
                self.health_monitor.stop_monitoring()
            
            if self.system_monitor:
                self.system_monitor.stop_monitoring()
            
            if self.notification_service:
                self.notification_service.stop_processing()
            
            self.logger.info("Monitoring services stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping monitoring: {e}", exc_info=True)
    
    def _send_startup_alert(self) -> None:
        """Send startup notification."""
        if self.notification_service:
            self.notification_service.alert_info(
                title="Trading Bot Started",
                message="Upbit Trading Bot has started successfully",
                component="main",
                details={
                    'version': '0.1.0',
                    'log_level': self.logger_manager.log_level,
                    'monitoring_enabled': self.health_monitor is not None,
                    'trading_enabled': self.trading_enabled,
                    'dry_run_mode': self.dry_run_mode
                }
            )
    
    def _send_shutdown_alert(self) -> None:
        """Send shutdown notification."""
        if self.notification_service:
            self.notification_service.alert_info(
                title="Trading Bot Stopped",
                message="Upbit Trading Bot has been shut down",
                component="main"
            )
    
    def start(self) -> None:
        """Start the trading bot application."""
        try:
            self.logger.info("Starting Upbit Trading Bot v0.1.0")
            
            # Initialize all components
            if not self._initialize_components():
                self.logger.error("Failed to initialize components, exiting")
                sys.exit(1)
            
            # Setup and start monitoring
            self._setup_monitoring()
            self._start_monitoring()
            
            # Start market data collection
            if not self._start_market_data():
                self.logger.error("Failed to start market data collection, exiting")
                sys.exit(1)
            
            # Send startup notification
            self._send_startup_alert()
            
            # Set running state
            self.running = True
            
            # Log system information
            self._log_system_info()
            
            self.logger.info("Trading bot initialization complete")
            
            # Start main trading loop in separate thread
            self.main_loop_thread = threading.Thread(
                target=self._main_trading_loop,
                daemon=True,
                name="MainTradingLoop"
            )
            self.main_loop_thread.start()
            
            # Main thread waits for shutdown signal
            while self.running and not self.shutdown_requested:
                time.sleep(1)
            
            self.logger.info("Shutdown signal received, stopping...")
            
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal (Ctrl+C)")
        except Exception as e:
            self.logger.error(f"Fatal error occurred: {e}", exc_info=True)
            
            # Send critical alert
            if self.notification_service:
                self.notification_service.alert_critical_error(
                    title="Trading Bot Fatal Error",
                    message=f"Fatal error occurred: {str(e)}",
                    component="main",
                    details={'error_type': type(e).__name__}
                )
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Gracefully shutdown the trading bot."""
        if not self.running:
            return
        
        self.logger.info("Initiating graceful shutdown...")
        self.running = False
        
        try:
            # Send shutdown notification
            self._send_shutdown_alert()
            
            # Stop market data collection
            if self.market_data_handler:
                self.market_data_handler.stop()
                self.logger.info("Market data handler stopped")
            
            # Cancel any pending orders (in a real implementation)
            if self.order_manager and not self.dry_run_mode:
                active_orders = self.order_manager.get_active_orders()
                if active_orders:
                    self.logger.info(f"Cancelling {len(active_orders)} active orders...")
                    for order in active_orders:
                        try:
                            self.order_manager.cancel_order(order.order_id)
                        except Exception as e:
                            self.logger.error(f"Failed to cancel order {order.order_id}: {e}")
            
            # Stop configuration hot reload
            if self.config_manager:
                self.config_manager.stop_hot_reload()
                self.logger.info("Configuration hot reload stopped")
            
            # Wait for main loop thread to finish
            if self.main_loop_thread and self.main_loop_thread.is_alive():
                self.main_loop_thread.join(timeout=10)
                if self.main_loop_thread.is_alive():
                    self.logger.warning("Main loop thread did not stop gracefully")
            
            # Stop monitoring services
            self._stop_monitoring()
            
            # Cleanup old logs
            self.logger_manager.cleanup_old_logs(retention_days=30)
            
            self.logger.info("Trading bot shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)
    
    def _log_system_info(self) -> None:
        """Log system information at startup."""
        try:
            import platform
            import psutil
            
            system_info = {
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'cpu_count': psutil.cpu_count(),
                'memory_total_gb': psutil.virtual_memory().total / (1024**3),
                'disk_free_gb': psutil.disk_usage('/').free / (1024**3)
            }
            
            self.logger.info("System information", extra=system_info)
            
        except Exception as e:
            self.logger.warning(f"Could not collect system information: {e}")
    
    def get_health_status(self) -> dict:
        """Get current health status."""
        status = {
            'running': self.running,
            'trading_enabled': self.trading_enabled,
            'dry_run_mode': self.dry_run_mode,
            'components': {
                'config_manager': self.config_manager is not None,
                'api_client': self.api_client is not None and self.api_client.authenticated,
                'market_data_handler': self.market_data_handler is not None and self.market_data_handler.is_connected(),
                'strategy_manager': self.strategy_manager is not None,
                'order_manager': self.order_manager is not None,
                'risk_manager': self.risk_manager is not None,
                'portfolio_manager': self.portfolio_manager is not None
            }
        }
        
        if self.health_monitor:
            status['health_monitor'] = self.health_monitor.get_health_status()
        
        if self.risk_manager:
            status['risk_status'] = self.risk_manager.get_risk_status()
        
        return status
    
    def get_system_metrics(self) -> dict:
        """Get current system metrics."""
        if self.system_monitor:
            return self.system_monitor.get_current_metrics()
        else:
            return {'error': 'System monitoring not available'}


def main():
    """Main entry point for the trading bot."""
    print("Upbit Trading Bot v0.1.0")
    print("=" * 50)
    
    # Create and start the application
    app = TradingBotApplication()
    app.start()


if __name__ == "__main__":
    main()