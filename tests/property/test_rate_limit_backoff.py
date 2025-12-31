"""속도 제한 백오프 동작을 위한 속성 기반 테스트.

**Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
**Validates: Requirements 1.3**
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite
import requests

from upbit_trading_bot.api.client import UpbitAPIClient, UpbitAPIError, RateLimiter


@composite
def rate_limit_scenarios(draw):
    """속도 제한 시나리오를 생성합니다."""
    # 연속 실패 횟수 (1-5회)
    consecutive_failures = draw(st.integers(min_value=1, max_value=5))
    
    # 최대 재시도 횟수 (1-10회)
    max_retries = draw(st.integers(min_value=1, max_value=10))
    
    # 기본 백오프 지연 시간 (0.1-2.0초)
    base_delay = draw(st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False))
    
    return {
        'consecutive_failures': consecutive_failures,
        'max_retries': max_retries,
        'base_delay': base_delay
    }


@composite
def api_endpoints(draw):
    """다양한 API 엔드포인트를 생성합니다."""
    endpoints = [
        '/v1/accounts',
        '/v1/ticker',
        '/v1/orders',
        '/v1/order',
        '/v1/market/all'
    ]
    return draw(st.sampled_from(endpoints))


@composite
def http_methods(draw):
    """HTTP 메서드를 생성합니다."""
    methods = ['GET', 'POST', 'DELETE']
    return draw(st.sampled_from(methods))


class TestRateLimitBackoffBehavior:
    """속도 제한 백오프 동작을 위한 속성 기반 테스트."""
    
    @given(scenario=rate_limit_scenarios())
    @settings(max_examples=100)
    def test_property_4_exponential_backoff_calculation(self, scenario):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: 연속된 실패에 대해 지수적 백오프 지연이 올바르게 계산되어야 합니다.
        """
        rate_limiter = RateLimiter()
        rate_limiter.consecutive_failures = scenario['consecutive_failures']
        
        # 백오프 지연 계산
        backoff_delay = rate_limiter.get_backoff_delay()
        
        if scenario['consecutive_failures'] == 0:
            # 실패가 없으면 지연이 없어야 함
            assert backoff_delay == 0.0, "실패가 없을 때는 백오프 지연이 0이어야 합니다"
        else:
            # 지수적 백오프: 2^(failures-1)
            expected_delay = min(2 ** (scenario['consecutive_failures'] - 1), 60.0)
            assert backoff_delay == expected_delay, f"백오프 지연이 예상값 {expected_delay}와 일치해야 합니다"
            
            # 지연 시간이 합리적인 범위 내에 있어야 함
            assert 0 < backoff_delay <= 60.0, "백오프 지연은 0초 초과 60초 이하여야 합니다"
    
    @given(scenario=rate_limit_scenarios())
    @settings(max_examples=50)
    def test_property_4_retry_limit_enforcement(self, scenario):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: 최대 재시도 횟수에 도달하면 더 이상 재시도하지 않아야 합니다.
        """
        rate_limiter = RateLimiter()
        rate_limiter.max_retries = scenario['max_retries']
        
        # 최대 재시도 횟수까지는 재시도 가능해야 함
        for failure_count in range(scenario['max_retries']):
            rate_limiter.consecutive_failures = failure_count
            assert rate_limiter.should_retry() is True, f"실패 {failure_count}회에서는 재시도가 가능해야 합니다"
        
        # 최대 재시도 횟수를 초과하면 재시도 불가능해야 함
        rate_limiter.consecutive_failures = scenario['max_retries']
        assert rate_limiter.should_retry() is False, "최대 재시도 횟수에 도달하면 재시도가 불가능해야 합니다"
        
        # 최대 재시도 횟수를 더 초과해도 재시도 불가능해야 함
        rate_limiter.consecutive_failures = scenario['max_retries'] + 1
        assert rate_limiter.should_retry() is False, "최대 재시도 횟수를 초과하면 재시도가 불가능해야 합니다"
    
    @given(endpoint=api_endpoints(), method=http_methods())
    @settings(max_examples=100)
    def test_property_4_rate_limit_response_handling(self, endpoint, method):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: 429 응답 코드를 받으면 백오프 후 재시도해야 합니다.
        """
        client = UpbitAPIClient()
        client.access_key = "test_access_key"
        client.secret_key = "test_secret_key"
        
        # 429 응답을 시뮬레이션
        with patch.object(client.session, 'get') as mock_get, \
             patch.object(client.session, 'post') as mock_post, \
             patch.object(client.session, 'delete') as mock_delete, \
             patch('time.sleep') as mock_sleep, \
             patch.object(client, '_generate_auth_header') as mock_auth:
            
            mock_auth.return_value = "Bearer test_token"
            
            # 첫 번째 요청은 429 (Rate Limit), 두 번째 요청은 성공
            rate_limit_response = Mock()
            rate_limit_response.status_code = 429
            rate_limit_response.content = b'{"error": {"message": "Rate limit exceeded"}}'
            rate_limit_response.json.return_value = {"error": {"message": "Rate limit exceeded", "name": "RATE_LIMIT_EXCEEDED"}}
            
            success_response = Mock()
            success_response.status_code = 200
            success_response.json.return_value = {"result": "success"}
            
            # HTTP 메서드에 따라 적절한 mock 설정
            if method == 'GET':
                mock_get.side_effect = [rate_limit_response, success_response]
            elif method == 'POST':
                mock_post.side_effect = [rate_limit_response, success_response]
            elif method == 'DELETE':
                mock_delete.side_effect = [rate_limit_response, success_response]
            
            try:
                # API 요청 실행
                if method == 'GET':
                    response = client._make_authenticated_request(method, endpoint)
                elif method == 'POST':
                    response = client._make_authenticated_request(method, endpoint, data={'test': 'data'})
                elif method == 'DELETE':
                    response = client._make_authenticated_request(method, endpoint, params={'test': 'param'})
                
                # 속성 검증: 성공적으로 응답을 받아야 함
                assert response.status_code == 200, "백오프 후 재시도가 성공해야 합니다"
                
                # 속성 검증: sleep이 호출되어야 함 (백오프 지연)
                assert mock_sleep.called, "속도 제한 시 백오프 지연이 발생해야 합니다"
                
                # 속성 검증: 백오프 지연 시간이 양수여야 함
                sleep_calls = mock_sleep.call_args_list
                for call in sleep_calls:
                    delay = call[0][0]  # sleep의 첫 번째 인자
                    assert delay > 0, "백오프 지연 시간은 양수여야 합니다"
                    assert delay <= 60.0, "백오프 지연 시간은 60초를 초과하지 않아야 합니다"
                
            except UpbitAPIError as e:
                # 최대 재시도 횟수에 도달한 경우에만 예외가 발생해야 함
                assert "Rate limit exceeded" in str(e), "속도 제한 예외 메시지가 포함되어야 합니다"
    
    @given(failure_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50)
    def test_property_4_backoff_progression(self, failure_count):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: 연속 실패 횟수가 증가할수록 백오프 지연이 지수적으로 증가해야 합니다.
        """
        rate_limiter = RateLimiter()
        
        previous_delay = 0
        for i in range(1, failure_count + 1):
            rate_limiter.consecutive_failures = i
            current_delay = rate_limiter.get_backoff_delay()
            
            # 지연 시간이 이전보다 크거나 같아야 함 (지수적 증가 또는 최대값 도달)
            assert current_delay >= previous_delay, f"백오프 지연이 단조 증가해야 합니다 (실패 {i}회)"
            
            # 예상 지연 시간 계산
            expected_delay = min(2 ** (i - 1), 60.0)
            assert current_delay == expected_delay, f"실패 {i}회에서 백오프 지연이 {expected_delay}초여야 합니다"
            
            previous_delay = current_delay
    
    @given(scenario=rate_limit_scenarios())
    @settings(max_examples=30)
    def test_property_4_success_resets_failure_count(self, scenario):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: 성공적인 요청 후에는 연속 실패 횟수가 리셋되어야 합니다.
        """
        rate_limiter = RateLimiter()
        
        # 실패 횟수 설정
        rate_limiter.consecutive_failures = scenario['consecutive_failures']
        initial_failures = rate_limiter.consecutive_failures
        
        # 성공 기록
        rate_limiter.record_success()
        
        # 속성 검증: 연속 실패 횟수가 0으로 리셋되어야 함
        assert rate_limiter.consecutive_failures == 0, "성공 후 연속 실패 횟수가 0으로 리셋되어야 합니다"
        
        # 속성 검증: 백오프 지연이 0이 되어야 함
        backoff_delay = rate_limiter.get_backoff_delay()
        assert backoff_delay == 0.0, "성공 후 백오프 지연이 0이 되어야 합니다"
        
        # 속성 검증: 재시도 가능 상태가 되어야 함
        assert rate_limiter.should_retry() is True, "성공 후 재시도가 가능해야 합니다"
    
    @given(scenario=rate_limit_scenarios())
    @settings(max_examples=30)
    def test_property_4_failure_increments_count(self, scenario):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: 실패한 요청은 연속 실패 횟수를 증가시켜야 합니다.
        """
        rate_limiter = RateLimiter()
        initial_failures = 0
        rate_limiter.consecutive_failures = initial_failures
        
        # 여러 번 실패 기록
        for i in range(1, scenario['consecutive_failures'] + 1):
            rate_limiter.record_failure()
            
            # 속성 검증: 연속 실패 횟수가 증가해야 함
            assert rate_limiter.consecutive_failures == i, f"실패 {i}회 후 연속 실패 횟수가 {i}여야 합니다"
            
            # 속성 검증: 백오프 지연이 증가해야 함
            backoff_delay = rate_limiter.get_backoff_delay()
            expected_delay = min(2 ** (i - 1), 60.0)
            assert backoff_delay == expected_delay, f"실패 {i}회 후 백오프 지연이 {expected_delay}초여야 합니다"
    
    def test_property_4_rate_limiter_initialization(self):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: RateLimiter는 올바른 초기 상태로 시작해야 합니다.
        """
        rate_limiter = RateLimiter()
        
        # 속성 검증: 초기 연속 실패 횟수는 0이어야 함
        assert rate_limiter.consecutive_failures == 0, "초기 연속 실패 횟수는 0이어야 합니다"
        
        # 속성 검증: 초기 백오프 지연은 0이어야 함
        assert rate_limiter.get_backoff_delay() == 0.0, "초기 백오프 지연은 0이어야 합니다"
        
        # 속성 검증: 초기에는 재시도 가능해야 함
        assert rate_limiter.should_retry() is True, "초기에는 재시도가 가능해야 합니다"
        
        # 속성 검증: 기본 설정값들이 올바르게 설정되어야 함
        assert rate_limiter.max_requests_per_second > 0, "초당 최대 요청 수는 양수여야 합니다"
        assert rate_limiter.min_interval > 0, "최소 간격은 양수여야 합니다"
        assert rate_limiter.max_retries > 0, "최대 재시도 횟수는 양수여야 합니다"
    
    @given(requests_per_second=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=30)
    def test_property_4_rate_limiter_configuration(self, requests_per_second):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: RateLimiter는 설정된 속도 제한을 올바르게 적용해야 합니다.
        """
        rate_limiter = RateLimiter(max_requests_per_second=requests_per_second)
        
        # 속성 검증: 설정된 값이 올바르게 저장되어야 함
        assert rate_limiter.max_requests_per_second == requests_per_second, "설정된 초당 최대 요청 수가 저장되어야 합니다"
        
        # 속성 검증: 최소 간격이 올바르게 계산되어야 함
        expected_min_interval = 1.0 / requests_per_second
        assert abs(rate_limiter.min_interval - expected_min_interval) < 1e-10, "최소 간격이 올바르게 계산되어야 합니다"
        
        # 속성 검증: 최소 간격이 양수여야 함
        assert rate_limiter.min_interval > 0, "최소 간격은 양수여야 합니다"
    
    def test_property_4_wait_if_needed_timing(self):
        """
        **Feature: upbit-trading-bot, Property 4: Rate Limit Backoff Behavior**
        **Validates: Requirements 1.3**
        
        속성: wait_if_needed는 필요한 경우에만 대기해야 합니다.
        """
        rate_limiter = RateLimiter(max_requests_per_second=10.0)  # 0.1초 간격
        
        # 첫 번째 호출 - 대기 없음
        start_time = time.time()
        rate_limiter.wait_if_needed()
        first_call_time = time.time()
        
        # 즉시 두 번째 호출 - 대기 발생해야 함
        rate_limiter.wait_if_needed()
        second_call_time = time.time()
        
        # 속성 검증: 두 번째 호출에서 최소 간격만큼 대기했어야 함
        actual_interval = second_call_time - first_call_time
        expected_min_interval = rate_limiter.min_interval
        
        # 약간의 오차 허용 (시스템 지연 등)
        assert actual_interval >= expected_min_interval * 0.9, f"실제 간격 {actual_interval}이 최소 간격 {expected_min_interval}보다 작습니다"
        
        # 충분한 시간 후 호출 - 대기 없음
        time.sleep(rate_limiter.min_interval * 2)
        third_call_start = time.time()
        rate_limiter.wait_if_needed()
        third_call_end = time.time()
        
        # 속성 검증: 충분한 시간 후에는 대기하지 않아야 함
        third_call_duration = third_call_end - third_call_start
        assert third_call_duration < rate_limiter.min_interval * 0.5, "충분한 시간 후에는 대기하지 않아야 합니다"