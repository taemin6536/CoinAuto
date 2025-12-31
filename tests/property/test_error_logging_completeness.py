"""오류 로깅 완전성을 위한 속성 기반 테스트.

**Feature: upbit-trading-bot, Property 22: 오류 로깅 완전성**
**Validates: Requirements 8.2**
"""

import pytest
import tempfile
import json
import logging
import traceback
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.logging.logger import LoggerManager, get_logger


@composite
def error_context_data(draw):
    """오류 컨텍스트 데이터 생성."""
    context = {}
    
    # 기본 컨텍스트 필드들
    context['component'] = draw(st.sampled_from([
        'api_client', 'market_data', 'order_manager', 'risk_manager',
        'portfolio_manager', 'strategy_manager', 'config_manager'
    ]))
    
    context['operation'] = draw(st.sampled_from([
        'place_order', 'cancel_order', 'fetch_balance', 'get_ticker',
        'evaluate_strategy', 'update_portfolio', 'load_config'
    ]))
    
    # 선택적 컨텍스트 필드들
    if draw(st.booleans()):
        context['market'] = draw(st.sampled_from([
            'KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT'
        ]))
    
    if draw(st.booleans()):
        context['order_id'] = draw(st.text(min_size=10, max_size=50, alphabet=st.characters(min_codepoint=48, max_codepoint=122)))
    
    if draw(st.booleans()):
        context['user_id'] = draw(st.text(min_size=5, max_size=20, alphabet=st.characters(min_codepoint=48, max_codepoint=122)))
    
    if draw(st.booleans()):
        context['amount'] = draw(st.floats(min_value=0.001, max_value=1000000.0))
    
    if draw(st.booleans()):
        context['price'] = draw(st.floats(min_value=1.0, max_value=100000000.0))
    
    # 추가 메타데이터
    if draw(st.booleans()):
        context['request_id'] = draw(st.text(min_size=8, max_size=32, alphabet=st.characters(min_codepoint=48, max_codepoint=122)))
    
    if draw(st.booleans()):
        context['session_id'] = draw(st.text(min_size=8, max_size=32, alphabet=st.characters(min_codepoint=48, max_codepoint=122)))
    
    return context


@composite
def exception_data(draw):
    """테스트용 예외 데이터 생성."""
    exception_types = [
        ValueError, TypeError, KeyError, AttributeError,
        ConnectionError, TimeoutError, RuntimeError
    ]
    
    exception_type = draw(st.sampled_from(exception_types))
    # 안전한 ASCII 문자만 사용하여 오류 메시지 생성
    error_message = draw(st.text(
        min_size=10, 
        max_size=100,
        alphabet=st.characters(min_codepoint=32, max_codepoint=126)  # 출력 가능한 ASCII 문자만
    ))
    
    # 유효한 에러 메시지인지 확인
    assume(error_message.strip() != "")
    assume(not error_message.isspace())
    assume('"' not in error_message)  # 따옴표 제외
    assume("'" not in error_message)  # 작은따옴표 제외
    assume('\\' not in error_message)  # 백슬래시 제외
    
    return exception_type, error_message


