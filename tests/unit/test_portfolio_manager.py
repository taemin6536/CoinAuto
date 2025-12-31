"""
Unit tests for PortfolioManager.

Tests the core functionality of portfolio management including position tracking,
performance metrics calculation, and report generation.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from upbit_trading_bot.portfolio.manager import PortfolioManager
from upbit_trading_bot.data.models import Account, OrderResult, Position


class TestPortfolioManager:
    """Unit tests for PortfolioManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock database manager
        self.mock_db = Mock()
        self.mock_db.insert_trade.return_value = True
        self.mock_db.insert_portfolio_snapshot.return_value = True
        self.mock_db.get_trades.return_value = []
        
        # Create portfolio manager with mocked database
        self.portfolio = PortfolioManager(db_manager=self.mock_db)
        
        # Test data
        self.test_accounts = [
            Account(
                currency='KRW',
                balance=1000000.0,
                locked=0.0,
                avg_buy_price=0.0,
                avg_buy_price_modified=False,
                unit_currency='KRW'
            ),
            Account(
                currency='BTC',
                balance=0.01,
                locked=0.0,
                avg_buy_price=50000000.0,
                avg_buy_price_modified=True,
                unit_currency='KRW'
            ),
            Account(
                currency='ETH',
                balance=0.5,
                locked=0.1,
                avg_buy_price=3000000.0,
                avg_buy_price_modified=True,
                unit_currency='KRW'
            )
        ]
        
        self.test_order_result = OrderResult(
            order_id='test-order-123',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            volume=0.001,
            remaining_volume=0.0,
            reserved_fee=50.0,
            remaining_fee=0.0,
            paid_fee=50.0,
            locked=50000.0,
            executed_volume=0.001,
            trades_count=1
        )
    
    def test_portfolio_manager_initialization(self):
        """Test portfolio manager initialization."""
        assert self.portfolio is not None
        assert self.portfolio.db == self.mock_db
        assert len(self.portfolio._positions) == 0
        assert len(self.portfolio._accounts) == 0
        assert self.portfolio._total_krw_value == 0.0
        assert self.portfolio._total_btc_value == 0.0
    
    def test_update_positions_success(self):
        """Test successful position update."""
        success = self.portfolio.update_positions(self.test_accounts)
        
        assert success is True
        assert len(self.portfolio._positions) == 2  # BTC and ETH positions
        assert len(self.portfolio._accounts) == 3   # KRW, BTC, ETH accounts
        
        # Check KRW account
        krw_account = self.portfolio.get_account('KRW')
        assert krw_account is not None
        assert krw_account.balance == 1000000.0
        
        # Check BTC position
        btc_position = self.portfolio.get_position('KRW-BTC')
        assert btc_position is not None
        assert btc_position.balance == 0.01
        assert btc_position.avg_buy_price == 50000000.0
        
        # Check ETH position
        eth_position = self.portfolio.get_position('KRW-ETH')
        assert eth_position is not None
        assert eth_position.balance == 0.5
        assert eth_position.locked == 0.1
        
        # Check total values
        total_krw, total_btc = self.portfolio.get_total_value()
        assert total_krw > 0  # Should include KRW balance and crypto values
        assert total_btc == 0.01  # Only BTC balance
        
        # Verify database snapshot was saved
        self.mock_db.insert_portfolio_snapshot.assert_called_once()
    
    def test_update_positions_with_invalid_account(self):
        """Test position update with invalid account data."""
        invalid_accounts = [
            Account(
                currency='',  # Invalid empty currency
                balance=1000.0,
                locked=0.0,
                avg_buy_price=0.0,
                avg_buy_price_modified=False,
                unit_currency='KRW'
            )
        ]
        
        success = self.portfolio.update_positions(invalid_accounts)
        
        # Should still succeed but skip invalid accounts
        assert success is True
        assert len(self.portfolio._positions) == 0
        assert len(self.portfolio._accounts) == 0
    
    def test_record_trade_success(self):
        """Test successful trade recording."""
        success = self.portfolio.record_trade(self.test_order_result, 'test_strategy')
        
        assert success is True
        
        # Verify database insert was called with correct data
        self.mock_db.insert_trade.assert_called_once()
        call_args = self.mock_db.insert_trade.call_args[0][0]
        
        assert call_args['market'] == 'KRW-BTC'
        assert call_args['side'] == 'bid'
        assert call_args['price'] == 50000000.0
        assert call_args['volume'] == 0.001
        assert call_args['fee'] == 50.0
        assert call_args['strategy_id'] == 'test_strategy'
        assert 'timestamp' in call_args
    
    def test_record_trade_with_zero_executed_volume(self):
        """Test trade recording with zero executed volume."""
        order_result = OrderResult(
            order_id='test-order-456',
            market='KRW-ETH',
            side='ask',
            ord_type='limit',
            price=3000000.0,
            volume=0.1,
            remaining_volume=0.1,
            reserved_fee=300.0,
            remaining_fee=300.0,
            paid_fee=0.0,
            locked=300000.0,
            executed_volume=0.0,  # No execution
            trades_count=0
        )
        
        success = self.portfolio.record_trade(order_result, 'test_strategy')
        
        # Should succeed but not insert to database
        assert success is True
        self.mock_db.insert_trade.assert_not_called()
    
    def test_record_trade_with_invalid_order_result(self):
        """Test trade recording with invalid order result."""
        invalid_order_result = OrderResult(
            order_id='',  # Invalid empty order ID
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            volume=0.001,
            remaining_volume=0.0,
            reserved_fee=50.0,
            remaining_fee=0.0,
            paid_fee=50.0,
            locked=50000.0,
            executed_volume=0.001,
            trades_count=1
        )
        
        success = self.portfolio.record_trade(invalid_order_result, 'test_strategy')
        
        assert success is False
        self.mock_db.insert_trade.assert_not_called()
    
    def test_get_positions(self):
        """Test position retrieval."""
        # Update positions first
        self.portfolio.update_positions(self.test_accounts)
        
        positions = self.portfolio.get_positions()
        
        assert isinstance(positions, dict)
        assert len(positions) == 2
        assert 'KRW-BTC' in positions
        assert 'KRW-ETH' in positions
        
        # Verify it returns a copy (not the original)
        positions['KRW-TEST'] = Position('KRW-TEST', 0, 0, 0, 'KRW')
        assert 'KRW-TEST' not in self.portfolio._positions
    
    def test_get_accounts(self):
        """Test account retrieval."""
        # Update positions first
        self.portfolio.update_positions(self.test_accounts)
        
        accounts = self.portfolio.get_accounts()
        
        assert isinstance(accounts, dict)
        assert len(accounts) == 3
        assert 'KRW' in accounts
        assert 'BTC' in accounts
        assert 'ETH' in accounts
        
        # Verify it returns a copy (not the original)
        accounts['TEST'] = Account('TEST', 0, 0, 0, False, 'KRW')
        assert 'TEST' not in self.portfolio._accounts
    
    def test_calculate_performance_metrics_empty(self):
        """Test performance metrics calculation with no trades."""
        metrics = self.portfolio.calculate_performance_metrics()
        
        assert isinstance(metrics, dict)
        assert 'period' in metrics
        assert 'trading_summary' in metrics
        assert 'profitability' in metrics
        assert 'performance_ratios' in metrics
        assert 'portfolio_value' in metrics
        
        # Check empty metrics
        assert metrics['trading_summary']['total_trades'] == 0
        assert metrics['profitability']['net_profit'] == 0.0
        assert metrics['performance_ratios']['win_rate'] == 0.0
        assert metrics['performance_ratios']['sharpe_ratio'] == 0.0
    
    def test_calculate_performance_metrics_with_trades(self):
        """Test performance metrics calculation with sample trades."""
        # Mock trade data
        sample_trades = [
            {
                'market': 'KRW-BTC',
                'side': 'bid',
                'price': 50000000.0,
                'volume': 0.001,
                'fee': 50.0,
                'timestamp': '2024-01-01T10:00:00+00:00',
                'strategy_id': 'test'
            },
            {
                'market': 'KRW-BTC',
                'side': 'ask',
                'price': 55000000.0,
                'volume': 0.001,
                'fee': 55.0,
                'timestamp': '2024-01-02T10:00:00+00:00',
                'strategy_id': 'test'
            }
        ]
        
        self.mock_db.get_trades.return_value = sample_trades
        
        metrics = self.portfolio.calculate_performance_metrics()
        
        assert metrics['trading_summary']['total_trades'] == 2
        assert metrics['trading_summary']['buy_trades'] == 1
        assert metrics['trading_summary']['sell_trades'] == 1
        assert metrics['profitability']['gross_profit'] > 0  # Should be profitable
        assert metrics['profitability']['total_fees'] == 105.0
    
    def test_generate_report_basic(self):
        """Test basic report generation."""
        # Update positions first
        self.portfolio.update_positions(self.test_accounts)
        
        report = self.portfolio.generate_report(
            include_positions=True,
            include_trades=False
        )
        
        assert isinstance(report, dict)
        assert 'report_info' in report
        assert 'performance_metrics' in report
        assert 'current_positions' in report
        assert 'account_balances' in report
        assert 'trade_history' not in report  # Not included
        
        # Check report info
        assert report['report_info']['report_type'] == 'trading_performance'
        assert report['report_info']['version'] == '1.0'
        
        # Check positions
        assert len(report['current_positions']) == 2
        assert 'KRW-BTC' in report['current_positions']
        assert 'KRW-ETH' in report['current_positions']
        
        # Check account balances
        assert len(report['account_balances']) == 3
        assert 'KRW' in report['account_balances']
        assert 'BTC' in report['account_balances']
        assert 'ETH' in report['account_balances']
    
    def test_generate_report_with_trades(self):
        """Test report generation including trade history."""
        # Mock trade data
        sample_trades = [
            {
                'market': 'KRW-BTC',
                'side': 'bid',
                'price': 50000000.0,
                'volume': 0.001,
                'fee': 50.0,
                'timestamp': '2024-01-01T10:00:00+00:00',
                'strategy_id': 'test'
            }
        ]
        
        self.mock_db.get_trades.return_value = sample_trades
        
        report = self.portfolio.generate_report(
            include_positions=False,
            include_trades=True
        )
        
        assert 'trade_history' in report
        assert 'current_positions' not in report  # Not included
        assert len(report['trade_history']) == 1
        
        trade = report['trade_history'][0]
        assert trade['market'] == 'KRW-BTC'
        assert trade['side'] == 'bid'
        assert trade['price'] == 50000000.0
        assert trade['volume'] == 0.001
        assert trade['fee'] == 50.0
        assert 'trade_value' in trade
    
    def test_save_report_to_file(self):
        """Test saving report to file."""
        test_report = {
            'test': 'data',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            success = self.portfolio.save_report_to_file(test_report, 'test_report.json')
            
            assert success is True
            mock_open.assert_called_once_with('test_report.json', 'w', encoding='utf-8')
            mock_file.write.assert_called()  # JSON data should be written
    
    def test_get_total_value(self):
        """Test total portfolio value calculation."""
        # Update positions first
        self.portfolio.update_positions(self.test_accounts)
        
        total_krw, total_btc = self.portfolio.get_total_value()
        
        assert isinstance(total_krw, float)
        assert isinstance(total_btc, float)
        assert total_krw >= 1000000.0  # At least KRW balance
        assert total_btc == 0.01  # BTC balance
    
    def test_portfolio_manager_with_database_error(self):
        """Test portfolio manager behavior when database operations fail."""
        # Mock database to raise exceptions
        self.mock_db.insert_trade.side_effect = Exception("Database error")
        self.mock_db.insert_portfolio_snapshot.side_effect = Exception("Database error")
        
        # Position update should still work (only snapshot saving fails)
        success = self.portfolio.update_positions(self.test_accounts)
        assert success is True  # Position update in memory should succeed
        
        # Trade recording should fail gracefully
        success = self.portfolio.record_trade(self.test_order_result, 'test_strategy')
        assert success is False
    
    def test_empty_performance_metrics_structure(self):
        """Test that empty performance metrics have correct structure."""
        metrics = self.portfolio._get_empty_performance_metrics()
        
        # Verify all required sections exist
        required_sections = [
            'period', 'trading_summary', 'profitability', 
            'performance_ratios', 'portfolio_value'
        ]
        
        for section in required_sections:
            assert section in metrics
        
        # Verify period section
        assert 'start_date' in metrics['period']
        assert 'end_date' in metrics['period']
        assert 'days' in metrics['period']
        
        # Verify trading summary section
        trading_fields = [
            'total_trades', 'buy_trades', 'sell_trades',
            'total_buy_volume', 'total_sell_volume', 'total_fees'
        ]
        for field in trading_fields:
            assert field in metrics['trading_summary']
            assert metrics['trading_summary'][field] == 0 or metrics['trading_summary'][field] == 0.0
        
        # Verify profitability section
        profit_fields = ['gross_profit', 'net_profit', 'total_fees', 'profit_margin']
        for field in profit_fields:
            assert field in metrics['profitability']
            assert metrics['profitability'][field] == 0.0
        
        # Verify performance ratios section
        ratio_fields = ['win_rate', 'sharpe_ratio', 'max_drawdown']
        for field in ratio_fields:
            assert field in metrics['performance_ratios']
            assert metrics['performance_ratios'][field] == 0.0
        
        # Verify portfolio value section
        value_fields = ['total_krw', 'total_btc', 'positions_count']
        for field in value_fields:
            assert field in metrics['portfolio_value']