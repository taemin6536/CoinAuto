"""
Trailing Stop Manager for Stop-Loss Averaging Strategy

This module implements the TrailingStopManager class that handles trailing stop activation,
high price tracking, and trailing stop execution conditions for the stop-loss averaging strategy.
"""

from typing import Optional, Dict, Any
from decimal import Decimal, ROUND_HALF_UP


class TrailingStopManager:
    """
    트레일링 스톱 관리자 클래스
    
    손절-물타기 전략에서 트레일링 스톱 활성화 조건을 확인하고
    최고가를 추적하여 트레일링 스톱 실행 조건을 관리합니다.
    """
    
    def __init__(self, activation_profit: float, trail_percentage: float):
        """
        트레일링 스톱 관리자 초기화
        
        Args:
            activation_profit: 트레일링 스톱 활성화 수익률 (%)
            trail_percentage: 트레일링 스톱 하락 비율 (%)
            
        Raises:
            ValueError: 잘못된 파라미터가 제공된 경우
        """
        if not isinstance(activation_profit, (int, float)) or activation_profit <= 0:
            raise ValueError("Activation profit must be a positive number")
        if not isinstance(trail_percentage, (int, float)) or trail_percentage <= 0:
            raise ValueError("Trail percentage must be a positive number")
        
        self.activation_profit = activation_profit
        self.trail_percentage = trail_percentage
        
        # 트레일링 스톱 상태
        self.is_active = False
        self.high_price = None
        self.activation_price = None
        self.stop_price = None
    
    def should_activate(self, current_pnl_percent: float) -> bool:
        """
        현재 손익률을 기준으로 트레일링 스톱 활성화 여부를 확인합니다.
        
        Args:
            current_pnl_percent: 현재 손익률 (%)
            
        Returns:
            bool: 트레일링 스톱 활성화 여부
            
        Raises:
            ValueError: 잘못된 손익률이 제공된 경우
        """
        if not isinstance(current_pnl_percent, (int, float)):
            raise ValueError("Current PnL percent must be a number")
        
        # 이미 활성화된 경우 True 반환
        if self.is_active:
            return True
        
        # 활성화 조건 확인
        return current_pnl_percent >= self.activation_profit
    
    def activate(self, current_price: float) -> None:
        """
        트레일링 스톱을 활성화하고 초기 최고가를 설정합니다.
        
        Args:
            current_price: 현재 가격
            
        Raises:
            ValueError: 잘못된 가격이 제공된 경우
        """
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            raise ValueError("Current price must be a positive number")
        
        self.is_active = True
        self.high_price = current_price
        self.activation_price = current_price
        self._update_stop_price()
    
    def update_high_price(self, current_price: float) -> None:
        """
        현재 가격으로 최고가를 업데이트하고 스톱 가격을 재계산합니다.
        
        Args:
            current_price: 현재 가격
            
        Raises:
            ValueError: 잘못된 가격이 제공된 경우
        """
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            raise ValueError("Current price must be a positive number")
        
        if not self.is_active:
            return
        
        # 최고가 업데이트 (현재 가격이 더 높은 경우만)
        if self.high_price is None or current_price > self.high_price:
            self.high_price = current_price
            self._update_stop_price()
    
    def should_trigger_stop(self, current_price: float) -> bool:
        """
        현재 가격을 기준으로 트레일링 스톱 실행 여부를 확인합니다.
        
        Args:
            current_price: 현재 가격
            
        Returns:
            bool: 트레일링 스톱 실행 여부
            
        Raises:
            ValueError: 잘못된 가격이 제공된 경우
        """
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            raise ValueError("Current price must be a positive number")
        
        if not self.is_active or self.stop_price is None:
            return False
        
        # 현재 가격이 스톱 가격 이하로 떨어지면 실행
        return current_price <= self.stop_price
    
    def get_stop_price(self) -> Optional[float]:
        """
        현재 스톱 가격을 반환합니다.
        
        Returns:
            Optional[float]: 스톱 가격 (활성화되지 않았으면 None)
        """
        return self.stop_price
    
    def get_high_price(self) -> Optional[float]:
        """
        추적 중인 최고가를 반환합니다.
        
        Returns:
            Optional[float]: 최고가 (활성화되지 않았으면 None)
        """
        return self.high_price
    
    def is_activated(self) -> bool:
        """
        트레일링 스톱 활성화 상태를 반환합니다.
        
        Returns:
            bool: 활성화 상태
        """
        return self.is_active
    
    def reset(self) -> None:
        """트레일링 스톱 상태를 초기화합니다."""
        self.is_active = False
        self.high_price = None
        self.activation_price = None
        self.stop_price = None
    
    def get_status(self) -> Dict[str, Any]:
        """
        현재 트레일링 스톱 관리자 상태를 반환합니다.
        
        Returns:
            Dict[str, Any]: 상태 정보
        """
        return {
            'activation_profit': self.activation_profit,
            'trail_percentage': self.trail_percentage,
            'is_active': self.is_active,
            'high_price': self.high_price,
            'activation_price': self.activation_price,
            'stop_price': self.stop_price
        }
    
    def _update_stop_price(self) -> None:
        """최고가를 기준으로 스톱 가격을 계산합니다."""
        if self.high_price is None:
            self.stop_price = None
            return
        
        # 정밀한 계산을 위해 Decimal 사용
        high_price_decimal = Decimal(str(self.high_price))
        trail_ratio = Decimal(str(self.trail_percentage / 100))
        
        # 스톱 가격 = 최고가 * (1 - 트레일링 비율)
        stop_price_decimal = high_price_decimal * (Decimal('1') - trail_ratio)
        self.stop_price = float(stop_price_decimal)