class TestErrorLoggingCompleteness:
    """오류 로깅 완전성을 위한 속성 기반 테스트."""
    
    @given(
        context_data=error_context_data(),
        exception_data=exception_data()
    )
    @settings(max_examples=20, deadline=10000)
    def test_property_22_error_logging_completeness(self, context_data, exception_data):
        """
        **Feature: upbit-trading-bot, Property 22: 오류 로깅 완전성**
        **Validates: Requirements 8.2**
        
        속성: 모든 오류 조건에 대해, 시스템은 스택 트레이스와 충분한 컨텍스트 정보를 디버깅을 위해 로그에 기록해야 한다.
        """
        exception_type, error_message = exception_data
        
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            # 구조화된 JSON 로깅을 사용하는 LoggerManager 생성
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="DEBUG",
                console_output=False,  # 테스트에서는 콘솔 출력 비활성화
                structured_format=True
            )
            
            # 테스트용 로거 생성
            test_logger = logger_manager.get_logger("test_component")
            
            # 예외 생성 및 발생
            test_exception = exception_type(error_message)
            
            try:
                # 의도적으로 예외 발생시키기 (스택 트레이스 생성을 위해)
                def inner_function():
                    def nested_function():
                        raise test_exception
                    nested_function()
                
                inner_function()
                
            except Exception as caught_exception:
                # 오류를 컨텍스트와 함께 로깅
                logger_manager.log_error_with_context(caught_exception, context_data)
                
                # 추가로 일반 로거를 통한 오류 로깅도 테스트
                test_logger.error(
                    f"Test error in {context_data.get('component', 'unknown')}: {str(caught_exception)}",
                    extra=context_data,
                    exc_info=True
                )
            
            # 로그 파일들이 생성되었는지 확인
            log_files = list(log_dir.glob("*.log"))
            assert len(log_files) > 0, "로그 파일이 생성되어야 함"
            
            # 에러 로그 파일 확인
            error_log_file = log_dir / "errors.log"
            assert error_log_file.exists(), "errors.log 파일이 생성되어야 함"
            
            # 로그 내용 읽기 및 파싱
            log_entries = []
            with open(error_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            log_entry = json.loads(line)
                            log_entries.append(log_entry)
                        except json.JSONDecodeError:
                            # JSON이 아닌 로그 라인은 무시 (구조화되지 않은 로그일 수 있음)
                            pass
            
            # 속성 1: 최소 하나의 오류 로그 엔트리가 있어야 함
            error_entries = [entry for entry in log_entries if entry.get('level') == 'ERROR']
            assert len(error_entries) > 0, "최소 하나의 ERROR 레벨 로그 엔트리가 있어야 함"
            
            # 가장 최근 오류 엔트리 선택
            latest_error = error_entries[-1]
            
            # 속성 2: 오류 메시지가 포함되어야 함
            assert 'message' in latest_error, "로그 엔트리에 'message' 필드가 있어야 함"
            # 오류 메시지가 로그 메시지에 포함되어 있는지 확인 (문자열 이스케이프 고려)
            log_message = latest_error['message']
            assert error_message in log_message or repr(error_message) in log_message, \
                f"오류 메시지가 로그에 포함되어야 함: {error_message}, 실제 로그: {log_message}"
            
            # 속성 3: 예외 정보가 포함되어야 함
            assert 'exception' in latest_error, "로그 엔트리에 'exception' 필드가 있어야 함"
            exception_info = latest_error['exception']
            
            # 속성 4: 예외 타입이 올바르게 기록되어야 함
            assert 'type' in exception_info, "예외 정보에 'type' 필드가 있어야 함"
            assert exception_info['type'] == exception_type.__name__, f"예외 타입이 올바르게 기록되어야 함: {exception_type.__name__}"
            
            # 속성 5: 예외 메시지가 올바르게 기록되어야 함
            assert 'message' in exception_info, "예외 정보에 'message' 필드가 있어야 함"
            recorded_message = exception_info['message']
            # 예외 메시지는 str() 변환으로 인해 따옴표가 추가될 수 있음
            assert recorded_message == error_message or recorded_message == repr(error_message), \
                f"예외 메시지가 올바르게 기록되어야 함: 예상='{error_message}', 실제='{recorded_message}'"
            
            # 속성 6: 스택 트레이스가 포함되어야 함 (요구사항 8.2)
            assert 'traceback' in exception_info, "예외 정보에 'traceback' 필드가 있어야 함"
            traceback_lines = exception_info['traceback']
            assert isinstance(traceback_lines, list), "스택 트레이스는 리스트 형태여야 함"
            assert len(traceback_lines) > 0, "스택 트레이스가 비어있지 않아야 함"
            
            # 속성 7: 스택 트레이스에 함수 이름들이 포함되어야 함
            traceback_text = ''.join(traceback_lines)
            assert 'inner_function' in traceback_text, "스택 트레이스에 'inner_function'이 포함되어야 함"
            assert 'nested_function' in traceback_text, "스택 트레이스에 'nested_function'이 포함되어야 함"
            
            # 속성 8: 기본 로그 메타데이터가 포함되어야 함
            required_fields = ['timestamp', 'level', 'logger', 'module', 'function', 'line']
            for field in required_fields:
                assert field in latest_error, f"로그 엔트리에 '{field}' 필드가 있어야 함"
            
            # 속성 9: 타임스탬프가 유효한 ISO 형식이어야 함
            timestamp_str = latest_error['timestamp']
            try:
                datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                pytest.fail(f"타임스탬프가 유효한 ISO 형식이어야 함: {timestamp_str}")
            
            # 속성 10: 컨텍스트 정보가 포함되어야 함 (요구사항 8.2)
            # extra 필드 또는 직접 필드로 컨텍스트가 포함되어야 함
            context_found = False
            
            # extra 필드에서 컨텍스트 확인
            if 'extra' in latest_error:
                extra_data = latest_error['extra']
                for key, value in context_data.items():
                    if key in extra_data and extra_data[key] == value:
                        context_found = True
                        break
            
            # 직접 필드에서 컨텍스트 확인
            if not context_found:
                for key, value in context_data.items():
                    if key in latest_error and latest_error[key] == value:
                        context_found = True
                        break
            
            assert context_found, f"컨텍스트 정보가 로그에 포함되어야 함: {context_data}"
            
            # 속성 11: 로그 레벨이 ERROR여야 함
            assert latest_error['level'] == 'ERROR', "오류 로그의 레벨이 'ERROR'여야 함"
    
    def test_error_logging_with_nested_exceptions(self):
        """중첩된 예외에 대한 오류 로깅 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="DEBUG",
                console_output=False,
                structured_format=True
            )
            
            test_logger = logger_manager.get_logger("test_nested_errors")
            
            # 중첩된 예외 생성
            try:
                try:
                    # 내부 예외
                    raise ValueError("Inner exception message")
                except ValueError as inner_ex:
                    # 외부 예외 (내부 예외를 감싸는)
                    raise RuntimeError("Outer exception message") from inner_ex
            except Exception as caught_exception:
                # 오류 로깅
                context = {
                    'component': 'test_component',
                    'operation': 'nested_exception_test',
                    'test_case': 'nested_exceptions'
                }
                logger_manager.log_error_with_context(caught_exception, context)
            
            # 로그 검증
            error_log_file = log_dir / "errors.log"
            assert error_log_file.exists()
            
            with open(error_log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
                log_entries = [json.loads(line) for line in log_content.strip().split('\n') if line.strip()]
            
            error_entries = [entry for entry in log_entries if entry.get('level') == 'ERROR']
            assert len(error_entries) > 0
            
            latest_error = error_entries[-1]
            
            # 중첩된 예외 정보 확인
            assert 'exception' in latest_error
            exception_info = latest_error['exception']
            
            # 외부 예외 정보
            assert exception_info['type'] == 'RuntimeError'
            assert 'Outer exception message' in exception_info['message']
            
            # 스택 트레이스에 두 예외 모두 포함되어야 함
            traceback_text = ''.join(exception_info['traceback'])
            assert 'RuntimeError' in traceback_text
            assert 'ValueError' in traceback_text
            assert 'Inner exception message' in traceback_text
            assert 'Outer exception message' in traceback_text
    
    def test_error_logging_without_exception_info(self):
        """예외 정보 없이 오류 로깅하는 경우 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="DEBUG",
                console_output=False,
                structured_format=True
            )
            
            test_logger = logger_manager.get_logger("test_no_exception")
            
            # 예외 정보 없이 오류 로깅
            context = {
                'component': 'api_client',
                'operation': 'fetch_data',
                'error_code': 'NETWORK_ERROR',
                'retry_count': 3
            }
            
            test_logger.error("Network connection failed", extra=context)
            
            # 로그 검증
            error_log_file = log_dir / "errors.log"
            assert error_log_file.exists()
            
            with open(error_log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
                log_entries = [json.loads(line) for line in log_content.strip().split('\n') if line.strip()]
            
            error_entries = [entry for entry in log_entries if entry.get('level') == 'ERROR']
            assert len(error_entries) > 0
            
            latest_error = error_entries[-1]
            
            # 기본 필드들 확인
            assert latest_error['level'] == 'ERROR'
            assert 'Network connection failed' in latest_error['message']
            assert 'timestamp' in latest_error
            
            # 컨텍스트 정보 확인
            assert 'extra' in latest_error
            extra_data = latest_error['extra']
            assert extra_data['component'] == 'api_client'
            assert extra_data['operation'] == 'fetch_data'
            assert extra_data['error_code'] == 'NETWORK_ERROR'
            assert extra_data['retry_count'] == 3
            
            # 예외 정보는 없어야 함 (exc_info=False이므로)
            assert 'exception' not in latest_error
    
    def test_critical_error_logging(self):
        """CRITICAL 레벨 오류 로깅 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="DEBUG",
                console_output=False,
                structured_format=True
            )
            
            test_logger = logger_manager.get_logger("test_critical")
            
            # CRITICAL 오류 생성
            try:
                raise SystemError("Critical system failure")
            except Exception as e:
                context = {
                    'component': 'system_core',
                    'operation': 'startup',
                    'severity': 'critical',
                    'requires_immediate_attention': True
                }
                
                test_logger.critical(
                    f"Critical system error: {str(e)}",
                    extra=context,
                    exc_info=True
                )
            
            # 로그 검증
            error_log_file = log_dir / "errors.log"
            assert error_log_file.exists()
            
            with open(error_log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
                log_entries = [json.loads(line) for line in log_content.strip().split('\n') if line.strip()]
            
            critical_entries = [entry for entry in log_entries if entry.get('level') == 'CRITICAL']
            assert len(critical_entries) > 0, "CRITICAL 레벨 로그 엔트리가 있어야 함"
            
            latest_critical = critical_entries[-1]
            
            # CRITICAL 레벨 확인
            assert latest_critical['level'] == 'CRITICAL'
            assert 'Critical system failure' in latest_critical['message']
            
            # 예외 정보 확인
            assert 'exception' in latest_critical
            exception_info = latest_critical['exception']
            assert exception_info['type'] == 'SystemError'
            assert exception_info['message'] == 'Critical system failure'
            
            # 컨텍스트 정보 확인
            assert 'extra' in latest_critical
            extra_data = latest_critical['extra']
            assert extra_data['severity'] == 'critical'
            assert extra_data['requires_immediate_attention'] is True
    
    def test_log_file_creation_and_structure(self):
        """로그 파일 생성 및 구조 테스트."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            logger_manager = LoggerManager(
                log_dir=str(log_dir),
                log_level="INFO",
                console_output=False,
                structured_format=True
            )
            
            test_logger = logger_manager.get_logger("test_structure")
            
            # 다양한 레벨의 로그 생성
            test_logger.info("Info message")
            test_logger.warning("Warning message")
            test_logger.error("Error message")
            
            # 로그 파일들이 생성되었는지 확인
            main_log_file = log_dir / "trading_bot.log"
            error_log_file = log_dir / "errors.log"
            
            assert main_log_file.exists(), "메인 로그 파일이 생성되어야 함"
            assert error_log_file.exists(), "에러 로그 파일이 생성되어야 함"
            
            # 메인 로그 파일에는 모든 레벨의 로그가 있어야 함
            with open(main_log_file, 'r', encoding='utf-8') as f:
                main_content = f.read()
                assert 'Info message' in main_content
                assert 'Warning message' in main_content
                assert 'Error message' in main_content
            
            # 에러 로그 파일에는 ERROR 레벨만 있어야 함
            with open(error_log_file, 'r', encoding='utf-8') as f:
                error_content = f.read()
                assert 'Error message' in error_content
                assert 'Info message' not in error_content
                assert 'Warning message' not in error_content