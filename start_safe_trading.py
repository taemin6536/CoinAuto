#!/usr/bin/env python3
"""
안전한 실제 거래 시작 스크립트
5만원 계좌로 매우 보수적인 거래를 시작합니다.
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

# 환경변수 설정
load_env_file()
os.environ['DRY_RUN'] = 'false'  # 실제 거래 모드

def main():
    print("🚨 공격적인 테스트 거래 모드 시작 🚨")
    print("=" * 50)
    print("⚠️  주의사항:")
    print("   - 5만원 계좌로 공격적인 테스트 설정")
    print("   - 최대 포지션: 10,000원 (20%)")
    print("   - 손절매: 2% (약 500원)")
    print("   - 일일 손실 한도: 5% (2,500원)")
    print("   - 하루 최대 20번 거래")
    print("   - 매우 빠른 매매 (2초마다 평가)")
    print("   - 0.1% 변동으로도 거래 시도")
    print()
    
    # API 키 확인
    access_key = os.getenv('UPBIT_ACCESS_KEY')
    secret_key = os.getenv('UPBIT_SECRET_KEY')
    
    if not access_key or not secret_key:
        print("❌ API 키가 설정되지 않았습니다!")
        print("   .env 파일에서 UPBIT_ACCESS_KEY와 UPBIT_SECRET_KEY를 설정하세요.")
        return
    
    if access_key == 'XWsnwB9OkqX1xshSfAb4rDjHBXgO4pOoU7gbtht7':
        print("❌ 템플릿 API 키를 사용하고 있습니다!")
        print("   .env 파일에서 본인의 실제 API 키로 변경하세요.")
        return
    
    print("✅ API 키 설정 확인됨")
    print()
    
    # 사용자 확인
    response = input("정말로 실제 거래를 시작하시겠습니까? (yes/no): ")
    if response.lower() != 'yes':
        print("거래 취소됨")
        return
    
    print("🤖 공격적인 테스트 봇 시작...")
    
    # 공격적인 설정 파일 사용
    os.environ['CONFIG_PATH'] = 'config/test_safe.yaml'
    
    # 봇 실행
    from upbit_trading_bot.main import main as bot_main
    try:
        bot_main()
    except KeyboardInterrupt:
        print("\n👋 사용자에 의해 종료되었습니다.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()