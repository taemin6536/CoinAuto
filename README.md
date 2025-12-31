# Upbit Trading Bot

업비트 자동매매 프로그램 - A modular cryptocurrency trading bot for Upbit exchange.

## Features

- **Secure API Integration**: Encrypted credential storage and secure authentication
- **Real-time Market Data**: WebSocket-based real-time price and orderbook monitoring
- **Modular Strategy System**: Pluggable trading strategies with hot-reload configuration
- **Risk Management**: Comprehensive risk controls including stop-loss, position limits, and daily limits
- **Portfolio Tracking**: Real-time portfolio monitoring and performance analytics
- **Property-Based Testing**: Comprehensive testing with property-based test coverage

## Quick Start

### Prerequisites

- Python 3.8 or higher
- Upbit API keys (Access Key and Secret Key)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd upbit-trading-bot
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up configuration:
```bash
cp .env.template .env
# Edit .env with your API keys and preferences
```

5. Initialize database:
```bash
python -m upbit_trading_bot.database.init_db
```

### Configuration

The bot uses YAML configuration files located in the `config/` directory:

- `config/default.yaml`: Main configuration file
- `config/strategies/`: Individual strategy configurations

Copy `.env.template` to `.env` and configure your API keys and preferences.

### Running the Bot

```bash
python -m upbit_trading_bot.main
```

Or using the console script:
```bash
upbit-bot
```

## Architecture

The bot follows a modular architecture with the following components:

- **API Client**: Handles all Upbit API communications
- **Market Data Handler**: Real-time data collection and processing
- **Strategy Manager**: Trading strategy execution and management
- **Order Manager**: Order creation, execution, and tracking
- **Risk Manager**: Risk controls and position monitoring
- **Portfolio Manager**: Portfolio tracking and performance analytics
- **Config Manager**: Configuration management with hot-reload

## Development

### Setting up Development Environment

1. Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

2. Install pre-commit hooks:
```bash
pre-commit install
```

3. Run tests:
```bash
pytest
```

4. Run property-based tests:
```bash
pytest -m property
```

### Code Quality

The project uses several tools for code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking
- **bandit**: Security analysis

Run all quality checks:
```bash
pre-commit run --all-files
```

### Testing

The project includes both unit tests and property-based tests:

- Unit tests: `pytest tests/unit/`
- Property tests: `pytest tests/property/`
- Integration tests: `pytest tests/integration/`

## Configuration

### API Configuration

Set your Upbit API credentials in the `.env` file:

```env
UPBIT_ACCESS_KEY=your_access_key_here
UPBIT_SECRET_KEY=your_secret_key_here
```

### Strategy Configuration

Strategies are configured in YAML files under `config/strategies/`. Each strategy can be enabled/disabled and configured independently.

### Risk Management

Configure risk parameters in `config/default.yaml`:

```yaml
risk:
  stop_loss_percentage: 0.05  # 5%
  daily_loss_limit: 0.02  # 2%
  max_daily_trades: 50
  position_size_limit: 0.2  # 20% per position
```

## Strategies

The bot comes with built-in trading strategies:

### 1. Simple Moving Average Crossover (SMA)
- **매수 신호**: 단기 이동평균선이 장기 이동평균선을 상향 돌파
- **매도 신호**: 단기 이동평균선이 장기 이동평균선을 하향 돌파
- **설정 파일**: `config/strategies/sma_crossover.yaml`
- **문서**: [SMA 전략 가이드](docs/strategies/sma_crossover.md)

### 2. RSI Momentum Strategy
- **매수 신호**: RSI < 30 (과매도 구간)
- **매도 신호**: RSI > 70 (과매수 구간)
- **설정 파일**: `config/strategies/rsi_momentum.yaml`
- **문서**: [RSI 전략 가이드](docs/strategies/rsi_momentum.md)

### Strategy Templates
사전 구성된 전략 템플릿을 제공합니다:

- **보수적 설정**: `config/templates/conservative.yaml` - 안전성 중심
- **균형 설정**: `config/templates/balanced.yaml` - 안정성과 수익성의 균형
- **적극적 설정**: `config/templates/aggressive.yaml` - 높은 수익 추구

### Custom Strategies
새로운 전략을 개발하려면:

1. `upbit_trading_bot/strategy/base.py`의 `TradingStrategy` 클래스를 상속
2. `evaluate()` 메서드 구현
3. 설정 파일 생성
4. 테스트 작성

자세한 내용은 [전략 개발 가이드](docs/strategies/README.md)를 참조하세요.

### Strategy Usage Example
```bash
python examples/strategy_usage.py
```

## Monitoring

The bot provides several monitoring capabilities:

- **Health Checks**: HTTP endpoint for system health monitoring
- **Metrics**: Prometheus-compatible metrics endpoint
- **Logging**: Structured logging with configurable levels
- **Notifications**: Support for Telegram, Slack, and email notifications

## Security

- API credentials are encrypted at rest
- All API requests use proper authentication headers
- Rate limiting and retry mechanisms prevent API abuse
- Comprehensive input validation and error handling

## License

MIT License - see LICENSE file for details.

## Disclaimer

This software is for educational purposes only. Cryptocurrency trading involves substantial risk of loss. Use at your own risk.