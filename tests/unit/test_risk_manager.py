"""
Unit tests for RiskManager.

Tests the core functionality of the risk management system including
position limits, daily limits, stop loss calculations, and balance protection.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal

from upbit_trading_bot.risk.manager import RiskManager, RiskEvent, PortfolioSnapshot, NotificationService
from upbit_trading_bot.data.models import Order, Position, Account, Ticker
from upbit_trading_bot.config.manager import ConfigManager


class TestRiskManager:
    """Test cases for RiskManager class."""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock config manager with risk settings."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.get_section.return_value = {
            'stop_loss_percentage': 0.05,
            'daily_loss_limit': 0.10,
            'max_daily_trades': 50,
            'min_balance_threshold': 10000.0,
            'position_size_limit': 0.20
        }
        return config_manager
    
    @pytest.fixture
    def mock_api_client(self):
        """Create a mock API client."""
        api_client = Mock()
        return api_client
    
    @pytest.fixture
    def risk_manager(self, mock_config_manager, mock_api_client):
        """Create a RiskManager instance for testing."""
        with patch('upbit_trading_bot.risk.manager.get_db_manager'):
            return RiskManager(mock_config_manager, mock_api_client)
    
    def test_risk_manager_initialization(self, risk_manager):
        """Test RiskManager initialization."""
        assert risk_manager.stop_loss_percentage == 0.05
        assert risk_manager.daily_loss_limit == 0.10
        assert risk_manager.max_daily_trades == 50
        assert risk_manager.min_balance_threshold == 10000.0
        assert risk_manager.position_size_limit == 0.20
        assert risk_manager.daily_trade_count == 0
        assert risk_manager.trading_paused is False
    
    def test_check_position_limits_within_limit(self, risk_manager):
        """Test position limit check when within limits."""
        # Mock API client to return account data
        accounts = [
            Account(currency='KRW', balance=100000.0, locked=0.0, 
                   avg_buy_price=0.0, avg_buy_price_modified=False, unit_currency='KRW'),
            Account(currency='BTC', balance=0.1, locked=0.0, 
                   avg_buy_price=50000000.0, avg_buy_price_modified=False, unit_currency='KRW')
        ]
        risk_manager.api_client.get_accounts.return_value = accounts
        
        # Mock ticker for BTC price
        ticker = Ticker(market='KRW-BTC', trade_price=50000000.0, trade_volume=1.0,
                       timestamp=datetime.now(), change_rate=0.01)
        risk_manager.api_client.get_ticker.return_value = ticker
        
        # Create order within position limit (10% of portfolio)
        order = Order(market='KRW-BTC', side='bid', ord_type='limit', 
                     price=50000000.0, volume=0.0003)  # 15,000 KRW worth
        
        result = risk_manager.check_position_limits(order)
        assert result is True
    
    def test_check_position_limits_exceeds_limit(self, risk_manager):
        """Test position limit check when exceeding limits."""
        # Mock API client to return account data
        accounts = [
            Account(currency='KRW', balance=100000.0, locked=0.0, 
                   avg_buy_price=0.0, avg_buy_price_modified=False, unit_currency='KRW')
        ]
        risk_manager.api_client.get_accounts.return_value = accounts
        
        # Create order exceeding position limit (30% of portfolio)
        order = Order(market='KRW-BTC', side='bid', ord_type='market', 
                     price=None, volume=30000.0)  # 30,000 KRW worth
        
        result = risk_manager.check_position_limits(order)
        assert result is False
    
    def test_check_daily_limits_within_limit(self, risk_manager):
        """Test daily limits check when within limits."""
        risk_manager.daily_trade_count = 10
        
        result = risk_manager.check_daily_limits()
        assert result is True
    
    def test_check_daily_limits_exceeds_trade_count(self, risk_manager):
        """Test daily limits check when exceeding trade count."""
        risk_manager.daily_trade_count = 50
        
        result = risk_manager.check_daily_limits()
        assert result is False
        assert risk_manager.trading_paused is True
    
    def test_calculate_stop_loss(self, risk_manager):
        """Test stop loss calculation."""
        position = Position(market='BTC', avg_buy_price=50000000.0, 
                          balance=0.1, locked=0.0, unit_currency='KRW')
        
        stop_loss_price = risk_manager.calculate_stop_loss(position)
        expected_price = 50000000.0 * (1 - 0.05)  # 5% stop loss
        
        assert stop_loss_price == expected_price
    
    def test_calculate_stop_loss_zero_balance(self, risk_manager):
        """Test stop loss calculation with zero balance."""
        position = Position(market='BTC', avg_buy_price=50000000.0, 
                          balance=0.0, locked=0.0, unit_currency='KRW')
        
        stop_loss_price = risk_manager.calculate_stop_loss(position)
        assert stop_loss_price == 0.0
    
    def test_should_stop_trading_normal_conditions(self, risk_manager):
        """Test should_stop_trading under normal conditions."""
        # Mock all checks to return True (no issues)
        with patch.object(risk_manager, 'check_daily_limits', return_value=True), \
             patch.object(risk_manager, '_check_balance_protection', return_value=True), \
             patch.object(risk_manager, '_check_stop_loss_triggers', return_value=False):
            
            result = risk_manager.should_stop_trading()
            assert result is False
    
    def test_should_stop_trading_when_paused(self, risk_manager):
        """Test should_stop_trading when trading is paused."""
        risk_manager.trading_paused = True
        
        result = risk_manager.should_stop_trading()
        assert result is True
    
    def test_get_max_order_size(self, risk_manager):
        """Test maximum order size calculation."""
        # Mock API client to return account data
        accounts = [
            Account(currency='KRW', balance=100000.0, locked=0.0, 
                   avg_buy_price=0.0, avg_buy_price_modified=False, unit_currency='KRW')
        ]
        risk_manager.api_client.get_accounts.return_value = accounts
        
        # Mock config manager for trading settings
        risk_manager.config_manager.get_section.return_value = {
            'min_order_amount': 5000.0
        }
        
        max_order_size = risk_manager.get_max_order_size('KRW-BTC')
        expected_size = 100000.0 * 0.20  # 20% position limit
        
        assert max_order_size == expected_size
    
    def test_get_max_order_size_insufficient_balance(self, risk_manager):
        """Test maximum order size when balance is too low."""
        # Mock API client to return low balance
        accounts = [
            Account(currency='KRW', balance=1000.0, locked=0.0, 
                   avg_buy_price=0.0, avg_buy_price_modified=False, unit_currency='KRW')
        ]
        risk_manager.api_client.get_accounts.return_value = accounts
        
        # Mock config manager for trading settings
        risk_manager.config_manager.get_section.return_value = {
            'min_order_amount': 5000.0
        }
        
        max_order_size = risk_manager.get_max_order_size('KRW-BTC')
        assert max_order_size == 0.0  # Below minimum order amount
    
    def test_update_portfolio_snapshot(self, risk_manager):
        """Test portfolio snapshot update."""
        accounts = [
            Account(currency='KRW', balance=100000.0, locked=0.0, 
                   avg_buy_price=0.0, avg_buy_price_modified=False, unit_currency='KRW'),
            Account(currency='BTC', balance=0.1, locked=0.0, 
                   avg_buy_price=50000000.0, avg_buy_price_modified=False, unit_currency='KRW')
        ]
        
        # Mock ticker for BTC price
        ticker = Ticker(market='KRW-BTC', trade_price=50000000.0, trade_volume=1.0,
                       timestamp=datetime.now(), change_rate=0.01)
        risk_manager.api_client.get_ticker.return_value = ticker
        
        snapshot = risk_manager.update_portfolio_snapshot(accounts)
        
        assert isinstance(snapshot, PortfolioSnapshot)
        assert snapshot.total_krw_value > 0
        assert len(snapshot.positions) == 2  # KRW and BTC positions
        assert 'KRW' in snapshot.positions
        assert 'BTC' in snapshot.positions
    
    def test_record_trade(self, risk_manager):
        """Test trade recording."""
        initial_count = risk_manager.daily_trade_count
        initial_volume = risk_manager.daily_trade_volume
        
        risk_manager.record_trade('KRW-BTC', 'bid', 0.001, 50000000.0)
        
        assert risk_manager.daily_trade_count == initial_count + 1
        assert risk_manager.daily_trade_volume > initial_volume
    
    def test_reset_daily_stats(self, risk_manager):
        """Test daily statistics reset."""
        # Set some values
        risk_manager.daily_trade_count = 10
        risk_manager.daily_trade_volume = 1000000.0
        risk_manager.trading_paused = True
        
        risk_manager.reset_daily_stats()
        
        assert risk_manager.daily_trade_count == 0
        assert risk_manager.daily_trade_volume == 0.0
        assert risk_manager.trading_paused is False
    
    def test_pause_and_resume_trading(self, risk_manager):
        """Test trading pause and resume functionality."""
        # Test pause
        risk_manager.pause_trading("Test reason")
        assert risk_manager.trading_paused is True
        assert risk_manager.pause_reason == "Test reason"
        
        # Test resume
        risk_manager.resume_trading()
        assert risk_manager.trading_paused is False
        assert risk_manager.pause_reason == ""
    
    def test_get_risk_status(self, risk_manager):
        """Test risk status retrieval."""
        status = risk_manager.get_risk_status()
        
        assert isinstance(status, dict)
        assert 'trading_paused' in status
        assert 'daily_trade_count' in status
        assert 'max_daily_trades' in status
        assert 'stop_loss_percentage' in status
        assert 'daily_loss_limit' in status
        assert 'position_size_limit' in status
        assert 'min_balance_threshold' in status


class TestNotificationService:
    """Test cases for NotificationService class."""
    
    def test_notification_service_initialization(self):
        """Test NotificationService initialization."""
        service = NotificationService()
        assert service.enabled is True
    
    def test_send_notification(self):
        """Test notification sending."""
        service = NotificationService()
        
        event = RiskEvent(
            event_type='test',
            severity='warning',
            message='Test message',
            timestamp=datetime.now()
        )
        
        result = service.send_notification(event)
        assert result is True


class TestRiskEvent:
    """Test cases for RiskEvent dataclass."""
    
    def test_risk_event_creation(self):
        """Test RiskEvent creation."""
        event = RiskEvent(
            event_type='stop_loss',
            severity='critical',
            message='Stop loss triggered',
            timestamp=datetime.now(),
            market='KRW-BTC',
            current_value=45000000.0,
            threshold_value=47500000.0,
            action_taken='Emergency sell order created'
        )
        
        assert event.event_type == 'stop_loss'
        assert event.severity == 'critical'
        assert event.message == 'Stop loss triggered'
        assert event.market == 'KRW-BTC'
        assert event.current_value == 45000000.0
        assert event.threshold_value == 47500000.0
        assert event.action_taken == 'Emergency sell order created'


class TestPortfolioSnapshot:
    """Test cases for PortfolioSnapshot dataclass."""
    
    def test_portfolio_snapshot_creation(self):
        """Test PortfolioSnapshot creation."""
        positions = {
            'KRW': Position(market='KRW', avg_buy_price=1.0, balance=100000.0, 
                          locked=0.0, unit_currency='KRW'),
            'BTC': Position(market='BTC', avg_buy_price=50000000.0, balance=0.1, 
                          locked=0.0, unit_currency='KRW')
        }
        
        snapshot = PortfolioSnapshot(
            total_krw_value=150000.0,
            total_btc_value=0.003,
            positions=positions,
            timestamp=datetime.now(),
            daily_pnl=5000.0,
            daily_pnl_percentage=0.034
        )
        
        assert snapshot.total_krw_value == 150000.0
        assert snapshot.total_btc_value == 0.003
        assert len(snapshot.positions) == 2
        assert snapshot.daily_pnl == 5000.0
        assert snapshot.daily_pnl_percentage == 0.034