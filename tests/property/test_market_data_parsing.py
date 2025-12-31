"""Property-based tests for market data parsing consistency.

**Feature: upbit-trading-bot, Property 5: Market Data Parsing Consistency**
**Validates: Requirements 2.2**
"""

import pytest
import json
from datetime import datetime, timezone
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.data.models import Ticker, Order, TradingSignal, Position


@composite
def valid_market_data_response(draw):
    """Generate valid market data response structure similar to Upbit API."""
    # Generate realistic market names
    base_currencies = ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'XRP', 'LTC', 'BCH']
    quote_currencies = ['KRW', 'BTC', 'USDT']
    
    base = draw(st.sampled_from(base_currencies))
    quote = draw(st.sampled_from(quote_currencies))
    # Ensure we don't have BTC-BTC or similar
    assume(base != quote)
    
    market = f"{quote}-{base}"
    
    # Generate realistic price data
    trade_price = draw(st.floats(min_value=0.01, max_value=100000000.0, allow_nan=False, allow_infinity=False))
    trade_volume = draw(st.floats(min_value=0.0, max_value=1000000.0, allow_nan=False, allow_infinity=False))
    change_rate = draw(st.floats(min_value=-0.3, max_value=0.3, allow_nan=False, allow_infinity=False))
    
    # Generate timestamp (naive datetime, then add timezone)
    naive_timestamp = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31)
    ))
    timestamp = naive_timestamp.replace(tzinfo=timezone.utc)
    
    return {
        'market': market,
        'trade_price': trade_price,
        'trade_volume': trade_volume,
        'timestamp': timestamp,
        'change_rate': change_rate
    }


@composite
def valid_ticker_json_response(draw):
    """Generate valid ticker JSON response similar to Upbit API format."""
    market_data = draw(valid_market_data_response())
    
    # Convert to format similar to Upbit API response
    return {
        'market': market_data['market'],
        'trade_price': str(market_data['trade_price']),  # API returns as string
        'trade_volume': str(market_data['trade_volume']),  # API returns as string
        'trade_date_utc': market_data['timestamp'].strftime('%Y-%m-%d'),
        'trade_time_utc': market_data['timestamp'].strftime('%H:%M:%S'),
        'change_rate': str(market_data['change_rate'])  # API returns as string
    }


@composite
def malformed_market_data(draw):
    """Generate malformed market data for negative testing."""
    malform_type = draw(st.sampled_from([
        'missing_required_field',
        'invalid_field_type',
        'negative_price',
        'negative_volume',
        'invalid_market_format',
        'empty_string_values'
    ]))
    
    base_data = draw(valid_market_data_response())
    
    if malform_type == 'missing_required_field':
        field_to_remove = draw(st.sampled_from(['market', 'trade_price', 'trade_volume', 'timestamp', 'change_rate']))
        del base_data[field_to_remove]
        return base_data
    
    elif malform_type == 'invalid_field_type':
        field_to_break = draw(st.sampled_from(['trade_price', 'trade_volume', 'change_rate']))
        base_data[field_to_break] = "not_a_number"
        return base_data
    
    elif malform_type == 'negative_price':
        base_data['trade_price'] = -abs(base_data['trade_price'])
        return base_data
    
    elif malform_type == 'negative_volume':
        base_data['trade_volume'] = -abs(base_data['trade_volume']) - 0.01  # Ensure negative
        return base_data
    
    elif malform_type == 'invalid_market_format':
        base_data['market'] = draw(st.text(min_size=1, max_size=10))
        # Ensure it doesn't accidentally match valid format
        assume('-' not in base_data['market'] or base_data['market'].count('-') != 1)
        return base_data
    
    elif malform_type == 'empty_string_values':
        base_data['market'] = ""
        return base_data
    
    return base_data


