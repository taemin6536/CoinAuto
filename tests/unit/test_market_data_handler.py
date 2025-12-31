"""Unit tests for MarketDataHandler and RollingWindow classes."""

import pytest
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from upbit_trading_bot.data.market_data import MarketDataHandler, RollingWindow, OrderBook, MarketData
from upbit_trading_bot.data.models import Ticker


class TestRollingWindow:
    """Test cases for RollingWindow class."""
    
    def test_rolling_window_initialization(self):
        """Test RollingWindow initialization."""
        window = RollingWindow(5)
        assert window.max_size == 5
        assert window.size() == 0
        assert not window.is_full()
        assert window.get_latest() is None
    
    def test_rolling_window_invalid_size(self):
        """Test RollingWindow with invalid size."""
        with pytest.raises(ValueError, match="max_size must be positive"):
            RollingWindow(0)
        
        with pytest.raises(ValueError, match="max_size must be positive"):
            RollingWindow(-1)
    
    def test_rolling_window_append_and_retrieve(self):
        """Test appending data and retrieving it."""
        window = RollingWindow(3)
        
        ticker1 = Ticker('KRW-BTC', 50000000, 1.5, datetime.now(), 0.05)
        ticker2 = Ticker('KRW-ETH', 3000000, 2.0, datetime.now(), -0.02)
        ticker3 = Ticker('KRW-ADA', 500, 100.0, datetime.now(), 0.10)
        
        window.append(ticker1)
        assert window.size() == 1
        assert window.get_latest() == ticker1
        
        window.append(ticker2)
        assert window.size() == 2
        assert window.get_latest() == ticker2
        
        window.append(ticker3)
        assert window.size() == 3
        assert window.is_full()
        assert window.get_latest() == ticker3
        
        # Test get_data returns all items in order
        data = window.get_data()
        assert len(data) == 3
        assert data[0] == ticker1
        assert data[1] == ticker2
        assert data[2] == ticker3
    
    def test_rolling_window_overflow(self):
        """Test rolling window behavior when exceeding max size."""
        window = RollingWindow(2)
        
        ticker1 = Ticker('KRW-BTC', 50000000, 1.5, datetime.now(), 0.05)
        ticker2 = Ticker('KRW-ETH', 3000000, 2.0, datetime.now(), -0.02)
        ticker3 = Ticker('KRW-ADA', 500, 100.0, datetime.now(), 0.10)
        
        window.append(ticker1)
        window.append(ticker2)
        assert window.size() == 2
        assert window.is_full()
        
        # Adding third item should remove first item
        window.append(ticker3)
        assert window.size() == 2
        assert window.is_full()
        
        data = window.get_data()
        assert len(data) == 2
        assert data[0] == ticker2  # ticker1 should be removed
        assert data[1] == ticker3
    
    def test_rolling_window_invalid_ticker(self):
        """Test appending invalid ticker data."""
        window = RollingWindow(3)
        
        # Create invalid ticker (negative price)
        invalid_ticker = Ticker('KRW-BTC', -50000000, 1.5, datetime.now(), 0.05)
        
        with pytest.raises(ValueError, match="Invalid ticker data"):
            window.append(invalid_ticker)
    
    def test_rolling_window_price_history(self):
        """Test getting price history for specific time period."""
        window = RollingWindow(10)
        
        now = datetime.now()
        
        # Add tickers with different timestamps
        old_ticker = Ticker('KRW-BTC', 50000000, 1.5, now - timedelta(hours=2), 0.05)
        recent_ticker = Ticker('KRW-BTC', 51000000, 1.6, now - timedelta(minutes=30), 0.02)
        current_ticker = Ticker('KRW-BTC', 52000000, 1.7, now, 0.03)
        
        window.append(old_ticker)
        window.append(recent_ticker)
        window.append(current_ticker)
        
        # Get history for last 60 minutes
        history = window.get_price_history(60)
        assert len(history) == 2  # Should exclude old_ticker
        assert recent_ticker in history
        assert current_ticker in history
        assert old_ticker not in history
        
        # Get history for last 3 hours
        history_long = window.get_price_history(180)
        assert len(history_long) == 3  # Should include all
    
    def test_rolling_window_clear(self):
        """Test clearing the rolling window."""
        window = RollingWindow(3)
        
        ticker = Ticker('KRW-BTC', 50000000, 1.5, datetime.now(), 0.05)
        window.append(ticker)
        assert window.size() == 1
        
        window.clear()
        assert window.size() == 0
        assert window.get_latest() is None
        assert not window.is_full()
    
    def test_rolling_window_thread_safety(self):
        """Test thread safety of rolling window operations."""
        window = RollingWindow(100)
        
        def add_tickers():
            for i in range(50):
                ticker = Ticker(f'KRW-TEST{i}', 1000 + i, 1.0, datetime.now(), 0.01)
                window.append(ticker)
                time.sleep(0.001)  # Small delay to simulate real usage
        
        # Start multiple threads adding data
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=add_tickers)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify final state
        assert window.size() == 100  # Should be at max capacity
        assert window.is_full()


