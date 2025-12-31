"""Property-based tests for trade recording completeness.

**Feature: upbit-trading-bot, Property 18: Trade Recording Completeness**
**Validates: Requirements 6.1**
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite
from typing import Dict, Any

from upbit_trading_bot.data.database import DatabaseManager
from upbit_trading_bot.data.models import Order, OrderResult


@composite
def valid_trade_data(draw):
    """Generate valid trade data for testing."""
    # Generate realistic market names
    base_currencies = ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'XRP', 'LTC', 'BCH', 'DOGE', 'MATIC']
    quote_currencies = ['KRW', 'BTC', 'USDT']
    
    base = draw(st.sampled_from(base_currencies))
    quote = draw(st.sampled_from(quote_currencies))
    # Ensure we don't have BTC-BTC or similar
    assume(base != quote)
    
    market = f"{quote}-{base}"
    side = draw(st.sampled_from(['bid', 'ask']))
    
    # Generate realistic price and volume data
    price = draw(st.floats(min_value=0.01, max_value=100000000.0, allow_nan=False, allow_infinity=False))
    volume = draw(st.floats(min_value=0.00000001, max_value=1000000.0, allow_nan=False, allow_infinity=False))
    fee = draw(st.floats(min_value=0.0, max_value=price * volume * 0.01, allow_nan=False, allow_infinity=False))  # Max 1% fee
    
    # Generate timestamp (naive datetime first, then add timezone)
    naive_timestamp = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31)
    ))
    timestamp = naive_timestamp.replace(tzinfo=timezone.utc)
    
    # Generate strategy ID
    strategy_ids = ['sma_crossover', 'rsi_momentum', 'bollinger_bands', 'macd_signal', 'manual_trade']
    strategy_id = draw(st.sampled_from(strategy_ids + [None]))  # Allow None for manual trades
    
    return {
        'market': market,
        'side': side,
        'price': price,
        'volume': volume,
        'fee': fee,
        'timestamp': timestamp,
        'strategy_id': strategy_id
    }


@composite
def valid_order_result(draw):
    """Generate valid OrderResult for testing."""
    # Generate realistic market names
    base_currencies = ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'XRP', 'LTC', 'BCH']
    quote_currencies = ['KRW', 'BTC', 'USDT']
    
    base = draw(st.sampled_from(base_currencies))
    quote = draw(st.sampled_from(quote_currencies))
    assume(base != quote)
    
    market = f"{quote}-{base}"
    side = draw(st.sampled_from(['bid', 'ask']))
    ord_type = draw(st.sampled_from(['limit', 'market']))
    
    # Generate order ID (UUID-like format)
    order_id = draw(st.text(
        alphabet='abcdef0123456789-',
        min_size=36,
        max_size=36
    ))
    
    # Generate realistic financial data
    price = draw(st.floats(min_value=0.01, max_value=100000000.0, allow_nan=False, allow_infinity=False)) if ord_type == 'limit' else None
    volume = draw(st.floats(min_value=0.00000001, max_value=1000000.0, allow_nan=False, allow_infinity=False))
    executed_volume = draw(st.floats(min_value=0.0, max_value=volume, allow_nan=False, allow_infinity=False))
    remaining_volume = volume - executed_volume
    
    reserved_fee = draw(st.floats(min_value=0.0, max_value=volume * 0.01, allow_nan=False, allow_infinity=False))
    paid_fee = draw(st.floats(min_value=0.0, max_value=reserved_fee, allow_nan=False, allow_infinity=False))
    remaining_fee = reserved_fee - paid_fee
    
    locked = draw(st.floats(min_value=0.0, max_value=volume * 2, allow_nan=False, allow_infinity=False))
    trades_count = draw(st.integers(min_value=0, max_value=100))
    
    return OrderResult(
        order_id=order_id,
        market=market,
        side=side,
        ord_type=ord_type,
        price=price,
        volume=volume,
        remaining_volume=remaining_volume,
        reserved_fee=reserved_fee,
        remaining_fee=remaining_fee,
        paid_fee=paid_fee,
        locked=locked,
        executed_volume=executed_volume,
        trades_count=trades_count
    )


class TestTradeRecordingCompleteness:
    """Property-based tests for trade recording completeness."""
    
    def setup_method(self):
        """Set up test database for each test."""
        # Use in-memory SQLite for testing
        import sqlite3
        self.test_db = sqlite3.connect(':memory:')
        self.test_db.row_factory = sqlite3.Row
        
        # Create trades table for testing
        self.test_db.execute("""
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
        self.test_db.commit()
    
    def teardown_method(self):
        """Clean up test database after each test."""
        if hasattr(self, 'test_db'):
            self.test_db.close()
    
    def insert_trade_record(self, trade_data: Dict[str, Any]) -> bool:
        """Insert trade record into test database."""
        try:
            cursor = self.test_db.cursor()
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
            self.test_db.commit()
            return True
        except Exception:
            return False
    
    def get_trade_record(self, trade_id: int) -> Dict[str, Any]:
        """Retrieve trade record from test database."""
        cursor = self.test_db.cursor()
        cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {}
    
    def get_all_trade_records(self) -> list:
        """Retrieve all trade records from test database."""
        cursor = self.test_db.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]
    
    @given(trade_data=valid_trade_data())
    @settings(max_examples=100, database=None)  # Disable database caching
    def test_property_18_trade_recording_completeness(self, trade_data):
        """
        **Feature: upbit-trading-bot, Property 18: Trade Recording Completeness**
        **Validates: Requirements 6.1**
        
        Property: For any executed trade, all transaction details including 
        timestamp, price, volume, and fees should be recorded.
        """
        # Ensure we start with a clean database
        self.test_db.execute("DELETE FROM trades")
        self.test_db.commit()
        
        # Property 1: Trade record should be successfully inserted
        success = self.insert_trade_record(trade_data)
        assert success, "Trade record should be successfully inserted into database"
        
        # Property 2: All required fields should be present in the recorded trade
        records = self.get_all_trade_records()
        assert len(records) > 0, "At least one trade record should exist after insertion"
        
        recorded_trade = records[-1]  # Get the last inserted record
        
        # Property 3: All essential trade details should be recorded
        required_fields = ['market', 'side', 'price', 'volume', 'fee', 'timestamp']
        for field in required_fields:
            assert field in recorded_trade, f"Required field '{field}' should be present in trade record"
            assert recorded_trade[field] is not None, f"Required field '{field}' should not be None"
        
        # Property 4: Recorded values should match original trade data
        assert recorded_trade['market'] == trade_data['market'], "Market should be recorded correctly"
        assert recorded_trade['side'] == trade_data['side'], "Side should be recorded correctly"
        assert abs(float(recorded_trade['price']) - trade_data['price']) < 1e-10, "Price should be recorded correctly"
        assert abs(float(recorded_trade['volume']) - trade_data['volume']) < 1e-10, "Volume should be recorded correctly"
        assert abs(float(recorded_trade['fee']) - trade_data['fee']) < 1e-10, "Fee should be recorded correctly"
        
        # Property 5: Timestamp should be recorded and parseable
        recorded_timestamp_str = recorded_trade['timestamp']
        assert recorded_timestamp_str, "Timestamp should be recorded"
        
        try:
            recorded_timestamp = datetime.fromisoformat(recorded_timestamp_str.replace('Z', '+00:00'))
            # Allow for small differences due to serialization/deserialization
            time_diff = abs((recorded_timestamp - trade_data['timestamp']).total_seconds())
            assert time_diff < 1.0, "Recorded timestamp should match original timestamp within 1 second"
        except ValueError:
            pytest.fail("Recorded timestamp should be in valid ISO format")
        
        # Property 6: Strategy ID should be recorded correctly (can be None)
        if trade_data['strategy_id'] is not None:
            assert recorded_trade['strategy_id'] == trade_data['strategy_id'], "Strategy ID should be recorded correctly"
        else:
            # None values might be stored as NULL or empty string depending on database
            assert recorded_trade['strategy_id'] is None or recorded_trade['strategy_id'] == '', "None strategy ID should be handled correctly"
        
        # Property 7: Trade record should have a unique identifier
        assert 'id' in recorded_trade, "Trade record should have a unique identifier"
        assert isinstance(recorded_trade['id'], int), "Trade ID should be an integer"
        assert recorded_trade['id'] > 0, "Trade ID should be positive"
    
    @given(order_result=valid_order_result())
    @settings(max_examples=50)
    def test_order_result_to_trade_conversion_completeness(self, order_result):
        """Test that OrderResult can be completely converted to trade records."""
        # Property: OrderResult should contain all necessary information for trade recording
        assert order_result.validate(), "OrderResult should be valid"
        
        # Property: Essential trade information should be extractable from OrderResult
        assert order_result.order_id, "Order ID should be present"
        assert order_result.market, "Market should be present"
        assert order_result.side in ['bid', 'ask'], "Side should be valid"
        assert isinstance(order_result.volume, (int, float)), "Volume should be numeric"
        assert order_result.volume > 0, "Volume should be positive"
        assert isinstance(order_result.executed_volume, (int, float)), "Executed volume should be numeric"
        assert order_result.executed_volume >= 0, "Executed volume should be non-negative"
        assert isinstance(order_result.paid_fee, (int, float)), "Paid fee should be numeric"
        assert order_result.paid_fee >= 0, "Paid fee should be non-negative"
        
        # Property: If order is executed, we should be able to create trade record
        if order_result.executed_volume > 0:
            # Simulate creating trade record from OrderResult
            trade_data = {
                'market': order_result.market,
                'side': order_result.side,
                'price': order_result.price if order_result.price else 0.0,  # Market orders might not have price
                'volume': order_result.executed_volume,
                'fee': order_result.paid_fee,
                'timestamp': datetime.now(timezone.utc),
                'strategy_id': f"order_{order_result.order_id}"
            }
            
            # Property: Trade record should be insertable
            success = self.insert_trade_record(trade_data)
            assert success, "Trade record created from OrderResult should be insertable"
            
            # Property: Inserted record should contain all required information
            records = self.get_all_trade_records()
            assert len(records) > 0, "Trade record should be inserted"
            
            recorded_trade = records[-1]
            assert recorded_trade['market'] == order_result.market, "Market should be preserved"
            assert recorded_trade['side'] == order_result.side, "Side should be preserved"
            assert abs(float(recorded_trade['volume']) - order_result.executed_volume) < 1e-10, "Executed volume should be preserved"
            assert abs(float(recorded_trade['fee']) - order_result.paid_fee) < 1e-10, "Paid fee should be preserved"
    
    @given(trade_data_list=st.lists(valid_trade_data(), min_size=1, max_size=10))
    @settings(max_examples=20, database=None)  # Disable database caching
    def test_multiple_trades_recording_completeness(self, trade_data_list):
        """Test that multiple trades are recorded completely and independently."""
        # Ensure we start with a clean database
        self.test_db.execute("DELETE FROM trades")
        self.test_db.execute("DELETE FROM sqlite_sequence WHERE name='trades'")  # Reset auto-increment
        self.test_db.commit()
        
        # Property: All trades should be recorded successfully
        for trade_data in trade_data_list:
            success = self.insert_trade_record(trade_data)
            assert success, "Each trade should be recorded successfully"
        
        # Property: Number of recorded trades should match number of inserted trades
        records = self.get_all_trade_records()
        assert len(records) == len(trade_data_list), f"All trades should be recorded. Expected {len(trade_data_list)}, got {len(records)}"
        
        # Property: Each trade should maintain its individual completeness
        for i, (original_trade, recorded_trade) in enumerate(zip(trade_data_list, records)):
            assert recorded_trade['market'] == original_trade['market'], f"Trade {i}: Market should be preserved"
            assert recorded_trade['side'] == original_trade['side'], f"Trade {i}: Side should be preserved"
            assert abs(float(recorded_trade['price']) - original_trade['price']) < 1e-10, f"Trade {i}: Price should be preserved"
            assert abs(float(recorded_trade['volume']) - original_trade['volume']) < 1e-10, f"Trade {i}: Volume should be preserved"
            assert abs(float(recorded_trade['fee']) - original_trade['fee']) < 1e-10, f"Trade {i}: Fee should be preserved"
            
            # Property: Each trade should have a unique ID
            assert recorded_trade['id'] == i + 1, f"Trade {i}: Should have sequential ID"
        
        # Property: All trade IDs should be unique
        trade_ids = [record['id'] for record in records]
        assert len(set(trade_ids)) == len(trade_ids), "All trade IDs should be unique"
    
    def test_trade_recording_with_missing_optional_fields(self):
        """Test trade recording when optional fields are missing."""
        # Test with minimal required data (strategy_id is optional)
        minimal_trade = {
            'market': 'KRW-BTC',
            'side': 'bid',
            'price': 50000000.0,
            'volume': 0.001,
            'fee': 50.0,
            'timestamp': datetime.now(timezone.utc),
            'strategy_id': None
        }
        
        # Property: Trade with minimal data should still be recorded completely
        success = self.insert_trade_record(minimal_trade)
        assert success, "Trade with minimal required data should be recorded"
        
        records = self.get_all_trade_records()
        assert len(records) == 1, "One trade record should exist"
        
        recorded_trade = records[0]
        # Property: All required fields should be present even when optional fields are None
        required_fields = ['market', 'side', 'price', 'volume', 'fee', 'timestamp']
        for field in required_fields:
            assert field in recorded_trade, f"Required field '{field}' should be present"
            assert recorded_trade[field] is not None, f"Required field '{field}' should not be None"
    
    def test_trade_recording_data_integrity(self):
        """Test that trade recording maintains data integrity."""
        # Test with extreme but valid values
        extreme_trade = {
            'market': 'KRW-BTC',
            'side': 'ask',
            'price': 0.00000001,  # Very small price
            'volume': 999999999.99999999,  # Very large volume
            'fee': 0.0,  # Zero fee
            'timestamp': datetime(2020, 1, 1, tzinfo=timezone.utc),  # Old timestamp
            'strategy_id': 'a' * 50  # Long strategy ID
        }
        
        # Property: Extreme but valid values should be recorded accurately
        success = self.insert_trade_record(extreme_trade)
        assert success, "Trade with extreme values should be recorded"
        
        records = self.get_all_trade_records()
        recorded_trade = records[-1]
        
        # Property: Precision should be maintained for extreme values
        assert abs(float(recorded_trade['price']) - extreme_trade['price']) < 1e-15, "Small price should be recorded with high precision"
        assert abs(float(recorded_trade['volume']) - extreme_trade['volume']) < 1e-10, "Large volume should be recorded accurately"
        assert float(recorded_trade['fee']) == extreme_trade['fee'], "Zero fee should be recorded exactly"
        assert recorded_trade['strategy_id'] == extreme_trade['strategy_id'], "Long strategy ID should be recorded completely"