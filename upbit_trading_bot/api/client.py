"""
Upbit API Client with authentication and rate limiting.

This module provides a comprehensive client for interacting with the Upbit API,
including secure authentication, credential encryption, and robust error handling.
"""

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode, unquote

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

from ..data.models import Ticker, Order, OrderResult, OrderStatus, Position


logger = logging.getLogger(__name__)


class UpbitAPIError(Exception):
    """Custom exception for Upbit API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class RateLimiter:
    """Rate limiter with exponential backoff for API requests."""
    
    def __init__(self, max_requests_per_second: float = 10.0):
        self.max_requests_per_second = max_requests_per_second
        self.min_interval = 1.0 / max_requests_per_second
        self.last_request_time = 0.0
        self.consecutive_failures = 0
        self.max_retries = 3
    
    def wait_if_needed(self) -> None:
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def get_backoff_delay(self) -> float:
        """Calculate exponential backoff delay based on consecutive failures."""
        if self.consecutive_failures == 0:
            return 0.0
        
        # Exponential backoff: 1s, 2s, 4s, 8s, etc.
        delay = min(2 ** (self.consecutive_failures - 1), 60.0)  # Cap at 60 seconds
        return delay
    
    def record_success(self) -> None:
        """Record a successful request."""
        self.consecutive_failures = 0
    
    def record_failure(self) -> None:
        """Record a failed request."""
        self.consecutive_failures += 1
    
    def should_retry(self) -> bool:
        """Check if we should retry based on failure count."""
        return self.consecutive_failures < self.max_retries


class CredentialManager:
    """Secure credential storage and encryption manager."""
    
    def __init__(self, password: Optional[str] = None):
        """
        Initialize credential manager with optional password for encryption.
        
        Args:
            password: Password for encryption. If None, uses environment variable.
        """
        self.password = password or os.getenv('CREDENTIAL_PASSWORD', 'default_password')
        self._key = self._derive_key(self.password)
        self._cipher = Fernet(self._key)
    
    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password using PBKDF2."""
        password_bytes = password.encode()
        salt = b'upbit_trading_bot_salt'  # In production, use random salt per user
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
        return key
    
    def encrypt_credentials(self, access_key: str, secret_key: str) -> Dict[str, str]:
        """
        Encrypt API credentials.
        
        Args:
            access_key: Upbit API access key
            secret_key: Upbit API secret key
            
        Returns:
            Dict containing encrypted credentials
        """
        encrypted_access = self._cipher.encrypt(access_key.encode()).decode()
        encrypted_secret = self._cipher.encrypt(secret_key.encode()).decode()
        
        return {
            'encrypted_access_key': encrypted_access,
            'encrypted_secret_key': encrypted_secret
        }
    
    def decrypt_credentials(self, encrypted_data: Dict[str, str]) -> Dict[str, str]:
        """
        Decrypt API credentials.
        
        Args:
            encrypted_data: Dictionary containing encrypted credentials
            
        Returns:
            Dict containing decrypted credentials
        """
        try:
            access_key = self._cipher.decrypt(encrypted_data['encrypted_access_key'].encode()).decode()
            secret_key = self._cipher.decrypt(encrypted_data['encrypted_secret_key'].encode()).decode()
            
            return {
                'access_key': access_key,
                'secret_key': secret_key
            }
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            raise UpbitAPIError("Failed to decrypt credentials")


