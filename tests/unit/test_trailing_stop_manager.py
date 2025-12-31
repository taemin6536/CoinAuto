"""
Unit tests for TrailingStopManager class.

Tests trailing stop activation, high price tracking, and stop price calculation.
"""

import pytest
from upbit_trading_bot.strategy.trailing_stop_manager import TrailingStopManager


class TestTrailingStopManager:
    """트레일링 스톱 관리자 단위 테스트"""
    
    def setup_method(self):
        """각 테스트 메서드 실행 전 설정"""
        self.activation_profit = 3.0  # 3% 활성화 수익률
        self.trail_percentage = 1.0   # 1% 트레일링 비율
        self.manager = TrailingStopManager(self.activation_profit, self.trail_percentage)
    
    def test_initialization_with_valid_parameters(self):
        """유효한 파라미터로 초기화 테스트"""
        # Given & When: 유효한 파라미터로 관리자 생성
        manager = TrailingStopManager(2.5, 1.5)
        
        # Then: 올바르게 초기화되어야 함
        assert manager.activation_profit == 2.5
        assert manager.trail_percentage == 1.5
        assert manager.is_active is False
        assert manager.high_price is None
        assert manager.activation_price is None
        assert manager.stop_price is None
    
    def test_initialization_with_invalid_activation_profit(self):
        """잘못된 활성화 수익률로 초기화 시 오류 테스트"""
        # Given & When & Then: 잘못된 활성화 수익률로 초기화 시 오류 발생
        with pytest.raises(ValueError, match="Activation profit must be a positive number"):
            TrailingStopManager(0, 1.0)
        
        with pytest.raises(ValueError, match="Activation profit must be a positive number"):
            TrailingStopManager(-1.0, 1.0)
        
        with pytest.raises(ValueError, match="Activation profit must be a positive number"):
            TrailingStopManager("invalid", 1.0)
    
    def test_initialization_with_invalid_trail_percentage(self):
        """잘못된 트레일링 비율로 초기화 시 오류 테스트"""
        # Given & When & Then: 잘못된 트레일링 비율로 초기화 시 오류 발생
        with pytest.raises(ValueError, match="Trail percentage must be a positive number"):
            TrailingStopManager(2.0, 0)
        
        with pytest.raises(ValueError, match="Trail percentage must be a positive number"):
            TrailingStopManager(2.0, -1.0)
        
        with pytest.raises(ValueError, match="Trail percentage must be a positive number"):
            TrailingStopManager(2.0, "invalid")
    
    def test_should_activate_when_pnl_meets_threshold(self):
        """손익률이 임계값에 도달했을 때 활성화 조건 테스트"""
        # Given: 활성화 임계값에 도달한 손익률
        current_pnl = self.activation_profit  # 3.0%
        
        # When: 활성화 조건 확인
        should_activate = self.manager.should_activate(current_pnl)
        
        # Then: 활성화되어야 함
        assert should_activate is True
    
    def test_should_not_activate_when_pnl_below_threshold(self):
        """손익률이 임계값 미만일 때 활성화 조건 테스트"""
        # Given: 활성화 임계값 미만의 손익률
        current_pnl = self.activation_profit - 0.1  # 2.9%
        
        # When: 활성화 조건 확인
        should_activate = self.manager.should_activate(current_pnl)
        
        # Then: 활성화되지 않아야 함
        assert should_activate is False
    
    def test_should_activate_with_invalid_pnl(self):
        """잘못된 손익률로 활성화 조건 확인 시 오류 테스트"""
        # Given & When & Then: 잘못된 손익률로 확인 시 오류 발생
        with pytest.raises(ValueError, match="Current PnL percent must be a number"):
            self.manager.should_activate("invalid")
    
    def test_activate_with_valid_price(self):
        """유효한 가격으로 활성화 테스트"""
        # Given: 유효한 현재 가격
        current_price = 50000.0
        
        # When: 트레일링 스톱 활성화
        self.manager.activate(current_price)
        
        # Then: 올바르게 활성화되어야 함
        assert self.manager.is_activated() is True
        assert self.manager.get_high_price() == current_price
        assert self.manager.activation_price == current_price
        
        # 스톱 가격이 올바르게 계산되어야 함
        expected_stop_price = current_price * (1 - self.trail_percentage / 100)
        assert abs(self.manager.get_stop_price() - expected_stop_price) < 0.01
    
    def test_activate_with_invalid_price(self):
        """잘못된 가격으로 활성화 시 오류 테스트"""
        # Given & When & Then: 잘못된 가격으로 활성화 시 오류 발생
        with pytest.raises(ValueError, match="Current price must be a positive number"):
            self.manager.activate(0)
        
        with pytest.raises(ValueError, match="Current price must be a positive number"):
            self.manager.activate(-1000.0)
        
        with pytest.raises(ValueError, match="Current price must be a positive number"):
            self.manager.activate("invalid")
    
    def test_update_high_price_when_price_increases(self):
        """가격 상승 시 최고가 업데이트 테스트"""
        # Given: 트레일링 스톱 활성화
        initial_price = 50000.0
        self.manager.activate(initial_price)
        
        # When: 더 높은 가격으로 업데이트
        higher_price = 52000.0
        self.manager.update_high_price(higher_price)
        
        # Then: 최고가가 업데이트되어야 함
        assert self.manager.get_high_price() == higher_price
        
        # 스톱 가격도 새로운 최고가 기준으로 업데이트되어야 함
        expected_stop_price = higher_price * (1 - self.trail_percentage / 100)
        assert abs(self.manager.get_stop_price() - expected_stop_price) < 0.01
    
    def test_update_high_price_when_price_decreases(self):
        """가격 하락 시 최고가 유지 테스트"""
        # Given: 트레일링 스톱 활성화
        initial_price = 50000.0
        self.manager.activate(initial_price)
        initial_stop_price = self.manager.get_stop_price()
        
        # When: 더 낮은 가격으로 업데이트 시도
        lower_price = 48000.0
        self.manager.update_high_price(lower_price)
        
        # Then: 최고가가 유지되어야 함
        assert self.manager.get_high_price() == initial_price
        
        # 스톱 가격도 변경되지 않아야 함
        assert self.manager.get_stop_price() == initial_stop_price
    
    def test_update_high_price_when_not_activated(self):
        """비활성화 상태에서 최고가 업데이트 시도 테스트"""
        # Given: 비활성화 상태
        assert self.manager.is_activated() is False
        
        # When: 가격 업데이트 시도
        self.manager.update_high_price(50000.0)
        
        # Then: 아무것도 변경되지 않아야 함
        assert self.manager.get_high_price() is None
        assert self.manager.get_stop_price() is None
    
    def test_update_high_price_with_invalid_price(self):
        """잘못된 가격으로 최고가 업데이트 시 오류 테스트"""
        # Given: 트레일링 스톱 활성화
        self.manager.activate(50000.0)
        
        # When & Then: 잘못된 가격으로 업데이트 시 오류 발생
        with pytest.raises(ValueError, match="Current price must be a positive number"):
            self.manager.update_high_price(0)
        
        with pytest.raises(ValueError, match="Current price must be a positive number"):
            self.manager.update_high_price(-1000.0)
    
    def test_should_trigger_stop_when_price_drops_below_stop_price(self):
        """가격이 스톱 가격 이하로 떨어질 때 실행 조건 테스트"""
        # Given: 트레일링 스톱 활성화
        initial_price = 50000.0
        self.manager.activate(initial_price)
        stop_price = self.manager.get_stop_price()
        
        # When: 스톱 가격 이하로 가격 하락
        current_price = stop_price - 100.0
        should_trigger = self.manager.should_trigger_stop(current_price)
        
        # Then: 트레일링 스톱이 실행되어야 함
        assert should_trigger is True
    
    def test_should_not_trigger_stop_when_price_above_stop_price(self):
        """가격이 스톱 가격 위에 있을 때 실행 조건 테스트"""
        # Given: 트레일링 스톱 활성화
        initial_price = 50000.0
        self.manager.activate(initial_price)
        stop_price = self.manager.get_stop_price()
        
        # When: 스톱 가격 위의 가격
        current_price = stop_price + 100.0
        should_trigger = self.manager.should_trigger_stop(current_price)
        
        # Then: 트레일링 스톱이 실행되지 않아야 함
        assert should_trigger is False
    
    def test_should_not_trigger_stop_when_not_activated(self):
        """비활성화 상태에서 실행 조건 테스트"""
        # Given: 비활성화 상태
        assert self.manager.is_activated() is False
        
        # When: 매우 낮은 가격
        current_price = 1000.0
        should_trigger = self.manager.should_trigger_stop(current_price)
        
        # Then: 트레일링 스톱이 실행되지 않아야 함
        assert should_trigger is False
    
    def test_should_trigger_stop_with_invalid_price(self):
        """잘못된 가격으로 실행 조건 확인 시 오류 테스트"""
        # Given: 트레일링 스톱 활성화
        self.manager.activate(50000.0)
        
        # When & Then: 잘못된 가격으로 확인 시 오류 발생
        with pytest.raises(ValueError, match="Current price must be a positive number"):
            self.manager.should_trigger_stop(0)
        
        with pytest.raises(ValueError, match="Current price must be a positive number"):
            self.manager.should_trigger_stop(-1000.0)
    
    def test_stop_price_calculation_accuracy(self):
        """스톱 가격 계산 정확성 테스트"""
        # Given: 다양한 트레일링 비율로 테스트
        test_cases = [
            (50000.0, 1.0),   # 1% 트레일링
            (30000.0, 2.5),   # 2.5% 트레일링
            (100000.0, 0.5),  # 0.5% 트레일링
        ]
        
        for price, trail_pct in test_cases:
            # When: 트레일링 스톱 관리자 생성 및 활성화
            manager = TrailingStopManager(3.0, trail_pct)
            manager.activate(price)
            
            # Then: 스톱 가격이 정확히 계산되어야 함
            expected_stop_price = price * (1 - trail_pct / 100)
            actual_stop_price = manager.get_stop_price()
            assert abs(actual_stop_price - expected_stop_price) < 0.01
    
    def test_reset_functionality(self):
        """리셋 기능 테스트"""
        # Given: 트레일링 스톱 활성화 및 최고가 업데이트
        initial_price = 50000.0
        self.manager.activate(initial_price)
        self.manager.update_high_price(52000.0)
        
        # When: 리셋 실행
        self.manager.reset()
        
        # Then: 모든 상태가 초기화되어야 함
        assert self.manager.is_activated() is False
        assert self.manager.get_high_price() is None
        assert self.manager.get_stop_price() is None
        assert self.manager.activation_price is None
    
    def test_get_status_when_not_activated(self):
        """비활성화 상태에서 상태 정보 테스트"""
        # Given: 비활성화 상태
        
        # When: 상태 정보 조회
        status = self.manager.get_status()
        
        # Then: 올바른 상태 정보가 반환되어야 함
        assert status['activation_profit'] == self.activation_profit
        assert status['trail_percentage'] == self.trail_percentage
        assert status['is_active'] is False
        assert status['high_price'] is None
        assert status['activation_price'] is None
        assert status['stop_price'] is None
    
    def test_get_status_when_activated(self):
        """활성화 상태에서 상태 정보 테스트"""
        # Given: 트레일링 스톱 활성화
        initial_price = 50000.0
        self.manager.activate(initial_price)
        
        # When: 상태 정보 조회
        status = self.manager.get_status()
        
        # Then: 올바른 상태 정보가 반환되어야 함
        assert status['activation_profit'] == self.activation_profit
        assert status['trail_percentage'] == self.trail_percentage
        assert status['is_active'] is True
        assert status['high_price'] == initial_price
        assert status['activation_price'] == initial_price
        assert status['stop_price'] is not None
    
    def test_already_activated_remains_active(self):
        """이미 활성화된 상태에서 활성화 조건 확인 테스트"""
        # Given: 트레일링 스톱 활성화
        self.manager.activate(50000.0)
        
        # When: 낮은 손익률에서 활성화 조건 확인
        low_pnl = self.activation_profit - 1.0  # 2.0%
        should_activate = self.manager.should_activate(low_pnl)
        
        # Then: 이미 활성화되어 있으므로 True여야 함
        assert should_activate is True
        assert self.manager.is_activated() is True
    
    def test_multiple_high_price_updates(self):
        """여러 번의 최고가 업데이트 테스트"""
        # Given: 트레일링 스톱 활성화
        initial_price = 50000.0
        self.manager.activate(initial_price)
        
        # When: 여러 번 가격 상승
        prices = [52000.0, 51000.0, 55000.0, 54000.0, 57000.0]
        for price in prices:
            self.manager.update_high_price(price)
        
        # Then: 최고가가 가장 높은 가격으로 설정되어야 함
        assert self.manager.get_high_price() == 57000.0
        
        # 스톱 가격도 최고가 기준으로 계산되어야 함
        expected_stop_price = 57000.0 * (1 - self.trail_percentage / 100)
        assert abs(self.manager.get_stop_price() - expected_stop_price) < 0.01
    
    def test_edge_case_exact_stop_price(self):
        """정확히 스톱 가격에서의 실행 조건 테스트"""
        # Given: 트레일링 스톱 활성화
        initial_price = 50000.0
        self.manager.activate(initial_price)
        stop_price = self.manager.get_stop_price()
        
        # When: 정확히 스톱 가격에서 확인
        should_trigger = self.manager.should_trigger_stop(stop_price)
        
        # Then: 트레일링 스톱이 실행되어야 함 (이하 조건이므로)
        assert should_trigger is True