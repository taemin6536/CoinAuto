#!/usr/bin/env python3
"""
간편한 봇 실행 스크립트

사용법:
    python run_bot.py                    # 기본 실행
    python run_bot.py --config custom.yaml  # 커스텀 설정
    python run_bot.py --dry-run          # 테스트 모드
    python run_bot.py --monitor          # 모니터링 모드
"""

import argparse
import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from upbit_trading_bot.config import ConfigManager
from upbit_trading_bot.api.client import UpbitAPIClient


def check_environment():
    """환경 설정 확인"""
    print("🔍 환경 설정 확인 중...")
    
    # Python 버전 확인
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 이상이 필요합니다.")
        return False
    
    # 필수 디렉토리 생성
    for directory in ['logs', 'data', 'config']:
        Path(directory).mkdir(exist_ok=True)
    
    print("✅ 환경 설정 완료")
    return True


def validate_config(config_path):
    """설정 파일 검증"""
    print(f"📋 설정 파일 검증 중: {config_path}")
    
    try:
        config_manager = ConfigManager(config_path, enable_hot_reload=False)
        config = config_manager.load_config()
        
        # 기본 검증
        trading_enabled = config.get('trading', {}).get('enabled', False)
        strategies = config.get('strategies', {}).get('enabled', [])
        
        print(f"   거래 활성화: {trading_enabled}")
        print(f"   활성 전략: {strategies if strategies else '없음'}")
        
        if trading_enabled and not strategies:
            print("⚠️  경고: 거래가 활성화되었지만 전략이 설정되지 않았습니다.")
        
        print("✅ 설정 파일 검증 완료")
        return True
        
    except Exception as e:
        print(f"❌ 설정 파일 오류: {e}")
        return False


def test_api_connection():
    """API 연결 테스트"""
    print("🔌 API 연결 테스트 중...")
    
    try:
        client = UpbitAPIClient()
        ticker = client.get_ticker('KRW-BTC')
        print(f"✅ API 연결 성공 - BTC 현재가: {ticker.trade_price:,}원")
        return True
    except Exception as e:
        print(f"❌ API 연결 실패: {e}")
        return False


def run_monitor_mode():
    """모니터링 모드 실행"""
    print("📊 모니터링 모드 시작...")
    
    try:
        client = UpbitAPIClient()
        markets = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP']
        
        print("\n=== 실시간 시세 모니터링 ===")
        while True:
            try:
                for market in markets:
                    ticker = client.get_ticker(market)
                    coin = market.split('-')[1]
                    print(f"{coin:>4}: {ticker.trade_price:>12,.0f}원 ({ticker.change_rate*100:+6.2f}%)")
                
                print("-" * 40)
                import time
                time.sleep(10)  # 10초마다 업데이트
                
            except KeyboardInterrupt:
                print("\n모니터링 종료")
                break
            except Exception as e:
                print(f"오류 발생: {e}")
                time.sleep(5)
                
    except Exception as e:
        print(f"❌ 모니터링 모드 실행 실패: {e}")


def main():
    parser = argparse.ArgumentParser(description='업비트 트레이딩 봇 실행')
    parser.add_argument('--config', default='config/default.yaml', help='설정 파일 경로')
    parser.add_argument('--dry-run', action='store_true', help='테스트 모드 (실제 거래 안함)')
    parser.add_argument('--monitor', action='store_true', help='모니터링 모드')
    parser.add_argument('--skip-checks', action='store_true', help='사전 검사 건너뛰기')
    
    args = parser.parse_args()
    
    print("🚀 업비트 트레이딩 봇 시작")
    print("=" * 50)
    
    # 모니터링 모드
    if args.monitor:
        run_monitor_mode()
        return
    
    # 사전 검사
    if not args.skip_checks:
        if not check_environment():
            sys.exit(1)
        
        if not validate_config(args.config):
            sys.exit(1)
        
        if not test_api_connection():
            print("⚠️  API 연결에 실패했지만 계속 진행합니다.")
    
    # 메인 봇 실행
    print("🤖 메인 트레이딩 봇 시작...")
    
    if args.dry_run:
        print("🧪 테스트 모드로 실행 중 (실제 거래 안함)")
        os.environ['DRY_RUN'] = 'true'
    
    try:
        # 메인 봇 실행
        from upbit_trading_bot.main import main as bot_main
        bot_main()
        
    except KeyboardInterrupt:
        print("\n👋 사용자에 의해 종료되었습니다.")
    except Exception as e:
        print(f"❌ 봇 실행 중 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()