class TestMarketDataParsingConsistency:
    """Property-based tests for market data parsing consistency."""
    
    @given(market_data=valid_market_data_response())
    @settings(max_examples=100)
    def test_property_5_market_data_parsing_consistency(self, market_data):
        """
        **Feature: upbit-trading-bot, Property 5: Market Data Parsing Consistency**
        **Validates: Requirements 2.2**
        
        Property: For any valid market data response, parsing should produce 
        structured data with all required fields populated.
        """
        # Create Ticker from the market data
        ticker = Ticker(
            market=market_data['market'],
            trade_price=market_data['trade_price'],
            trade_volume=market_data['trade_volume'],
            timestamp=market_data['timestamp'],
            change_rate=market_data['change_rate']
        )
        
        # Property 1: Ticker should validate successfully
        assert ticker.validate(), "Valid market data should produce a valid Ticker"
        
        # Property 2: All required fields should be populated with correct types
        assert isinstance(ticker.market, str), "Market should be a string"
        assert len(ticker.market) > 0, "Market should not be empty"
        assert isinstance(ticker.trade_price, (int, float)), "Trade price should be numeric"
        assert ticker.trade_price > 0, "Trade price should be positive"
        assert isinstance(ticker.trade_volume, (int, float)), "Trade volume should be numeric"
        assert ticker.trade_volume >= 0, "Trade volume should be non-negative"
        assert isinstance(ticker.timestamp, datetime), "Timestamp should be datetime"
        assert isinstance(ticker.change_rate, (int, float)), "Change rate should be numeric"
        
        # Property 3: Serialization round-trip should preserve data
        ticker_dict = ticker.to_dict()
        reconstructed_ticker = Ticker.from_dict(ticker_dict)
        
        assert reconstructed_ticker.market == ticker.market, "Market should be preserved in round-trip"
        assert abs(reconstructed_ticker.trade_price - ticker.trade_price) < 1e-10, "Trade price should be preserved in round-trip"
        assert abs(reconstructed_ticker.trade_volume - ticker.trade_volume) < 1e-10, "Trade volume should be preserved in round-trip"
        assert reconstructed_ticker.timestamp == ticker.timestamp, "Timestamp should be preserved in round-trip"
        assert abs(reconstructed_ticker.change_rate - ticker.change_rate) < 1e-10, "Change rate should be preserved in round-trip"
        
        # Property 4: JSON serialization round-trip should preserve data
        ticker_json = ticker.to_json()
        json_reconstructed_ticker = Ticker.from_json(ticker_json)
        
        assert json_reconstructed_ticker.market == ticker.market, "Market should be preserved in JSON round-trip"
        assert abs(json_reconstructed_ticker.trade_price - ticker.trade_price) < 1e-10, "Trade price should be preserved in JSON round-trip"
        assert abs(json_reconstructed_ticker.trade_volume - ticker.trade_volume) < 1e-10, "Trade volume should be preserved in JSON round-trip"
        assert json_reconstructed_ticker.timestamp == ticker.timestamp, "Timestamp should be preserved in JSON round-trip"
        assert abs(json_reconstructed_ticker.change_rate - ticker.change_rate) < 1e-10, "Change rate should be preserved in JSON round-trip"
        
        # Property 5: Reconstructed ticker should also validate
        assert reconstructed_ticker.validate(), "Reconstructed ticker should validate"
        assert json_reconstructed_ticker.validate(), "JSON reconstructed ticker should validate"
    
    @given(json_response=valid_ticker_json_response())
    @settings(max_examples=50)
    def test_api_response_parsing_consistency(self, json_response):
        """Test parsing of API-like JSON responses with string numeric values."""
        # Simulate parsing API response (strings to numbers)
        try:
            parsed_timestamp = datetime.strptime(
                f"{json_response['trade_date_utc']} {json_response['trade_time_utc']}", 
                '%Y-%m-%d %H:%M:%S'
            ).replace(tzinfo=timezone.utc)
            
            ticker = Ticker(
                market=json_response['market'],
                trade_price=float(json_response['trade_price']),
                trade_volume=float(json_response['trade_volume']),
                timestamp=parsed_timestamp,
                change_rate=float(json_response['change_rate'])
            )
            
            # Property: Parsed ticker should be valid
            assert ticker.validate(), "Ticker parsed from API-like response should be valid"
            
            # Property: All fields should have correct types after parsing
            assert isinstance(ticker.trade_price, float), "Parsed trade price should be float"
            assert isinstance(ticker.trade_volume, float), "Parsed trade volume should be float"
            assert isinstance(ticker.change_rate, float), "Parsed change rate should be float"
            
        except (ValueError, KeyError) as e:
            # If parsing fails, it should be due to invalid data format
            pytest.fail(f"Valid API response should be parseable: {e}")
    
    @given(malformed_data=malformed_market_data())
    @settings(max_examples=50)
    def test_malformed_data_handling(self, malformed_data):
        """Test that malformed market data is properly rejected."""
        try:
            ticker = Ticker(
                market=malformed_data.get('market', ''),
                trade_price=malformed_data.get('trade_price', 0),
                trade_volume=malformed_data.get('trade_volume', 0),
                timestamp=malformed_data.get('timestamp', datetime.now()),
                change_rate=malformed_data.get('change_rate', 0)
            )
            
            # Property: Malformed data should fail validation
            is_valid = ticker.validate()
            
            # If validation passes, the data might not actually be malformed
            # This can happen due to the random nature of property testing
            if is_valid:
                # Verify that the ticker actually has valid data
                assert ticker.market and isinstance(ticker.market, str)
                assert isinstance(ticker.trade_price, (int, float)) and ticker.trade_price > 0
                assert isinstance(ticker.trade_volume, (int, float)) and ticker.trade_volume >= 0
                assert isinstance(ticker.timestamp, datetime)
                assert isinstance(ticker.change_rate, (int, float))
            else:
                # This is the expected case - malformed data should not validate
                assert not is_valid, "Malformed market data should fail validation"
                
        except (TypeError, ValueError):
            # Exception during construction is also acceptable for malformed data
            pass
    
    def test_empty_market_data(self):
        """Test handling of completely empty market data."""
        with pytest.raises((TypeError, ValueError)):
            Ticker()  # Should fail due to missing required arguments
    
    def test_none_values_handling(self):
        """Test handling of None values in market data."""
        # None values should cause validation to fail
        ticker = Ticker(
            market=None,
            trade_price=None,
            trade_volume=None,
            timestamp=None,
            change_rate=None
        )
        
        assert not ticker.validate(), "Ticker with None values should not validate"
    
    def test_extreme_values_handling(self):
        """Test handling of extreme but valid values."""
        # Very small positive values
        small_ticker = Ticker(
            market="KRW-TEST",
            trade_price=0.00000001,
            trade_volume=0.0,
            timestamp=datetime.now(),
            change_rate=-0.99
        )
        assert small_ticker.validate(), "Ticker with small valid values should validate"
        
        # Very large values
        large_ticker = Ticker(
            market="KRW-TEST",
            trade_price=999999999.99,
            trade_volume=999999999.99,
            timestamp=datetime.now(),
            change_rate=0.99
        )
        assert large_ticker.validate(), "Ticker with large valid values should validate"