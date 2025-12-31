"""Property-based tests for performance metric calculation.

**Feature: upbit-trading-bot, Property 19: Performance Metric Calculation**
**Validates: Requirements 6.3**
"""

import pytest
import sqlite3
import statistics
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite
from typing import Dict, Any, List, Tuple

from upbit_trading_bot.portfolio.manager import PortfolioManager
from upbit_trading_bot.data.database import DatabaseManager
from upbit_trading_bot.data.models import Account, Position


@composite
def valid_trade_sequence(draw):
    """Generate a valid sequence of trades for performance testing."""
    # Generate a realistic trading sequence
    num_trades = draw(st.integers(min_value=2, max_value=50))
    
    # Generate base market info
    markets = ['KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT']
    market = draw(st.sampled_from(markets))
    
    trades = []
    current_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    
    # Generate alternating buy/sell trades to create realistic scenarios
    for i in range(num_trades):
        # Alternate between buy and sell, but allow some randomness
        if i == 0:
            side = 'bid'  # Start with a buy
        elif i == num_trades - 1:
            side = 'ask'  # End with a sell to realize profit/loss
        else:
            # Mostly alternate, but allow some consecutive trades
            if trades[-1]['side'] == 'bid':
                side = draw(st.sampled_from(['ask', 'ask', 'ask', 'bid']))  # Favor sell after buy
            else:
                side = draw(st.sampled_from(['bid', 'bid', 'bid', 'ask']))  # Favor buy after sell
        
        # Generate realistic price movement
        if i == 0:
            base_price = draw(st.floats(min_value=1000.0, max_value=100000.0))
        else:
            # Price should move realistically (within ±20% of previous)
            prev_price = trades[-1]['price']
            price_change = draw(st.floats(min_value=-0.2, max_value=0.2))
            base_price = prev_price * (1 + price_change)
            base_price = max(1.0, base_price)  # Ensure positive price
        
        volume = draw(st.floats(min_value=0.001, max_value=10.0))
        fee = base_price * volume * draw(st.floats(min_value=0.0005, max_value=0.005))  # 0.05% to 0.5% fee
        
        # Add some time between trades
        time_delta = draw(st.integers(min_value=1, max_value=3600))  # 1 second to 1 hour
        current_time += timedelta(seconds=time_delta)
        
        strategy_ids = ['sma_crossover', 'rsi_momentum', 'manual_trade', None]
        strategy_id = draw(st.sampled_from(strategy_ids))
        
        trade = {
            'market': market,
            'side': side,
            'price': base_price,
            'volume': volume,
            'fee': fee,
            'timestamp': current_time,
            'strategy_id': strategy_id
        }
        trades.append(trade)
    
    return trades


@composite
def valid_account_list(draw):
    """Generate valid account list for portfolio testing."""
    # Always include KRW account
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
    
    # Add some crypto accounts
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
    
    return accounts


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


