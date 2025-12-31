"""Property-based tests for report generation consistency.

**Feature: upbit-trading-bot, Property 20: Report Generation Consistency**
**Validates: Requirements 6.4**
"""

import pytest
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite
from typing import Dict, Any, List, Optional

from upbit_trading_bot.portfolio.manager import PortfolioManager
from upbit_trading_bot.data.database import DatabaseManager
from upbit_trading_bot.data.models import Account, Position, OrderResult


@composite
def valid_trading_data(draw):
    """Generate valid trading data including accounts and trades."""
    # Generate accounts
    krw_balance = draw(st.floats(min_value=0.0, max_value=10000000.0))
    accounts = [
        Account(
            currency='KRW',
            balance=krw_balance,
            locked=0.0,
            avg_buy_price=1.0,
            avg_buy_price_modified=False,
            unit_currency='KRW'
        )
    ]
    
    # Add crypto accounts
    crypto_currencies = ['BTC', 'ETH', 'ADA', 'DOT']
    num_cryptos = draw(st.integers(min_value=0, max_value=3))
    
    for _ in range(num_cryptos):
        currency = draw(st.sampled_from(crypto_currencies))
        # Avoid duplicates
        if any(acc.currency == currency for acc in accounts):
            continue
            
        balance = draw(st.floats(min_value=0.0, max_value=100.0))
        locked = draw(st.floats(min_value=0.0, max_value=balance * 0.1))
        avg_buy_price = draw(st.floats(min_value=1000.0, max_value=100000.0))
        
        accounts.append(
            Account(
                currency=currency,
                balance=balance,
                locked=locked,
                avg_buy_price=avg_buy_price,
                avg_buy_price_modified=False,
                unit_currency='KRW'
            )
        )
    
    # Generate trades
    num_trades = draw(st.integers(min_value=0, max_value=20))
    trades = []
    current_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    
    markets = ['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT']
    
    for i in range(num_trades):
        market = draw(st.sampled_from(markets))
        side = draw(st.sampled_from(['bid', 'ask']))
        price = draw(st.floats(min_value=1000.0, max_value=100000.0))
        volume = draw(st.floats(min_value=0.001, max_value=10.0))
        fee = price * volume * draw(st.floats(min_value=0.0005, max_value=0.005))
        
        # Add time between trades
        time_delta = draw(st.integers(min_value=1, max_value=3600))
        current_time += timedelta(seconds=time_delta)
        
        strategy_ids = ['sma_crossover', 'rsi_momentum', 'manual_trade', None]
        strategy_id = draw(st.sampled_from(strategy_ids))
        
        trade = {
            'market': market,
            'side': side,
            'price': price,
            'volume': volume,
            'fee': fee,
            'timestamp': current_time,
            'strategy_id': strategy_id
        }
        trades.append(trade)
    
    return accounts, trades


@composite
def report_options(draw):
    """Generate valid report generation options."""
    include_positions = draw(st.booleans())
    include_trades = draw(st.booleans())
    
    # Generate optional date range
    use_date_range = draw(st.booleans())
    if use_date_range:
        base_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        days_range = draw(st.integers(min_value=1, max_value=90))
        start_date = base_date
        end_date = base_date + timedelta(days=days_range)
    else:
        start_date = None
        end_date = None
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'include_positions': include_positions,
        'include_trades': include_trades
    }


class MockDatabaseManager:
    """Mock database manager for testing."""
    
    def __init__(self):
        # Use in-memory SQLite for testing
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self._create_test_tables()
        self.trades_data = []
    
    def _create_test_tables(self):
        """Create test tables."""
        cursor = self.connection.cursor()
        
        # Create trades table
        cursor.execute("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('bid', 'ask')),
                price REAL NOT NULL,
                volume REAL NOT NULL,
                fee REAL NOT NULL,
                timestamp TEXT NOT NULL,
                strategy_id TEXT
            )
        """)
        
        # Create portfolio_snapshots table
        cursor.execute("""
            CREATE TABLE portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_krw REAL NOT NULL,
                total_btc REAL NOT NULL,
                timestamp TEXT NOT NULL,
                positions TEXT
            )
        """)
        
        self.connection.commit()
    
    def insert_trade(self, trade_data: Dict[str, Any]) -> bool:
        """Insert trade data."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO trades (market, side, price, volume, fee, timestamp, strategy_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data['market'],
                trade_data['side'],
                trade_data['price'],
                trade_data['volume'],
                trade_data['fee'],
                trade_data['timestamp'].isoformat(),
                trade_data['strategy_id']
            ))
            self.connection.commit()
            self.trades_data.append(trade_data)
            return True
        except Exception:
            return False
    
    def insert_portfolio_snapshot(self, snapshot_data: Dict[str, Any]) -> bool:
        """Insert portfolio snapshot."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO portfolio_snapshots (total_krw, total_btc, timestamp, positions)
                VALUES (?, ?, ?, ?)
            """, (
                snapshot_data['total_krw'],
                snapshot_data['total_btc'],
                snapshot_data['timestamp'].isoformat(),
                str(snapshot_data.get('positions', {}))
            ))
            self.connection.commit()
            return True
        except Exception:
            return False
    
    def get_trades(self, start_date=None, end_date=None, market=None, limit=10000):
        """Get trades from database."""
        cursor = self.connection.cursor()
        sql = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if start_date:
            sql += " AND timestamp >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            sql += " AND timestamp <= ?"
            params.append(end_date.isoformat())
        
        if market:
            sql += " AND market = ?"
            params.append(market)
        
        sql += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_cursor(self):
        """Get database cursor context manager."""
        from contextlib import contextmanager
        
        @contextmanager
        def cursor_context():
            cursor = self.connection.cursor()
            try:
                yield cursor
            finally:
                cursor.close()
        
        return cursor_context()


