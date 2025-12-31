"""
OrderManager 단위 테스트.

주문 관리 시스템의 핵심 기능들을 테스트합니다.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from decimal import Decimal

from upbit_trading_bot.order.manager import OrderManager, OrderValidationResult
from upbit_trading_bot.data.models import (
    Order, OrderResult, OrderStatus, TradingSignal, Position
)
from upbit_trading_bot.api.client import UpbitAPIClient, UpbitAPIError


class TestOrderManager:
    """OrderManager 클래스 테스트."""
    
    @pytest.fixture
    def mock_api_client(self):
        """Mock API 클라이언트 생성."""
        return Mock(spec=UpbitAPIClient)
    
    @pytest.fixture
    def order_manager(self, mock_api_client):
        """OrderManager 인스턴스 생성."""
        with patch('upbit_trading_bot.order.manager.get_db_manager'):
            return OrderManager(mock_api_client, max_retries=3)
    
    @pytest.fixture
    def sample_trading_signal(self):
        """샘플 트레이딩 신호 생성."""
        return TradingSignal(
            market='KRW-BTC',
            action='buy',
            confidence=0.9,
            price=50000000.0,
            volume=0.001,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
    
    @pytest.fixture
    def sample_order(self):
        """샘플 주문 생성."""
        return Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            volume=0.001,
            identifier='test_order_123'
        )
    
    @pytest.fixture
    def sample_positions(self):
        """샘플 포지션 목록 생성."""
        return [
            Position(
                market='KRW',
                avg_buy_price=0.0,
                balance=1000000.0,
                locked=0.0,
                unit_currency='KRW'
            ),
            Position(
                market='BTC',
                avg_buy_price=45000000.0,
                balance=0.002,
                locked=0.0,
                unit_currency='KRW'
            )
        ]
    
    def test_order_manager_initialization(self, mock_api_client):
        """OrderManager 초기화 테스트."""
        with patch('upbit_trading_bot.order.manager.get_db_manager'):
            manager = OrderManager(mock_api_client, max_retries=5)
            
            assert manager.api_client == mock_api_client
            assert manager.max_retries == 5
            assert manager.active_orders == {}
            assert len(manager.retry_delays) == 3
    
    def test_create_order_from_buy_signal(self, order_manager, sample_trading_signal):
        """매수 신호로부터 주문 생성 테스트."""
        # 매수 신호 (높은 신뢰도 - 시장가)
        signal = sample_trading_signal
        signal.confidence = 0.9
        
        order = order_manager.create_order(signal)
        
        assert order is not None
        assert order.market == 'KRW-BTC'
        assert order.side == 'bid'
        assert order.ord_type == 'market'  # 높은 신뢰도로 시장가
        assert order.price is None
        assert order.volume == 0.001
        assert 'test_strategy' in order.identifier
    
    def test_create_order_from_sell_signal(self, order_manager):
        """매도 신호로부터 주문 생성 테스트."""
        signal = TradingSignal(
            market='KRW-BTC',
            action='sell',
            confidence=0.7,  # 낮은 신뢰도 - 지정가
            price=50000000.0,
            volume=0.001,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
        
        order = order_manager.create_order(signal)
        
        assert order is not None
        assert order.market == 'KRW-BTC'
        assert order.side == 'ask'
        assert order.ord_type == 'limit'  # 낮은 신뢰도로 지정가
        assert order.price == 50000000.0
        assert order.volume == 0.001
    
    def test_create_order_invalid_signal(self, order_manager):
        """유효하지 않은 신호로 주문 생성 테스트."""
        invalid_signal = TradingSignal(
            market='',  # 빈 마켓
            action='buy',
            confidence=0.9,
            price=50000000.0,
            volume=0.001,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
        
        order = order_manager.create_order(invalid_signal)
        assert order is None
    
    def test_validate_order_buy_sufficient_balance(self, order_manager, sample_order, sample_positions):
        """매수 주문 잔고 충분 검증 테스트."""
        order_manager.api_client.get_accounts.return_value = sample_positions
        
        # 지정가 매수 주문 (50,000,000 * 0.001 = 50,000 KRW 필요)
        buy_order = sample_order
        buy_order.side = 'bid'
        buy_order.ord_type = 'limit'
        buy_order.price = 50000000.0
        buy_order.volume = 0.001
        
        result = order_manager.validate_order(buy_order)
        
        assert result.is_valid is True
        assert result.error_message is None
    
    def test_validate_order_buy_insufficient_balance(self, order_manager, sample_order, sample_positions):
        """매수 주문 잔고 부족 검증 테스트."""
        order_manager.api_client.get_accounts.return_value = sample_positions
        
        # 지정가 매수 주문 (50,000,000 * 0.1 = 5,000,000 KRW 필요, 하지만 잔고는 1,000,000)
        buy_order = sample_order
        buy_order.side = 'bid'
        buy_order.ord_type = 'limit'
        buy_order.price = 50000000.0
        buy_order.volume = 0.1  # 큰 수량
        
        result = order_manager.validate_order(buy_order)
        
        assert result.is_valid is False
        assert "잔고가 부족합니다" in result.error_message
        assert result.required_balance == 5000000.0
        assert result.available_balance == 1000000.0
    
    def test_validate_order_sell_sufficient_balance(self, order_manager, sample_order, sample_positions):
        """매도 주문 잔고 충분 검증 테스트."""
        order_manager.api_client.get_accounts.return_value = sample_positions
        
        # 매도 주문 (0.001 BTC 매도, 잔고는 0.002 BTC)
        sell_order = sample_order
        sell_order.side = 'ask'
        sell_order.volume = 0.001
        
        result = order_manager.validate_order(sell_order)
        
        assert result.is_valid is True
        assert result.error_message is None
    
    def test_validate_order_sell_insufficient_balance(self, order_manager, sample_order, sample_positions):
        """매도 주문 잔고 부족 검증 테스트."""
        order_manager.api_client.get_accounts.return_value = sample_positions
        
        # 매도 주문 (0.01 BTC 매도, 하지만 잔고는 0.002 BTC)
        sell_order = sample_order
        sell_order.side = 'ask'
        sell_order.volume = 0.01  # 큰 수량
        
        result = order_manager.validate_order(sell_order)
        
        assert result.is_valid is False
        assert "매도할 코인이 부족합니다" in result.error_message
        assert result.required_balance == 0.01
        assert result.available_balance == 0.002
    
    def test_execute_order_success(self, order_manager, sample_order):
        """주문 실행 성공 테스트."""
        # Mock 설정
        order_manager.api_client.get_accounts.return_value = [
            Position(market='KRW', avg_buy_price=0.0, balance=1000000.0, locked=0.0, unit_currency='KRW')
        ]
        
        order_result = OrderResult(
            order_id='test_order_id',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            volume=0.001,
            remaining_volume=0.001,
            reserved_fee=125.0,
            remaining_fee=125.0,
            paid_fee=0.0,
            locked=50125.0,
            executed_volume=0.0,
            trades_count=0
        )
        
        order_manager.api_client.place_order.return_value = order_result
        order_manager.db_manager = Mock()
        
        result = order_manager.execute_order(sample_order)
        
        assert result is not None
        assert result.order_id == 'test_order_id'
        assert 'test_order_id' in order_manager.active_orders
        order_manager.api_client.place_order.assert_called_once_with(sample_order)
    
    def test_execute_order_validation_failure(self, order_manager, sample_order):
        """주문 실행 검증 실패 테스트."""
        # 잔고 부족 상황 설정
        order_manager.api_client.get_accounts.return_value = [
            Position(market='KRW', avg_buy_price=0.0, balance=1000.0, locked=0.0, unit_currency='KRW')
        ]
        
        result = order_manager.execute_order(sample_order)
        
        assert result is None
        order_manager.api_client.place_order.assert_not_called()
    
    def test_execute_order_api_error_with_retry(self, order_manager, sample_order):
        """주문 실행 API 오류 및 재시도 테스트."""
        # Mock 설정
        order_manager.api_client.get_accounts.return_value = [
            Position(market='KRW', avg_buy_price=0.0, balance=1000000.0, locked=0.0, unit_currency='KRW')
        ]
        
        # 처음 두 번은 실패, 세 번째는 성공
        order_result = OrderResult(
            order_id='test_order_id',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            volume=0.001,
            remaining_volume=0.001,
            reserved_fee=125.0,
            remaining_fee=125.0,
            paid_fee=0.0,
            locked=50125.0,
            executed_volume=0.0,
            trades_count=0
        )
        
        order_manager.api_client.place_order.side_effect = [
            UpbitAPIError("Rate limit exceeded", 429),
            UpbitAPIError("Server error", 500),
            order_result
        ]
        order_manager.db_manager = Mock()
        
        with patch('time.sleep'):  # 실제 대기 시간 제거
            result = order_manager.execute_order(sample_order)
        
        assert result is not None
        assert result.order_id == 'test_order_id'
        assert order_manager.api_client.place_order.call_count == 3
    
    def test_execute_order_max_retries_exceeded(self, order_manager, sample_order):
        """주문 실행 최대 재시도 초과 테스트."""
        # Mock 설정
        order_manager.api_client.get_accounts.return_value = [
            Position(market='KRW', avg_buy_price=0.0, balance=1000000.0, locked=0.0, unit_currency='KRW')
        ]
        
        # 모든 시도에서 실패
        order_manager.api_client.place_order.side_effect = UpbitAPIError("Server error", 500)
        
        with patch('time.sleep'):  # 실제 대기 시간 제거
            result = order_manager.execute_order(sample_order)
        
        assert result is None
        assert order_manager.api_client.place_order.call_count == 4  # 최초 + 3번 재시도
    
    def test_cancel_order_success(self, order_manager):
        """주문 취소 성공 테스트."""
        # 활성 주문 추가
        order_status = OrderStatus(
            order_id='test_order_id',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            state='wait',
            volume=0.001,
            remaining_volume=0.001,
            executed_volume=0.0,
            created_at=datetime.now()
        )
        order_manager.active_orders['test_order_id'] = order_status
        
        order_manager.api_client.cancel_order.return_value = True
        order_manager.db_manager = Mock()
        
        result = order_manager.cancel_order('test_order_id')
        
        assert result is True
        assert order_manager.active_orders['test_order_id'].state == 'cancel'
        order_manager.api_client.cancel_order.assert_called_once_with('test_order_id')
    
    def test_cancel_order_failure(self, order_manager):
        """주문 취소 실패 테스트."""
        order_manager.api_client.cancel_order.return_value = False
        
        result = order_manager.cancel_order('test_order_id')
        
        assert result is False
        order_manager.api_client.cancel_order.assert_called_once_with('test_order_id')
    
    def test_track_orders_status_update(self, order_manager):
        """주문 상태 추적 및 업데이트 테스트."""
        # 활성 주문 추가
        cached_status = OrderStatus(
            order_id='test_order_id',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            state='wait',
            volume=0.001,
            remaining_volume=0.001,
            executed_volume=0.0,
            created_at=datetime.now()
        )
        order_manager.active_orders['test_order_id'] = cached_status
        
        # API에서 업데이트된 상태 반환
        updated_status = OrderStatus(
            order_id='test_order_id',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            state='done',  # 상태 변경
            volume=0.001,
            remaining_volume=0.0,
            executed_volume=0.001,
            created_at=datetime.now()
        )
        
        order_manager.api_client.get_order_status.return_value = updated_status
        order_manager.db_manager = Mock()
        
        orders = order_manager.track_orders()
        
        assert len(orders) == 1
        assert orders[0].state == 'done'
        assert 'test_order_id' not in order_manager.active_orders  # 완료된 주문은 제거
    
    def test_get_order_status_from_cache(self, order_manager):
        """캐시에서 주문 상태 조회 테스트."""
        order_status = OrderStatus(
            order_id='test_order_id',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            state='wait',
            volume=0.001,
            remaining_volume=0.001,
            executed_volume=0.0,
            created_at=datetime.now()
        )
        order_manager.active_orders['test_order_id'] = order_status
        
        result = order_manager.get_order_status('test_order_id')
        
        assert result == order_status
        order_manager.api_client.get_order_status.assert_not_called()
    
    def test_get_order_status_from_api(self, order_manager):
        """API에서 주문 상태 조회 테스트."""
        order_status = OrderStatus(
            order_id='test_order_id',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            state='done',
            volume=0.001,
            remaining_volume=0.0,
            executed_volume=0.001,
            created_at=datetime.now()
        )
        
        order_manager.api_client.get_order_status.return_value = order_status
        
        result = order_manager.get_order_status('test_order_id')
        
        assert result == order_status
        order_manager.api_client.get_order_status.assert_called_once_with('test_order_id')
    
    def test_get_active_orders(self, order_manager):
        """활성 주문 목록 조회 테스트."""
        order_status1 = OrderStatus(
            order_id='order1',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            state='wait',
            volume=0.001,
            remaining_volume=0.001,
            executed_volume=0.0,
            created_at=datetime.now()
        )
        
        order_status2 = OrderStatus(
            order_id='order2',
            market='KRW-ETH',
            side='ask',
            ord_type='market',
            price=None,
            state='wait',
            volume=0.1,
            remaining_volume=0.1,
            executed_volume=0.0,
            created_at=datetime.now()
        )
        
        order_manager.active_orders['order1'] = order_status1
        order_manager.active_orders['order2'] = order_status2
        
        active_orders = order_manager.get_active_orders()
        
        assert len(active_orders) == 2
        assert order_status1 in active_orders
        assert order_status2 in active_orders
    
    def test_cleanup_completed_orders(self, order_manager):
        """완료된 주문 정리 테스트."""
        from datetime import timedelta
        
        # 오래된 완료 주문
        old_completed_order = OrderStatus(
            order_id='old_order',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            state='done',
            volume=0.001,
            remaining_volume=0.0,
            executed_volume=0.001,
            created_at=datetime.now() - timedelta(hours=25)  # 25시간 전
        )
        
        # 최근 완료 주문
        recent_completed_order = OrderStatus(
            order_id='recent_order',
            market='KRW-ETH',
            side='ask',
            ord_type='market',
            price=None,
            state='done',
            volume=0.1,
            remaining_volume=0.0,
            executed_volume=0.1,
            created_at=datetime.now() - timedelta(hours=1)  # 1시간 전
        )
        
        # 대기 중인 주문
        waiting_order = OrderStatus(
            order_id='waiting_order',
            market='KRW-ADA',
            side='bid',
            ord_type='limit',
            price=1000.0,
            state='wait',
            volume=100.0,
            remaining_volume=100.0,
            executed_volume=0.0,
            created_at=datetime.now() - timedelta(hours=25)  # 25시간 전이지만 대기 중
        )
        
        order_manager.active_orders['old_order'] = old_completed_order
        order_manager.active_orders['recent_order'] = recent_completed_order
        order_manager.active_orders['waiting_order'] = waiting_order
        
        cleaned_count = order_manager.cleanup_completed_orders(max_age_hours=24)
        
        assert cleaned_count == 1
        assert 'old_order' not in order_manager.active_orders
        assert 'recent_order' in order_manager.active_orders  # 최근 완료 주문은 유지
        assert 'waiting_order' in order_manager.active_orders  # 대기 중인 주문은 유지