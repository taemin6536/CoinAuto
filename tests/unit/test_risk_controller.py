"""
리스크 컨트롤러 단위 테스트.

각 리스크 관리 기능별 단위 테스트와 엣지 케이스 및 오류 조건 테스트를 포함합니다.
요구사항: 2.3, 2.4, 2.5
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any

from upbit_trading_bot.strategy.risk_controller import RiskController, Trade


class TestRiskController:
    """리스크 컨트롤러 단위 테스트"""
    
    @pytest.fixture
    def default_config(self) -> Dict[str, Any]:
        """기본 리스크 설정"""
        return {
            'daily_loss_limit': 10000.0,
            'consecutive_loss_limit': 3,
            'min_balance_threshold': 20000.0
        }
    
    @pytest.fixture
    def risk_controller(self, default_config) -> RiskController:
        """기본 리스크 컨트롤러 인스턴스"""
        return RiskController(default_config)
    
    def test_initialization(self, default_config):
        """리스크 컨트롤러 초기화 테스트"""
        # Given & When: 리스크 컨트롤러 생성
        controller = RiskController(default_config)
        
        # Then: 설정이 올바르게 적용되어야 함
        assert controller.daily_loss_limit == 10000.0
        assert controller.consecutive_loss_limit == 3
        assert controller.min_balance_threshold == 20000.0
        assert len(controller.trade_history) == 0
    
    def test_initialization_with_default_values(self):
        """기본값으로 초기화 테스트"""
        # Given & When: 빈 설정으로 리스크 컨트롤러 생성
        controller = RiskController({})
        
        # Then: 기본값이 적용되어야 함
        assert controller.daily_loss_limit == 5000.0
        assert controller.consecutive_loss_limit == 3
        assert controller.min_balance_threshold == 10000.0
    
    def test_check_daily_loss_limit_within_limit(self, risk_controller):
        """일일 손실 한도 내 확인"""
        # Given: 한도 내 손실
        current_loss = 5000.0
        
        # When: 일일 손실 한도 확인
        result = risk_controller.check_daily_loss_limit(current_loss)
        
        # Then: True를 반환해야 함
        assert result == True
    
    def test_check_daily_loss_limit_exceeds_limit(self, risk_controller):
        """일일 손실 한도 초과 확인"""
        # Given: 한도 초과 손실
        current_loss = 15000.0
        
        # When: 일일 손실 한도 확인
        result = risk_controller.check_daily_loss_limit(current_loss)
        
        # Then: False를 반환해야 함
        assert result == False
    
    def test_check_daily_loss_limit_at_limit(self, risk_controller):
        """일일 손실 한도와 같은 경우 확인"""
        # Given: 한도와 같은 손실
        current_loss = 10000.0
        
        # When: 일일 손실 한도 확인
        result = risk_controller.check_daily_loss_limit(current_loss)
        
        # Then: True를 반환해야 함 (한도와 같으면 아직 초과하지 않음)
        assert result == True
    
    def test_check_consecutive_losses_no_losses(self, risk_controller):
        """연속 손절이 없는 경우"""
        # Given: 손절이 없는 거래 기록
        trades = [
            Trade('KRW-BTC', 'sell', 51000000.0, 0.001, datetime.now(), False, 1000.0),
            Trade('KRW-ETH', 'sell', 3100000.0, 0.01, datetime.now(), False, 500.0)
        ]
        
        # When: 연속 손절 확인
        result = risk_controller.check_consecutive_losses(trades)
        
        # Then: True를 반환해야 함
        assert result == True
    
    def test_check_consecutive_losses_within_limit(self, risk_controller):
        """연속 손절이 한도 내인 경우"""
        # Given: 2회 연속 손절 (한도는 3회)
        trades = [
            Trade('KRW-BTC', 'sell', 49000000.0, 0.001, datetime.now() - timedelta(minutes=20), True, -1000.0),
            Trade('KRW-ETH', 'sell', 2900000.0, 0.01, datetime.now() - timedelta(minutes=10), True, -500.0),
            Trade('KRW-ADA', 'sell', 1100.0, 10.0, datetime.now(), False, 200.0)  # 성공 거래로 연속성 끊어짐
        ]
        
        # When: 연속 손절 확인
        result = risk_controller.check_consecutive_losses(trades)
        
        # Then: True를 반환해야 함
        assert result == True
    
    def test_check_consecutive_losses_at_limit(self, risk_controller):
        """연속 손절이 한도와 같은 경우"""
        # Given: 3회 연속 손절 (한도와 같음)
        trades = [
            Trade('KRW-BTC', 'sell', 49000000.0, 0.001, datetime.now() - timedelta(minutes=30), True, -1000.0),
            Trade('KRW-ETH', 'sell', 2900000.0, 0.01, datetime.now() - timedelta(minutes=20), True, -500.0),
            Trade('KRW-ADA', 'sell', 1000.0, 10.0, datetime.now() - timedelta(minutes=10), True, -300.0)
        ]
        
        # When: 연속 손절 확인
        result = risk_controller.check_consecutive_losses(trades)
        
        # Then: False를 반환해야 함
        assert result == False
    
    def test_check_consecutive_losses_exceeds_limit(self, risk_controller):
        """연속 손절이 한도를 초과하는 경우"""
        # Given: 4회 연속 손절 (한도 초과)
        trades = [
            Trade('KRW-BTC', 'sell', 49000000.0, 0.001, datetime.now() - timedelta(minutes=40), True, -1000.0),
            Trade('KRW-ETH', 'sell', 2900000.0, 0.01, datetime.now() - timedelta(minutes=30), True, -500.0),
            Trade('KRW-ADA', 'sell', 1000.0, 10.0, datetime.now() - timedelta(minutes=20), True, -300.0),
            Trade('KRW-DOT', 'sell', 8000.0, 1.0, datetime.now() - timedelta(minutes=10), True, -200.0)
        ]
        
        # When: 연속 손절 확인
        result = risk_controller.check_consecutive_losses(trades)
        
        # Then: False를 반환해야 함
        assert result == False
    
    def test_check_account_balance_sufficient(self, risk_controller):
        """계좌 잔고가 충분한 경우"""
        # Given: 충분한 잔고
        balance = 50000.0
        min_balance = 5000.0
        
        # When: 계좌 잔고 확인
        result = risk_controller.check_account_balance(balance, min_balance)
        
        # Then: True를 반환해야 함
        assert result == True
    
    def test_check_account_balance_insufficient_below_threshold(self, risk_controller):
        """계좌 잔고가 임계값보다 부족한 경우"""
        # Given: 임계값보다 부족한 잔고
        balance = 15000.0  # 임계값 20000.0보다 부족
        min_balance = 5000.0
        
        # When: 계좌 잔고 확인
        result = risk_controller.check_account_balance(balance, min_balance)
        
        # Then: False를 반환해야 함
        assert result == False
    
    def test_check_account_balance_insufficient_below_min_balance(self, risk_controller):
        """계좌 잔고가 최소 거래 금액보다 부족한 경우"""
        # Given: 최소 거래 금액보다 부족한 잔고
        balance = 25000.0  # 임계값보다는 크지만
        min_balance = 30000.0  # 최소 거래 금액보다 부족
        
        # When: 계좌 잔고 확인
        result = risk_controller.check_account_balance(balance, min_balance)
        
        # Then: False를 반환해야 함
        assert result == False
    
    def test_should_suspend_strategy_normal_conditions(self, risk_controller):
        """정상 조건에서 전략 중단 확인"""
        # Given: 정상적인 시장 상황
        market_conditions = {
            'daily_loss': 5000.0,  # 한도 내
            'balance': 50000.0,    # 충분한 잔고
            'min_order_amount': 5000.0
        }
        
        # When: 전략 중단 조건 확인
        result = risk_controller.should_suspend_strategy(market_conditions)
        
        # Then: False를 반환해야 함 (중단하지 않음)
        assert result == False
    
    def test_should_suspend_strategy_daily_loss_exceeded(self, risk_controller):
        """일일 손실 한도 초과 시 전략 중단"""
        # Given: 일일 손실 한도 초과
        market_conditions = {
            'daily_loss': 15000.0,  # 한도 초과
            'balance': 50000.0,
            'min_order_amount': 5000.0
        }
        
        # When: 전략 중단 조건 확인
        result = risk_controller.should_suspend_strategy(market_conditions)
        
        # Then: True를 반환해야 함 (중단)
        assert result == True
    
    def test_should_suspend_strategy_insufficient_balance(self, risk_controller):
        """잔고 부족 시 전략 중단"""
        # Given: 잔고 부족
        market_conditions = {
            'daily_loss': 5000.0,
            'balance': 15000.0,    # 임계값보다 부족
            'min_order_amount': 5000.0
        }
        
        # When: 전략 중단 조건 확인
        result = risk_controller.should_suspend_strategy(market_conditions)
        
        # Then: True를 반환해야 함 (중단)
        assert result == True
    
    def test_validate_order_size_normal(self, risk_controller):
        """정상적인 주문 크기 검증"""
        # Given: 정상적인 주문 크기와 잔고
        order_size = 10000.0
        available_balance = 50000.0
        
        # When: 주문 크기 검증
        result = risk_controller.validate_order_size(order_size, available_balance)
        
        # Then: 원래 주문 크기를 반환해야 함
        assert result == order_size
    
    def test_validate_order_size_exceeds_usable_balance(self, risk_controller):
        """사용 가능한 잔고를 초과하는 주문 크기"""
        # Given: 사용 가능한 잔고를 초과하는 주문 크기
        order_size = 40000.0
        available_balance = 35000.0  # 사용 가능: 35000 - 20000(임계값) = 15000
        
        # When: 주문 크기 검증
        result = risk_controller.validate_order_size(order_size, available_balance)
        
        # Then: 사용 가능한 최대 금액을 반환해야 함
        expected_max = available_balance - risk_controller.min_balance_threshold
        assert result == expected_max
    
    def test_validate_order_size_insufficient_balance_for_protection(self, risk_controller):
        """잔고 보호로 인한 주문 불가"""
        # Given: 잔고 보호 임계값보다 적은 잔고
        order_size = 10000.0
        available_balance = 15000.0  # 임계값 20000.0보다 적음
        
        # When: 주문 크기 검증
        result = risk_controller.validate_order_size(order_size, available_balance)
        
        # Then: 0을 반환해야 함
        assert result == 0.0
    
    def test_validate_order_size_zero_or_negative(self, risk_controller):
        """0 또는 음수 주문 크기"""
        # Given: 0 또는 음수 주문 크기
        available_balance = 50000.0
        
        # When: 0과 음수 주문 크기 검증
        zero_result = risk_controller.validate_order_size(0.0, available_balance)
        negative_result = risk_controller.validate_order_size(-1000.0, available_balance)
        
        # Then: 모두 0을 반환해야 함
        assert zero_result == 0.0
        assert negative_result == 0.0
    
    def test_record_trade(self, risk_controller):
        """거래 기록 테스트"""
        # Given: 거래 정보
        trade = Trade(
            market='KRW-BTC',
            side='sell',
            price=50000000.0,
            quantity=0.001,
            timestamp=datetime.now(),
            is_stop_loss=True,
            pnl=-1000.0
        )
        
        # When: 거래 기록
        risk_controller.record_trade(trade)
        
        # Then: 거래 기록에 추가되어야 함
        assert len(risk_controller.trade_history) == 1
        assert risk_controller.trade_history[0] == trade
    
    def test_get_daily_loss_calculation(self, risk_controller):
        """일일 손실 계산 테스트"""
        # Given: 손실과 이익이 섞인 거래들
        trades = [
            Trade('KRW-BTC', 'sell', 49000000.0, 0.001, datetime.now(), True, -1000.0),
            Trade('KRW-ETH', 'sell', 3100000.0, 0.01, datetime.now(), False, 500.0),
            Trade('KRW-ADA', 'sell', 900.0, 10.0, datetime.now(), True, -300.0)
        ]
        
        # When: 거래들을 기록하고 일일 손실 계산
        for trade in trades:
            risk_controller.record_trade(trade)
        
        daily_loss = risk_controller.get_daily_loss()
        
        # Then: 손실만 합산되어야 함 (1000 + 300 = 1300)
        assert daily_loss == 1300.0
    
    def test_get_consecutive_loss_count(self, risk_controller):
        """연속 손절 횟수 계산 테스트"""
        # Given: 연속 손절이 포함된 거래들
        trades = [
            Trade('KRW-BTC', 'sell', 51000000.0, 0.001, datetime.now() - timedelta(minutes=30), False, 1000.0),
            Trade('KRW-ETH', 'sell', 2900000.0, 0.01, datetime.now() - timedelta(minutes=20), True, -500.0),
            Trade('KRW-ADA', 'sell', 900.0, 10.0, datetime.now() - timedelta(minutes=10), True, -300.0)
        ]
        
        # When: 거래들을 기록하고 연속 손절 횟수 계산
        for trade in trades:
            risk_controller.record_trade(trade)
        
        consecutive_count = risk_controller.get_consecutive_loss_count()
        
        # Then: 마지막 2개의 연속 손절이 계산되어야 함
        assert consecutive_count == 2
    
    def test_reset_daily_stats(self, risk_controller):
        """일일 통계 초기화 테스트"""
        # Given: 거래 기록이 있는 상태
        trade = Trade('KRW-BTC', 'sell', 49000000.0, 0.001, datetime.now(), True, -1000.0)
        risk_controller.record_trade(trade)
        
        # When: 일일 통계 초기화
        risk_controller.reset_daily_stats()
        
        # Then: 거래 기록이 초기화되어야 함
        assert len(risk_controller.trade_history) == 0
    
    def test_get_risk_status(self, risk_controller):
        """리스크 상태 조회 테스트"""
        # Given: 일부 거래 기록
        trade = Trade('KRW-BTC', 'sell', 49000000.0, 0.001, datetime.now(), True, -1000.0)
        risk_controller.record_trade(trade)
        
        # When: 리스크 상태 조회
        status = risk_controller.get_risk_status()
        
        # Then: 모든 필요한 정보가 포함되어야 함
        assert 'daily_loss_limit' in status
        assert 'consecutive_loss_limit' in status
        assert 'min_balance_threshold' in status
        assert 'current_daily_loss' in status
        assert 'consecutive_loss_count' in status
        assert 'total_trades_today' in status
        
        assert status['daily_loss_limit'] == 10000.0
        assert status['consecutive_loss_limit'] == 3
        assert status['min_balance_threshold'] == 20000.0
        assert status['current_daily_loss'] == 1000.0
        assert status['consecutive_loss_count'] == 1
        assert status['total_trades_today'] == 1
    
    def test_edge_case_empty_trade_history(self, risk_controller):
        """빈 거래 기록 엣지 케이스"""
        # Given: 빈 거래 기록
        
        # When: 각종 계산 수행
        daily_loss = risk_controller.get_daily_loss()
        consecutive_count = risk_controller.get_consecutive_loss_count()
        consecutive_check = risk_controller.check_consecutive_losses([])
        
        # Then: 모두 안전한 값을 반환해야 함
        assert daily_loss == 0.0
        assert consecutive_count == 0
        assert consecutive_check == True
    
    def test_error_handling_invalid_market_conditions(self, risk_controller):
        """잘못된 시장 상황 데이터 처리"""
        # Given: 불완전한 시장 상황 데이터
        incomplete_conditions = {
            'daily_loss': 5000.0
            # balance와 min_order_amount 누락
        }
        
        # When: 전략 중단 조건 확인
        result = risk_controller.should_suspend_strategy(incomplete_conditions)
        
        # Then: 안전하게 True를 반환해야 함 (오류 시 중단)
        assert result == True