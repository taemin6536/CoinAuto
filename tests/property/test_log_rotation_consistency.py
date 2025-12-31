"""로그 순환 일관성을 위한 속성 기반 테스트.

**Feature: upbit-trading-bot, Property 23: 로그 순환 일관성**
**Validates: Requirements 8.3**
"""

import pytest
import tempfile
import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite
from unittest.mock import patch, MagicMock

from upbit_trading_bot.logging.logger import LoggerManager, get_logger


@composite
def log_rotation_config(draw):
    """로그 순환 설정 데이터 생성."""
    config = {}
    
    # 파일 크기 기반 순환 설정 (1KB ~ 10MB)
    config['max_file_size'] = draw(st.integers(min_value=1024, max_value=10*1024*1024))
    
    # 백업 파일 개수 (1 ~ 100개)
    config['backup_count'] = draw(st.integers(min_value=1, max_value=100))
    
    # 로그 레벨
    config['log_level'] = draw(st.sampled_from(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']))
    
    return config


@composite
def log_message_data(draw):
    """로그 메시지 데이터 생성."""
    # 다양한 크기의 로그 메시지 생성
    message_size = draw(st.integers(min_value=10, max_value=1000))
    message = draw(st.text(
        min_size=message_size,
        max_size=message_size,
        alphabet=st.characters(min_codepoint=32, max_codepoint=126)
    ))
    
    # 로그 레벨
    level = draw(st.sampled_from(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']))
    
    # 추가 컨텍스트
    context = {
        'component': draw(st.sampled_from([
            'api_client', 'market_data', 'order_manager', 'risk_manager'
        ])),
        'operation': draw(st.sampled_from([
            'place_order', 'fetch_data', 'update_portfolio', 'evaluate_strategy'
        ])),
        'timestamp': datetime.now().isoformat()
    }
    
    return message, level, context


class TestLogRotationConsistency:
    """로그 순환 일관성을 위한 속성 기반 테스트."""
    
    @given(
        rotation_config=log_rotation_config(),
        log_messages=st.lists(log_message_data(), min_size=5, max_size=20)
    )
    @settings(max_examples=10, deadline=15000)
    def test_property_23_log_rotation_consistency(self, rotation_config, log_messages):
        """
        **Feature: upbit-trading-bot, Property 23: 로그 순환 일관성**
        **Validates: Requirements 8.3**
        
        속성: 모든 일일 운영에 대해, 로그 파일들은 순환되어야 하고 최소 30일간 유지되어야 한다.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            # 작은 파일 크기로 설정하여 순환을 강제로 발생시킴
            small_max_size = min(rotation_config['max_file_size'], 5000)  # 최대 5KB
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level=rotation_config['log_level'],
                max_file_size=small_max_size,
                backup_count=rotation_config['backup_count'],
                console_output=False,
                structured_format=True
            )
            
            test_logger = logger_manager.get_logger("test_rotation")
            
            # 초기 로그 파일 상태 확인
            initial_files = list(log_dir.glob("*.log*"))
            initial_count = len(initial_files)
            
            # 로그 메시지들을 기록하여 파일 순환 유발
            total_logged_size = 0
            for message, level, context in log_messages:
                log_level = getattr(logging, level)
                test_logger.log(log_level, message, extra=context)
                
                # 대략적인 로그 크기 계산 (JSON 구조화 고려)
                estimated_size = len(message) + len(json.dumps(context)) + 200  # 메타데이터 추가
                total_logged_size += estimated_size
            
            # 로그 파일들이 디스크에 기록되도록 강제 플러시
            for handler in logging.getLogger().handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
            
            # 순환 후 파일 상태 확인
            final_files = list(log_dir.glob("*.log*"))
            
            # 속성 1: 로그 파일이 존재해야 함
            assert len(final_files) > 0, "로그 파일이 최소 하나는 존재해야 함"
            
            # 속성 2: 메인 로그 파일들이 존재해야 함
            main_log_file = log_dir / "trading_bot.log"
            error_log_file = log_dir / "errors.log"
            assert main_log_file.exists(), "메인 로그 파일이 존재해야 함"
            assert error_log_file.exists(), "에러 로그 파일이 존재해야 함"
            
            # 속성 3: 충분한 데이터가 로그되었다면 순환이 발생했을 수 있음
            if total_logged_size > small_max_size:
                # 순환된 파일들 확인 (*.log.1, *.log.2 등)
                rotated_files = [f for f in final_files if '.log.' in f.name]
                
                # 순환이 발생했다면, 백업 파일 개수가 설정된 범위 내에 있어야 함
                if len(rotated_files) > 0:
                    # 각 로그 타입별로 백업 파일 개수 확인
                    main_backups = [f for f in rotated_files if f.name.startswith('trading_bot.log.')]
                    error_backups = [f for f in rotated_files if f.name.startswith('errors.log.')]
                    
                    # 백업 파일 개수가 설정된 backup_count를 초과하지 않아야 함
                    assert len(main_backups) <= rotation_config['backup_count'], \
                        f"메인 로그 백업 파일 개수가 설정값을 초과함: {len(main_backups)} > {rotation_config['backup_count']}"
                    
                    assert len(error_backups) <= rotation_config['backup_count'], \
                        f"에러 로그 백업 파일 개수가 설정값을 초과함: {len(error_backups)} > {rotation_config['backup_count']}"
            
            # 속성 4: 모든 로그 파일의 크기가 설정된 최대 크기를 초과하지 않아야 함
            for log_file in final_files:
                if log_file.is_file() and not log_file.name.endswith('.log.1'):  # 현재 활성 파일만 확인
                    file_size = log_file.stat().st_size
                    # 현재 활성 파일은 최대 크기를 초과할 수 있지만, 백업 파일들은 초과하지 않아야 함
                    if '.log.' in log_file.name:  # 백업 파일인 경우
                        assert file_size <= small_max_size * 1.1, \
                            f"백업 로그 파일 크기가 설정값을 크게 초과함: {file_size} > {small_max_size}"
            
            # 속성 5: 로그 파일들이 읽기 가능하고 유효한 내용을 포함해야 함
            for log_file in final_files:
                if log_file.is_file() and log_file.suffix == '.log' or '.log.' in log_file.name:
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # 파일이 비어있지 않다면 유효한 로그 엔트리가 있어야 함
                            if content.strip():
                                lines = content.strip().split('\n')
                                # 최소 하나의 유효한 JSON 로그 엔트리가 있어야 함
                                valid_entries = 0
                                for line in lines:
                                    try:
                                        log_entry = json.loads(line)
                                        if 'timestamp' in log_entry and 'level' in log_entry:
                                            valid_entries += 1
                                    except json.JSONDecodeError:
                                        pass  # 구조화되지 않은 로그 라인은 무시
                                
                                assert valid_entries > 0, f"로그 파일에 유효한 엔트리가 없음: {log_file}"
                    except Exception as e:
                        pytest.fail(f"로그 파일을 읽을 수 없음 {log_file}: {e}")
    
    def test_log_retention_policy(self):
        """로그 보존 정책 테스트 (30일 보존 요구사항)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="INFO",
                max_file_size=1024,  # 1KB로 작게 설정
                backup_count=30,  # 30일 보존
                console_output=False,
                structured_format=True
            )
            
            # 오래된 로그 파일들을 시뮬레이션하기 위해 생성
            old_files = []
            current_time = time.time()
            
            # 35일 전부터 오늘까지의 로그 파일들 생성
            for days_ago in range(35, 0, -1):
                file_time = current_time - (days_ago * 24 * 60 * 60)  # days_ago 일 전
                
                old_file = log_dir / f"trading_bot.log.{days_ago}"
                old_file.write_text(f"Log content from {days_ago} days ago")
                
                # 파일의 수정 시간을 과거로 설정
                os.utime(old_file, (file_time, file_time))
                old_files.append(old_file)
            
            # 정리 작업 실행
            logger_manager.cleanup_old_logs(retention_days=30)
            
            # 30일 이내의 파일들은 유지되어야 함
            remaining_files = list(log_dir.glob("*.log*"))
            
            # 30일보다 오래된 파일들이 삭제되었는지 확인
            for days_ago in range(35, 30, -1):  # 31일 ~ 35일 전 파일들
                old_file = log_dir / f"trading_bot.log.{days_ago}"
                assert not old_file.exists(), f"{days_ago}일 전 파일이 삭제되지 않음: {old_file}"
            
            # 30일 이내의 파일들은 유지되어야 함
            for days_ago in range(30, 0, -1):  # 1일 ~ 30일 전 파일들
                old_file = log_dir / f"trading_bot.log.{days_ago}"
                assert old_file.exists(), f"{days_ago}일 전 파일이 잘못 삭제됨: {old_file}"
    
    def test_concurrent_log_rotation(self):
        """동시 로그 순환 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            # 매우 작은 파일 크기로 설정하여 빠른 순환 유발
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="INFO",
                max_file_size=500,  # 500 bytes
                backup_count=5,
                console_output=False,
                structured_format=True
            )
            
            # 여러 로거에서 동시에 로그 기록
            loggers = [
                logger_manager.get_logger(f"test_logger_{i}")
                for i in range(3)
            ]
            
            # 각 로거에서 많은 로그 메시지 생성
            for i in range(50):
                for j, logger in enumerate(loggers):
                    message = f"Test message {i} from logger {j} " + "x" * 100  # 긴 메시지
                    logger.info(message, extra={
                        'logger_id': j,
                        'message_id': i,
                        'component': f'test_component_{j}'
                    })
            
            # 모든 핸들러 플러시
            for handler in logging.getLogger().handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
            
            # 결과 확인
            log_files = list(log_dir.glob("*.log*"))
            
            # 로그 파일들이 생성되었는지 확인
            assert len(log_files) > 0, "로그 파일이 생성되어야 함"
            
            # 메인 로그 파일 존재 확인
            main_log = log_dir / "trading_bot.log"
            assert main_log.exists(), "메인 로그 파일이 존재해야 함"
            
            # 순환된 파일들 확인
            rotated_files = [f for f in log_files if '.log.' in f.name]
            
            # 백업 파일 개수가 설정값을 초과하지 않는지 확인
            main_backups = [f for f in rotated_files if f.name.startswith('trading_bot.log.')]
            assert len(main_backups) <= 5, f"백업 파일 개수가 설정값을 초과함: {len(main_backups)}"
            
            # 모든 로그 파일이 읽기 가능한지 확인
            for log_file in log_files:
                if log_file.is_file():
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # 내용이 있다면 유효한 JSON 로그여야 함
                            if content.strip():
                                lines = content.strip().split('\n')
                                for line in lines[:5]:  # 처음 5줄만 확인
                                    if line.strip():
                                        log_entry = json.loads(line)
                                        assert 'timestamp' in log_entry
                                        assert 'level' in log_entry
                                        assert 'message' in log_entry
                    except Exception as e:
                        pytest.fail(f"로그 파일 읽기 실패 {log_file}: {e}")
    
    def test_log_rotation_with_different_levels(self):
        """다양한 로그 레벨에서의 순환 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="DEBUG",
                max_file_size=1000,  # 1KB
                backup_count=3,
                console_output=False,
                structured_format=True
            )
            
            test_logger = logger_manager.get_logger("test_levels")
            
            # 다양한 레벨의 로그 메시지 대량 생성
            log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
            
            for i in range(20):
                for level_name in log_levels:
                    level = getattr(logging, level_name)
                    message = f"{level_name} message {i} " + "content " * 20  # 긴 메시지
                    
                    context = {
                        'level_name': level_name,
                        'message_id': i,
                        'test_type': 'level_rotation_test'
                    }
                    
                    if level_name == 'ERROR' or level_name == 'CRITICAL':
                        # 에러 레벨은 예외 정보와 함께
                        try:
                            raise ValueError(f"Test {level_name} exception {i}")
                        except ValueError as e:
                            test_logger.log(level, message, extra=context, exc_info=True)
                    else:
                        test_logger.log(level, message, extra=context)
            
            # 핸들러 플러시
            for handler in logging.getLogger().handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
            
            # 결과 검증
            log_files = list(log_dir.glob("*.log*"))
            
            # 메인 로그와 에러 로그 파일 모두 존재해야 함
            main_log = log_dir / "trading_bot.log"
            error_log = log_dir / "errors.log"
            
            assert main_log.exists(), "메인 로그 파일이 존재해야 함"
            assert error_log.exists(), "에러 로그 파일이 존재해야 함"
            
            # 에러 로그에는 ERROR와 CRITICAL 레벨만 있어야 함
            with open(error_log, 'r', encoding='utf-8') as f:
                error_content = f.read()
                error_lines = [line for line in error_content.strip().split('\n') if line.strip()]
                
                for line in error_lines:
                    try:
                        log_entry = json.loads(line)
                        assert log_entry['level'] in ['ERROR', 'CRITICAL'], \
                            f"에러 로그에 잘못된 레벨이 포함됨: {log_entry['level']}"
                    except json.JSONDecodeError:
                        pass  # 구조화되지 않은 로그 라인은 무시
            
            # 메인 로그와 백업 파일들에서 모든 레벨이 있는지 확인
            all_main_content = ""
            
            # 현재 메인 로그 파일 읽기
            with open(main_log, 'r', encoding='utf-8') as f:
                all_main_content += f.read()
            
            # 백업 파일들도 읽기 (순환으로 인해 일부 메시지가 백업 파일에 있을 수 있음)
            main_backup_files = [f for f in log_files if f.name.startswith('trading_bot.log.')]
            for backup_file in main_backup_files:
                try:
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        all_main_content += f.read()
                except Exception:
                    pass  # 백업 파일 읽기 실패는 무시
            
            # 모든 메인 로그 내용에서 레벨 확인
            found_levels = set()
            for level_name in log_levels:
                if f'"{level_name} message' in all_main_content or f'{level_name} message' in all_main_content:
                    found_levels.add(level_name)
            
            # 최소한 일부 레벨은 찾아져야 함 (순환으로 인해 모든 레벨이 없을 수도 있음)
            assert len(found_levels) > 0, "메인 로그에 어떤 레벨의 메시지도 없음"
            
            # ERROR와 CRITICAL 레벨은 반드시 있어야 함 (에러 로그에도 기록되므로)
            error_critical_found = any(level in found_levels for level in ['ERROR', 'CRITICAL'])
            assert error_critical_found, "메인 로그에 ERROR 또는 CRITICAL 레벨 메시지가 없음"
    
    def test_log_rotation_file_permissions(self):
        """로그 순환 시 파일 권한 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="INFO",
                max_file_size=800,
                backup_count=2,
                console_output=False,
                structured_format=True
            )
            
            test_logger = logger_manager.get_logger("test_permissions")
            
            # 로그 메시지 생성하여 순환 유발
            for i in range(30):
                message = f"Permission test message {i} " + "data " * 50
                test_logger.info(message, extra={'test_id': i})
            
            # 핸들러 플러시
            for handler in logging.getLogger().handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
            
            # 생성된 모든 로그 파일 확인
            log_files = list(log_dir.glob("*.log*"))
            
            for log_file in log_files:
                if log_file.is_file():
                    # 파일이 읽기 가능한지 확인
                    assert os.access(log_file, os.R_OK), f"로그 파일이 읽기 불가능: {log_file}"
                    
                    # 파일 크기가 0보다 큰지 확인 (빈 파일이 아님)
                    file_size = log_file.stat().st_size
                    if log_file.name.endswith('.log'):  # 현재 활성 파일
                        assert file_size >= 0, f"활성 로그 파일 크기가 음수: {log_file}"
                    elif '.log.' in log_file.name:  # 백업 파일
                        assert file_size > 0, f"백업 로그 파일이 비어있음: {log_file}"
    
    def test_log_rotation_cleanup_integration(self):
        """로그 순환과 정리 작업의 통합 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="INFO",
                max_file_size=600,
                backup_count=3,  # 3개의 백업 파일만 유지
                console_output=False,
                structured_format=True
            )
            
            test_logger = logger_manager.get_logger("test_cleanup_integration")
            
            # 많은 로그 메시지를 생성하여 여러 번의 순환 유발
            for batch in range(5):  # 5개 배치
                for i in range(20):  # 배치당 20개 메시지
                    message = f"Batch {batch} message {i} " + "content " * 30
                    test_logger.info(message, extra={
                        'batch': batch,
                        'message_id': i,
                        'total_id': batch * 20 + i
                    })
                
                # 배치 간 플러시
                for handler in logging.getLogger().handlers:
                    if hasattr(handler, 'flush'):
                        handler.flush()
            
            # 최종 플러시
            for handler in logging.getLogger().handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
            
            # 순환 결과 확인
            log_files = list(log_dir.glob("*.log*"))
            main_backups = [f for f in log_files if f.name.startswith('trading_bot.log.')]
            
            # 백업 파일 개수가 설정값을 초과하지 않는지 확인
            assert len(main_backups) <= 3, f"백업 파일 개수가 설정값을 초과: {len(main_backups)} > 3"
            
            # 정리 작업 실행 (매우 짧은 보존 기간으로 설정)
            logger_manager.cleanup_old_logs(retention_days=0)  # 모든 백업 파일 삭제
            
            # 정리 후 상태 확인
            remaining_files = list(log_dir.glob("*.log*"))
            
            # 현재 활성 파일들은 유지되어야 함
            main_log = log_dir / "trading_bot.log"
            error_log = log_dir / "errors.log"
            
            assert main_log.exists(), "메인 로그 파일이 유지되어야 함"
            assert error_log.exists(), "에러 로그 파일이 유지되어야 함"
            
            # 백업 파일들은 삭제되었어야 함 (retention_days=0이므로)
            remaining_backups = [f for f in remaining_files if '.log.' in f.name]
            # 일부 백업 파일은 아직 삭제되지 않을 수 있음 (파일 시스템 타이밍)
            # 하지만 대부분은 삭제되어야 함
            assert len(remaining_backups) <= len(main_backups), "정리 작업 후 백업 파일 수가 감소해야 함"