class TestReportGenerationConsistency:
    """Property-based tests for report generation consistency."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.mock_db = MockDatabaseManager()
        self.portfolio_manager = PortfolioManager(db_manager=self.mock_db)
        # Clear any existing data
        self.mock_db.connection.execute("DELETE FROM trades")
        self.mock_db.connection.execute("DELETE FROM portfolio_snapshots")
        self.mock_db.connection.commit()
        self.mock_db.trades_data = []
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'mock_db') and self.mock_db.connection:
            self.mock_db.connection.close()
    
    def _validate_report_structure(self, report: Dict[str, Any], options: Dict[str, Any]) -> None:
        """Validate that report has the expected structure."""
        # Property 1: Report should be a valid dictionary
        assert isinstance(report, dict), "Report should be a dictionary"
        
        # Property 2: Report should contain required top-level sections
        required_sections = ['report_info', 'performance_metrics', 'account_balances']
        for section in required_sections:
            assert section in report, f"Report should contain '{section}' section"
        
        # Property 3: Report info should contain metadata
        report_info = report['report_info']
        assert 'generated_at' in report_info, "Report info should contain generated_at timestamp"
        assert 'report_type' in report_info, "Report info should contain report_type"
        assert 'version' in report_info, "Report info should contain version"
        
        # Validate timestamp format
        try:
            datetime.fromisoformat(report_info['generated_at'].replace('Z', '+00:00'))
        except ValueError:
            pytest.fail("generated_at should be a valid ISO format timestamp")
        
        # Property 4: Performance metrics should have expected structure
        performance_metrics = report['performance_metrics']
        required_perf_sections = ['period', 'trading_summary', 'profitability', 'performance_ratios', 'portfolio_value']
        for section in required_perf_sections:
            assert section in performance_metrics, f"Performance metrics should contain '{section}' section"
        
        # Property 5: Account balances should be present and valid
        account_balances = report['account_balances']
        assert isinstance(account_balances, dict), "Account balances should be a dictionary"
        
        # Property 6: Optional sections should be present based on options
        if options['include_positions']:
            assert 'current_positions' in report, "Report should contain current_positions when requested"
            assert isinstance(report['current_positions'], dict), "Current positions should be a dictionary"
        
        if options['include_trades']:
            assert 'trade_history' in report, "Report should contain trade_history when requested"
            assert isinstance(report['trade_history'], list), "Trade history should be a list"
    
    def _validate_json_serializable(self, report: Dict[str, Any]) -> None:
        """Validate that report can be serialized to JSON."""
        try:
            json_str = json.dumps(report, ensure_ascii=False, indent=2)
            # Verify it can be parsed back
            parsed_report = json.loads(json_str)
            assert parsed_report == report, "Report should be JSON serializable and parseable"
        except (TypeError, ValueError) as e:
            pytest.fail(f"Report should be JSON serializable: {e}")
    
    def _validate_data_consistency(self, report: Dict[str, Any], accounts: List[Account], trades: List[Dict[str, Any]]) -> None:
        """Validate that report data is consistent with input data."""
        # Property: Account balances should match input accounts
        account_balances = report['account_balances']
        
        for account in accounts:
            if account.currency in account_balances:
                reported_balance = account_balances[account.currency]
                assert abs(reported_balance['balance'] - account.balance) < 1e-8, \
                    f"Account balance for {account.currency} should match input data"
                assert abs(reported_balance['locked'] - account.locked) < 1e-8, \
                    f"Account locked amount for {account.currency} should match input data"
                assert abs(reported_balance['avg_buy_price'] - account.avg_buy_price) < 0.01, \
                    f"Account avg_buy_price for {account.currency} should match input data"
        
        # Property: Trade history should match input trades (if included)
        if 'trade_history' in report:
            trade_history = report['trade_history']
            
            # Should have same number of trades (within date range if specified)
            if len(trades) > 0:
                assert len(trade_history) <= len(trades), \
                    "Trade history should not contain more trades than input"
            
            # Each trade should have required fields
            for trade in trade_history:
                required_trade_fields = ['timestamp', 'market', 'side', 'price', 'volume', 'fee', 'trade_value']
                for field in required_trade_fields:
                    assert field in trade, f"Trade should contain '{field}' field"
                
                # Validate trade_value calculation
                expected_trade_value = trade['price'] * trade['volume']
                assert abs(trade['trade_value'] - expected_trade_value) < 0.01, \
                    "Trade value should be calculated correctly (price * volume)"
    
    @given(trading_data=valid_trading_data(), options=report_options())
    @settings(max_examples=100, database=None)
    def test_property_20_report_generation_consistency(self, trading_data, options):
        """
        **Feature: upbit-trading-bot, Property 20: Report Generation Consistency**
        **Validates: Requirements 6.4**
        
        Property: For any trading data set, generated JSON reports should contain 
        all required fields and valid data.
        """
        accounts, trades = trading_data
        
        # Clear database before inserting new data
        self.mock_db.connection.execute("DELETE FROM trades")
        self.mock_db.connection.execute("DELETE FROM portfolio_snapshots")
        self.mock_db.connection.commit()
        self.mock_db.trades_data = []
        
        # Update portfolio with accounts
        success = self.portfolio_manager.update_positions(accounts)
        assert success, "Portfolio should be updated successfully"
        
        # Insert trades into database
        for trade in trades:
            success = self.mock_db.insert_trade(trade)
            assert success, "Trade should be inserted successfully"
        
        # Generate report with specified options
        report = self.portfolio_manager.generate_report(
            start_date=options['start_date'],
            end_date=options['end_date'],
            include_positions=options['include_positions'],
            include_trades=options['include_trades']
        )
        
        # Property 1: Report should not contain error field (indicating successful generation)
        assert 'error' not in report, f"Report generation should succeed, but got error: {report.get('error')}"
        
        # Property 2: Report should have valid structure
        self._validate_report_structure(report, options)
        
        # Property 3: Report should be JSON serializable
        self._validate_json_serializable(report)
        
        # Property 4: Report data should be consistent with input data
        self._validate_data_consistency(report, accounts, trades)
        
        # Property 5: Generated timestamp should be recent
        report_info = report['report_info']
        generated_at = datetime.fromisoformat(report_info['generated_at'].replace('Z', '+00:00'))
        time_diff = abs((datetime.now(timezone.utc) - generated_at).total_seconds())
        assert time_diff < 60, "Generated timestamp should be recent (within 1 minute)"
        
        # Property 6: Report type and version should be consistent
        assert report_info['report_type'] == 'trading_performance', \
            "Report type should be 'trading_performance'"
        assert report_info['version'] == '1.0', \
            "Report version should be '1.0'"
    
    def test_empty_data_report_generation(self):
        """Test report generation with no accounts or trades."""
        # Generate report with empty data
        report = self.portfolio_manager.generate_report()
        
        # Property: Empty data should still generate valid report structure
        assert 'error' not in report, "Report generation should succeed even with empty data"
        
        options = {'include_positions': True, 'include_trades': True}
        self._validate_report_structure(report, options)
        self._validate_json_serializable(report)
        
        # Property: Empty data should result in zero values
        performance_metrics = report['performance_metrics']
        trading_summary = performance_metrics['trading_summary']
        assert trading_summary['total_trades'] == 0, "Total trades should be zero"
        
        profitability = performance_metrics['profitability']
        assert profitability['gross_profit'] == 0.0, "Gross profit should be zero"
        assert profitability['net_profit'] == 0.0, "Net profit should be zero"
    
    def test_report_with_positions_only(self):
        """Test report generation with positions but no trades."""
        # Create accounts with positions
        accounts = [
            Account(
                currency='KRW',
                balance=1000000.0,
                locked=0.0,
                avg_buy_price=1.0,
                avg_buy_price_modified=False,
                unit_currency='KRW'
            ),
            Account(
                currency='BTC',
                balance=0.1,
                locked=0.0,
                avg_buy_price=50000000.0,
                avg_buy_price_modified=False,
                unit_currency='KRW'
            )
        ]
        
        # Update portfolio
        success = self.portfolio_manager.update_positions(accounts)
        assert success, "Portfolio should be updated successfully"
        
        # Generate report with positions
        report = self.portfolio_manager.generate_report(include_positions=True, include_trades=False)
        
        # Property: Report should contain positions but not trades
        assert 'current_positions' in report, "Report should contain current_positions"
        assert 'trade_history' not in report, "Report should not contain trade_history when not requested"
        
        # Property: Positions should reflect account data
        positions = report['current_positions']
        assert 'KRW-BTC' in positions, "Should have BTC position"
        
        btc_position = positions['KRW-BTC']
        assert abs(btc_position['balance'] - 0.1) < 1e-8, "BTC balance should match"
        assert abs(btc_position['avg_buy_price'] - 50000000.0) < 0.01, "BTC avg_buy_price should match"
    
    def test_report_with_trades_only(self):
        """Test report generation with trades but no positions."""
        # Insert a trade
        trade = {
            'market': 'KRW-BTC',
            'side': 'bid',
            'price': 50000000.0,
            'volume': 0.001,
            'fee': 50.0,
            'timestamp': datetime.now(timezone.utc),
            'strategy_id': 'test'
        }
        
        success = self.mock_db.insert_trade(trade)
        assert success, "Trade should be inserted"
        
        # Generate report with trades only
        report = self.portfolio_manager.generate_report(include_positions=False, include_trades=True)
        
        # Property: Report should contain trades but not positions
        assert 'trade_history' in report, "Report should contain trade_history"
        assert 'current_positions' not in report, "Report should not contain current_positions when not requested"
        
        # Property: Trade history should contain the inserted trade
        trade_history = report['trade_history']
        assert len(trade_history) == 1, "Should have one trade"
        
        reported_trade = trade_history[0]
        assert reported_trade['market'] == trade['market'], "Trade market should match"
        assert reported_trade['side'] == trade['side'], "Trade side should match"
        assert abs(reported_trade['price'] - trade['price']) < 0.01, "Trade price should match"
        assert abs(reported_trade['volume'] - trade['volume']) < 1e-8, "Trade volume should match"
    
    def test_report_date_filtering(self):
        """Test report generation with date range filtering."""
        # Insert trades with different timestamps
        base_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        
        trades = [
            {
                'market': 'KRW-BTC',
                'side': 'bid',
                'price': 50000000.0,
                'volume': 0.001,
                'fee': 50.0,
                'timestamp': base_time,
                'strategy_id': 'test'
            },
            {
                'market': 'KRW-BTC',
                'side': 'ask',
                'price': 55000000.0,
                'volume': 0.001,
                'fee': 55.0,
                'timestamp': base_time + timedelta(days=5),
                'strategy_id': 'test'
            },
            {
                'market': 'KRW-BTC',
                'side': 'bid',
                'price': 52000000.0,
                'volume': 0.001,
                'fee': 52.0,
                'timestamp': base_time + timedelta(days=15),
                'strategy_id': 'test'
            }
        ]
        
        # Insert all trades
        for trade in trades:
            success = self.mock_db.insert_trade(trade)
            assert success, "Trade should be inserted"
        
        # Generate report with date range that includes only first two trades
        start_date = base_time - timedelta(days=1)
        end_date = base_time + timedelta(days=10)
        
        report = self.portfolio_manager.generate_report(
            start_date=start_date,
            end_date=end_date,
            include_trades=True
        )
        
        # Property: Date filtering should work correctly
        trade_history = report['trade_history']
        assert len(trade_history) <= 2, "Should have at most 2 trades within date range"
        
        # Property: All returned trades should be within date range
        for trade in trade_history:
            trade_time = datetime.fromisoformat(trade['timestamp'])
            assert start_date <= trade_time <= end_date, \
                "All trades should be within specified date range"
        
        # Property: Performance metrics should reflect only filtered trades
        performance_metrics = report['performance_metrics']
        period = performance_metrics['period']
        assert period['start_date'] == start_date.isoformat(), "Period start should match filter"
        assert period['end_date'] == end_date.isoformat(), "Period end should match filter"
    
    def test_report_file_saving(self):
        """Test saving report to file."""
        # Generate a simple report
        report = self.portfolio_manager.generate_report()
        
        # Test file saving
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, "test_report.json")
            success = self.portfolio_manager.save_report_to_file(report, filename)
            
            # Property: File saving should succeed
            assert success, "Report file saving should succeed"
            
            # Property: File should exist and contain valid JSON
            assert os.path.exists(filename), "Report file should be created"
            
            with open(filename, 'r', encoding='utf-8') as f:
                loaded_report = json.load(f)
            
            # Property: Loaded report should match original
            assert loaded_report == report, "Loaded report should match original report"