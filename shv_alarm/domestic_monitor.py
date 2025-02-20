import asyncio
from datetime import datetime
from kis import KISApi
import json
import websockets

# 모니터링할 종목 리스트
SYMBOLS = [
    "005930"  # 삼성전자
]

# 웹소켓 설정
WEBSOCKET_URL = "ws://ops.koreainvestment.com:21000"  # 국내주식 실시간 포트

def load_config():
    """설정 파일 로드"""
    try:
        config = {}
        with open('shv_alarm/.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    if '#' in value:
                        value = value.split('#')[0]
                    config[key.strip()] = value.strip()
        return config
    except Exception as e:
        print(f"설정 파일 로드 중 오류 발생: {e}")
        return {}

class DomesticMonitor:
    def __init__(self, api):
        self.api = api
        self.websocket = None
        self.stock_names = {}  # 종목코드: 종목명 매핑
        
    async def initialize(self):
        """종목 정보 초기화"""
        try:
            for symbol in SYMBOLS:
                stock_info = await self.api.get_stock_basic_info(symbol)
                self.stock_names[symbol] = stock_info["한글명"]
            return True
        except Exception as e:
            print(f"종목 정보 초기화 실패: {str(e)}")
            return False
        
    async def connect_websocket(self):
        """웹소켓 연결"""
        try:
            # 웹소켓 승인키 발급
            approval_key = await self.api.get_approval_key()
            
            # 웹소켓 연결
            self.websocket = await websockets.connect(
                WEBSOCKET_URL,
                ping_interval=None,
                ping_timeout=None
            )

            # 웹소켓 접속 요청
            connect_request = {
                "header": {
                    "approval_key": approval_key,
                    "custtype": "P",
                    "tr_type": "1",
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": "H0STCNT0",  # 주식체결통보
                        "tr_key": f"K{SYMBOLS[0]}",  # 'K' + 종목코드
                    }
                }
            }
            
            await self.websocket.send(json.dumps(connect_request))
            response = await self.websocket.recv()
            print(f"웹소켓 연결 응답: {response}")
            
            return True
            
        except Exception as e:
            print(f"웹소켓 연결 실패: {str(e)}")
            return False

    def format_trade_data(self, data):
        """실시간 체결 데이터 포맷팅"""
        try:
            symbol = data.get('mksc_shrn_iscd', '')  # 종목코드
            stock_name = self.stock_names.get(symbol, symbol)
            
            current_price = float(data.get('stck_prpr', '0'))      # 현재가
            price_change = float(data.get('prdy_vrss', '0'))      # 전일대비
            change_rate = float(data.get('prdy_ctrt', '0'))       # 등락률
            trade_volume = int(data.get('cntg_vol', '0'))         # 체결수량
            total_volume = int(data.get('acml_vol', '0'))         # 누적체결수량
            trade_time = data.get('stck_cntg_hour', '')           # 체결시각
            
            # 등락 기호
            diff_sign = "▲" if price_change > 0 else "▼" if price_change < 0 else "-"
            
            # 시간 포맷팅 (HHMMSS -> HH:MM:SS)
            if len(trade_time) == 6:
                trade_time = f"{trade_time[:2]}:{trade_time[2:4]}:{trade_time[4:]}"
            
            return (
                f"\n=== {stock_name} 실시간 체결 정보 ===\n"
                f"시간: {trade_time}\n"
                f"현재가: {current_price:,}원\n"
                f"전일대비: {diff_sign}{abs(price_change):,}원 ({diff_sign}{abs(change_rate):.2f}%)\n"
                f"체결량: {trade_volume:,}\n"
                f"거래량: {total_volume:,}"
            )
        except Exception as e:
            return f"데이터 포맷 오류: {str(e)}\n원본 데이터: {data}"

    async def monitor_realtime(self):
        """실시간 체결가 모니터링"""
        try:
            # 종목 정보 초기화
            if not await self.initialize():
                return
                
            # 웹소켓 연결
            if not await self.connect_websocket():
                return
                
            while True:
                try:
                    message = await self.websocket.recv()
                    
                    # 실시간 데이터 처리
                    if message[0] in ['0', '1']:  # 실시간 데이터
                        data = json.loads(message)
                        if "body" in data and "output" in data["body"]:
                            trade_info = self.format_trade_data(data["body"]["output"])
                            print(trade_info)
                            print("-" * 50)
                    else:  # 기타 메시지 (핑퐁 등)
                        data = json.loads(message)
                        if "cmd" in data and data["cmd"] == "ping":
                            await self.websocket.send(json.dumps({"cmd": "pong"}))
                    
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"\n처리 오류: {str(e)}")
                    await asyncio.sleep(1)
                
        except websockets.exceptions.ConnectionClosed:
            print("\n웹소켓 연결이 종료되었습니다.")
        except Exception as e:
            print(f"\n모니터링 오류: {str(e)}")
        finally:
            if self.websocket:
                await self.websocket.close()

async def main():
    """메인 함수"""
    # 설정 로드
    config = load_config()
    if not config:
        print("설정 파일을 찾을 수 없습니다.")
        return
    
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
            
        print("\n=== 국내주식 실시간 모니터링 시작 ===")
        print(f"대상 종목: {', '.join(SYMBOLS)}")
        print("-" * 50)
        
        monitor = DomesticMonitor(api)
        await monitor.monitor_realtime()
                
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 