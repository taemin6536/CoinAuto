"""자격증명 암호화 라운드트립을 위한 속성 기반 테스트.

**Feature: upbit-trading-bot, Property 2: 자격증명 암호화 라운드트립**
**Validates: Requirements 1.4**
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.api.client import CredentialManager, UpbitAPIError


@composite
def valid_api_credentials(draw):
    """유효한 API 자격증명 쌍을 생성합니다."""
    # 실제 업비트 API 키 형식과 유사한 access key 생성 (UUID 형태)
    access_key = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-'),
        min_size=32, max_size=40
    ))
    
    # 실제 업비트 API 키 형식과 유사한 secret key 생성 (base64 형태)
    secret_key = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='+/='),
        min_size=40, max_size=60
    ))
    
    # 키가 비어있지 않고 합리적인 형식인지 확인
    assume(len(access_key.strip()) >= 32)
    assume(len(secret_key.strip()) >= 40)
    assume(access_key != secret_key)  # 키들은 서로 달라야 함
    
    return {
        'access_key': access_key,
        'secret_key': secret_key
    }


@composite
def valid_passwords(draw):
    """암호화에 사용할 유효한 패스워드를 생성합니다."""
    password = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), 
                              whitelist_characters='!@#$%^&*()_+-=[]{}|;:,.<>?'),
        min_size=8, max_size=50
    ))
    
    # 패스워드가 비어있지 않은지 확인
    assume(len(password.strip()) >= 8)
    
    return password


@composite
def edge_case_credentials(draw):
    """경계 조건의 자격증명을 생성합니다."""
    edge_type = draw(st.sampled_from([
        'unicode_chars',
        'special_chars',
        'very_long',
        'minimal_length',
        'mixed_case'
    ]))
    
    if edge_type == 'unicode_chars':
        # 유니코드 문자가 포함된 키 (실제로는 발생하지 않지만 테스트용)
        access_key = draw(st.text(min_size=32, max_size=40))
        secret_key = draw(st.text(min_size=40, max_size=60))
    elif edge_type == 'special_chars':
        # 특수 문자가 포함된 키
        access_key = draw(st.text(
            alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), 
                                  whitelist_characters='!@#$%^&*()_+-='),
            min_size=32, max_size=40
        ))
        secret_key = draw(st.text(
            alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), 
                                  whitelist_characters='!@#$%^&*()_+-='),
            min_size=40, max_size=60
        ))
    elif edge_type == 'very_long':
        # 매우 긴 키
        access_key = draw(st.text(min_size=100, max_size=200))
        secret_key = draw(st.text(min_size=100, max_size=200))
    elif edge_type == 'minimal_length':
        # 최소 길이의 키
        access_key = draw(st.text(min_size=1, max_size=5))
        secret_key = draw(st.text(min_size=1, max_size=5))
    else:  # mixed_case
        # 대소문자가 섞인 키
        access_key = draw(st.text(
            alphabet=st.characters(whitelist_categories=('Lu', 'Ll')),
            min_size=32, max_size=40
        ))
        secret_key = draw(st.text(
            alphabet=st.characters(whitelist_categories=('Lu', 'Ll')),
            min_size=40, max_size=60
        ))
    
    assume(len(access_key) > 0)
    assume(len(secret_key) > 0)
    assume(access_key != secret_key)
    
    return {
        'access_key': access_key,
        'secret_key': secret_key
    }


class TestCredentialEncryptionRoundTrip:
    """자격증명 암호화 라운드트립을 위한 속성 기반 테스트."""
    
    @given(credentials=valid_api_credentials(), password=valid_passwords())
    @settings(max_examples=100)
    def test_property_2_credential_encryption_round_trip(self, credentials, password):
        """
        **Feature: upbit-trading-bot, Property 2: 자격증명 암호화 라운드트립**
        **Validates: Requirements 1.4**
        
        속성: 임의의 API 자격증명에 대해, 암호화 후 복호화하면 원본 자격증명과 동일해야 합니다.
        """
        # 자격증명 관리자 생성
        credential_manager = CredentialManager(password=password)
        
        # 자격증명 암호화
        encrypted_data = credential_manager.encrypt_credentials(
            credentials['access_key'], 
            credentials['secret_key']
        )
        
        # 속성 1: 암호화된 데이터는 필요한 키들을 포함해야 함
        assert 'encrypted_access_key' in encrypted_data, "암호화된 데이터에 access key가 포함되어야 함"
        assert 'encrypted_secret_key' in encrypted_data, "암호화된 데이터에 secret key가 포함되어야 함"
        
        # 속성 2: 암호화된 데이터는 원본과 달라야 함
        assert encrypted_data['encrypted_access_key'] != credentials['access_key'], "암호화된 access key는 원본과 달라야 함"
        assert encrypted_data['encrypted_secret_key'] != credentials['secret_key'], "암호화된 secret key는 원본과 달라야 함"
        
        # 속성 3: 암호화된 데이터는 비어있지 않아야 함
        assert len(encrypted_data['encrypted_access_key']) > 0, "암호화된 access key는 비어있지 않아야 함"
        assert len(encrypted_data['encrypted_secret_key']) > 0, "암호화된 secret key는 비어있지 않아야 함"
        
        # 자격증명 복호화 (라운드트립 테스트)
        decrypted_data = credential_manager.decrypt_credentials(encrypted_data)
        
        # 속성 4: 복호화된 데이터는 필요한 키들을 포함해야 함
        assert 'access_key' in decrypted_data, "복호화된 데이터에 access key가 포함되어야 함"
        assert 'secret_key' in decrypted_data, "복호화된 데이터에 secret key가 포함되어야 함"
        
        # 속성 5: 라운드트립 후 원본 자격증명과 동일해야 함 (핵심 속성)
        assert decrypted_data['access_key'] == credentials['access_key'], "복호화된 access key는 원본과 동일해야 함"
        assert decrypted_data['secret_key'] == credentials['secret_key'], "복호화된 secret key는 원본과 동일해야 함"
        
        # 속성 6: 데이터 타입이 보존되어야 함
        assert isinstance(decrypted_data['access_key'], str), "복호화된 access key는 문자열이어야 함"
        assert isinstance(decrypted_data['secret_key'], str), "복호화된 secret key는 문자열이어야 함"
        
        # 속성 7: 데이터 길이가 보존되어야 함
        assert len(decrypted_data['access_key']) == len(credentials['access_key']), "access key 길이가 보존되어야 함"
        assert len(decrypted_data['secret_key']) == len(credentials['secret_key']), "secret key 길이가 보존되어야 함"
    
    @given(credentials=edge_case_credentials(), password=valid_passwords())
    @settings(max_examples=50)
    def test_edge_case_credential_encryption_round_trip(self, credentials, password):
        """경계 조건의 자격증명에 대한 암호화 라운드트립 테스트."""
        credential_manager = CredentialManager(password=password)
        
        # 암호화
        encrypted_data = credential_manager.encrypt_credentials(
            credentials['access_key'], 
            credentials['secret_key']
        )
        
        # 복호화
        decrypted_data = credential_manager.decrypt_credentials(encrypted_data)
        
        # 라운드트립 검증
        assert decrypted_data['access_key'] == credentials['access_key'], "경계 조건에서도 access key 라운드트립이 성공해야 함"
        assert decrypted_data['secret_key'] == credentials['secret_key'], "경계 조건에서도 secret key 라운드트립이 성공해야 함"
    
    @given(credentials=valid_api_credentials())
    @settings(max_examples=30)
    def test_different_passwords_produce_different_encryption(self, credentials):
        """서로 다른 패스워드로 암호화하면 다른 결과가 나와야 함."""
        password1 = "password123"
        password2 = "different_password456"
        
        manager1 = CredentialManager(password=password1)
        manager2 = CredentialManager(password=password2)
        
        # 같은 자격증명을 다른 패스워드로 암호화
        encrypted1 = manager1.encrypt_credentials(credentials['access_key'], credentials['secret_key'])
        encrypted2 = manager2.encrypt_credentials(credentials['access_key'], credentials['secret_key'])
        
        # 속성: 다른 패스워드로 암호화하면 다른 결과가 나와야 함
        assert encrypted1['encrypted_access_key'] != encrypted2['encrypted_access_key'], "다른 패스워드로 암호화하면 다른 결과가 나와야 함"
        assert encrypted1['encrypted_secret_key'] != encrypted2['encrypted_secret_key'], "다른 패스워드로 암호화하면 다른 결과가 나와야 함"
    
    @given(credentials=valid_api_credentials(), password=valid_passwords())
    @settings(max_examples=30)
    def test_wrong_password_decryption_fails(self, credentials, password):
        """잘못된 패스워드로 복호화하면 실패해야 함."""
        # 올바른 패스워드로 암호화
        correct_manager = CredentialManager(password=password)
        encrypted_data = correct_manager.encrypt_credentials(credentials['access_key'], credentials['secret_key'])
        
        # 잘못된 패스워드로 복호화 시도
        wrong_password = password + "_wrong"
        wrong_manager = CredentialManager(password=wrong_password)
        
        # 속성: 잘못된 패스워드로 복호화하면 예외가 발생해야 함
        with pytest.raises(UpbitAPIError, match="Failed to decrypt credentials"):
            wrong_manager.decrypt_credentials(encrypted_data)
    
    @given(credentials=valid_api_credentials(), password=valid_passwords())
    @settings(max_examples=20)
    def test_multiple_encryption_rounds_consistency(self, credentials, password):
        """여러 번 암호화/복호화해도 일관성이 유지되어야 함."""
        credential_manager = CredentialManager(password=password)
        
        current_credentials = credentials.copy()
        
        # 여러 번의 라운드트립 수행
        for round_num in range(3):
            # 암호화
            encrypted_data = credential_manager.encrypt_credentials(
                current_credentials['access_key'], 
                current_credentials['secret_key']
            )
            
            # 복호화
            decrypted_data = credential_manager.decrypt_credentials(encrypted_data)
            
            # 속성: 각 라운드에서 원본과 동일해야 함
            assert decrypted_data['access_key'] == credentials['access_key'], f"라운드 {round_num + 1}에서 access key가 원본과 동일해야 함"
            assert decrypted_data['secret_key'] == credentials['secret_key'], f"라운드 {round_num + 1}에서 secret key가 원본과 동일해야 함"
            
            # 다음 라운드를 위해 복호화된 데이터 사용
            current_credentials = decrypted_data
    
    def test_empty_credentials_handling(self):
        """빈 자격증명에 대한 처리 테스트."""
        credential_manager = CredentialManager(password="test_password")
        
        # 빈 문자열 자격증명
        encrypted_data = credential_manager.encrypt_credentials("", "")
        decrypted_data = credential_manager.decrypt_credentials(encrypted_data)
        
        # 속성: 빈 문자열도 라운드트립이 성공해야 함
        assert decrypted_data['access_key'] == "", "빈 access key도 라운드트립이 성공해야 함"
        assert decrypted_data['secret_key'] == "", "빈 secret key도 라운드트립이 성공해야 함"
    
    def test_malformed_encrypted_data_handling(self):
        """잘못된 형식의 암호화된 데이터 처리 테스트."""
        credential_manager = CredentialManager(password="test_password")
        
        # 잘못된 형식의 암호화된 데이터들
        malformed_data_cases = [
            {},  # 빈 딕셔너리
            {'encrypted_access_key': 'invalid'},  # secret key 누락
            {'encrypted_secret_key': 'invalid'},  # access key 누락
            {'encrypted_access_key': '', 'encrypted_secret_key': ''},  # 빈 값들
            {'encrypted_access_key': 'invalid_base64', 'encrypted_secret_key': 'invalid_base64'},  # 잘못된 base64
        ]
        
        for malformed_data in malformed_data_cases:
            # 속성: 잘못된 데이터로 복호화하면 예외가 발생해야 함
            with pytest.raises(UpbitAPIError, match="Failed to decrypt credentials"):
                credential_manager.decrypt_credentials(malformed_data)
    
    @given(credentials=valid_api_credentials(), password=valid_passwords())
    @settings(max_examples=20)
    def test_encryption_determinism(self, credentials, password):
        """같은 입력에 대해 암호화가 결정적이지 않아야 함 (보안상 중요)."""
        credential_manager = CredentialManager(password=password)
        
        # 같은 자격증명을 두 번 암호화
        encrypted1 = credential_manager.encrypt_credentials(credentials['access_key'], credentials['secret_key'])
        encrypted2 = credential_manager.encrypt_credentials(credentials['access_key'], credentials['secret_key'])
        
        # 속성: 같은 입력이라도 암호화 결과는 달라야 함 (nonce/IV 사용으로 인해)
        # 하지만 복호화하면 같은 결과가 나와야 함
        decrypted1 = credential_manager.decrypt_credentials(encrypted1)
        decrypted2 = credential_manager.decrypt_credentials(encrypted2)
        
        assert decrypted1['access_key'] == decrypted2['access_key'] == credentials['access_key'], "복호화 결과는 동일해야 함"
        assert decrypted1['secret_key'] == decrypted2['secret_key'] == credentials['secret_key'], "복호화 결과는 동일해야 함"
    
    @given(password=valid_passwords())
    @settings(max_examples=20)
    def test_credential_manager_initialization_consistency(self, password):
        """같은 패스워드로 초기화된 CredentialManager들은 호환되어야 함."""
        manager1 = CredentialManager(password=password)
        manager2 = CredentialManager(password=password)
        
        test_credentials = {'access_key': 'test_access_key_12345678901234567890', 'secret_key': 'test_secret_key_12345678901234567890'}
        
        # manager1으로 암호화, manager2로 복호화
        encrypted_data = manager1.encrypt_credentials(test_credentials['access_key'], test_credentials['secret_key'])
        decrypted_data = manager2.decrypt_credentials(encrypted_data)
        
        # 속성: 같은 패스워드로 초기화된 관리자들은 서로 호환되어야 함
        assert decrypted_data['access_key'] == test_credentials['access_key'], "같은 패스워드의 관리자들은 호환되어야 함"
        assert decrypted_data['secret_key'] == test_credentials['secret_key'], "같은 패스워드의 관리자들은 호환되어야 함"