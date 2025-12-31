#!/usr/bin/env python3
"""
API 연결 테스트 스크립트
"""

import os
import sys
from pathlib import Path

# .env 파일 로드
def load_env_file():
    env_path = Path('.env')
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def main():
    print("🔍 API 연결 테스트")
    print("=" * 30)
    
    # .env 파일 로드
    load_env_file()
    
    # API 키 확인
    access_key = os.getenv('UPBIT_ACCESS_KEY')
    secret_key = os.getenv('UPBIT_SECRET_KEY')
    
    print(f"Access Key: {access_key[:10]}...{access_key[-10:] if access_key else 'None'}")
    print(f"Secret Key: {secret_key[:10]}...{secret_key[-10:] if secret_key else 'None'}")
    
    if not access_key or not secret_key:
        print("❌ API 키가 설정되지 않았습니다!")
        return
    
    if access_key == 'XWsnwB9OkqX1xshSfAb4rDjHBXgO4pOoU7gbtht7':
        print("❌ 아직 템플릿 API 키를 사용하고 있습니다!")
        print("   .env 파일에서 본인의 실제 API 키로 변경하세요.")
        return
    
    # API 클라이언트 테스트
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from upbit_trading_bot.api.client import UpbitAPIClient
        
        print("🔌 API 연결 테스트 중...")
        client = UpbitAPIClient()
        
        # 인증 테스트
        if client.authenticate(access_key, secret_key):
            print("✅ API 인증 성공!")
            
            # 계좌 정보 조회 테스트
            try:
                accounts = client.get_accounts()
                print(f"✅ 계좌 정보 조회 성공! ({len(accounts)}개 계좌)")
                
                # KRW 잔고 확인
                krw_balance = 0
                for account in accounts:
                    if hasattr(account, 'currency') and account.currency == 'KRW':
                        krw_balance = account.balance
                        break
                    elif hasattr(account, 'market') and account.market == 'KRW':
                        krw_balance = account.balance
                        break
                
                print(f"💰 KRW 잔고: {krw_balance:,.0f}원")
                
                if krw_balance >= 50000:
                    print("✅ 거래 가능한 잔고가 있습니다!")
                    print("\n🚀 이제 실제 거래를 시작할 수 있습니다:")
                    print("   python start_safe_trading.py")
                else:
                    print("⚠️  잔고가 부족합니다. 최소 5만원이 필요합니다.")
                    
            except Exception as e:
                print(f"❌ 계좌 정보 조회 실패: {e}")
                
        else:
            print("❌ API 인증 실패!")
            print("   API 키가 올바른지 확인하세요.")
            
    except Exception as e:
        print(f"❌ API 클라이언트 오류: {e}")

if __name__ == "__main__":
    main()