"""
MySQL 데이터베이스 연결 및 기능 테스트.

데이터베이스 연결, 테이블 생성, 기본 CRUD 작업을 테스트합니다.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
import json

from upbit_trading_bot.data.database import DatabaseManager, get_db_manager, init_database


class TestDatabaseManager:
    """데이터베이스 매니저 테스트 클래스."""
    
    def test_database_manager_initialization(self):
        """데이터베이스 매니저 초기화 테스트."""
        db = DatabaseManager(
            host='localhost',
            port=3306,
            user='test_user',
            password='test_pass',
            database='test_db'
        )
        
        assert db.config['host'] == 'localhost'
        assert db.config['port'] == 3306
        assert db.config['user'] == 'test_user'
        assert db.config['password'] == 'test_pass'
        assert db.config['database'] == 'test_db'
    
    @patch('upbit_trading_bot.data.database.pymysql.connect')
    def test_database_connection_success(self, mock_connect):
        """데이터베이스 연결 성공 테스트."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        
        db = DatabaseManager()
        result = db.connect()
        
        assert result is True
        assert db._connection == mock_connection
        mock_connect.assert_called_once()
    
    @patch('upbit_trading_bot.data.database.pymysql.connect')
    def test_database_connection_failure(self, mock_connect):
        """데이터베이스 연결 실패 테스트."""
        mock_connect.side_effect = Exception("연결 실패")
        
        db = DatabaseManager()
        result = db.connect()
        
        assert result is False
        assert db._connection is None
    
    def test_database_disconnect(self):
        """데이터베이스 연결 종료 테스트."""
        db = DatabaseManager()
        mock_connection = MagicMock()
        db._connection = mock_connection
        
        db.disconnect()
        
        mock_connection.close.assert_called_once()
        assert db._connection is None
    
    @patch('upbit_trading_bot.data.database.pymysql.connect')
    def test_insert_trade_data(self, mock_connect):
        """거래 데이터 삽입 테스트."""
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_connection
        
        db = DatabaseManager()
        db.connect()
        
        trade_data = {
            'market': 'KRW-BTC',
            'side': 'bid',
            'price': 50000000.0,
            'volume': 0.001,
            'fee': 500.0,
            'timestamp': datetime.now(),
            'strategy_id': 'test_strategy'
        }
        
        result = db.insert_trade(trade_data)
        
        assert result is True
        mock_cursor.execute.assert_called_once()
    
    @patch('upbit_trading_bot.data.database.pymysql.connect')
    def test_insert_portfolio_snapshot(self, mock_connect):
        """포트폴리오 스냅샷 삽입 테스트."""
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_connection
        
        db = DatabaseManager()
        db.connect()
        
        snapshot_data = {
            'total_krw': 1000000.0,
            'total_btc': 0.02,
            'timestamp': datetime.now(),
            'positions': {'KRW-BTC': {'balance': 0.001, 'avg_price': 50000000}}
        }
        
        result = db.insert_portfolio_snapshot(snapshot_data)
        
        assert result is True
        mock_cursor.execute.assert_called_once()
        # positions가 JSON 문자열로 변환되었는지 확인
        assert isinstance(snapshot_data['positions'], str)
    
    @patch('upbit_trading_bot.data.database.pymysql.connect')
    def test_get_trades(self, mock_connect):
        """거래 기록 조회 테스트."""
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'market': 'KRW-BTC',
                'side': 'bid',
                'price': 50000000.0,
                'volume': 0.001,
                'fee': 500.0,
                'timestamp': datetime.now(),
                'strategy_id': 'test_strategy'
            }
        ]
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_connection
        
        db = DatabaseManager()
        db.connect()
        
        trades = db.get_trades(market='KRW-BTC', limit=10)
        
        assert len(trades) == 1
        assert trades[0]['market'] == 'KRW-BTC'
        mock_cursor.execute.assert_called_once()
        mock_cursor.fetchall.assert_called_once()
    
    @patch('upbit_trading_bot.data.database.pymysql.connect')
    def test_get_latest_portfolio_snapshot(self, mock_connect):
        """최신 포트폴리오 스냅샷 조회 테스트."""
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        positions_json = json.dumps({'KRW-BTC': {'balance': 0.001}})
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'total_krw': 1000000.0,
            'total_btc': 0.02,
            'timestamp': datetime.now(),
            'positions': positions_json
        }
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_connection
        
        db = DatabaseManager()
        db.connect()
        
        snapshot = db.get_latest_portfolio_snapshot()
        
        assert snapshot is not None
        assert snapshot['total_krw'] == 1000000.0
        assert isinstance(snapshot['positions'], dict)  # JSON이 파싱되었는지 확인
        mock_cursor.execute.assert_called_once()
        mock_cursor.fetchone.assert_called_once()
    
    @patch.dict('os.environ', {
        'DB_HOST': 'test_host',
        'DB_PORT': '3307',
        'DB_USER': 'test_user',
        'DB_PASSWORD': 'test_pass',
        'DB_NAME': 'test_db'
    })
    def test_get_db_manager_with_env_vars(self):
        """환경 변수를 사용한 데이터베이스 매니저 생성 테스트."""
        # 전역 변수 초기화
        import upbit_trading_bot.data.database
        upbit_trading_bot.data.database._db_manager = None
        
        db = get_db_manager()
        
        assert db.config['host'] == 'test_host'
        assert db.config['port'] == 3307
        assert db.config['user'] == 'test_user'
        assert db.config['password'] == 'test_pass'
        assert db.config['database'] == 'test_db'
    
    @patch('upbit_trading_bot.data.database.get_db_manager')
    def test_init_database(self, mock_get_db_manager):
        """데이터베이스 초기화 테스트."""
        mock_db = MagicMock()
        mock_db.connect.return_value = True
        mock_get_db_manager.return_value = mock_db
        
        init_database()
        
        mock_db.connect.assert_called_once()
        mock_db.create_tables.assert_called_once()
    
    @patch('upbit_trading_bot.data.database.get_db_manager')
    def test_init_database_connection_failure(self, mock_get_db_manager):
        """데이터베이스 초기화 연결 실패 테스트."""
        mock_db = MagicMock()
        mock_db.connect.return_value = False
        mock_get_db_manager.return_value = mock_db
        
        with pytest.raises(Exception, match="데이터베이스 초기화 실패"):
            init_database()