class TestMarketDataHandler:
    """Test cases for MarketDataHandler class."""
    
    def test_market_data_handler_initialization(self):
        """Test MarketDataHandler initialization."""
        handler = MarketDataHandler(window_size=50)
        
        assert handler.window_size == 50
        assert not handler.is_connected()
        assert handler.get_subscribed_markets() == []
        assert handler.get_current_price('KRW-BTC') is None
    
    def test_market_data_handler_invalid_markets(self):
        """Test MarketDataHandler with invalid market formats."""
        handler = MarketDataHandler()
        
        # Empty markets list
        with pytest.raises(ValueError, match="Markets list cannot be empty"):
            handler.start_websocket_connection([])
        
        # Invalid market format
        with pytest.raises(ValueError, match="Invalid market format"):
            handler.start_websocket_connection(['INVALID_MARKET'])
        
        with pytest.raises(ValueError, match="Invalid market format"):
            handler.start_websocket_connection(['KRW-BTC', 'INVALID'])
    
    def test_market_data_handler_callback_subscription(self):
        """Test callback subscription functionality."""
        handler = MarketDataHandler()
        
        callback_called = []
        
        def test_callback(market_data):
            callback_called.append(market_data)
        
        # Test valid callback
        handler.subscribe_to_ticker(test_callback)
        
        # Test invalid callback
        with pytest.raises(ValueError, match="Callback must be callable"):
            handler.subscribe_to_ticker("not_callable")
    
    def test_market_data_handler_ticker_validation(self):
        """Test ticker data validation in MarketDataHandler."""
        handler = MarketDataHandler()
        
        # Test valid ticker data
        valid_data = {
            'code': 'KRW-BTC',
            'trade_price': 50000000,
            'trade_volume': 1.5,
            'trade_timestamp': int(datetime.now().timestamp() * 1000),
            'signed_change_rate': 0.05
        }
        
        assert handler._is_valid_ticker_data(valid_data)
        
        # Test invalid ticker data (missing required field)
        invalid_data = {
            'code': 'KRW-BTC',
            'trade_price': 50000000,
            # Missing trade_volume
            'trade_timestamp': int(datetime.now().timestamp() * 1000),
            'signed_change_rate': 0.05
        }
        
        assert not handler._is_valid_ticker_data(invalid_data)
    
    def test_market_data_handler_ticker_parsing(self):
        """Test ticker data parsing in MarketDataHandler."""
        handler = MarketDataHandler()
        
        # Test valid ticker data parsing
        valid_data = {
            'code': 'KRW-BTC',
            'trade_price': 50000000,
            'trade_volume': 1.5,
            'trade_timestamp': int(datetime.now().timestamp() * 1000),
            'signed_change_rate': 0.05
        }
        
        ticker = handler._parse_ticker_data(valid_data)
        assert ticker is not None
        assert ticker.market == 'KRW-BTC'
        assert ticker.trade_price == 50000000
        assert ticker.trade_volume == 1.5
        assert ticker.change_rate == 0.05
        assert isinstance(ticker.timestamp, datetime)
        assert ticker.validate()
        
        # Test invalid ticker data parsing
        invalid_data = {
            'code': 'KRW-BTC',
            'trade_price': 'invalid_price',  # Should be numeric
            'trade_volume': 1.5,
            'trade_timestamp': int(datetime.now().timestamp() * 1000),
            'signed_change_rate': 0.05
        }
        
        ticker = handler._parse_ticker_data(invalid_data)
        assert ticker is None
    
    def test_market_data_handler_rolling_window_size(self):
        """Test rolling window size tracking."""
        handler = MarketDataHandler(window_size=10)
        
        # Initially no windows exist
        assert handler.get_rolling_window_size('KRW-BTC') == 0
        
        # Simulate adding a market (normally done in start_websocket_connection)
        handler._rolling_windows['KRW-BTC'] = RollingWindow(10)
        
        assert handler.get_rolling_window_size('KRW-BTC') == 0
        
        # Add some data
        ticker = Ticker('KRW-BTC', 50000000, 1.5, datetime.now(), 0.05)
        handler._rolling_windows['KRW-BTC'].append(ticker)
        
        assert handler.get_rolling_window_size('KRW-BTC') == 1
    
    def test_market_data_handler_price_history(self):
        """Test price history retrieval."""
        handler = MarketDataHandler()
        
        # Test with non-existent market
        history = handler.get_price_history('KRW-NONEXISTENT')
        assert history == []
        
        # Add a rolling window and test
        handler._rolling_windows['KRW-BTC'] = RollingWindow(10)
        
        now = datetime.now()
        ticker1 = Ticker('KRW-BTC', 50000000, 1.5, now - timedelta(minutes=30), 0.05)
        ticker2 = Ticker('KRW-BTC', 51000000, 1.6, now, 0.02)
        
        handler._rolling_windows['KRW-BTC'].append(ticker1)
        handler._rolling_windows['KRW-BTC'].append(ticker2)
        
        # Get recent history
        history = handler.get_price_history('KRW-BTC', 60)
        assert len(history) == 2
        assert ticker1 in history
        assert ticker2 in history
    
    @patch('requests.get')
    def test_market_data_handler_orderbook(self, mock_get):
        """Test orderbook retrieval via REST API."""
        handler = MarketDataHandler()
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = [{
            'market': 'KRW-BTC',
            'timestamp': int(datetime.now().timestamp() * 1000),
            'total_ask_size': 100.5,
            'total_bid_size': 200.3,
            'orderbook_units': [
                {'ask_price': 50001000, 'bid_price': 50000000, 'ask_size': 1.0, 'bid_size': 2.0}
            ]
        }]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        orderbook = handler.get_orderbook('KRW-BTC')
        
        assert orderbook is not None
        assert orderbook.market == 'KRW-BTC'
        assert orderbook.total_ask_size == 100.5
        assert orderbook.total_bid_size == 200.3
        assert len(orderbook.orderbook_units) == 1
        assert orderbook.validate()
        
        # Verify API call
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert 'orderbook' in args[0]
        assert kwargs['params']['markets'] == 'KRW-BTC'
    
    @patch('requests.get')
    def test_market_data_handler_orderbook_failure(self, mock_get):
        """Test orderbook retrieval failure handling."""
        handler = MarketDataHandler()
        
        # Mock API failure
        mock_get.side_effect = Exception("API Error")
        
        orderbook = handler.get_orderbook('KRW-BTC')
        assert orderbook is None
    
    def test_market_data_handler_stop(self):
        """Test stopping the market data handler."""
        handler = MarketDataHandler()
        
        # Add some test data
        handler._current_prices['KRW-BTC'] = 50000000
        handler._rolling_windows['KRW-BTC'] = RollingWindow(10)
        handler._callbacks.append(lambda x: None)
        
        # Stop the handler
        handler.stop()
        
        # Verify cleanup
        assert not handler.is_connected()
        assert len(handler._callbacks) == 0
        assert len(handler._current_prices) == 0
        assert handler.get_rolling_window_size('KRW-BTC') == 0