class UpbitAPIClient:
    """
    Upbit API client with authentication, rate limiting, and error handling.
    
    This client provides secure access to Upbit's REST API with proper authentication,
    rate limiting, and robust error handling mechanisms.
    """
    
    BASE_URL = "https://api.upbit.com"
    
    def __init__(self, access_key: Optional[str] = None, secret_key: Optional[str] = None):
        """
        Initialize Upbit API client.
        
        Args:
            access_key: Upbit API access key (optional, can be set later)
            secret_key: Upbit API secret key (optional, can be set later)
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.session = requests.Session()
        self.rate_limiter = RateLimiter(max_requests_per_second=10.0)
        self.credential_manager = CredentialManager()
        self.authenticated = False
        
        # Set default headers
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
    
    def authenticate(self, access_key: str, secret_key: str) -> bool:
        """
        Authenticate with Upbit API using provided credentials.
        
        Args:
            access_key: Upbit API access key
            secret_key: Upbit API secret key
            
        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            self.access_key = access_key
            self.secret_key = secret_key
            
            # Test authentication by making a simple API call
            response = self._make_authenticated_request('GET', '/v1/accounts')
            
            if response.status_code == 200:
                self.authenticated = True
                logger.info("Successfully authenticated with Upbit API")
                return True
            else:
                self.authenticated = False
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.authenticated = False
            logger.error(f"Authentication error: {e}")
            return False
    
    def _generate_auth_header(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> str:
        """
        Generate JWT authentication header for Upbit API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Request parameters
            data: Request body data
            
        Returns:
            str: JWT token for Authorization header
        """
        import jwt
        
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
        }
        
        # POST 요청의 경우 data를 query_hash에 포함
        if method.upper() == 'POST' and data:
            query_string = unquote(urlencode(data, doseq=True)).encode("utf-8")
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
        # GET/DELETE 요청의 경우 params를 query_hash에 포함
        elif params:
            query_string = unquote(urlencode(params, doseq=True)).encode("utf-8")
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
        
        jwt_token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return f'Bearer {jwt_token}'
    
    def _make_authenticated_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                                  data: Optional[Dict] = None) -> requests.Response:
        """
        Make authenticated request to Upbit API with rate limiting and retry logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            
        Returns:
            requests.Response: API response
        """
        if not self.access_key or not self.secret_key:
            raise UpbitAPIError("API credentials not set")
        
        url = f"{self.BASE_URL}{endpoint}"
        
        while True:
            self.rate_limiter.wait_if_needed()
            
            try:
                # Generate authentication header
                auth_header = self._generate_auth_header(method, endpoint, params, data)
                headers = {'Authorization': auth_header}
                
                # Make request
                if method.upper() == 'GET':
                    response = self.session.get(url, params=params, headers=headers)
                elif method.upper() == 'POST':
                    response = self.session.post(url, json=data, headers=headers)
                elif method.upper() == 'DELETE':
                    response = self.session.delete(url, params=params, headers=headers)
                else:
                    raise UpbitAPIError(f"Unsupported HTTP method: {method}")
                
                # Handle rate limiting
                if response.status_code == 429:
                    self.rate_limiter.record_failure()
                    if self.rate_limiter.should_retry():
                        backoff_delay = self.rate_limiter.get_backoff_delay()
                        logger.warning(f"Rate limit exceeded, backing off for {backoff_delay}s")
                        time.sleep(backoff_delay)
                        continue
                    else:
                        raise UpbitAPIError("Rate limit exceeded, max retries reached", 429)
                
                # Handle other errors
                if response.status_code >= 400:
                    error_data = response.json() if response.content else {}
                    error_message = error_data.get('error', {}).get('message', 'Unknown error')
                    error_code = error_data.get('error', {}).get('name', 'UNKNOWN_ERROR')
                    
                    self.rate_limiter.record_failure()
                    if self.rate_limiter.should_retry() and response.status_code >= 500:
                        backoff_delay = self.rate_limiter.get_backoff_delay()
                        logger.warning(f"Server error {response.status_code}, retrying in {backoff_delay}s")
                        time.sleep(backoff_delay)
                        continue
                    else:
                        raise UpbitAPIError(error_message, response.status_code, error_code)
                
                # Success
                self.rate_limiter.record_success()
                return response
                
            except requests.RequestException as e:
                self.rate_limiter.record_failure()
                if self.rate_limiter.should_retry():
                    backoff_delay = self.rate_limiter.get_backoff_delay()
                    logger.warning(f"Request failed: {e}, retrying in {backoff_delay}s")
                    time.sleep(backoff_delay)
                    continue
                else:
                    raise UpbitAPIError(f"Request failed: {e}")
    
    def _make_public_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> requests.Response:
        """
        Make public (non-authenticated) request to Upbit API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            requests.Response: API response
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        while True:
            self.rate_limiter.wait_if_needed()
            
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url, params=params)
                else:
                    raise UpbitAPIError(f"Unsupported HTTP method for public request: {method}")
                
                # Handle rate limiting
                if response.status_code == 429:
                    self.rate_limiter.record_failure()
                    if self.rate_limiter.should_retry():
                        backoff_delay = self.rate_limiter.get_backoff_delay()
                        logger.warning(f"Rate limit exceeded, backing off for {backoff_delay}s")
                        time.sleep(backoff_delay)
                        continue
                    else:
                        raise UpbitAPIError("Rate limit exceeded, max retries reached", 429)
                
                # Handle errors
                if response.status_code >= 400:
                    self.rate_limiter.record_failure()
                    if self.rate_limiter.should_retry() and response.status_code >= 500:
                        backoff_delay = self.rate_limiter.get_backoff_delay()
                        logger.warning(f"Server error {response.status_code}, retrying in {backoff_delay}s")
                        time.sleep(backoff_delay)
                        continue
                    else:
                        raise UpbitAPIError(f"Request failed with status {response.status_code}")
                
                # Success
                self.rate_limiter.record_success()
                return response
                
            except requests.RequestException as e:
                self.rate_limiter.record_failure()
                if self.rate_limiter.should_retry():
                    backoff_delay = self.rate_limiter.get_backoff_delay()
                    logger.warning(f"Request failed: {e}, retrying in {backoff_delay}s")
                    time.sleep(backoff_delay)
                    continue
                else:
                    raise UpbitAPIError(f"Request failed: {e}")
    
    def get_accounts(self) -> List[Position]:
        """
        Get account information (balances).
        
        Returns:
            List[Position]: List of account positions
        """
        response = self._make_authenticated_request('GET', '/v1/accounts')
        accounts_data = response.json()
        
        positions = []
        for account in accounts_data:
            position = Position(
                market=account['currency'],
                avg_buy_price=float(account.get('avg_buy_price', 0)),
                balance=float(account['balance']),
                locked=float(account['locked']),
                unit_currency=account['unit_currency']
            )
            positions.append(position)
        
        return positions
    
    def get_ticker(self, market: str) -> Ticker:
        """
        Get current ticker information for a market.
        
        Args:
            market: Market identifier (e.g., 'KRW-BTC')
            
        Returns:
            Ticker: Current ticker data
        """
        params = {'markets': market}
        response = self._make_public_request('GET', '/v1/ticker', params)
        ticker_data = response.json()[0]  # API returns list with single item
        
        ticker = Ticker(
            market=ticker_data['market'],
            trade_price=float(ticker_data['trade_price']),
            trade_volume=float(ticker_data['acc_trade_volume_24h']),
            timestamp=datetime.now(),  # Upbit doesn't provide timestamp in ticker
            change_rate=float(ticker_data['change_rate'])
        )
        
        return ticker
    
    def place_order(self, order: Order) -> OrderResult:
        """
        Place a trading order.
        
        Args:
            order: Order to place
            
        Returns:
            OrderResult: Result of order placement
        """
        if not order.validate():
            raise UpbitAPIError("Invalid order data")
        
        data = {
            'market': order.market,
            'side': order.side,
            'ord_type': order.ord_type
        }
        
        # 주문 타입에 따라 price 또는 volume 설정
        if order.ord_type == 'price':  # 시장가 매수
            data['price'] = str(order.price)
        elif order.ord_type == 'market':  # 시장가 매도
            data['volume'] = str(order.volume)
        elif order.ord_type == 'limit':  # 지정가
            data['price'] = str(order.price)
            data['volume'] = str(order.volume)
        
        if order.identifier:
            data['identifier'] = order.identifier
        
        response = self._make_authenticated_request('POST', '/v1/orders', data=data)
        result_data = response.json()
        
        order_result = OrderResult(
            order_id=result_data['uuid'],
            market=result_data['market'],
            side=result_data['side'],
            ord_type=result_data['ord_type'],
            price=float(result_data['price']) if result_data.get('price') else None,
            volume=float(result_data['volume']) if result_data.get('volume') else None,
            remaining_volume=float(result_data['remaining_volume']) if result_data.get('remaining_volume') else 0,
            reserved_fee=float(result_data['reserved_fee']),
            remaining_fee=float(result_data['remaining_fee']),
            paid_fee=float(result_data['paid_fee']),
            locked=float(result_data['locked']),
            executed_volume=float(result_data['executed_volume']),
            trades_count=int(result_data['trades_count'])
        )
        
        return order_result
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: UUID of the order to cancel
            
        Returns:
            bool: True if cancellation successful
        """
        params = {'uuid': order_id}
        
        try:
            response = self._make_authenticated_request('DELETE', '/v1/order', params=params)
            return response.status_code == 200
        except UpbitAPIError:
            return False
    
    def get_order_status(self, order_id: str) -> OrderStatus:
        """
        Get status of a specific order.
        
        Args:
            order_id: UUID of the order
            
        Returns:
            OrderStatus: Current order status
        """
        params = {'uuid': order_id}
        response = self._make_authenticated_request('GET', '/v1/order', params=params)
        order_data = response.json()
        
        order_status = OrderStatus(
            order_id=order_data['uuid'],
            market=order_data['market'],
            side=order_data['side'],
            ord_type=order_data['ord_type'],
            price=float(order_data['price']) if order_data.get('price') else None,
            state=order_data['state'],
            volume=float(order_data['volume']) if order_data.get('volume') else None,
            remaining_volume=float(order_data['remaining_volume']) if order_data.get('remaining_volume') else None,
            executed_volume=float(order_data['executed_volume']) if order_data.get('executed_volume') else 0.0,
            created_at=datetime.fromisoformat(order_data['created_at'].replace('Z', '+00:00'))
        )
        
        return order_status
    
    def get_markets(self) -> List[Dict[str, Any]]:
        """
        Get list of available markets.
        
        Returns:
            List[Dict]: List of market information
        """
        response = self._make_public_request('GET', '/v1/market/all')
        return response.json()
    
    def store_encrypted_credentials(self, access_key: str, secret_key: str, 
                                  storage_path: str = 'credentials.json') -> None:
        """
        Store encrypted credentials to file.
        
        Args:
            access_key: API access key
            secret_key: API secret key
            storage_path: Path to store encrypted credentials
        """
        encrypted_data = self.credential_manager.encrypt_credentials(access_key, secret_key)
        
        with open(storage_path, 'w') as f:
            json.dump(encrypted_data, f)
        
        logger.info(f"Encrypted credentials stored to {storage_path}")
    
    def load_encrypted_credentials(self, storage_path: str = 'credentials.json') -> bool:
        """
        Load and decrypt credentials from file.
        
        Args:
            storage_path: Path to encrypted credentials file
            
        Returns:
            bool: True if credentials loaded successfully
        """
        try:
            with open(storage_path, 'r') as f:
                encrypted_data = json.load(f)
            
            credentials = self.credential_manager.decrypt_credentials(encrypted_data)
            self.access_key = credentials['access_key']
            self.secret_key = credentials['secret_key']
            
            logger.info(f"Credentials loaded from {storage_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return False