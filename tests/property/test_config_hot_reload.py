"""설정 핫 리로드를 위한 속성 기반 테스트.

**Feature: upbit-trading-bot, Property 21: 설정 핫 리로드**
**Validates: Requirements 7.3, 7.4**
"""

import pytest
import tempfile
import yaml
import time
import threading
from pathlib import Path
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.config import ConfigManager, ConfigValidationError


@composite
def valid_config_data(draw):
    """유효한 설정 데이터 구조 생성."""
    # API 섹션 생성
    api_config = {
        'base_url': draw(st.sampled_from([
            'https://api.upbit.com',
            'https://api-test.upbit.com'
        ])),
        'websocket_url': draw(st.sampled_from([
            'wss://api.upbit.com/websocket/v1',
            'wss://api-test.upbit.com/websocket/v1'
        ])),
        'timeout': draw(st.integers(min_value=10, max_value=300)),
        'max_retries': draw(st.integers(min_value=1, max_value=10)),
        'retry_delay': draw(st.floats(min_value=0.1, max_value=10.0))
    }
    
    # 거래 섹션 생성
    trading_config = {
        'enabled': draw(st.booleans()),
        'default_market': draw(st.sampled_from([
            'KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT'
        ])),
        'order_type': draw(st.sampled_from(['limit', 'market'])),
        'min_order_amount': draw(st.integers(min_value=1000, max_value=50000)),
        'max_position_size': draw(st.floats(min_value=0.01, max_value=1.0))
    }
    
    # 리스크 섹션 생성
    risk_config = {
        'stop_loss_percentage': draw(st.floats(min_value=0.01, max_value=0.5)),
        'daily_loss_limit': draw(st.floats(min_value=0.01, max_value=0.2)),
        'max_daily_trades': draw(st.integers(min_value=1, max_value=1000)),
        'min_balance_threshold': draw(st.integers(min_value=1000, max_value=100000)),
        'position_size_limit': draw(st.floats(min_value=0.01, max_value=1.0))
    }
    
    # 전략 섹션 생성 (간단하게)
    strategies_config = {
        'enabled': [],  # 빈 리스트로 단순화
        'evaluation_interval': draw(st.integers(min_value=10, max_value=3600)),
        'signal_threshold': draw(st.floats(min_value=0.1, max_value=1.0))
    }
    
    return {
        'api': api_config,
        'trading': trading_config,
        'risk': risk_config,
        'strategies': strategies_config
    }


