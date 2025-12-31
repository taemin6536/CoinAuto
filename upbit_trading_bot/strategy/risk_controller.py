"""
손절-물타기 전략을 위한 리스크 컨트롤러.

일일 손실 한도, 연속 손절 제한, 계좌 잔고 확인 등의 리스크 관리 기능을 제공합니다.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from ..data.models import Order, Account, StopLossPosition, StrategyState


logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """거래 기록"""
    
    market: str
    side: str  # 'buy' or 'sell'
    price: float
    quantity: float
    timestamp: datetime
    is_stop_loss: bool = False
    pnl: Optional[float] = None


class RiskController:
    """
    손절-물타기 전략을 위한 리스크 컨트롤러.
    
    일일 손실 한도, 연속 손절 제한, 계좌 잔고 확인 등의 리스크 관리 기능을 제공합니다.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        RiskController 초기화.
        
        Args:
            config: 리스크 관리 설정
        """
        self.config = config
        
        # 리스크 설정
        self.daily_loss_limit = config.get('daily_loss_limit', 5000.0)  # KRW
        self.consecutive_loss_limit = config.get('consecutive_loss_limit', 3)
        self.min_balance_threshold = config.get('min_balance_threshold', 10000.0)  # KRW
        
        # 거래 기록
        self.trade_history: List[Trade] = []
        self.daily_start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        logger.info(f"RiskController 초기화 완료: "
                   f"일일 손실 한도 {self.daily_loss_limit:,.0f} KRW, "
                   f"연속 손절 제한 {self.consecutive_loss_limit}회, "
                   f"최소 잔고 {self.min_balance_threshold:,.0f} KRW")
    
    def check_daily_loss_limit(self, current_loss: float) -> bool:
        """
        일일 손실 한도를 확인합니다.
        
        Args:
            current_loss: 현재 일일 누적 손실 (양수)
            
        Returns:
            bool: 한도 내에 있으면 True, 초과하면 False
        """
        try:
            if current_loss > self.daily_loss_limit:
                logger.warning(f"일일 손실 한도 초과: {current_loss:,.0f} > {self.daily_loss_limit:,.0f} KRW")
                return False
            
            logger.debug(f"일일 손실 한도 확인: {current_loss:,.0f} / {self.daily_loss_limit:,.0f} KRW")
            return True
            
        except Exception as e:
            logger.error(f"일일 손실 한도 확인 중 오류: {e}")
            return False
    
    def check_consecutive_losses(self, trade_history: List[Trade]) -> bool:
        """
        연속 손절 제한을 확인합니다.
        
        Args:
            trade_history: 거래 기록 목록
            
        Returns:
            bool: 제한 내에 있으면 True, 초과하면 False
        """
        try:
            if not trade_history:
                return True
            
            # 최근 거래부터 역순으로 연속 손절 횟수 계산
            consecutive_losses = 0
            for trade in reversed(trade_history):
                if trade.is_stop_loss:
                    consecutive_losses += 1
                else:
                    break  # 손절이 아닌 거래가 나오면 중단
            
            if consecutive_losses >= self.consecutive_loss_limit:
                logger.warning(f"연속 손절 제한 초과: {consecutive_losses} >= {self.consecutive_loss_limit}")
                return False
            
            logger.debug(f"연속 손절 확인: {consecutive_losses} / {self.consecutive_loss_limit}")
            return True
            
        except Exception as e:
            logger.error(f"연속 손절 제한 확인 중 오류: {e}")
            return False
    
    def check_account_balance(self, balance: float, min_balance: float) -> bool:
        """
        계좌 잔고를 확인합니다.
        
        Args:
            balance: 현재 계좌 잔고
            min_balance: 최소 거래 금액
            
        Returns:
            bool: 잔고가 충분하면 True, 부족하면 False
        """
        try:
            # 설정된 최소 잔고 임계값과 요청된 최소 금액 중 큰 값 사용
            effective_min_balance = max(self.min_balance_threshold, min_balance)
            
            if balance < effective_min_balance:
                logger.warning(f"계좌 잔고 부족: {balance:,.0f} < {effective_min_balance:,.0f} KRW")
                return False
            
            logger.debug(f"계좌 잔고 확인: {balance:,.0f} >= {effective_min_balance:,.0f} KRW")
            return True
            
        except Exception as e:
            logger.error(f"계좌 잔고 확인 중 오류: {e}")
            return False
    
    def should_suspend_strategy(self, market_conditions: Dict[str, Any]) -> bool:
        """
        전략 중단 조건을 확인합니다.
        
        Args:
            market_conditions: 시장 상황 정보
            
        Returns:
            bool: 전략을 중단해야 하면 True
        """
        try:
            # 일일 손실 한도 확인
            daily_loss = market_conditions.get('daily_loss', 0.0)
            if not self.check_daily_loss_limit(daily_loss):
                return True
            
            # 연속 손절 제한 확인
            if not self.check_consecutive_losses(self.trade_history):
                return True
            
            # 계좌 잔고 확인
            balance = market_conditions.get('balance', 0.0)
            min_order_amount = market_conditions.get('min_order_amount', 5000.0)
            if not self.check_account_balance(balance, min_order_amount):
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"전략 중단 조건 확인 중 오류: {e}")
            return True  # 오류 시 안전하게 중단
    
    def validate_order_size(self, order_size: float, available_balance: float) -> float:
        """
        주문 크기를 검증하고 조정합니다.
        
        Args:
            order_size: 요청된 주문 크기
            available_balance: 사용 가능한 잔고
            
        Returns:
            float: 조정된 주문 크기 (0이면 주문 불가)
        """
        try:
            if order_size <= 0:
                logger.warning("주문 크기가 0 이하입니다")
                return 0.0
            
            if available_balance <= 0:
                logger.warning("사용 가능한 잔고가 없습니다")
                return 0.0
            
            # 잔고 보호를 위해 최소 잔고를 남겨둠
            max_usable_balance = available_balance - self.min_balance_threshold
            if max_usable_balance <= 0:
                logger.warning(f"잔고 보호로 인한 주문 불가: "
                             f"사용 가능 {available_balance:,.0f} - 보호 {self.min_balance_threshold:,.0f} = {max_usable_balance:,.0f}")
                return 0.0
            
            # 주문 크기가 사용 가능한 잔고를 초과하면 조정
            if order_size > max_usable_balance:
                logger.info(f"주문 크기 조정: {order_size:,.0f} -> {max_usable_balance:,.0f} KRW")
                return max_usable_balance
            
            logger.debug(f"주문 크기 검증 통과: {order_size:,.0f} KRW")
            return order_size
            
        except Exception as e:
            logger.error(f"주문 크기 검증 중 오류: {e}")
            return 0.0
    
    def record_trade(self, trade: Trade) -> None:
        """
        거래를 기록합니다.
        
        Args:
            trade: 거래 정보
        """
        try:
            # 일일 거래 기록만 유지 (메모리 절약)
            current_date = datetime.now().date()
            self.trade_history = [
                t for t in self.trade_history 
                if t.timestamp.date() == current_date
            ]
            
            self.trade_history.append(trade)
            
            logger.info(f"거래 기록: {trade.market} {trade.side} "
                       f"{trade.quantity} @ {trade.price:,.0f} "
                       f"{'(손절)' if trade.is_stop_loss else ''}")
            
        except Exception as e:
            logger.error(f"거래 기록 중 오류: {e}")
    
    def get_daily_loss(self) -> float:
        """
        일일 누적 손실을 계산합니다.
        
        Returns:
            float: 일일 누적 손실 (양수)
        """
        try:
            current_date = datetime.now().date()
            daily_trades = [
                t for t in self.trade_history 
                if t.timestamp.date() == current_date and t.pnl is not None
            ]
            
            # 손실만 합산 (음수 PnL만)
            total_loss = sum(abs(t.pnl) for t in daily_trades if t.pnl < 0)
            return total_loss
            
        except Exception as e:
            logger.error(f"일일 손실 계산 중 오류: {e}")
            return 0.0
    
    def get_consecutive_loss_count(self) -> int:
        """
        연속 손절 횟수를 반환합니다.
        
        Returns:
            int: 연속 손절 횟수
        """
        try:
            if not self.trade_history:
                return 0
            
            consecutive_losses = 0
            for trade in reversed(self.trade_history):
                if trade.is_stop_loss:
                    consecutive_losses += 1
                else:
                    break
            
            return consecutive_losses
            
        except Exception as e:
            logger.error(f"연속 손절 횟수 계산 중 오류: {e}")
            return 0
    
    def reset_daily_stats(self) -> None:
        """일일 통계를 초기화합니다."""
        try:
            self.trade_history.clear()
            self.daily_start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            logger.info("일일 통계 초기화 완료")
            
        except Exception as e:
            logger.error(f"일일 통계 초기화 중 오류: {e}")
    
    def get_risk_status(self) -> Dict[str, Any]:
        """
        현재 리스크 상태를 반환합니다.
        
        Returns:
            Dict[str, Any]: 리스크 상태 정보
        """
        try:
            return {
                'daily_loss_limit': self.daily_loss_limit,
                'consecutive_loss_limit': self.consecutive_loss_limit,
                'min_balance_threshold': self.min_balance_threshold,
                'current_daily_loss': self.get_daily_loss(),
                'consecutive_loss_count': self.get_consecutive_loss_count(),
                'total_trades_today': len([
                    t for t in self.trade_history 
                    if t.timestamp.date() == datetime.now().date()
                ])
            }
            
        except Exception as e:
            logger.error(f"리스크 상태 조회 중 오류: {e}")
            return {}