"""
주문 관리 시스템.

주문 생성, 실행, 추적 및 상태 모니터링을 담당하는 OrderManager 클래스를 제공합니다.
"""

import logging
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from ..api.client import UpbitAPIClient, UpbitAPIError
from ..data.models import Order, OrderResult, OrderStatus, TradingSignal, Position
from ..data.database import get_db_manager


logger = logging.getLogger(__name__)


@dataclass
class OrderValidationResult:
    """주문 검증 결과."""
    
    is_valid: bool
    error_message: Optional[str] = None
    required_balance: Optional[float] = None
    available_balance: Optional[float] = None


class OrderManager:
    """
    주문 관리 시스템.
    
    트레이딩 신호를 받아 주문을 생성하고 실행하며, 주문 상태를 추적하고 관리합니다.
    잔고 확인, 재시도 메커니즘, 주문 추적 기능을 제공합니다.
    """
    
    def __init__(self, api_client: UpbitAPIClient, max_retries: int = 3):
        """
        OrderManager 초기화.
        
        Args:
            api_client: 업비트 API 클라이언트
            max_retries: 주문 실패 시 최대 재시도 횟수
        """
        self.api_client = api_client
        self.max_retries = max_retries
        self.db_manager = get_db_manager()
        self.active_orders: Dict[str, OrderStatus] = {}
        
        # 재시도 설정
        self.retry_delays = [1.0, 2.0, 4.0]  # 지수 백오프 지연 시간
        
        logger.info(f"OrderManager 초기화 완료 (최대 재시도: {max_retries}회)")
    
    def create_order(self, signal: TradingSignal) -> Optional[Order]:
        """
        트레이딩 신호로부터 주문을 생성합니다.
        
        Args:
            signal: 트레이딩 신호
            
        Returns:
            Optional[Order]: 생성된 주문 (실패 시 None)
        """
        if not signal.validate():
            logger.error(f"유효하지 않은 트레이딩 신호: {signal}")
            return None
        
        try:
            # 트레이딩 신호를 주문으로 변환
            side = 'bid' if signal.action == 'buy' else 'ask'
            
            if side == 'bid':  # 매수 주문
                # 시장가 매수: price에 KRW 금액, volume은 None
                ord_type = 'price'  # 업비트 시장가 매수는 'price' 타입
                price = signal.volume  # signal.volume이 KRW 금액
                volume = None
            else:  # 매도 주문
                # 시장가 매도: volume에 코인 수량, price는 None
                ord_type = 'market'  # 시장가 매도
                price = None
                volume = round(signal.volume, 8)
            
            order = Order(
                market=signal.market,
                side=side,
                ord_type=ord_type,
                price=price,
                volume=volume,
                identifier=f"{signal.strategy_id}_{int(signal.timestamp.timestamp())}"
            )
            
            if not order.validate():
                logger.error(f"생성된 주문이 유효하지 않음: {order}")
                return None
            
            logger.info(f"주문 생성 완료: {order.market} {order.side} "
                       f"{'price=' + str(price) if price else 'volume=' + str(volume)}")
            return order
            
        except Exception as e:
            logger.error(f"주문 생성 중 오류 발생: {e}")
            return None
    
    def validate_order(self, order: Order) -> OrderValidationResult:
        """
        주문 실행 전 검증을 수행합니다.
        
        Args:
            order: 검증할 주문
            
        Returns:
            OrderValidationResult: 검증 결과
        """
        try:
            # 기본 주문 데이터 검증
            if not order.validate():
                return OrderValidationResult(
                    is_valid=False,
                    error_message="주문 데이터가 유효하지 않습니다"
                )
            
            # 계정 정보 조회
            positions = self.api_client.get_accounts()
            
            if order.side == 'bid':  # 매수 주문
                # KRW 잔고 확인
                krw_position = next((p for p in positions if p.market == 'KRW'), None)
                if not krw_position:
                    return OrderValidationResult(
                        is_valid=False,
                        error_message="KRW 잔고 정보를 찾을 수 없습니다"
                    )
                
                # 필요한 금액 계산
                if order.ord_type == 'price':
                    # 시장가 매수: price가 KRW 금액
                    required_balance = order.price
                elif order.ord_type == 'market':
                    # 시장가 매도는 매수 검증 불필요
                    required_balance = 0
                else:
                    # 지정가 매수: price * volume (현재는 사용하지 않음)
                    required_balance = order.price * order.volume if order.price and order.volume else 0
                
                available_balance = krw_position.balance - krw_position.locked
                
                if available_balance < required_balance:
                    return OrderValidationResult(
                        is_valid=False,
                        error_message="잔고가 부족합니다",
                        required_balance=required_balance,
                        available_balance=available_balance
                    )
            
            else:  # 매도 주문
                # 해당 코인 잔고 확인
                market_currency = order.market.split('-')[1]  # KRW-BTC -> BTC
                coin_position = next((p for p in positions if p.market == market_currency), None)
                
                if not coin_position:
                    return OrderValidationResult(
                        is_valid=False,
                        error_message=f"{market_currency} 잔고 정보를 찾을 수 없습니다"
                    )
                
                available_balance = coin_position.balance - coin_position.locked
                
                if available_balance < order.volume:
                    return OrderValidationResult(
                        is_valid=False,
                        error_message="매도할 코인이 부족합니다",
                        required_balance=order.volume,
                        available_balance=available_balance
                    )
            
            return OrderValidationResult(is_valid=True)
            
        except Exception as e:
            logger.error(f"주문 검증 중 오류 발생: {e}")
            return OrderValidationResult(
                is_valid=False,
                error_message=f"검증 중 오류 발생: {str(e)}"
            )
    
    def execute_order(self, order: Order) -> Optional[OrderResult]:
        """
        주문을 실행합니다. 실패 시 재시도 메커니즘을 적용합니다.
        
        Args:
            order: 실행할 주문
            
        Returns:
            Optional[OrderResult]: 주문 실행 결과 (실패 시 None)
        """
        # 주문 검증
        validation_result = self.validate_order(order)
        if not validation_result.is_valid:
            logger.error(f"주문 검증 실패: {validation_result.error_message}")
            return None
        
        # 재시도 로직으로 주문 실행
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"주문 실행 시도 {attempt + 1}/{self.max_retries + 1}: {order.market} {order.side}")
                
                # API를 통해 주문 실행
                result = self.api_client.place_order(order)
                
                # 주문 정보를 데이터베이스에 저장
                self._save_order_to_db(order, result)
                
                # 활성 주문 목록에 추가
                order_status = OrderStatus(
                    order_id=result.order_id,
                    market=result.market,
                    side=result.side,
                    ord_type=result.ord_type,
                    price=result.price,
                    state='wait',
                    volume=result.volume,
                    remaining_volume=result.remaining_volume,
                    executed_volume=result.executed_volume,
                    created_at=datetime.now()
                )
                self.active_orders[result.order_id] = order_status
                
                logger.info(f"주문 실행 성공: {result.order_id}")
                return result
                
            except UpbitAPIError as e:
                last_error = e
                logger.warning(f"주문 실행 실패 (시도 {attempt + 1}): {e}")
                
                # 마지막 시도가 아니면 대기 후 재시도
                if attempt < self.max_retries:
                    delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                    logger.info(f"{delay}초 후 재시도...")
                    time.sleep(delay)
                else:
                    logger.error(f"주문 실행 최종 실패: {e}")
            
            except Exception as e:
                last_error = e
                logger.error(f"주문 실행 중 예상치 못한 오류: {e}")
                break
        
        logger.error(f"주문 실행 실패 (모든 재시도 소진): {last_error}")
        return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        주문을 취소합니다.
        
        Args:
            order_id: 취소할 주문 ID
            
        Returns:
            bool: 취소 성공 여부
        """
        try:
            success = self.api_client.cancel_order(order_id)
            
            if success:
                # 활성 주문 목록에서 제거
                if order_id in self.active_orders:
                    self.active_orders[order_id].state = 'cancel'
                
                # 데이터베이스 업데이트
                self._update_order_status_in_db(order_id, 'cancel')
                
                logger.info(f"주문 취소 성공: {order_id}")
            else:
                logger.warning(f"주문 취소 실패: {order_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"주문 취소 중 오류 발생: {e}")
            return False
    
    def track_orders(self) -> List[OrderStatus]:
        """
        활성 주문들의 상태를 추적하고 업데이트합니다.
        
        Returns:
            List[OrderStatus]: 현재 활성 주문 상태 목록
        """
        updated_orders = []
        orders_to_remove = []
        
        for order_id, cached_status in self.active_orders.items():
            try:
                # API에서 최신 주문 상태 조회
                current_status = self.api_client.get_order_status(order_id)
                
                # 상태가 변경되었으면 업데이트
                if current_status.state != cached_status.state:
                    logger.info(f"주문 상태 변경: {order_id} {cached_status.state} -> {current_status.state}")
                    
                    # 캐시 업데이트
                    self.active_orders[order_id] = current_status
                    
                    # 데이터베이스 업데이트
                    self._update_order_status_in_db(order_id, current_status.state)
                    
                    # 완료된 주문은 활성 목록에서 제거 예약
                    if current_status.state in ['done', 'cancel']:
                        orders_to_remove.append(order_id)
                
                updated_orders.append(current_status)
                
            except Exception as e:
                logger.error(f"주문 상태 추적 중 오류 발생 ({order_id}): {e}")
                # 오류가 발생한 주문은 그대로 유지
                updated_orders.append(cached_status)
        
        # 완료된 주문들을 활성 목록에서 제거
        for order_id in orders_to_remove:
            del self.active_orders[order_id]
            logger.info(f"완료된 주문을 활성 목록에서 제거: {order_id}")
        
        return updated_orders
    
    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """
        특정 주문의 상태를 조회합니다.
        
        Args:
            order_id: 조회할 주문 ID
            
        Returns:
            Optional[OrderStatus]: 주문 상태 (없으면 None)
        """
        try:
            # 먼저 캐시에서 확인
            if order_id in self.active_orders:
                return self.active_orders[order_id]
            
            # API에서 조회
            return self.api_client.get_order_status(order_id)
            
        except Exception as e:
            logger.error(f"주문 상태 조회 중 오류 발생: {e}")
            return None
    
    def get_active_orders(self) -> List[OrderStatus]:
        """
        현재 활성 주문 목록을 반환합니다.
        
        Returns:
            List[OrderStatus]: 활성 주문 상태 목록
        """
        return list(self.active_orders.values())
    
    def _save_order_to_db(self, order: Order, result: OrderResult) -> None:
        """
        주문 정보를 데이터베이스에 저장합니다.
        
        Args:
            order: 원본 주문
            result: 주문 실행 결과
        """
        try:
            order_data = {
                'order_id': result.order_id,
                'market': result.market,
                'side': result.side,
                'ord_type': result.ord_type,
                'price': result.price,
                'volume': result.volume,
                'state': 'wait',  # 초기 상태
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
            
            self.db_manager.insert_order(order_data)
            
        except Exception as e:
            logger.error(f"주문 정보 DB 저장 중 오류: {e}")
    
    def _update_order_status_in_db(self, order_id: str, new_state: str) -> None:
        """
        데이터베이스의 주문 상태를 업데이트합니다.
        
        Args:
            order_id: 주문 ID
            new_state: 새로운 상태
        """
        try:
            order_data = {
                'order_id': order_id,
                'market': '',  # 업데이트에서는 필요없지만 스키마상 필요
                'side': 'bid',  # 업데이트에서는 필요없지만 스키마상 필요
                'ord_type': 'limit',  # 업데이트에서는 필요없지만 스키마상 필요
                'price': 0,
                'volume': 0,
                'state': new_state,
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
            
            # ON DUPLICATE KEY UPDATE를 사용하여 상태만 업데이트
            self.db_manager.insert_order(order_data)
            
        except Exception as e:
            logger.error(f"주문 상태 DB 업데이트 중 오류: {e}")
    
    def cleanup_completed_orders(self, max_age_hours: int = 24) -> int:
        """
        완료된 주문들을 정리합니다.
        
        Args:
            max_age_hours: 정리할 주문의 최대 나이 (시간)
            
        Returns:
            int: 정리된 주문 수
        """
        cleaned_count = 0
        current_time = datetime.now()
        orders_to_remove = []
        
        for order_id, order_status in self.active_orders.items():
            # 완료된 주문이고 지정된 시간이 지났으면 제거
            if (order_status.state in ['done', 'cancel'] and 
                (current_time - order_status.created_at).total_seconds() > max_age_hours * 3600):
                orders_to_remove.append(order_id)
        
        for order_id in orders_to_remove:
            del self.active_orders[order_id]
            cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"완료된 주문 {cleaned_count}개 정리 완료")
        
        return cleaned_count