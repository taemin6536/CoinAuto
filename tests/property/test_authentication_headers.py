"""Property-based tests for authentication header consistency.

**Feature: upbit-trading-bot, Property 3: Authentication Header Consistency**
**Validates: Requirements 1.5**
"""

import pytest
import jwt
import hashlib
import uuid
from urllib.parse import urlencode, unquote
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.api.client import UpbitAPIClient, UpbitAPIError


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
def api_request_data(draw):
    """Generate API request data including method, endpoint, and parameters."""
    method = draw(st.sampled_from(['GET', 'POST', 'DELETE']))
    
    # Generate realistic API endpoints
    endpoints = [
        '/v1/accounts',
        '/v1/orders',
        '/v1/order',
        '/v1/ticker',
        '/v1/market/all',
        '/v1/candles/minutes/1',
        '/v1/candles/days',
        '/v1/orderbook'
    ]
    endpoint = draw(st.sampled_from(endpoints))
    
    # Generate parameters (can be None or a dictionary)
    has_params = draw(st.booleans())
    if has_params:
        # Generate realistic parameter names and values
        param_names = ['market', 'side', 'volume', 'price', 'ord_type', 'uuid', 'count', 'to', 'from']
        param_values = st.one_of(
            st.text(min_size=1, max_size=20),
            st.integers(min_value=1, max_value=1000).map(str),
            st.floats(min_value=0.1, max_value=1000000.0, allow_nan=False, allow_infinity=False).map(str)
        )
        
        num_params = draw(st.integers(min_value=1, max_value=4))
        params = {}
        for _ in range(num_params):
            param_name = draw(st.sampled_from(param_names))
            param_value = draw(param_values)
            params[param_name] = param_value
        
        # Ensure we don't have empty parameter values
        params = {k: v for k, v in params.items() if v and len(str(v).strip()) > 0}
        if not params:
            params = None
    else:
        params = None
    
    return {
        'method': method,
        'endpoint': endpoint,
        'params': params
    }


@composite
def request_data_with_body(draw):
    """Generate API request data that includes request body for POST requests."""
    request_data = draw(api_request_data())
    
    # Add request body for POST requests
    if request_data['method'] == 'POST':
        has_body = draw(st.booleans())
        if has_body:
            # Generate realistic request body data
            body_data = {}
            possible_fields = ['market', 'side', 'volume', 'price', 'ord_type', 'identifier']
            num_fields = draw(st.integers(min_value=1, max_value=4))
            
            for _ in range(num_fields):
                field_name = draw(st.sampled_from(possible_fields))
                field_value = draw(st.one_of(
                    st.text(min_size=1, max_size=20),
                    st.integers(min_value=1, max_value=1000),
                    st.floats(min_value=0.1, max_value=1000000.0, allow_nan=False, allow_infinity=False)
                ))
                body_data[field_name] = field_value
            
            request_data['data'] = body_data
        else:
            request_data['data'] = None
    else:
        request_data['data'] = None
    
    return request_data


