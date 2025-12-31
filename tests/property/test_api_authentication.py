"""Property-based tests for API authentication success.

**Feature: upbit-trading-bot, Property 1: API Authentication Success**
**Validates: Requirements 1.1**
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.api.client import UpbitAPIClient, UpbitAPIError, CredentialManager


@composite
def valid_api_credentials(draw):
    """Generate valid API credential pairs."""
    # Generate realistic access key format (UUID-like)
    access_key = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-'),
        min_size=32, max_size=40
    ))
    
    # Generate realistic secret key format (base64-like)
    secret_key = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='+/='),
        min_size=40, max_size=60
    ))
    
    # Ensure keys are not empty and have reasonable format
    assume(len(access_key.strip()) >= 32)
    assume(len(secret_key.strip()) >= 40)
    assume(access_key != secret_key)  # Keys should be different
    
    return {
        'access_key': access_key,
        'secret_key': secret_key
    }


@composite
def invalid_api_credentials(draw):
    """Generate invalid API credential pairs for negative testing."""
    invalid_type = draw(st.sampled_from([
        'empty_access_key',
        'empty_secret_key',
        'both_empty',
        'none_access_key',
        'none_secret_key',
        'both_none',
        'whitespace_only',
        'too_short_keys',
        'same_keys'
    ]))
    
    if invalid_type == 'empty_access_key':
        return {'access_key': '', 'secret_key': 'valid_secret_key_12345678901234567890'}
    elif invalid_type == 'empty_secret_key':
        return {'access_key': 'valid_access_key_12345678901234567890', 'secret_key': ''}
    elif invalid_type == 'both_empty':
        return {'access_key': '', 'secret_key': ''}
    elif invalid_type == 'none_access_key':
        return {'access_key': None, 'secret_key': 'valid_secret_key_12345678901234567890'}
    elif invalid_type == 'none_secret_key':
        return {'access_key': 'valid_access_key_12345678901234567890', 'secret_key': None}
    elif invalid_type == 'both_none':
        return {'access_key': None, 'secret_key': None}
    elif invalid_type == 'whitespace_only':
        return {'access_key': '   ', 'secret_key': '   '}
    elif invalid_type == 'too_short_keys':
        return {'access_key': 'short', 'secret_key': 'short'}
    elif invalid_type == 'same_keys':
        same_key = 'same_key_12345678901234567890'
        return {'access_key': same_key, 'secret_key': same_key}


@composite
def mock_successful_api_response(draw):
    """Generate mock successful API response for authentication test."""
    # Generate realistic account data that would be returned on successful auth
    currencies = ['KRW', 'BTC', 'ETH', 'ADA', 'DOT']
    accounts = []
    
    num_accounts = draw(st.integers(min_value=1, max_value=5))
    for _ in range(num_accounts):
        currency = draw(st.sampled_from(currencies))
        balance = draw(st.floats(min_value=0.0, max_value=1000000.0, allow_nan=False, allow_infinity=False))
        locked = draw(st.floats(min_value=0.0, max_value=balance, allow_nan=False, allow_infinity=False))
        avg_buy_price = draw(st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False))
        
        accounts.append({
            'currency': currency,
            'balance': str(balance),
            'locked': str(locked),
            'avg_buy_price': str(avg_buy_price),
            'unit_currency': 'KRW'
        })
    
    return accounts


class TestAPIAuthenticationSuccess:
    """Property-based tests for API authentication success."""
    
    @given(credentials=valid_api_credentials(), mock_response=mock_successful_api_response())
    @settings(max_examples=100)
    def test_property_1_api_authentication_success(self, credentials, mock_response):
        """
        **Feature: upbit-trading-bot, Property 1: API Authentication Success**
        **Validates: Requirements 1.1**
        
        Property: For any valid API key pair, authentication with Upbit API 
        should succeed and return valid session credentials.
        """
        # Create API client
        client = UpbitAPIClient()
        
        # Mock the HTTP response for successful authentication
        with patch.object(client, '_make_authenticated_request') as mock_request:
            # Configure mock to return successful response
            mock_response_obj = Mock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_request.return_value = mock_response_obj
            
            # Test authentication
            result = client.authenticate(
                credentials['access_key'], 
                credentials['secret_key']
            )
            
            # Property 1: Authentication should succeed for valid credentials
            assert result is True, "Authentication should succeed for valid API credentials"
            
            # Property 2: Client should store the credentials
            assert client.access_key == credentials['access_key'], "Client should store access key"
            assert client.secret_key == credentials['secret_key'], "Client should store secret key"
            
            # Property 3: Client should be marked as authenticated
            assert client.authenticated is True, "Client should be marked as authenticated"
            
            # Property 4: Authentication should make exactly one API call
            mock_request.assert_called_once_with('GET', '/v1/accounts')
            
            # Property 5: Subsequent authenticated calls should include proper headers
            # Test by making another call and checking that it uses the stored credentials
            client.get_accounts()
            assert mock_request.call_count == 2, "Subsequent calls should use stored credentials"
    
    @given(credentials=invalid_api_credentials())
    @settings(max_examples=50)
    def test_invalid_credentials_handling(self, credentials):
        """Test that invalid credentials are properly rejected."""
        client = UpbitAPIClient()
        
        # Mock the HTTP response for failed authentication
        with patch.object(client, '_make_authenticated_request') as mock_request:
            # Configure mock to return authentication failure
            mock_response_obj = Mock()
            mock_response_obj.status_code = 401
            mock_response_obj.text = "Authentication failed"
            mock_request.return_value = mock_response_obj
            
            # Test authentication with invalid credentials
            result = client.authenticate(
                credentials['access_key'], 
                credentials['secret_key']
            )
            
            # Property: Authentication should fail for invalid credentials
            assert result is False, "Authentication should fail for invalid credentials"
            
            # Property: Client should not be marked as authenticated
            assert client.authenticated is False, "Client should not be marked as authenticated"
    
    @given(credentials=valid_api_credentials())
    @settings(max_examples=30)
    def test_authentication_network_error_handling(self, credentials):
        """Test authentication behavior when network errors occur."""
        client = UpbitAPIClient()
        
        # Mock network error during authentication
        with patch.object(client, '_make_authenticated_request') as mock_request:
            mock_request.side_effect = UpbitAPIError("Network error")
            
            # Test authentication with network error
            result = client.authenticate(
                credentials['access_key'], 
                credentials['secret_key']
            )
            
            # Property: Authentication should fail gracefully on network errors
            assert result is False, "Authentication should fail gracefully on network errors"
            
            # Property: Client should not be marked as authenticated
            assert client.authenticated is False, "Client should not be marked as authenticated on network error"
    
    @given(credentials=valid_api_credentials())
    @settings(max_examples=30)
    def test_authentication_server_error_handling(self, credentials):
        """Test authentication behavior when server errors occur."""
        client = UpbitAPIClient()
        
        # Mock server error during authentication
        with patch.object(client, '_make_authenticated_request') as mock_request:
            mock_response_obj = Mock()
            mock_response_obj.status_code = 500
            mock_response_obj.text = "Internal server error"
            mock_request.return_value = mock_response_obj
            
            # Test authentication with server error
            result = client.authenticate(
                credentials['access_key'], 
                credentials['secret_key']
            )
            
            # Property: Authentication should fail on server errors
            assert result is False, "Authentication should fail on server errors"
            
            # Property: Client should not be marked as authenticated
            assert client.authenticated is False, "Client should not be marked as authenticated on server error"
    
    def test_authentication_without_credentials(self):
        """Test authentication behavior when no credentials are provided."""
        client = UpbitAPIClient()
        
        # Test authentication with None values
        result = client.authenticate(None, None)
        
        # Property: Authentication should fail without credentials
        assert result is False, "Authentication should fail without credentials"
        assert client.authenticated is False, "Client should not be marked as authenticated"
    
    def test_authentication_state_consistency(self):
        """Test that authentication state remains consistent."""
        client = UpbitAPIClient()
        
        # Initially should not be authenticated
        assert client.authenticated is False, "Client should start as not authenticated"
        
        # Mock successful authentication
        with patch.object(client, '_make_authenticated_request') as mock_request:
            mock_response_obj = Mock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = [{'currency': 'KRW', 'balance': '1000', 'locked': '0', 'avg_buy_price': '0', 'unit_currency': 'KRW'}]
            mock_request.return_value = mock_response_obj
            
            # Authenticate
            result = client.authenticate('test_access_key', 'test_secret_key')
            assert result is True
            assert client.authenticated is True
            
            # Mock failed re-authentication
            mock_response_obj.status_code = 401
            result = client.authenticate('invalid_key', 'invalid_secret')
            assert result is False
            assert client.authenticated is False, "Failed authentication should reset authenticated state"
    
    @given(credentials=valid_api_credentials())
    @settings(max_examples=20)
    def test_authentication_credentials_storage(self, credentials):
        """Test that credentials are properly stored during authentication."""
        client = UpbitAPIClient()
        
        # Mock successful authentication
        with patch.object(client, '_make_authenticated_request') as mock_request:
            mock_response_obj = Mock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = [{'currency': 'KRW', 'balance': '1000', 'locked': '0', 'avg_buy_price': '0', 'unit_currency': 'KRW'}]
            mock_request.return_value = mock_response_obj
            
            # Test authentication
            result = client.authenticate(
                credentials['access_key'], 
                credentials['secret_key']
            )
            
            # Property: Credentials should be stored exactly as provided
            assert client.access_key == credentials['access_key'], "Access key should be stored exactly as provided"
            assert client.secret_key == credentials['secret_key'], "Secret key should be stored exactly as provided"
            
            # Property: Stored credentials should not be modified
            assert isinstance(client.access_key, str), "Stored access key should remain a string"
            assert isinstance(client.secret_key, str), "Stored secret key should remain a string"
            assert len(client.access_key) == len(credentials['access_key']), "Access key length should be preserved"
            assert len(client.secret_key) == len(credentials['secret_key']), "Secret key length should be preserved"
    
    def test_multiple_authentication_attempts(self):
        """Test behavior with multiple authentication attempts."""
        client = UpbitAPIClient()
        
        with patch.object(client, '_make_authenticated_request') as mock_request:
            # First authentication succeeds
            mock_response_obj = Mock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = [{'currency': 'KRW', 'balance': '1000', 'locked': '0', 'avg_buy_price': '0', 'unit_currency': 'KRW'}]
            mock_request.return_value = mock_response_obj
            
            result1 = client.authenticate('key1', 'secret1')
            assert result1 is True
            assert client.access_key == 'key1'
            assert client.secret_key == 'secret1'
            
            # Second authentication with different credentials
            result2 = client.authenticate('key2', 'secret2')
            assert result2 is True
            assert client.access_key == 'key2', "New credentials should replace old ones"
            assert client.secret_key == 'secret2', "New credentials should replace old ones"
            
            # Property: Each authentication should make its own API call
            assert mock_request.call_count == 2, "Each authentication attempt should make an API call"