class TestPerformanceMetricCalculation:
    """Property-based tests for performance metric calculation."""
    
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
    
    def _calculate_expected_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate expected performance metrics manually for verification."""
        if not trades:
            return {
                'total_trades': 0,
                'buy_trades': 0,
                'sell_trades': 0,
                'gross_profit': 0.0,
                'net_profit': 0.0,
                'total_fees': 0.0,
                'win_rate': 0.0
            }
        
        buy_trades = [t for t in trades if t['side'] == 'bid']
        sell_trades = [t for t in trades if t['side'] == 'ask']
        
        # Calculate total values (this matches the portfolio manager logic)
        total_buy_value = sum(t['price'] * t['volume'] for t in buy_trades)
        total_sell_value = sum(t['price'] * t['volume'] for t in sell_trades)
        total_fees = sum(t['fee'] for t in trades)
        
        gross_profit = total_sell_value - total_buy_value
        net_profit = gross_profit - total_fees
        
        # Simple win rate calculation: profitable sells vs total sells
        profitable_sells = 0
        if sell_trades and buy_trades:
            avg_buy_price = total_buy_value / sum(t['volume'] for t in buy_trades) if buy_trades else 0
            for sell_trade in sell_trades:
                if sell_trade['price'] > avg_buy_price:
                    profitable_sells += 1
        
        win_rate = (profitable_sells / len(sell_trades)) if sell_trades else 0.0
        
        return {
            'total_trades': len(trades),
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'gross_profit': gross_profit,
            'net_profit': net_profit,
            'total_fees': total_fees,
            'win_rate': win_rate
        }
    
    @given(trades=valid_trade_sequence())
    @settings(max_examples=100, database=None)
    def test_property_19_performance_metric_calculation(self, trades):
        """
        **Feature: upbit-trading-bot, Property 19: Performance Metric Calculation**
        **Validates: Requirements 6.3**
        
        Property: For any trading history, calculated metrics (profit/loss, win rate, Sharpe ratio) 
        should accurately reflect the trading performance.
        """
        # Ensure we have at least some meaningful trades
        assume(len(trades) >= 2)
        assume(any(t['side'] == 'bid' for t in trades))  # At least one buy
        assume(any(t['side'] == 'ask' for t in trades))  # At least one sell
        
        # Clear database before inserting new trades
        self.mock_db.connection.execute("DELETE FROM trades")
        self.mock_db.connection.commit()
        self.mock_db.trades_data = []
        
        # Insert trades into mock database
        for trade in trades:
            success = self.mock_db.insert_trade(trade)
            assert success, "Trade should be inserted successfully"
        
        # Calculate performance metrics
        start_date = min(t['timestamp'] for t in trades) - timedelta(hours=1)
        end_date = max(t['timestamp'] for t in trades) + timedelta(hours=1)
        
        metrics = self.portfolio_manager.calculate_performance_metrics(start_date, end_date)
        
        # Property 1: Metrics should be returned in expected format
        assert isinstance(metrics, dict), "Performance metrics should be returned as dictionary"
        
        required_sections = ['period', 'trading_summary', 'profitability', 'performance_ratios', 'portfolio_value']
        for section in required_sections:
            assert section in metrics, f"Metrics should contain '{section}' section"
        
        # Property 2: Trading summary should accurately reflect trade counts
        trading_summary = metrics['trading_summary']
        expected_metrics = self._calculate_expected_metrics(trades)
        
        assert trading_summary['total_trades'] == expected_metrics['total_trades'], \
            "Total trades count should be accurate"
        assert trading_summary['buy_trades'] == expected_metrics['buy_trades'], \
            "Buy trades count should be accurate"
        assert trading_summary['sell_trades'] == expected_metrics['sell_trades'], \
            "Sell trades count should be accurate"
        
        # Property 3: Fee calculation should be accurate
        assert abs(trading_summary['total_fees'] - expected_metrics['total_fees']) < 0.01, \
            "Total fees should be calculated accurately"
        
        # Property 4: Profit/loss calculation should be mathematically correct
        profitability = metrics['profitability']
        
        # Allow for small floating point differences
        assert abs(profitability['gross_profit'] - expected_metrics['gross_profit']) < 0.01, \
            "Gross profit should be calculated correctly"
        assert abs(profitability['net_profit'] - expected_metrics['net_profit']) < 0.01, \
            "Net profit should be calculated correctly"
        
        # Property 5: Net profit should equal gross profit minus fees (allow for floating point precision)
        calculated_net = profitability['gross_profit'] - profitability['total_fees']
        assert abs(profitability['net_profit'] - calculated_net) < 0.02, \
            f"Net profit should equal gross profit minus total fees. Expected: {calculated_net}, Got: {profitability['net_profit']}"
        
        # Property 6: Performance ratios should be within valid ranges
        performance_ratios = metrics['performance_ratios']
        
        assert 0.0 <= performance_ratios['win_rate'] <= 100.0, \
            "Win rate should be between 0% and 100%"
        
        # Sharpe ratio can be negative, but should be finite
        assert math.isfinite(performance_ratios['sharpe_ratio']), \
            "Sharpe ratio should be a finite number"
        
        # Max drawdown should be non-negative and finite (can exceed 100% in extreme cases)
        assert performance_ratios['max_drawdown'] >= 0.0, \
            "Max drawdown should be non-negative"
        assert math.isfinite(performance_ratios['max_drawdown']), \
            "Max drawdown should be a finite number"
        
        # Property 7: Period information should be accurate
        period = metrics['period']
        assert period['start_date'] == start_date.isoformat(), \
            "Start date should match input"
        assert period['end_date'] == end_date.isoformat(), \
            "End date should match input"
        assert period['days'] == (end_date - start_date).days, \
            "Days calculation should be accurate"
        
        # Property 8: Calculated timestamp should be recent
        calculated_at = datetime.fromisoformat(metrics['calculated_at'].replace('Z', '+00:00'))
        time_diff = abs((datetime.now(timezone.utc) - calculated_at).total_seconds())
        assert time_diff < 60, "Calculated timestamp should be recent (within 1 minute)"
    
    @given(accounts=valid_account_list())
    @settings(max_examples=50)
    def test_portfolio_value_calculation_accuracy(self, accounts):
        """Test that portfolio value calculations are accurate."""
        # Update portfolio with accounts
        success = self.portfolio_manager.update_positions(accounts)
        assert success, "Portfolio should be updated successfully"
        
        # Calculate performance metrics (will use empty trade history)
        metrics = self.portfolio_manager.calculate_performance_metrics()
        
        # Property: Portfolio value should reflect account balances
        portfolio_value = metrics['portfolio_value']
        
        # Calculate expected KRW and BTC values
        expected_krw = 0.0
        expected_btc = 0.0
        expected_positions = 0
        
        for account in accounts:
            if account.currency == 'KRW':
                expected_krw += account.balance
            elif account.balance > 0 or account.locked > 0:
                if account.currency == 'BTC':
                    expected_btc += account.balance
                else:
                    # Other cryptos are valued in KRW
                    expected_krw += account.balance * account.avg_buy_price
                expected_positions += 1
        
        # Allow for small floating point differences
        assert abs(portfolio_value['total_krw'] - expected_krw) < 0.01, \
            f"Total KRW value should be calculated accurately. Expected: {expected_krw}, Got: {portfolio_value['total_krw']}"
        assert abs(portfolio_value['total_btc'] - expected_btc) < 1e-8, \
            f"Total BTC value should be calculated accurately. Expected: {expected_btc}, Got: {portfolio_value['total_btc']}"
        assert portfolio_value['positions_count'] == expected_positions, \
            f"Positions count should be accurate. Expected: {expected_positions}, Got: {portfolio_value['positions_count']}"
    
    def test_empty_trade_history_metrics(self):
        """Test performance metrics calculation with no trades."""
        # Calculate metrics with no trades
        metrics = self.portfolio_manager.calculate_performance_metrics()
        
        # Property: Empty trade history should return zero metrics
        trading_summary = metrics['trading_summary']
        assert trading_summary['total_trades'] == 0, "Total trades should be zero"
        assert trading_summary['buy_trades'] == 0, "Buy trades should be zero"
        assert trading_summary['sell_trades'] == 0, "Sell trades should be zero"
        
        profitability = metrics['profitability']
        assert profitability['gross_profit'] == 0.0, "Gross profit should be zero"
        assert profitability['net_profit'] == 0.0, "Net profit should be zero"
        assert profitability['total_fees'] == 0.0, "Total fees should be zero"
        
        performance_ratios = metrics['performance_ratios']
        assert performance_ratios['win_rate'] == 0.0, "Win rate should be zero"
        assert performance_ratios['sharpe_ratio'] == 0.0, "Sharpe ratio should be zero"
        assert performance_ratios['max_drawdown'] == 0.0, "Max drawdown should be zero"
    
    def test_single_trade_metrics(self):
        """Test performance metrics with a single trade."""
        # Insert a single buy trade
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
        
        metrics = self.portfolio_manager.calculate_performance_metrics()
        
        # Property: Single trade should be reflected accurately
        trading_summary = metrics['trading_summary']
        assert trading_summary['total_trades'] == 1, "Should have one trade"
        assert trading_summary['buy_trades'] == 1, "Should have one buy trade"
        assert trading_summary['sell_trades'] == 0, "Should have no sell trades"
        
        # Property: With only buy trades, gross profit should be negative
        profitability = metrics['profitability']
        expected_gross_profit = -trade['price'] * trade['volume']  # Negative because it's a buy
        assert abs(profitability['gross_profit'] - expected_gross_profit) < 0.01, \
            "Gross profit should reflect the buy trade cost"
    
    def test_simple_profit_loss_calculation(self):
        """Test simple profit/loss calculation with known values."""
        # Clear database
        self.mock_db.connection.execute("DELETE FROM trades")
        self.mock_db.connection.commit()
        self.mock_db.trades_data = []
        
        # Create a simple buy-sell pair with known values
        base_time = datetime.now(timezone.utc)
        
        buy_trade = {
            'market': 'KRW-BTC',
            'side': 'bid',
            'price': 1000.0,
            'volume': 1.0,
            'fee': 2.5,  # 0.25% fee
            'timestamp': base_time,
            'strategy_id': 'test'
        }
        
        sell_trade = {
            'market': 'KRW-BTC',
            'side': 'ask',
            'price': 1200.0,
            'volume': 1.0,
            'fee': 3.0,  # 0.25% fee
            'timestamp': base_time + timedelta(minutes=10),
            'strategy_id': 'test'
        }
        
        # Insert both trades
        success1 = self.mock_db.insert_trade(buy_trade)
        success2 = self.mock_db.insert_trade(sell_trade)
        assert success1 and success2, "Both trades should be inserted successfully"
        
        # Verify exactly 2 trades in database
        all_trades = self.mock_db.get_trades()
        assert len(all_trades) == 2, f"Should have exactly 2 trades, got {len(all_trades)}"
        
        # Calculate metrics with explicit date range
        start_date = base_time - timedelta(hours=1)
        end_date = base_time + timedelta(hours=1)
        metrics = self.portfolio_manager.calculate_performance_metrics(start_date, end_date)
        profitability = metrics['profitability']
        
        # Expected calculations:
        # Buy value: 1000 * 1 = 1000
        # Sell value: 1200 * 1 = 1200
        # Gross profit: 1200 - 1000 = 200
        # Total fees: 2.5 + 3.0 = 5.5
        # Net profit: 200 - 5.5 = 194.5
        
        assert abs(profitability['gross_profit'] - 200.0) < 0.01, \
            f"Gross profit should be 200. Got: {profitability['gross_profit']}"
        assert abs(profitability['total_fees'] - 5.5) < 0.01, \
            f"Total fees should be 5.5. Got: {profitability['total_fees']}"
        assert abs(profitability['net_profit'] - 194.5) < 0.01, \
            f"Net profit should be 194.5. Got: {profitability['net_profit']}"
        assert abs(profitability['total_fees'] - 5.5) < 0.01, \
            f"Total fees should be 5.5. Got: {profitability['total_fees']}"
        assert abs(profitability['net_profit'] - 194.5) < 0.01, \
            f"Net profit should be 194.5. Got: {profitability['net_profit']}"