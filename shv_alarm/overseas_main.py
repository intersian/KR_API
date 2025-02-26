import asyncio
import json
from datetime import datetime
from kis import KISApi
import aiohttp  # 텔레그램 API 호출용
import os
import sys

# 모니터링할 종목 리스트
SYMBOLS = [
    "SHV"  # BlackRock Short-Term Treasury Bond ETF
]

# 모니터링 설정
INTERVAL = 5  # 조회 간격 (초)
VOLUME_THRESHOLD = 10000  # 거래량 임계값

def load_config():
    """설정 파일 로드"""
    try:
        # 실행 파일 경로 확인
        if getattr(sys, 'frozen', False):
            # PyInstaller로 생성된 실행 파일인 경우
            application_path = os.path.dirname(sys.executable)
        else:
            # 일반 Python 스크립트인 경우
            application_path = os.path.dirname(os.path.abspath(__file__))
            
        # .env 파일 경로 설정
        env_path = os.path.join(application_path, '.env')
        
        config = {}
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    if '#' in value:  # 주석 제거
                        value = value.split('#')[0]
                    config[key.strip()] = value.strip()
                    
                    # 문자열로 된 리스트를 실제 리스트로 변환
                    if value.strip().startswith('[') and value.strip().endswith(']'):
                        try:
                            config[key.strip()] = json.loads(value.strip())
                        except:
                            pass
                            
        return config
        
    except FileNotFoundError:
        print(f"설정 파일을 찾을 수 없습니다. (검색 경로: {env_path})")
        return None
    except Exception as e:
        print(f"설정 파일 로드 중 오류 발생: {e}")
        return None

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
    async def send_message(self, message):
        """텔레그램 메시지 전송"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }
                async with session.post(self.api_url, json=data) as response:
                    if response.status != 200:
                        print(f"텔레그램 전송 실패: {await response.text()}")
        except Exception as e:
            print(f"텔레그램 전송 오류: {e}")

class OverseasMonitor:
    def __init__(self, api, notifier):
        self.api = api
        self.notifier = notifier
        self.prev_volume = {}  # 이전 거래량 저장
        
    async def check_volume_surge(self, symbol):
        """거래량 급증 확인"""
        try:
            quote = await self.api.get_overseas_stock_price(symbol)
            current_time = datetime.now().strftime('%H:%M:%S')
            current_volume = quote['거래량']
            current_price = quote['현재가']
            
            # 초기 거래량 설정
            if symbol not in self.prev_volume:
                self.prev_volume[symbol] = current_volume
                return
            
            # 거래량 변화 계산
            volume_diff = current_volume - self.prev_volume[symbol]
            
            # 결과 출력
            print(f"\n=== {symbol} 시세 정보 ===")
            print(f"조회시각: {current_time}")
            print(f"현재가: ${current_price:,.2f}")
            print(f"거래량: {current_volume:,} (변화량: {volume_diff:,})")
            
            # 거래량 급증 확인 및 알림
            if volume_diff >= VOLUME_THRESHOLD:
                print(f"\n[!] 거래량 급증 감지")
                print(f"기준치: {VOLUME_THRESHOLD:,}")
                
                # 텔레그램 알림 메시지 생성
                message = (
                    f"🚨 <b>{symbol} 거래량 급증</b>\n\n"
                    f"시간: {current_time}\n"
                    f"현재가: ${current_price:,.2f}\n"
                    f"거래량: {current_volume:,}\n"
                    f"변화량: +{volume_diff:,}\n"
                    f"기준치: {VOLUME_THRESHOLD:,}"
                )
                await self.notifier.send_message(message)
            
            print("-" * 50)
            
            # 이전 거래량 업데이트
            self.prev_volume[symbol] = current_volume
            
        except Exception as e:
            print(f"모니터링 오류 ({symbol}): {e}")

async def main():
    """메인 함수"""
    # 설정 로드
    config = load_config()
    if not config:
        print("설정 파일을 찾을 수 없습니다.")
        return
    
    # 텔레그램 설정
    telegram = TelegramNotifier(
        bot_token=config.get("TELEGRAM_BOT_TOKEN"),
        chat_id=config.get("TELEGRAM_CHAT_ID")
    )
    
    # API 연결
    api = KISApi(
        api_key=config.get("KIS_API_KEY"),
        api_secret=config.get("KIS_API_SECRET"),
        account_number=config.get("KIS_ACCOUNT_NUMBER"),
        is_paper_trading=config.get("IS_PAPER_TRADING", "True").lower() == "true"
    )
    
    # 모니터링 시작
    try:
        if not await api.check_connection():
            print("API 연결에 실패했습니다.")
            return
            
        print("\n=== 해외주식 모니터링 시작 ===")
        print(f"대상 종목: {', '.join(SYMBOLS)}")
        print(f"조회 간격: {INTERVAL}초")
        print(f"거래량 임계값: {VOLUME_THRESHOLD:,}")
        print("-" * 50)
        
        # 시작 알림
        await telegram.send_message(
            f"✅ 해외주식 모니터링 시작\n\n"
            f"종목: {', '.join(SYMBOLS)}\n"
            f"간격: {INTERVAL}초\n"
            f"기준치: {VOLUME_THRESHOLD:,}"
        )
        
        monitor = OverseasMonitor(api, telegram)
        
        while True:
            try:
                for symbol in SYMBOLS:
                    await monitor.check_volume_surge(symbol)
                    await asyncio.sleep(1)  # API 호출 간격
                
                await asyncio.sleep(INTERVAL)  # 다음 조회까지 대기
                
            except asyncio.CancelledError:
                print("\n모니터링이 중단되었습니다.")
                await telegram.send_message("⛔ 모니터링이 중단되었습니다.")
                break
            except Exception as e:
                print(f"모니터링 오류: {e}")
                await asyncio.sleep(INTERVAL)
                
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
        await telegram.send_message("⛔ 프로그램이 종료되었습니다.")
    except Exception as e:
        error_msg = f"\n오류 발생: {e}"
        print(error_msg)
        await telegram.send_message(f"❌ {error_msg}")

if __name__ == "__main__":
    asyncio.run(main()) 