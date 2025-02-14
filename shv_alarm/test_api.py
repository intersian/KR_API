import asyncio
import json
from datetime import datetime
import websockets
import ssl
from kis import KISApi

# 모니터링 설정
SYMBOL = "233740"  # KODEX 코스닥150 레버리지

# 웹소켓 설정
WEBSOCKET_URL = "ws://ops.koreainvestment.com:21000"  # 실시간 시세 포트

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

class StockPriceMonitor:
    def __init__(self, api):
        self.api = api
        self.stock_name = None
        self.websocket = None
        
    async def initialize(self, symbol):
        """종목 정보 초기화"""
        try:
            stock_info = await self.api.get_stock_basic_info(symbol)
            self.stock_name = stock_info["한글명"]
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
                        "tr_key": f"K{SYMBOL}",  # 'K' + 종목코드
                        "tr_type": "1"  # 체결가
                    }
                }
            }
            
            await self.websocket.send(json.dumps(connect_request))
            response = await self.websocket.recv()
            print(f"웹소켓 연결 응답: {response}")
            
            # 실시간 시세 구독 확인
            if "error" in response.lower() or "invalid" in response.lower():
                print("실시간 시세 구독 실패")
                return False
                
            return True
            
        except Exception as e:
            print(f"웹소켓 연결 실패: {str(e)}")
            return False

    def format_trade_data(self, data):
        """실시간 시세 데이터 포맷팅"""
        try:
            # 실시간 시세 데이터 필드
            current_price = float(data.get("stck_prpr", 0))      # 현재가
            trade_volume = int(data.get("stck_cntg_qty", 0))    # 체결수량
            trade_time = data.get("stck_cntg_hour", "")         # 체결시각
            price_change = float(data.get("prdy_vrss", 0))      # 전일대비
            change_rate = float(data.get("prdy_ctrt", 0))       # 전일대비율
            total_volume = int(data.get("acml_vol", 0))         # 누적체결수량
            
            # 등락 기호
            sign_symbol = "▲" if price_change > 0 else "▼" if price_change < 0 else "-"
            
            # 시간 포맷팅 (HHMMSS -> HH:MM:SS)
            if len(trade_time) == 6:
                trade_time = f"{trade_time[:2]}:{trade_time[2:4]}:{trade_time[4:]}"
            
            return (
                f"[{trade_time}] {self.stock_name}\n"
                f"현재가: {current_price:,}원 ({sign_symbol}{abs(price_change):,}원, {change_rate:+.2f}%)\n"
                f"체결량: {trade_volume:,}주 (누적: {total_volume:,}주)"
            )
        except Exception as e:
            return f"데이터 포맷 오류: {str(e)}"

    async def monitor_price(self, symbol):
        """실시간 시세 모니터링"""
        if not self.stock_name:  # 종목명이 없으면 초기화
            if not await self.initialize(symbol):
                return
            
        print(f"\n=== {self.stock_name}({symbol}) 실시간 시세 모니터링 시작 ===")
        print("-" * 50)
        
        # 웹소켓 연결
        if not await self.connect_websocket():
            return
        
        try:
            while True:
                try:
                    message = await self.websocket.recv()
                    data = json.loads(message)
                    
                    # 핑퐁 메시지 무시
                    if "cmd" in data and data["cmd"] == "ping":
                        await self.websocket.send(json.dumps({"cmd": "pong"}))
                        continue
                    
                    # 실제 시세 데이터만 출력
                    if "body" in data and "output" in data["body"]:
                        output = data["body"]["output"]
                        # 체결 데이터가 있는 경우만 출력
                        if output.get("stck_cntg_hour") and output.get("stck_prpr"):
                            trade_info = self.format_trade_data(output)
                            print(f"\n{trade_info}")
                    
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"처리 오류: {str(e)}")
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
    
    try:
        monitor = StockPriceMonitor(api)
        await monitor.monitor_price(SYMBOL)
    except KeyboardInterrupt:
        print("\n\n모니터링을 종료합니다.")
    except Exception as e:
        print(f"\n오류: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 