class TestAuthenticationHeaderConsistency:
    """Property-based tests for authentication header consistency."""
    
    @given(credentials=valid_api_credentials(), request_data=api_request_data())
    @settings(max_examples=100)
    def test_property_3_authentication_header_consistency(self, credentials, request_data):
        """
        **Feature: upbit-trading-bot, Property 3: Authentication Header Consistency**
        **Validates: Requirements 1.5**
        
        Property: For any API request, the request should include properly formatted 
        authentication headers with valid signatures.
        """
        # Create API client with credentials
        client = UpbitAPIClient(
            access_key=credentials['access_key'],
            secret_key=credentials['secret_key']
        )
        
        # Generate authentication header
        auth_header = client._generate_auth_header(
            request_data['method'],
            request_data['endpoint'],
            request_data['params']
        )
        
        # Property 1: Authentication header should be properly formatted
        assert auth_header.startswith('Bearer '), "Authentication header should start with 'Bearer '"
        
        # Extract JWT token from header
        jwt_token = auth_header.replace('Bearer ', '')
        assert len(jwt_token) > 0, "JWT token should not be empty"
        
        # Property 2: JWT token should be valid and decodable
        try:
            # Decode JWT token (without verification for testing purposes)
            decoded_payload = jwt.decode(jwt_token, options={"verify_signature": False})
        except jwt.InvalidTokenError:
            pytest.fail("JWT token should be valid and decodable")
        
        # Property 3: JWT payload should contain required fields
        assert 'access_key' in decoded_payload, "JWT payload should contain access_key"
        assert 'nonce' in decoded_payload, "JWT payload should contain nonce"
        
        # Property 4: Access key in JWT should match the client's access key
        assert decoded_payload['access_key'] == credentials['access_key'], "JWT access_key should match client's access_key"
        
        # Property 5: Nonce should be a valid UUID string
        nonce = decoded_payload['nonce']
        try:
            uuid.UUID(nonce)
        except ValueError:
            pytest.fail("Nonce should be a valid UUID string")
        
        # Property 6: If parameters exist, JWT should include query hash
        if request_data['params']:
            assert 'query_hash' in decoded_payload, "JWT should contain query_hash when parameters exist"
            assert 'query_hash_alg' in decoded_payload, "JWT should contain query_hash_alg when parameters exist"
            assert decoded_payload['query_hash_alg'] == 'SHA512', "Query hash algorithm should be SHA512"
            
            # Verify query hash is correctly calculated
            query_string = unquote(urlencode(request_data['params'], doseq=True)).encode("utf-8")
            expected_hash = hashlib.sha512(query_string).hexdigest()
            assert decoded_payload['query_hash'] == expected_hash, "Query hash should be correctly calculated"
        else:
            # Property 7: If no parameters, JWT should not include query hash
            assert 'query_hash' not in decoded_payload, "JWT should not contain query_hash when no parameters"
            assert 'query_hash_alg' not in decoded_payload, "JWT should not contain query_hash_alg when no parameters"
        
        # Property 8: JWT should be properly signed with the secret key
        try:
            jwt.decode(jwt_token, credentials['secret_key'], algorithms=['HS256'])
        except jwt.InvalidSignatureError:
            pytest.fail("JWT token should be properly signed with the secret key")
        except jwt.InvalidTokenError as e:
            pytest.fail(f"JWT token should be valid: {e}")
    
    @given(credentials=valid_api_credentials(), request_data=api_request_data())
    @settings(max_examples=50)
    def test_authentication_header_uniqueness(self, credentials, request_data):
        """Test that each authentication header contains a unique nonce."""
        client = UpbitAPIClient(
            access_key=credentials['access_key'],
            secret_key=credentials['secret_key']
        )
        
        # Generate multiple authentication headers for the same request
        headers = []
        for _ in range(5):
            auth_header = client._generate_auth_header(
                request_data['method'],
                request_data['endpoint'],
                request_data['params']
            )
            headers.append(auth_header)
        
        # Extract nonces from all headers
        nonces = []
        for header in headers:
            jwt_token = header.replace('Bearer ', '')
            decoded_payload = jwt.decode(jwt_token, options={"verify_signature": False})
            nonces.append(decoded_payload['nonce'])
        
        # Property: Each authentication header should have a unique nonce
        assert len(set(nonces)) == len(nonces), "Each authentication header should have a unique nonce"
    
    @given(credentials=valid_api_credentials())
    @settings(max_examples=30)
    def test_authentication_header_with_various_parameter_types(self, credentials):
        """Test authentication header generation with various parameter types."""
        client = UpbitAPIClient(
            access_key=credentials['access_key'],
            secret_key=credentials['secret_key']
        )
        
        # Test with different parameter scenarios
        test_cases = [
            # No parameters
            {'params': None},
            # Single parameter
            {'params': {'market': 'KRW-BTC'}},
            # Multiple parameters
            {'params': {'market': 'KRW-BTC', 'side': 'bid', 'volume': '0.1'}},
            # Parameters with special characters
            {'params': {'identifier': 'test-order-123', 'market': 'KRW-ETH'}},
            # Numeric parameters
            {'params': {'count': '100', 'price': '50000000'}},
            # Boolean-like parameters
            {'params': {'is_buy_order': 'true', 'market': 'KRW-ADA'}},
        ]
        
        for test_case in test_cases:
            auth_header = client._generate_auth_header('GET', '/v1/test', test_case['params'])
            
            # Property: All parameter types should produce valid authentication headers
            assert auth_header.startswith('Bearer '), f"Header should be valid for params: {test_case['params']}"
            
            jwt_token = auth_header.replace('Bearer ', '')
            decoded_payload = jwt.decode(jwt_token, options={"verify_signature": False})
            
            # Verify payload structure based on parameters
            if test_case['params']:
                assert 'query_hash' in decoded_payload, f"Should have query_hash for params: {test_case['params']}"
                assert 'query_hash_alg' in decoded_payload, f"Should have query_hash_alg for params: {test_case['params']}"
            else:
                assert 'query_hash' not in decoded_payload, "Should not have query_hash for no params"
                assert 'query_hash_alg' not in decoded_payload, "Should not have query_hash_alg for no params"
    
    @given(credentials=valid_api_credentials(), request_data=request_data_with_body())
    @settings(max_examples=50)
    def test_authentication_header_with_request_body(self, credentials, request_data):
        """Test that authentication headers are consistent regardless of request body."""
        client = UpbitAPIClient(
            access_key=credentials['access_key'],
            secret_key=credentials['secret_key']
        )
        
        # Generate authentication header (body should not affect header generation)
        auth_header = client._generate_auth_header(
            request_data['method'],
            request_data['endpoint'],
            request_data['params']
        )
        
        # Property: Authentication header should be valid regardless of request body
        assert auth_header.startswith('Bearer '), "Authentication header should be valid with request body"
        
        jwt_token = auth_header.replace('Bearer ', '')
        decoded_payload = jwt.decode(jwt_token, options={"verify_signature": False})
        
        # Property: JWT payload should not be affected by request body
        assert 'access_key' in decoded_payload, "JWT should contain access_key regardless of request body"
        assert 'nonce' in decoded_payload, "JWT should contain nonce regardless of request body"
        assert decoded_payload['access_key'] == credentials['access_key'], "Access key should be correct regardless of request body"
    
    def test_authentication_header_without_credentials(self):
        """Test authentication header generation behavior without credentials."""
        client = UpbitAPIClient()  # No credentials provided
        
        # Property: Should handle missing credentials gracefully
        with pytest.raises((AttributeError, TypeError, UpbitAPIError)):
            client._generate_auth_header('GET', '/v1/accounts', None)
    
    @given(credentials=valid_api_credentials())
    @settings(max_examples=20)
    def test_authentication_header_algorithm_consistency(self, credentials):
        """Test that authentication headers consistently use HS256 algorithm."""
        client = UpbitAPIClient(
            access_key=credentials['access_key'],
            secret_key=credentials['secret_key']
        )
        
        auth_header = client._generate_auth_header('GET', '/v1/accounts', None)
        jwt_token = auth_header.replace('Bearer ', '')
        
        # Property: JWT should use HS256 algorithm
        try:
            # This should succeed with HS256
            jwt.decode(jwt_token, credentials['secret_key'], algorithms=['HS256'])
        except jwt.InvalidTokenError:
            pytest.fail("JWT should be decodable with HS256 algorithm")
        
        # Property: JWT should not be decodable with other algorithms
        with pytest.raises((jwt.InvalidSignatureError, jwt.InvalidAlgorithmError)):
            jwt.decode(jwt_token, credentials['secret_key'], algorithms=['HS512'])
    
    @given(credentials=valid_api_credentials(), request_data=api_request_data())
    @settings(max_examples=30)
    def test_authentication_header_format_consistency(self, credentials, request_data):
        """Test that authentication headers maintain consistent format."""
        client = UpbitAPIClient(
            access_key=credentials['access_key'],
            secret_key=credentials['secret_key']
        )
        
        auth_header = client._generate_auth_header(
            request_data['method'],
            request_data['endpoint'],
            request_data['params']
        )
        
        # Property: Header should always start with "Bearer " (with space)
        assert auth_header.startswith('Bearer '), "Header should start with 'Bearer ' (with space)"
        
        # Property: Header should not have extra whitespace
        assert auth_header == auth_header.strip(), "Header should not have leading/trailing whitespace"
        
        # Property: JWT token part should not contain spaces
        jwt_token = auth_header.replace('Bearer ', '')
        assert ' ' not in jwt_token, "JWT token should not contain spaces"
        
        # Property: JWT token should have proper structure (header.payload.signature)
        jwt_parts = jwt_token.split('.')
        assert len(jwt_parts) == 3, "JWT token should have exactly 3 parts separated by dots"
        
        # Each part should be non-empty
        for i, part in enumerate(jwt_parts):
            assert len(part) > 0, f"JWT part {i} should not be empty"
    
    @given(credentials=valid_api_credentials())
    @settings(max_examples=20)
    def test_authentication_header_parameter_encoding(self, credentials):
        """Test authentication header generation with various parameter encodings."""
        client = UpbitAPIClient(
            access_key=credentials['access_key'],
            secret_key=credentials['secret_key']
        )
        
        # Test parameters that require URL encoding
        test_params = [
            {'market': 'KRW-BTC', 'identifier': 'order with spaces'},
            {'search': 'test&value=123'},
            {'data': 'value+with+plus'},
            {'special': 'chars!@#$%'},
            {'unicode': 'test한글'},
        ]
        
        for params in test_params:
            auth_header = client._generate_auth_header('GET', '/v1/test', params)
            
            # Property: Should generate valid header for all parameter encodings
            assert auth_header.startswith('Bearer '), f"Should generate valid header for params: {params}"
            
            jwt_token = auth_header.replace('Bearer ', '')
            decoded_payload = jwt.decode(jwt_token, options={"verify_signature": False})
            
            # Property: Query hash should be present and valid
            assert 'query_hash' in decoded_payload, f"Should have query_hash for params: {params}"
            assert len(decoded_payload['query_hash']) == 128, "SHA512 hash should be 128 characters long"
            
            # Verify hash calculation
            query_string = unquote(urlencode(params, doseq=True)).encode("utf-8")
            expected_hash = hashlib.sha512(query_string).hexdigest()
            assert decoded_payload['query_hash'] == expected_hash, f"Query hash should be correct for params: {params}"