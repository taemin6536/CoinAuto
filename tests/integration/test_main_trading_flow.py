"""
메인 트레이딩 플로우 통합 테스트.

신호 생성부터 주문 실행까지의 완전한 트레이딩 사이클과
오류 처리 및 복구 시나리오, 시스템 시작/종료 절차를 테스트합니다.
"""

import pytest
import time
from datetime import datetime
from unittest.mock import Mock, patch
from typing import Dict, Any, List

from upbit_trading_bot.main import TradingBotApplication
from upbit_trading_bot.data.models import (
    Ticker, TradingSignal, Order, OrderResult, OrderStatus, Position
)
from upbit_trading_bot.strategy.base import MarketData
from upbit_trading_bot.api.client import UpbitAPIError
from upbit_trading_bot.config.manager import ConfigValidationError


class TestMainTradingFlow:
    """메인 트레이딩 플로우 통합 테스트."""
    
    @pytest.fixture
    def sample_config(self):
        """테스트용 설정 데이터."""
        return {
            'trading': {
                'enabled': True,
                'default_market': 'KRW-BTC'
            },
            'strategies': {
                'evaluation_interval': 5,
                'signal_threshold': 0.7
            },
            'risk': {
                'max_position_size': 0.1,
                'stop_loss_percentage': 0.05,
                'daily_volume_limit': 1000000
            }
        }
    
    @pytest.fixture
    def sample_ticker(self):
        """테스트용 시세 데이터."""
        return Ticker(
            market='KRW-BTC',
            trade_price=50000000.0,
            trade_volume=0.1,
            timestamp=datetime.now(),
            change_rate=0.02
        )
    
    @pytest.fixture
    def sample_trading_signal(self):
        """테스트용 트레이딩 신호."""
        return TradingSignal(
            market='KRW-BTC',
            action='buy',
            confidence=0.8,
            price=50000000.0,
            volume=0.001,
            strategy_id='test_strategy',
            timestamp=datetime.now()
        )
    
    @pytest.fixture
    def sample_order(self):
        """테스트용 주문."""
        return Order(
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            volume=0.001,
            identifier='test_order_1'
        )
    
    @pytest.fixture
    def sample_order_result(self):
        """테스트용 주문 결과."""
        return OrderResult(
            order_id='test_order_123',
            market='KRW-BTC',
            side='bid',
            ord_type='limit',
            price=50000000.0,
            volume=0.001,
            remaining_volume=0.001,
            reserved_fee=0.0,
            remaining_fee=0.0,
            paid_fee=0.0,
            locked=0.0,
            executed_volume=0.0,
            trades_count=0
        )
    
    def test_complete_trading_cycle_success(self, sample_config, sample_ticker, 
                                          sample_trading_signal, sample_order, sample_order_result):
        """완전한 트레이딩 사이클 성공 시나리오 테스트."""
        
        # 모든 컴포넌트를 개별적으로 모킹
        with patch('upbit_trading_bot.main.LoggerManager') as mock_logger_manager, \
             patch('upbit_trading_bot.main.HealthMonitor') as mock_health_monitor, \
             patch('upbit_trading_bot.main.SystemMonitor') as mock_system_monitor, \
             patch('upbit_trading_bot.main.NotificationService') as mock_notification, \
             patch('upbit_trading_bot.main.ConfigManager') as mock_config_manager, \
             patch('upbit_trading_bot.main.UpbitAPIClient') as mock_api_client, \
             patch('upbit_trading_bot.main.MarketDataHandler') as mock_market_data_handler, \
             patch('upbit_trading_bot.main.StrategyManager') as mock_strategy_manager, \
             patch('upbit_trading_bot.main.OrderManager') as mock_order_manager, \
             patch('upbit_trading_bot.main.RiskManager') as mock_risk_manager, \
             patch('upbit_trading_bot.main.PortfolioManager') as mock_portfolio_manager, \
             patch('upbit_trading_bot.main.get_db_manager') as mock_db_manager:
            
            # 설정 모킹
            mock_config_manager.return_value.load_config.return_value = sample_config
            
            # API 클라이언트 모킹
            mock_api = mock_api_client.return_value
            mock_api.authenticated = True
            mock_api.authenticate.return_value = True
            mock_api.load_encrypted_credentials.return_value = True
            mock_api.get_accounts.return_value = [
                Position(market='KRW', balance=1000000.0, locked=0.0, avg_buy_price=1.0, unit_currency='KRW')
            ]
            
            # 시장 데이터 핸들러 모킹
            mock_market_data = mock_market_data_handler.return_value
            mock_market_data.get_subscribed_markets.return_value = ['KRW-BTC']
            mock_market_data.get_rolling_window_size.return_value = 100
            mock_market_data.get_price_history.return_value = [sample_ticker]
            
            # 전략 매니저 모킹
            mock_strategy = mock_strategy_manager.return_value
            mock_strategy.get_enabled_strategies.return_value = ['test_strategy']
            mock_strategy.evaluate_strategies.return_value = [sample_trading_signal]
            
            # 주문 매니저 모킹
            mock_order_mgr = mock_order_manager.return_value
            mock_order_mgr.create_order.return_value = sample_order
            mock_order_mgr.execute_order.return_value = sample_order_result
            mock_order_mgr.track_orders.return_value = []
            
            # 리스크 매니저 모킹
            mock_risk = mock_risk_manager.return_value
            mock_risk.should_stop_trading.return_value = False
            mock_risk.check_position_limits.return_value = True
            mock_risk.check_daily_limits.return_value = True
            
            # 포트폴리오 매니저 모킹
            mock_portfolio = mock_portfolio_manager.return_value
            
            # credentials 파일 존재 모킹
            with patch('pathlib.Path.exists', return_value=True):
                # 트레이딩 봇 애플리케이션 생성 및 초기화
                app = TradingBotApplication()
                
                # 컴포넌트 초기화 테스트
                assert app._initialize_components() == True
                
                # 트레이딩 사이클 시뮬레이션
                app.trading_enabled = True
                app.dry_run_mode = False
                
                # 전략 평가 실행
                app._evaluate_strategies()
                
                # 검증: 전략이 평가되었는지 확인
                mock_strategy.evaluate_strategies.assert_called()
                
                # 검증: 주문이 생성되고 실행되었는지 확인
                mock_order_mgr.create_order.assert_called_with(sample_trading_signal)
                mock_order_mgr.execute_order.assert_called_with(sample_order)
                
                # 검증: 리스크 체크가 수행되었는지 확인
                mock_risk.check_position_limits.assert_called_with(sample_order)
                mock_risk.check_daily_limits.assert_called()
                
                # 검증: 거래가 기록되었는지 확인
                mock_portfolio.record_trade.assert_called_with(sample_order_result, 'test_strategy')
                mock_risk.record_trade.assert_called()
    
    def test_system_startup_and_shutdown_sequence(self, sample_config):
        """시스템 시작 및 종료 절차 테스트."""
        
        with patch.multiple(
            'upbit_trading_bot.main',
            LoggerManager=Mock(),
            HealthMonitor=Mock(),
            SystemMonitor=Mock(),
            NotificationService=Mock(),
            ConfigManager=Mock(),
            UpbitAPIClient=Mock(),
            MarketDataHandler=Mock(),
            StrategyManager=Mock(),
            OrderManager=Mock(),
            RiskManager=Mock(),
            PortfolioManager=Mock(),
            get_db_manager=Mock()
        ) as mocks:
            
            # 설정 모킹
            mock_config_manager = mocks['ConfigManager'].return_value
            mock_config_manager.load_config.return_value = sample_config
            
            # API 클라이언트 모킹
            mock_api = mocks['UpbitAPIClient'].return_value
            mock_api.authenticated = True
            mock_api.authenticate.return_value = True
            mock_api.load_encrypted_credentials.return_value = True
            mock_api.get_accounts.return_value = []
            
            # 시장 데이터 핸들러 모킹
            mock_market_data = mocks['MarketDataHandler'].return_value
            
            # 전략 매니저 모킹
            mock_strategy = mocks['StrategyManager'].return_value
            mock_strategy.get_enabled_strategies.return_value = ['test_strategy']
            
            # 주문 매니저 모킹 (활성 주문 있음)
            mock_order_manager = mocks['OrderManager'].return_value
            active_order = OrderStatus(
                order_id='test_order_123',
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
            mock_order_manager.get_active_orders.return_value = [active_order]
            
            # 모니터링 컴포넌트 모킹
            mock_health_monitor = mocks['HealthMonitor'].return_value
            mock_system_monitor = mocks['SystemMonitor'].return_value
            mock_notification = mocks['NotificationService'].return_value
            
            # 로거 매니저 모킹
            mock_logger_manager = mocks['LoggerManager'].return_value
            
            with patch('pathlib.Path.exists', return_value=True):
                # 트레이딩 봇 애플리케이션 생성
                app = TradingBotApplication()
                
                # 시작 절차 테스트
                result = app._initialize_components()
                assert result == True
                
                # 모니터링 설정 테스트
                app._setup_monitoring()
                
                # 시장 데이터 시작 테스트
                result = app._start_market_data()
                assert result == True
                
                # 검증: 모든 컴포넌트가 올바르게 초기화되었는지 확인
                mock_config_manager.load_config.assert_called()
                mock_api.authenticate.assert_called()
                mock_strategy.load_strategies.assert_called()
                mock_market_data.start_websocket_connection.assert_called()
                
                # 종료 절차 실행
                app.running = True
                app.dry_run_mode = False
                app.shutdown()
                
                # 검증: 종료 절차가 올바르게 실행되었는지 확인
                mock_market_data.stop.assert_called()
                mock_order_manager.get_active_orders.assert_called()
                mock_order_manager.cancel_order.assert_called_with('test_order_123')
                mock_config_manager.stop_hot_reload.assert_called()
                mock_health_monitor.stop_monitoring.assert_called()
                mock_system_monitor.stop_monitoring.assert_called()
                mock_notification.stop_processing.assert_called()
                mock_logger_manager.cleanup_old_logs.assert_called()
                
                # 실행 상태가 False로 변경되었는지 확인
                assert app.running == False
    
    def test_error_handling_scenarios(self, sample_config):
        """오류 처리 시나리오 테스트."""
        
        with patch.multiple(
            'upbit_trading_bot.main',
            LoggerManager=Mock(),
            HealthMonitor=Mock(),
            SystemMonitor=Mock(),
            NotificationService=Mock(),
            ConfigManager=Mock(),
            UpbitAPIClient=Mock(),
            MarketDataHandler=Mock(),
            StrategyManager=Mock(),
            OrderManager=Mock(),
            RiskManager=Mock(),
            PortfolioManager=Mock(),
            get_db_manager=Mock()
        ) as mocks:
            
            # 설정 매니저 모킹 (검증 오류 발생)
            mock_config_manager = mocks['ConfigManager'].return_value
            mock_config_manager.load_config.side_effect = ConfigValidationError("Invalid configuration")
            
            # 트레이딩 봇 애플리케이션 생성
            app = TradingBotApplication()
            
            # 컴포넌트 초기화 시도 (설정 검증 오류로 실패해야 함)
            result = app._initialize_components()
            assert result == False
            
            # API 인증 실패 테스트
            mock_config_manager.load_config.side_effect = None
            mock_config_manager.load_config.return_value = sample_config
            
            mock_api = mocks['UpbitAPIClient'].return_value
            mock_api.authenticated = False
            mock_api.authenticate.return_value = False  # 인증 실패
            mock_api.load_encrypted_credentials.return_value = True
            
            with patch('pathlib.Path.exists', return_value=True):
                with patch('os.getenv', return_value='false'):  # DRY_RUN=false
                    result = app._initialize_components()
                    assert result == False  # 초기화 실패
                
                # 드라이런 모드에서는 인증 실패해도 초기화 성공해야 함
                with patch('os.getenv', return_value='true'):  # DRY_RUN=true
                    app.dry_run_mode = True
                    result = app._initialize_components()
                    assert result == True  # 초기화 성공
    
    def test_risk_manager_stops_trading(self, sample_config):
        """리스크 매니저가 트레이딩을 중단하는 시나리오 테스트."""
        
        with patch.multiple(
            'upbit_trading_bot.main',
            LoggerManager=Mock(),
            HealthMonitor=Mock(),
            SystemMonitor=Mock(),
            NotificationService=Mock(),
            ConfigManager=Mock(),
            UpbitAPIClient=Mock(),
            MarketDataHandler=Mock(),
            StrategyManager=Mock(),
            OrderManager=Mock(),
            RiskManager=Mock(),
            PortfolioManager=Mock(),
            get_db_manager=Mock()
        ) as mocks:
            
            # 설정 모킹
            mocks['ConfigManager'].return_value.load_config.return_value = sample_config
            
            # API 클라이언트 모킹
            mock_api = mocks['UpbitAPIClient'].return_value
            mock_api.authenticated = True
            mock_api.load_encrypted_credentials.return_value = True
            
            # 리스크 매니저 모킹 (트레이딩 중단 요청)
            mock_risk = mocks['RiskManager'].return_value
            mock_risk.should_stop_trading.return_value = True  # 트레이딩 중단
            
            # 주문 매니저 모킹
            mock_order_manager = mocks['OrderManager'].return_value
            mock_order_manager.track_orders.return_value = []
            
            with patch('pathlib.Path.exists', return_value=True):
                # 트레이딩 봇 애플리케이션 생성 및 초기화
                app = TradingBotApplication()
                app._initialize_components()
                app.trading_enabled = True
                app.running = True
                
                # 메인 루프 한 번 실행 시뮬레이션
                with patch('time.sleep'):  # sleep 호출 무시
                    # 트레이딩이 중단되어야 함
                    app._main_trading_loop()
                
                # 검증: 리스크 매니저가 트레이딩 중단을 요청했는지 확인
                mock_risk.should_stop_trading.assert_called()
                
                # 트레이딩이 비활성화되었는지 확인
                assert app.trading_enabled == False
    
    def test_dry_run_mode_behavior(self, sample_config, sample_ticker, sample_trading_signal, sample_order):
        """드라이런 모드 동작 테스트."""
        
        with patch.multiple(
            'upbit_trading_bot.main',
            LoggerManager=Mock(),
            HealthMonitor=Mock(),
            SystemMonitor=Mock(),
            NotificationService=Mock(),
            ConfigManager=Mock(),
            UpbitAPIClient=Mock(),
            MarketDataHandler=Mock(),
            StrategyManager=Mock(),
            OrderManager=Mock(),
            RiskManager=Mock(),
            PortfolioManager=Mock(),
            get_db_manager=Mock()
        ) as mocks:
            
            # 설정 모킹
            mocks['ConfigManager'].return_value.load_config.return_value = sample_config
            
            # API 클라이언트 모킹
            mock_api = mocks['UpbitAPIClient'].return_value
            mock_api.authenticated = True
            mock_api.load_encrypted_credentials.return_value = True
            mock_api.get_accounts.return_value = [
                Position(market='KRW', balance=1000000.0, locked=0.0, avg_buy_price=1.0, unit_currency='KRW')
            ]
            
            # 시장 데이터 핸들러 모킹
            mock_market_data = mocks['MarketDataHandler'].return_value
            mock_market_data.get_subscribed_markets.return_value = ['KRW-BTC']
            mock_market_data.get_rolling_window_size.return_value = 100
            mock_market_data.get_price_history.return_value = [sample_ticker]
            
            # 전략 매니저 모킹
            mock_strategy = mocks['StrategyManager'].return_value
            mock_strategy.evaluate_strategies.return_value = [sample_trading_signal]
            
            # 주문 매니저 모킹
            mock_order_manager = mocks['OrderManager'].return_value
            mock_order_manager.create_order.return_value = sample_order
            
            # 리스크 매니저 모킹
            mock_risk = mocks['RiskManager'].return_value
            mock_risk.should_stop_trading.return_value = False
            mock_risk.check_position_limits.return_value = True
            mock_risk.check_daily_limits.return_value = True
            
            with patch('pathlib.Path.exists', return_value=True):
                # 트레이딩 봇 애플리케이션 생성 및 초기화
                app = TradingBotApplication()
                app._initialize_components()
                app.trading_enabled = True
                app.dry_run_mode = True  # 드라이런 모드 활성화
                
                # 전략 평가 실행
                app._evaluate_strategies()
                
                # 검증: 주문이 생성되고 리스크 체크는 수행되지만 실제 실행은 되지 않았는지 확인
                mock_order_manager.create_order.assert_called_with(sample_trading_signal)
                mock_risk.check_position_limits.assert_called_with(sample_order)
                mock_order_manager.execute_order.assert_not_called()  # 드라이런 모드에서는 실행되지 않음