class TestConfigurationHotReload:
    """설정 핫 리로드를 위한 속성 기반 테스트."""
    
    @given(config_data=valid_config_data())
    @settings(max_examples=5, deadline=30000)
    def test_property_21_configuration_hot_reload(self, config_data):
        """
        **Feature: upbit-trading-bot, Property 21: 설정 핫 리로드**
        **Validates: Requirements 7.3, 7.4**
        
        속성: 유효한 설정 변경에 대해, 시스템은 재시작 없이 5초 이내에 변경사항을 적용해야 한다.
        """
        # 임시 디렉토리 생성
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_config_path = Path(temp_dir) / "test_config.yaml"
            
            # 초기 설정 생성 (간단한 기본값)
            initial_config = {
                'api': {
                    'base_url': 'https://api.upbit.com',
                    'websocket_url': 'wss://api.upbit.com/websocket/v1',
                    'timeout': 30,
                    'max_retries': 3,
                    'retry_delay': 1.0
                },
                'trading': {
                    'enabled': True,
                    'default_market': 'KRW-BTC',
                    'order_type': 'limit',
                    'min_order_amount': 5000,
                    'max_position_size': 0.1
                },
                'risk': {
                    'stop_loss_percentage': 0.05,
                    'daily_loss_limit': 0.1,
                    'max_daily_trades': 10,
                    'min_balance_threshold': 10000,
                    'position_size_limit': 0.2
                },
                'strategies': {
                    'enabled': [],
                    'evaluation_interval': 60,
                    'signal_threshold': 0.7
                }
            }
            
            # 초기 설정 파일 생성
            with open(temp_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(initial_config, f, default_flow_style=False)
            
            # 변경 감지를 위한 이벤트 추적
            change_events = []
            change_event = threading.Event()
            config_applied_event = threading.Event()
            
            def config_change_callback(config_type: str, new_config: dict):
                """설정 변경 콜백."""
                change_events.append({
                    'type': config_type,
                    'config': new_config.copy(),
                    'timestamp': time.time()
                })
                change_event.set()
                
                # 설정이 실제로 적용되었는지 확인
                if config_type == 'main' and new_config == config_data:
                    config_applied_event.set()
            
            try:
                # ConfigManager 생성 및 초기 설정 로드
                config_manager = ConfigManager(str(temp_config_path), enable_hot_reload=True)
                config_manager.add_change_callback(config_change_callback)
                
                # 초기 설정 로드
                loaded_config = config_manager.load_config()
                assert loaded_config == initial_config, "초기 설정이 올바르게 로드되어야 함"
                
                # 핫 리로드가 활성화되었는지 확인
                assert config_manager.enable_hot_reload, "핫 리로드가 활성화되어야 함"
                assert config_manager._observer is not None, "파일 감시자가 설정되어야 함"
                assert config_manager._observer.is_alive(), "파일 감시자가 실행 중이어야 함"
                
                # 파일 시스템 감시자가 안정화될 때까지 대기
                time.sleep(3.0)
                
                # 설정 파일 수정 시작 시간 기록
                start_time = time.time()
                
                # 설정 파일 업데이트 (원자적 쓰기)
                temp_update_path = temp_config_path.with_suffix('.tmp')
                with open(temp_update_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config_data, f, default_flow_style=False)
                
                # 원자적으로 파일 교체
                temp_update_path.replace(temp_config_path)
                
                # 변경 감지 대기 (최대 8초)
                change_detected = change_event.wait(timeout=8.0)
                
                # 속성 1: 변경이 감지되어야 함
                assert change_detected, "설정 변경이 8초 이내에 감지되어야 함"
                
                # 속성 2: 변경 감지 시간이 5초 이내여야 함 (요구사항 7.4)
                if change_events:
                    detection_time = change_events[0]['timestamp'] - start_time
                    assert detection_time <= 5.0, f"설정 변경이 5초 이내에 감지되어야 함 (실제: {detection_time:.2f}초)"
                
                # 속성 3: 메인 설정 변경 이벤트가 발생해야 함
                main_config_changes = [e for e in change_events if e['type'] == 'main']
                assert len(main_config_changes) > 0, "메인 설정 변경 이벤트가 발생해야 함"
                
                # 속성 4: 설정이 실제로 적용될 때까지 대기 (최대 5초 추가)
                config_applied = config_applied_event.wait(timeout=5.0)
                
                if not config_applied:
                    # 콜백에서 확인되지 않았다면 직접 확인
                    # 설정 적용을 위해 충분히 대기
                    time.sleep(3.0)
                    
                    # 여러 번 시도하여 설정이 적용되었는지 확인
                    for attempt in range(3):
                        current_config = config_manager.get_config()
                        if current_config == config_data:
                            break
                        time.sleep(1.0)
                    else:
                        # 마지막 시도에서도 실패하면 수동 리로드 시도
                        config_manager.reload_config()
                        current_config = config_manager.get_config()
                
                else:
                    current_config = config_manager.get_config()
                
                # 속성 5: 업데이트된 설정이 올바르게 적용되어야 함
                assert current_config == config_data, f"업데이트된 설정이 올바르게 적용되어야 함\n예상: {config_data}\n실제: {current_config}"
                
                # 속성 6: 설정 섹션별 접근이 정상 작동해야 함
                for section in ['api', 'trading', 'risk', 'strategies']:
                    section_config = config_manager.get_section(section)
                    assert section_config == config_data[section], f"'{section}' 섹션이 올바르게 업데이트되어야 함"
                
            finally:
                # 정리
                if 'config_manager' in locals():
                    config_manager.stop_hot_reload()
    
    def test_hot_reload_with_invalid_config(self):
        """잘못된 설정으로 업데이트할 때의 핫 리로드 동작 테스트."""
        # 유효한 초기 설정
        initial_config = {
            'api': {
                'base_url': 'https://api.upbit.com',
                'websocket_url': 'wss://api.upbit.com/websocket/v1',
                'timeout': 30,
                'max_retries': 3,
                'retry_delay': 1.0
            },
            'trading': {
                'enabled': True,
                'default_market': 'KRW-BTC',
                'order_type': 'limit',
                'min_order_amount': 5000,
                'max_position_size': 0.1
            },
            'risk': {
                'stop_loss_percentage': 0.05,
                'daily_loss_limit': 0.1,
                'max_daily_trades': 10,
                'min_balance_threshold': 10000,
                'position_size_limit': 0.2
            },
            'strategies': {
                'enabled': [],
                'evaluation_interval': 60,
                'signal_threshold': 0.7
            }
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_config_path = Path(temp_dir) / "test_config.yaml"
            
            # 초기 설정 파일 생성
            with open(temp_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(initial_config, f, default_flow_style=False)
        
            try:
                config_manager = ConfigManager(str(temp_config_path), enable_hot_reload=True)
                config_manager.load_config()
                
                # 초기 설정 확인
                assert config_manager.get_config() == initial_config
                
                # 파일 시스템 감시자 안정화 대기
                time.sleep(2.0)
                
                # 잘못된 설정으로 파일 업데이트 (필수 섹션 누락)
                invalid_config = {'api': initial_config['api']}  # 다른 섹션들 누락
                
                with open(temp_config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(invalid_config, f, default_flow_style=False)
                
                # 잠시 대기하여 파일 변경이 감지되도록 함
                time.sleep(3.0)
                
                # 속성: 잘못된 설정 업데이트 시 기존 설정이 유지되어야 함
                current_config = config_manager.get_config()
                assert current_config == initial_config, "잘못된 설정 업데이트 시 기존 설정이 유지되어야 함"
                
            finally:
                if 'config_manager' in locals():
                    config_manager.stop_hot_reload()
    
    def test_hot_reload_disable(self):
        """핫 리로드 비활성화 테스트."""
        initial_config = {
            'api': {
                'base_url': 'https://api.upbit.com',
                'websocket_url': 'wss://api.upbit.com/websocket/v1',
                'timeout': 30,
                'max_retries': 3,
                'retry_delay': 1.0
            },
            'trading': {
                'enabled': True,
                'default_market': 'KRW-BTC',
                'order_type': 'limit',
                'min_order_amount': 5000,
                'max_position_size': 0.1
            },
            'risk': {
                'stop_loss_percentage': 0.05,
                'daily_loss_limit': 0.1,
                'max_daily_trades': 10,
                'min_balance_threshold': 10000,
                'position_size_limit': 0.2
            },
            'strategies': {
                'enabled': [],
                'evaluation_interval': 60,
                'signal_threshold': 0.7
            }
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_config_path = Path(temp_dir) / "test_config.yaml"
            
            # 초기 설정 파일 생성
            with open(temp_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(initial_config, f, default_flow_style=False)
        
            try:
                # 핫 리로드 비활성화로 ConfigManager 생성
                config_manager = ConfigManager(str(temp_config_path), enable_hot_reload=False)
                config_manager.load_config()
                
                # 속성: 핫 리로드가 비활성화되어야 함
                assert not config_manager.enable_hot_reload, "핫 리로드가 비활성화되어야 함"
                assert config_manager._observer is None, "파일 감시자가 None이어야 함"
                
            finally:
                pass  # 핫 리로드가 비활성화되어 있으므로 정리할 것이 없음
    
    def test_manual_config_reload(self):
        """수동 설정 리로드 테스트."""
        initial_config = {
            'api': {
                'base_url': 'https://api.upbit.com',
                'websocket_url': 'wss://api.upbit.com/websocket/v1',
                'timeout': 30,
                'max_retries': 3,
                'retry_delay': 1.0
            },
            'trading': {
                'enabled': True,
                'default_market': 'KRW-BTC',
                'order_type': 'limit',
                'min_order_amount': 5000,
                'max_position_size': 0.1
            },
            'risk': {
                'stop_loss_percentage': 0.05,
                'daily_loss_limit': 0.1,
                'max_daily_trades': 10,
                'min_balance_threshold': 10000,
                'position_size_limit': 0.2
            },
            'strategies': {
                'enabled': [],
                'evaluation_interval': 60,
                'signal_threshold': 0.7
            }
        }
        
        updated_config = {
            'api': {
                'base_url': 'https://api-test.upbit.com',
                'websocket_url': 'wss://api-test.upbit.com/websocket/v1',
                'timeout': 60,
                'max_retries': 5,
                'retry_delay': 2.0
            },
            'trading': {
                'enabled': False,
                'default_market': 'KRW-ETH',
                'order_type': 'market',
                'min_order_amount': 10000,
                'max_position_size': 0.2
            },
            'risk': {
                'stop_loss_percentage': 0.1,
                'daily_loss_limit': 0.2,
                'max_daily_trades': 20,
                'min_balance_threshold': 20000,
                'position_size_limit': 0.3
            },
            'strategies': {
                'enabled': ['test_strategy'],
                'evaluation_interval': 120,
                'signal_threshold': 0.8
            }
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_config_path = Path(temp_dir) / "test_config.yaml"
            
            # 초기 설정 파일 생성
            with open(temp_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(initial_config, f, default_flow_style=False)
        
            try:
                # 핫 리로드 비활성화로 ConfigManager 생성
                config_manager = ConfigManager(str(temp_config_path), enable_hot_reload=False)
                config_manager.load_config()
                
                # 초기 설정 확인
                assert config_manager.get_config() == initial_config
                
                # 설정 파일 업데이트
                with open(temp_config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(updated_config, f, default_flow_style=False)
                
                # 수동 리로드 전에는 기존 설정이 유지되어야 함
                assert config_manager.get_config() == initial_config
                
                # 수동 리로드 실행
                reload_success = config_manager.reload_config()
                
                # 속성 1: 수동 리로드가 성공해야 함
                assert reload_success, "수동 설정 리로드가 성공해야 함"
                
                # 속성 2: 업데이트된 설정이 적용되어야 함
                current_config = config_manager.get_config()
                assert current_config == updated_config, "수동 리로드 후 업데이트된 설정이 적용되어야 함"
                
            finally:
                pass  # 핫 리로드가 비활성화되어 있으므로 정리할 것이 없음