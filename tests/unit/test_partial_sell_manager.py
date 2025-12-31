"""
Unit tests for PartialSellManager class.

Tests partial sell conditions, quantity calculations, and sell level management.
"""

import pytest
from upbit_trading_bot.strategy.partial_sell_manager import PartialSellManager


class TestPartialSellManager:
    """부분 매도 관리자 단위 테스트"""
    
    def setup_method(self):
        """각 테스트 메서드 실행 전 설정"""
        self.target_profit = 2.0  # 2% 목표 수익률
        self.manager = PartialSellManager(self.target_profit)
    
    def test_initialization_with_valid_target_profit(self):
        """유효한 목표 수익률로 초기화 테스트"""
        # Given & When: 유효한 목표 수익률로 관리자 생성
        manager = PartialSellManager(1.5)
        
        # Then: 올바르게 초기화되어야 함
        assert manager.target_profit == 1.5
        assert len(manager.sell_levels) == 2
        assert manager.sell_levels[0]['threshold'] == 0.5
        assert manager.sell_levels[0]['ratio'] == 0.3
        assert manager.sell_levels[1]['threshold'] == 1.0
        assert manager.sell_levels[1]['ratio'] == 0.5
        assert manager.trailing_stop_threshold == 1.5
        assert manager.stop_loss_adjusted is False
    
    def test_initialization_with_invalid_target_profit(self):
        """잘못된 목표 수익률로 초기화 시 오류 테스트"""
        # Given & When & Then: 잘못된 목표 수익률로 초기화 시 오류 발생
        with pytest.raises(ValueError, match="Target profit must be a positive number"):
            PartialSellManager(0)
        
        with pytest.raises(ValueError, match="Target profit must be a positive number"):
            PartialSellManager(-1.0)
        
        with pytest.raises(ValueError, match="Target profit must be a positive number"):
            PartialSellManager("invalid")
    
    def test_first_partial_sell_condition(self):
        """첫 번째 부분 매도 조건 테스트"""
        # Given: 목표 수익률의 50%에 도달
        current_pnl = self.target_profit * 0.5  # 1.0%
        
        # When: 부분 매도 여부 확인
        sell_ratio = self.manager.should_partial_sell(current_pnl)
        
        # Then: 30% 매도 비율이 반환되어야 함
        assert sell_ratio == 0.3
    
    def test_second_partial_sell_condition(self):
        """두 번째 부분 매도 조건 테스트"""
        # Given: 첫 번째 부분 매도 완료
        first_pnl = self.target_profit * 0.5
        first_sell_ratio = self.manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 목표 수익률에 도달
        current_pnl = self.target_profit  # 2.0%
        sell_ratio = self.manager.should_partial_sell(current_pnl)
        
        # Then: 50% 매도 비율이 반환되어야 함
        assert sell_ratio == 0.5
    
    def test_no_partial_sell_below_threshold(self):
        """임계값 미만에서 부분 매도 없음 테스트"""
        # Given: 목표 수익률의 50% 미만
        current_pnl = self.target_profit * 0.4  # 0.8%
        
        # When: 부분 매도 여부 확인
        sell_ratio = self.manager.should_partial_sell(current_pnl)
        
        # Then: 매도 신호가 없어야 함
        assert sell_ratio is None
    
    def test_partial_sell_only_once_per_level(self):
        """각 레벨에서 부분 매도는 한 번만 실행 테스트"""
        # Given: 목표 수익률의 50%에 도달
        current_pnl = self.target_profit * 0.5
        
        # When: 첫 번째 확인
        first_sell_ratio = self.manager.should_partial_sell(current_pnl)
        
        # Then: 매도 신호가 있어야 함
        assert first_sell_ratio == 0.3
        
        # When: 같은 수익률에서 다시 확인
        second_sell_ratio = self.manager.should_partial_sell(current_pnl)
        
        # Then: 매도 신호가 없어야 함 (이미 완료됨)
        assert second_sell_ratio is None
    
    def test_calculate_sell_quantity_valid_inputs(self):
        """유효한 입력으로 매도 수량 계산 테스트"""
        # Given: 총 수량과 매도 비율
        total_quantity = 100.0
        sell_ratio = 0.3
        
        # When: 매도 수량 계산
        sell_quantity = self.manager.calculate_sell_quantity(total_quantity, sell_ratio)
        
        # Then: 정확한 매도 수량이 계산되어야 함
        assert sell_quantity == 30.0
    
    def test_calculate_sell_quantity_invalid_inputs(self):
        """잘못된 입력으로 매도 수량 계산 시 오류 테스트"""
        # Given & When & Then: 잘못된 입력으로 계산 시 오류 발생
        with pytest.raises(ValueError, match="Total quantity must be a positive number"):
            self.manager.calculate_sell_quantity(0, 0.3)
        
        with pytest.raises(ValueError, match="Total quantity must be a positive number"):
            self.manager.calculate_sell_quantity(-100, 0.3)
        
        with pytest.raises(ValueError, match="Sell ratio must be between 0 and 1"):
            self.manager.calculate_sell_quantity(100, 0)
        
        with pytest.raises(ValueError, match="Sell ratio must be between 0 and 1"):
            self.manager.calculate_sell_quantity(100, 1.5)
    
    def test_update_sell_levels_with_completed_sells(self):
        """완료된 매도 정보로 매도 레벨 업데이트 테스트"""
        # Given: 완료된 매도 정보
        completed_sells = [
            {'ratio': 0.3, 'price': 110.0, 'quantity': 30.0}
        ]
        
        # When: 매도 레벨 업데이트
        self.manager.update_sell_levels(completed_sells)
        
        # Then: 해당 레벨이 완료로 표시되어야 함
        assert self.manager.sell_levels[0]['completed'] is True
        assert self.manager.sell_levels[1]['completed'] is False
    
    def test_get_next_sell_level_initial_state(self):
        """초기 상태에서 다음 매도 레벨 조회 테스트"""
        # Given: 초기 상태
        
        # When: 다음 매도 레벨 조회
        next_level = self.manager.get_next_sell_level()
        
        # Then: 첫 번째 매도 레벨 정보가 반환되어야 함
        assert next_level is not None
        assert next_level['threshold_percent'] == self.target_profit * 0.5
        assert next_level['sell_ratio'] == 0.3
        assert "50%" in next_level['description']
        assert "30%" in next_level['description']
    
    def test_get_next_sell_level_after_first_sell(self):
        """첫 번째 매도 후 다음 매도 레벨 조회 테스트"""
        # Given: 첫 번째 부분 매도 완료
        first_pnl = self.target_profit * 0.5
        first_sell_ratio = self.manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 다음 매도 레벨 조회
        next_level = self.manager.get_next_sell_level()
        
        # Then: 두 번째 매도 레벨 정보가 반환되어야 함
        assert next_level is not None
        assert next_level['threshold_percent'] == self.target_profit
        assert next_level['sell_ratio'] == 0.5
        assert "100%" in next_level['description']
        assert "50%" in next_level['description']
    
    def test_get_next_sell_level_all_completed(self):
        """모든 매도 완료 후 다음 매도 레벨 조회 테스트"""
        # Given: 모든 부분 매도 완료
        first_pnl = self.target_profit * 0.5
        first_sell_ratio = self.manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        second_pnl = self.target_profit
        second_sell_ratio = self.manager.should_partial_sell(second_pnl)
        assert second_sell_ratio == 0.5
        
        # When: 다음 매도 레벨 조회
        next_level = self.manager.get_next_sell_level()
        
        # Then: 다음 매도 레벨이 없어야 함
        assert next_level is None
    
    def test_should_activate_trailing_stop(self):
        """트레일링 스톱 활성화 조건 테스트"""
        # Given: 목표 수익률의 150%에 도달
        current_pnl = self.target_profit * 1.5  # 3.0%
        
        # When: 트레일링 스톱 활성화 여부 확인
        should_activate = self.manager.should_activate_trailing_stop(current_pnl)
        
        # Then: 트레일링 스톱이 활성화되어야 함
        assert should_activate is True
    
    def test_should_not_activate_trailing_stop_below_threshold(self):
        """임계값 미만에서 트레일링 스톱 비활성화 테스트"""
        # Given: 목표 수익률의 150% 미만
        current_pnl = self.target_profit * 1.4  # 2.8%
        
        # When: 트레일링 스톱 활성화 여부 확인
        should_activate = self.manager.should_activate_trailing_stop(current_pnl)
        
        # Then: 트레일링 스톱이 활성화되지 않아야 함
        assert should_activate is False
    
    def test_should_adjust_stop_loss_after_first_partial_sell(self):
        """첫 번째 부분 매도 후 손절선 조정 테스트"""
        # Given: 첫 번째 부분 매도 완료
        first_pnl = self.target_profit * 0.5
        first_sell_ratio = self.manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 손절선 조정 필요 여부 확인
        should_adjust = self.manager.should_adjust_stop_loss()
        
        # Then: 손절선 조정이 필요해야 함
        assert should_adjust is True
    
    def test_mark_stop_loss_adjusted(self):
        """손절선 조정 완료 표시 테스트"""
        # Given: 첫 번째 부분 매도 완료
        first_pnl = self.target_profit * 0.5
        first_sell_ratio = self.manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # When: 손절선 조정 완료 표시
        self.manager.mark_stop_loss_adjusted()
        
        # Then: 더 이상 손절선 조정이 필요하지 않아야 함
        should_adjust = self.manager.should_adjust_stop_loss()
        assert should_adjust is False
    
    def test_get_remaining_quantity_ratio(self):
        """남은 수량 비율 계산 테스트"""
        # Given: 초기 상태
        initial_ratio = self.manager.get_remaining_quantity_ratio()
        assert initial_ratio == 1.0
        
        # When: 첫 번째 부분 매도 완료 (30% 매도)
        first_pnl = self.target_profit * 0.5
        first_sell_ratio = self.manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # Then: 남은 수량 비율이 70%여야 함
        remaining_ratio = self.manager.get_remaining_quantity_ratio()
        assert remaining_ratio == 0.7
        
        # When: 두 번째 부분 매도 완료 (50% 매도)
        second_pnl = self.target_profit
        second_sell_ratio = self.manager.should_partial_sell(second_pnl)
        assert second_sell_ratio == 0.5
        
        # Then: 남은 수량 비율이 20%여야 함
        final_ratio = self.manager.get_remaining_quantity_ratio()
        assert abs(final_ratio - 0.2) < 0.001
    
    def test_reset_functionality(self):
        """리셋 기능 테스트"""
        # Given: 부분 매도 완료 및 손절선 조정 완료
        first_pnl = self.target_profit * 0.5
        first_sell_ratio = self.manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        self.manager.mark_stop_loss_adjusted()
        
        # When: 리셋 실행
        self.manager.reset()
        
        # Then: 모든 상태가 초기화되어야 함
        assert all(not level['completed'] for level in self.manager.sell_levels)
        assert self.manager.stop_loss_adjusted is False
        assert self.manager.get_remaining_quantity_ratio() == 1.0
        
        # And: 다시 첫 번째 부분 매도가 가능해야 함
        sell_ratio_after_reset = self.manager.should_partial_sell(first_pnl)
        assert sell_ratio_after_reset == 0.3
    
    def test_get_status_comprehensive(self):
        """종합적인 상태 조회 테스트"""
        # Given: 초기 상태
        initial_status = self.manager.get_status()
        
        # Then: 초기 상태가 올바르게 반환되어야 함
        assert initial_status['target_profit'] == self.target_profit
        assert len(initial_status['sell_levels']) == 2
        assert initial_status['trailing_stop_threshold'] == 1.5
        assert initial_status['stop_loss_adjusted'] is False
        assert initial_status['remaining_quantity_ratio'] == 1.0
        assert initial_status['next_sell_level'] is not None
        
        # When: 첫 번째 부분 매도 완료
        first_pnl = self.target_profit * 0.5
        first_sell_ratio = self.manager.should_partial_sell(first_pnl)
        assert first_sell_ratio == 0.3
        
        # Then: 상태가 업데이트되어야 함
        updated_status = self.manager.get_status()
        assert updated_status['remaining_quantity_ratio'] == 0.7
        assert updated_status['sell_levels'][0]['completed'] is True
        assert updated_status['next_sell_level']['sell_ratio'] == 0.5
    
    def test_edge_case_very_small_quantities(self):
        """매우 작은 수량에 대한 엣지 케이스 테스트"""
        # Given: 매우 작은 총 수량
        total_quantity = 0.001
        sell_ratio = 0.3
        
        # When: 매도 수량 계산
        sell_quantity = self.manager.calculate_sell_quantity(total_quantity, sell_ratio)
        
        # Then: 정확한 계산이 되어야 함
        expected_quantity = 0.0003
        assert abs(sell_quantity - expected_quantity) < 0.0000001
    
    def test_edge_case_very_large_quantities(self):
        """매우 큰 수량에 대한 엣지 케이스 테스트"""
        # Given: 매우 큰 총 수량
        total_quantity = 1000000.0
        sell_ratio = 0.3
        
        # When: 매도 수량 계산
        sell_quantity = self.manager.calculate_sell_quantity(total_quantity, sell_ratio)
        
        # Then: 정확한 계산이 되어야 함
        expected_quantity = 300000.0
        assert sell_quantity == expected_quantity