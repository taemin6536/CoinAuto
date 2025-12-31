"""
Position Manager for Stop-Loss Averaging Strategy

This module implements the PositionManager class that handles position tracking,
average price calculation, and position state management for the stop-loss averaging strategy.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal, ROUND_HALF_UP

from upbit_trading_bot.data.models import (
    StopLossPosition, 
    PositionEntry,
    OrderResult
)


class PositionManager:
    """
    포지션 관리자 클래스
    
    손절-물타기 전략에서 포지션 상태를 추적하고 관리합니다.
    평균 단가 계산, 부분 매도 처리, 포지션 초기화 등의 기능을 제공합니다.
    """
    
    def __init__(self):
        """포지션 관리자 초기화"""
        self._positions: Dict[str, StopLossPosition] = {}
    
    def add_initial_position(self, market: str, price: float, quantity: float, 
                           order_result: Optional[OrderResult] = None) -> StopLossPosition:
        """
        최초 매수 포지션을 추가합니다.
        
        Args:
            market: 마켓 코드 (예: 'KRW-BTC')
            price: 매수 가격
            quantity: 매수 수량
            order_result: 주문 결과 (선택사항)
            
        Returns:
            StopLossPosition: 생성된 포지션 정보
            
        Raises:
            ValueError: 잘못된 입력값이 제공된 경우
        """
        if not market or not isinstance(market, str):
            raise ValueError("Market must be a non-empty string")
        if not isinstance(price, (int, float)) or price <= 0:
            raise ValueError("Price must be a positive number")
        if not isinstance(quantity, (int, float)) or quantity <= 0:
            raise ValueError("Quantity must be a positive number")
        
        # 기존 포지션이 있으면 오류
        if market in self._positions:
            raise ValueError(f"Position already exists for market {market}")
        
        # 비용 계산 (소수점 정밀도 처리)
        cost = float(Decimal(str(price)) * Decimal(str(quantity)))
        
        # 포지션 진입 정보 생성
        entry = PositionEntry(
            price=price,
            quantity=quantity,
            cost=cost,
            order_type='initial',
            timestamp=datetime.now()
        )
        
        # 포지션 생성
        position = StopLossPosition(
            market=market,
            entries=[entry],
            average_price=price,
            total_quantity=quantity,
            total_cost=cost,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # 포지션 저장
        self._positions[market] = position
        
        return position
    
    def add_averaging_position(self, market: str, price: float, quantity: float,
                             order_result: Optional[OrderResult] = None) -> StopLossPosition:
        """
        물타기 매수 포지션을 추가하고 평균 단가를 재계산합니다.
        
        Args:
            market: 마켓 코드
            price: 추가 매수 가격
            quantity: 추가 매수 수량
            order_result: 주문 결과 (선택사항)
            
        Returns:
            StopLossPosition: 업데이트된 포지션 정보
            
        Raises:
            ValueError: 잘못된 입력값이나 포지션이 없는 경우
        """
        if not market or not isinstance(market, str):
            raise ValueError("Market must be a non-empty string")
        if not isinstance(price, (int, float)) or price <= 0:
            raise ValueError("Price must be a positive number")
        if not isinstance(quantity, (int, float)) or quantity <= 0:
            raise ValueError("Quantity must be a positive number")
        
        # 기존 포지션 확인
        if market not in self._positions:
            raise ValueError(f"No existing position found for market {market}")
        
        position = self._positions[market]
        
        # 비용 계산
        cost = float(Decimal(str(price)) * Decimal(str(quantity)))
        
        # 새로운 진입 정보 생성
        entry = PositionEntry(
            price=price,
            quantity=quantity,
            cost=cost,
            order_type='averaging',
            timestamp=datetime.now()
        )
        
        # 포지션 업데이트
        position.entries.append(entry)
        position.total_quantity += quantity
        position.total_cost += cost
        
        # 평균 단가 재계산 (소수점 정밀도 처리)
        position.average_price = float(
            Decimal(str(position.total_cost)) / Decimal(str(position.total_quantity))
        )
        position.updated_at = datetime.now()
        
        return position
    
    def partial_sell(self, market: str, sell_quantity: float, sell_price: float,
                    order_result: Optional[OrderResult] = None) -> StopLossPosition:
        """
        부분 매도를 처리하고 포지션 수량을 업데이트합니다.
        
        Args:
            market: 마켓 코드
            sell_quantity: 매도 수량
            sell_price: 매도 가격
            order_result: 주문 결과 (선택사항)
            
        Returns:
            StopLossPosition: 업데이트된 포지션 정보
            
        Raises:
            ValueError: 잘못된 입력값이나 포지션이 없는 경우
        """
        if not market or not isinstance(market, str):
            raise ValueError("Market must be a non-empty string")
        if not isinstance(sell_quantity, (int, float)) or sell_quantity <= 0:
            raise ValueError("Sell quantity must be a positive number")
        if not isinstance(sell_price, (int, float)) or sell_price <= 0:
            raise ValueError("Sell price must be a positive number")
        
        # 기존 포지션 확인
        if market not in self._positions:
            raise ValueError(f"No existing position found for market {market}")
        
        position = self._positions[market]
        
        # 매도 수량이 보유 수량을 초과하는지 확인
        if sell_quantity > position.total_quantity:
            raise ValueError(f"Sell quantity ({sell_quantity}) exceeds position quantity ({position.total_quantity})")
        
        # 매도 비용 계산
        sell_cost = float(Decimal(str(sell_quantity)) * Decimal(str(position.average_price)))
        
        # 포지션 수량 및 비용 업데이트
        position.total_quantity -= sell_quantity
        position.total_cost -= sell_cost
        position.updated_at = datetime.now()
        
        # 수량이 0에 가까우면 포지션 제거
        if position.total_quantity < 0.00001:
            del self._positions[market]
            # 빈 포지션 반환 (청산 완료 표시)
            position.total_quantity = 0
            position.total_cost = 0
            position.average_price = 0
        
        return position
    
    def close_position(self, market: str) -> bool:
        """
        포지션을 완전히 청산하고 초기화합니다.
        
        Args:
            market: 마켓 코드
            
        Returns:
            bool: 청산 성공 여부
        """
        if not market or not isinstance(market, str):
            return False
        
        if market in self._positions:
            del self._positions[market]
            return True
        
        return False
    
    def get_position(self, market: str) -> Optional[StopLossPosition]:
        """
        특정 마켓의 포지션 정보를 반환합니다.
        
        Args:
            market: 마켓 코드
            
        Returns:
            Optional[StopLossPosition]: 포지션 정보 (없으면 None)
        """
        return self._positions.get(market)
    
    def get_all_positions(self) -> Dict[str, StopLossPosition]:
        """
        모든 포지션 정보를 반환합니다.
        
        Returns:
            Dict[str, StopLossPosition]: 마켓별 포지션 정보
        """
        return self._positions.copy()
    
    def has_position(self, market: str) -> bool:
        """
        특정 마켓에 포지션이 있는지 확인합니다.
        
        Args:
            market: 마켓 코드
            
        Returns:
            bool: 포지션 존재 여부
        """
        return market in self._positions
    
    def get_position_pnl(self, market: str, current_price: float) -> Optional[Dict[str, float]]:
        """
        포지션의 현재 손익을 계산합니다.
        
        Args:
            market: 마켓 코드
            current_price: 현재 가격
            
        Returns:
            Optional[Dict[str, float]]: 손익 정보 (pnl, pnl_rate)
        """
        position = self.get_position(market)
        if not position:
            return None
        
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            return None
        
        # 현재 가치 계산
        current_value = float(Decimal(str(current_price)) * Decimal(str(position.total_quantity)))
        
        # 손익 계산
        pnl = current_value - position.total_cost
        pnl_rate = (pnl / position.total_cost) * 100 if position.total_cost > 0 else 0
        
        return {
            'pnl': pnl,
            'pnl_rate': pnl_rate,
            'current_value': current_value,
            'total_cost': position.total_cost,
            'average_price': position.average_price,
            'current_price': current_price
        }
    
    def clear_all_positions(self) -> None:
        """모든 포지션을 초기화합니다."""
        self._positions.clear()
    
    def get_position_count(self) -> int:
        """현재 보유 중인 포지션 수를 반환합니다."""
        return len(self._positions)