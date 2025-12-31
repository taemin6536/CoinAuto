"""
Partial Sell Manager for Stop-Loss Averaging Strategy

This module implements the PartialSellManager class that handles partial sell conditions,
quantity calculations, and sell level management for the stop-loss averaging strategy.
"""

from typing import Optional, List, Dict, Any
from decimal import Decimal, ROUND_HALF_UP


class PartialSellManager:
    """
    부분 매도 관리자 클래스
    
    손절-물타기 전략에서 부분 매도 조건을 확인하고 매도 수량을 계산합니다.
    매도 레벨을 관리하고 다음 매도 시점을 결정하는 기능을 제공합니다.
    """
    
    def __init__(self, target_profit: float):
        """
        부분 매도 관리자 초기화
        
        Args:
            target_profit: 목표 수익률 (%)
            
        Raises:
            ValueError: 잘못된 목표 수익률이 제공된 경우
        """
        if not isinstance(target_profit, (int, float)) or target_profit <= 0:
            raise ValueError("Target profit must be a positive number")
        
        self.target_profit = target_profit
        
        # 부분 매도 레벨 정의 (목표 수익률 대비 비율)
        self.sell_levels = [
            {'threshold': 0.5, 'ratio': 0.3, 'completed': False},  # 목표 수익률의 50%에서 30% 매도
            {'threshold': 1.0, 'ratio': 0.5, 'completed': False},  # 목표 수익률에서 50% 매도
        ]
        
        # 트레일링 스톱 활성화 임계값 (목표 수익률의 150%)
        self.trailing_stop_threshold = 1.5
        
        # 손절선 조정 완료 여부
        self.stop_loss_adjusted = False
    
    def should_partial_sell(self, current_pnl_percent: float) -> Optional[float]:
        """
        현재 손익률을 기준으로 부분 매도 여부와 매도 비율을 결정합니다.
        
        Args:
            current_pnl_percent: 현재 손익률 (%)
            
        Returns:
            Optional[float]: 매도 비율 (0.0 ~ 1.0), 매도하지 않으면 None
            
        Raises:
            ValueError: 잘못된 손익률이 제공된 경우
        """
        if not isinstance(current_pnl_percent, (int, float)):
            raise ValueError("Current PnL percent must be a number")
        
        # 목표 수익률 대비 현재 달성률 계산
        achievement_ratio = current_pnl_percent / self.target_profit
        
        # 각 매도 레벨 확인
        for level in self.sell_levels:
            if not level['completed'] and achievement_ratio >= level['threshold']:
                level['completed'] = True
                return level['ratio']
        
        return None
    
    def calculate_sell_quantity(self, total_quantity: float, sell_ratio: float) -> float:
        """
        총 수량과 매도 비율을 기준으로 매도 수량을 계산합니다.
        
        Args:
            total_quantity: 총 보유 수량
            sell_ratio: 매도 비율 (0.0 ~ 1.0)
            
        Returns:
            float: 계산된 매도 수량
            
        Raises:
            ValueError: 잘못된 입력값이 제공된 경우
        """
        if not isinstance(total_quantity, (int, float)) or total_quantity <= 0:
            raise ValueError("Total quantity must be a positive number")
        if not isinstance(sell_ratio, (int, float)) or not (0 < sell_ratio <= 1):
            raise ValueError("Sell ratio must be between 0 and 1")
        
        # 정밀한 계산을 위해 Decimal 사용
        quantity_decimal = Decimal(str(total_quantity))
        ratio_decimal = Decimal(str(sell_ratio))
        
        sell_quantity = float(quantity_decimal * ratio_decimal)
        
        # 매도 수량이 총 수량을 초과하지 않도록 보정
        if sell_quantity > total_quantity:
            sell_quantity = total_quantity
        
        return sell_quantity
    
    def update_sell_levels(self, completed_sells: List[Dict[str, Any]]) -> None:
        """
        완료된 매도 정보를 기반으로 매도 레벨을 업데이트합니다.
        
        Args:
            completed_sells: 완료된 매도 정보 리스트
                각 항목은 {'ratio': float, 'price': float, 'quantity': float} 형태
        """
        if not isinstance(completed_sells, list):
            return
        
        # 완료된 매도 비율들을 추출
        completed_ratios = set()
        for sell in completed_sells:
            if isinstance(sell, dict) and 'ratio' in sell:
                completed_ratios.add(sell['ratio'])
        
        # 매도 레벨 상태 업데이트
        for level in self.sell_levels:
            if level['ratio'] in completed_ratios:
                level['completed'] = True
    
    def get_next_sell_level(self) -> Optional[Dict[str, Any]]:
        """
        다음 매도 레벨 정보를 반환합니다.
        
        Returns:
            Optional[Dict[str, Any]]: 다음 매도 레벨 정보, 없으면 None
        """
        for level in self.sell_levels:
            if not level['completed']:
                return {
                    'threshold_percent': level['threshold'] * self.target_profit,
                    'sell_ratio': level['ratio'],
                    'description': f"목표 수익률의 {level['threshold']*100:.0f}%에서 {level['ratio']*100:.0f}% 매도"
                }
        
        return None
    
    def should_activate_trailing_stop(self, current_pnl_percent: float) -> bool:
        """
        트레일링 스톱 활성화 여부를 확인합니다.
        
        Args:
            current_pnl_percent: 현재 손익률 (%)
            
        Returns:
            bool: 트레일링 스톱 활성화 여부
        """
        if not isinstance(current_pnl_percent, (int, float)):
            return False
        
        achievement_ratio = current_pnl_percent / self.target_profit
        return achievement_ratio >= self.trailing_stop_threshold
    
    def should_adjust_stop_loss(self) -> bool:
        """
        부분 매도 완료 후 손절선 조정 여부를 확인합니다.
        
        Returns:
            bool: 손절선 조정 필요 여부
        """
        # 첫 번째 부분 매도가 완료되었고 아직 손절선을 조정하지 않았으면 조정
        if self.sell_levels[0]['completed'] and not self.stop_loss_adjusted:
            return True
        
        return False
    
    def mark_stop_loss_adjusted(self) -> None:
        """손절선 조정 완료를 표시합니다."""
        self.stop_loss_adjusted = True
    
    def get_remaining_quantity_ratio(self) -> float:
        """
        부분 매도 후 남은 수량 비율을 계산합니다.
        
        Returns:
            float: 남은 수량 비율 (0.0 ~ 1.0)
        """
        total_sold_ratio = sum(level['ratio'] for level in self.sell_levels if level['completed'])
        return max(0.0, 1.0 - total_sold_ratio)
    
    def reset(self) -> None:
        """매도 레벨과 상태를 초기화합니다."""
        for level in self.sell_levels:
            level['completed'] = False
        self.stop_loss_adjusted = False
    
    def get_status(self) -> Dict[str, Any]:
        """
        현재 부분 매도 관리자 상태를 반환합니다.
        
        Returns:
            Dict[str, Any]: 상태 정보
        """
        return {
            'target_profit': self.target_profit,
            'sell_levels': self.sell_levels.copy(),
            'trailing_stop_threshold': self.trailing_stop_threshold,
            'stop_loss_adjusted': self.stop_loss_adjusted,
            'remaining_quantity_ratio': self.get_remaining_quantity_ratio(),
            'next_sell_level': self.get_next_sell_level()
        }