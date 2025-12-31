"""
Pytest configuration and fixtures for the Upbit Trading Bot test suite.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for test configurations."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_upbit_api():
    """Mock Upbit API client for testing."""
    mock_api = Mock()
    mock_api.authenticate.return_value = True
    mock_api.get_accounts.return_value = []
    mock_api.get_ticker.return_value = {
        "market": "KRW-BTC",
        "trade_price": 50000000,
        "trade_volume": 0.1,
        "timestamp": "2023-01-01T00:00:00Z"
    }
    return mock_api


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "market": "KRW-BTC",
        "trade_price": 50000000,
        "trade_volume": 0.1,
        "acc_trade_price": 1000000000,
        "acc_trade_volume": 20.0,
        "timestamp": "2023-01-01T00:00:00Z",
        "change": "RISE",
        "change_price": 1000000,
        "change_rate": 0.02
    }


@pytest.fixture
def sample_trading_signal():
    """Sample trading signal for testing."""
    return {
        "market": "KRW-BTC",
        "action": "buy",
        "confidence": 0.8,
        "price": 50000000,
        "volume": 0.001,
        "strategy_id": "test_strategy",
        "timestamp": "2023-01-01T00:00:00Z"
    }


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    test_env = {
        "UPBIT_ACCESS_KEY": "test_access_key",
        "UPBIT_SECRET_KEY": "test_secret_key",
        "DATABASE_URL": "sqlite:///:memory:",
        "LOG_LEVEL": "DEBUG",
        "TESTING": "True"
    }
    
    # Store original values
    original_env = {}
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    yield
    
    # Restore original values
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value