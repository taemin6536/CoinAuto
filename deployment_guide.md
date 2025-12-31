# 업비트 트레이딩 봇 배포 가이드

## 🚀 배포 방법들

### 1. **Python 스크립트 방식** (가장 간단)
```bash
# 직접 실행
python upbit_trading_bot/main.py

# 백그라운드 실행 (Linux/Mac)
nohup python upbit_trading_bot/main.py > bot.log 2>&1 &

# Windows 서비스로 실행
pythonw upbit_trading_bot/main.py
```

### 2. **PyInstaller로 실행 파일 생성** (추천)
```bash
# PyInstaller 설치
pip install pyinstaller

# 단일 실행 파일 생성
pyinstaller --onefile --name upbit-bot upbit_trading_bot/main.py

# 실행
./dist/upbit-bot  # Linux/Mac
./dist/upbit-bot.exe  # Windows
```

### 3. **Docker 컨테이너** (서버 배포용)
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN pip install -e .

CMD ["upbit-bot"]
```

```bash
# Docker 빌드 및 실행
docker build -t upbit-bot .
docker run -d --name trading-bot upbit-bot
```

### 4. **시스템 서비스** (Linux)
```ini
# /etc/systemd/system/upbit-bot.service
[Unit]
Description=Upbit Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/upbit-trading-bot
ExecStart=/home/ubuntu/upbit-trading-bot/venv/bin/python upbit_trading_bot/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 등록 및 시작
sudo systemctl enable upbit-bot
sudo systemctl start upbit-bot
sudo systemctl status upbit-bot
```

### 5. **클라우드 배포**

#### **AWS EC2**
```bash
# EC2 인스턴스에서
git clone <repository>
cd upbit-trading-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .

# 백그라운드 실행
nohup upbit-bot > bot.log 2>&1 &
```

#### **Google Cloud Run**
```yaml
# cloudbuild.yaml
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-t', 'gcr.io/$PROJECT_ID/upbit-bot', '.']
- name: 'gcr.io/cloud-builders/docker'
  args: ['push', 'gcr.io/$PROJECT_ID/upbit-bot']
```

### 6. **Windows 작업 스케줄러**
```batch
@echo off
cd /d "C:\path\to\upbit-trading-bot"
python upbit_trading_bot\main.py
```

## 🔧 배포 전 체크리스트

### 필수 설정
- [ ] API 키 설정 (.env 파일)
- [ ] 설정 파일 검증 (`upbit-bot config validate`)
- [ ] 로그 디렉토리 권한 확인
- [ ] 데이터베이스 파일 권한 확인

### 보안 설정
- [ ] API 키 암호화 확인
- [ ] 방화벽 설정 (필요한 포트만 열기)
- [ ] SSL/TLS 인증서 (웹 인터페이스 사용 시)
- [ ] 로그 파일 보안 설정

### 모니터링 설정
- [ ] 로그 로테이션 설정
- [ ] 알림 시스템 설정
- [ ] 헬스 체크 엔드포인트 확인
- [ ] 백업 전략 수립

## 📊 추천 배포 방식

### **개인 사용자**
1. **PyInstaller 실행 파일** - 가장 간단
2. **Python 스크립트** - 개발/테스트용

### **서버 운영**
1. **Docker + Docker Compose** - 확장성 좋음
2. **시스템 서비스** - 안정성 좋음
3. **클라우드 서비스** - 관리 편의성

### **상용 서비스**
1. **Kubernetes** - 대규모 운영
2. **AWS ECS/Fargate** - 관리형 서비스
3. **Google Cloud Run** - 서버리스