class TestOrderBook:
    """Test cases for OrderBook class."""
    
    def test_orderbook_validation(self):
        """Test OrderBook validation."""
        now = datetime.now()
        
        # Valid orderbook
        valid_orderbook = OrderBook(
            market='KRW-BTC',
            timestamp=now,
            total_ask_size=100.5,
            total_bid_size=200.3,
            orderbook_units=[]
        )
        
        assert valid_orderbook.validate()
        
        # Invalid orderbook (empty market)
        invalid_orderbook = OrderBook(
            market='',
            timestamp=now,
            total_ask_size=100.5,
            total_bid_size=200.3,
            orderbook_units=[]
        )
        
        assert not invalid_orderbook.validate()
        
        # Invalid orderbook (negative size)
        invalid_orderbook2 = OrderBook(
            market='KRW-BTC',
            timestamp=now,
            total_ask_size=-100.5,
            total_bid_size=200.3,
            orderbook_units=[]
        )
        
        assert not invalid_orderbook2.validate()


class TestMarketData:
    """Test cases for MarketData class."""
    
    def test_market_data_creation(self):
        """Test MarketData creation."""
        now = datetime.now()
        ticker = Ticker('KRW-BTC', 50000000, 1.5, now, 0.05)
        orderbook = OrderBook('KRW-BTC', now, 100.5, 200.3, [])
        
        # Test with ticker only
        market_data1 = MarketData(ticker=ticker)
        assert market_data1.ticker == ticker
        assert market_data1.orderbook is None
        assert market_data1.timestamp is None
        
        # Test with all fields
        market_data2 = MarketData(ticker=ticker, orderbook=orderbook, timestamp=now)
        assert market_data2.ticker == ticker
        assert market_data2.orderbook == orderbook
        assert market_data2.timestamp == now
        
        # Test with no fields
        market_data3 = MarketData()
        assert market_data3.ticker is None
        assert market_data3.orderbook is None
        assert market_data3.timestamp is None