import asyncio
from datetime import datetime
from kis import KISApi
import json
import websockets

# 모니터링할 종목 리스트
SYMBOLS = [
    "RNASSHV"
]

# 모니터링 설정
INTERVAL = 3  # 조회 간격 (초)

# 웹소켓 설정
WEBSOCKET_URL = "ws://ops.koreainvestment.com:31000"  # 해외주식 실시간 포트

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

class OverseasMonitor:
    def __init__(self, api):
        self.api = api
        self.websocket = None
        
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
                        "tr_id": "HDFSCNT0",  # 해외주식 체결가
                        "tr_key": SYMBOLS[0]   # 종목코드
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
            recvstr = data.split('|')  # 수신데이터 분리
            if len(recvstr) < 4:  # 데이터 형식 체크
                return "데이터 형식 오류"
                
            current_time = datetime.now().strftime('%H:%M:%S')
            trade_data = recvstr[3].split('^')  # 체결 데이터 분리
            
            # 데이터 필드 설명
            fields = {
                "실시간종목코드": trade_data[0],
                "종목코드": trade_data[1],
                "수수점자리수": trade_data[2],
                "현지영업일자": trade_data[3],
                "현지일자": trade_data[4],
                "현지시간": trade_data[5],
                "한국일자": trade_data[6],
                "한국시간": trade_data[7],
                "시가": float(trade_data[8]),
                "고가": float(trade_data[9]),
                "저가": float(trade_data[10]),
                "현재가": float(trade_data[11]),
                "대비구분": trade_data[12],  # 1:상한 2:상승 3:보합 4:하한 5:하락
                "전일대비": float(trade_data[13]),
                "등락율": float(trade_data[14].replace('+', '').replace('-', '')),
                "매수호가": float(trade_data[15]),
                "매도호가": float(trade_data[16]),
                "매수잔량": int(trade_data[17]),
                "매도잔량": int(trade_data[18]),
                "체결량": int(trade_data[19]),
                "거래량": int(trade_data[20]),
                "거래대금": float(trade_data[21]),
                "매도체결량": int(trade_data[22]),
                "매수체결량": int(trade_data[23]),
                "체결강도": float(trade_data[24]),
                "시장구분": trade_data[25]
            }
            
            # 전일대비구분에 따른 부호
            diff_sign = "+" if fields["대비구분"] in ["1", "2"] else "-" if fields["대비구분"] in ["4", "5"] else ""
            
            return (
                f"\n=== {fields['종목코드']} 실시간 체결 정보 ===\n"
                f"시간: {fields['한국시간'][:2]}:{fields['한국시간'][2:4]}:{fields['한국시간'][4:]} (한국시간)\n"
                f"현재가: ${fields['현재가']:,.4f}\n"
                f"전일대비: {diff_sign}${fields['전일대비']:,.4f} ({diff_sign}{fields['등락율']:,.2f}%)\n"
                f"체결량: {fields['체결량']:,}\n"
                f"거래량: {fields['거래량']:,}\n"
                f"거래대금: ${fields['거래대금']:,.2f}\n"
                f"매수/매도호가: ${fields['매수호가']:,.4f} / ${fields['매도호가']:,.4f}\n"
                f"매수/매도잔량: {fields['매수잔량']:,} / {fields['매도잔량']:,}\n"
                f"고가/저가: ${fields['고가']:,.4f} / ${fields['저가']:,.4f}\n"
                f"체결강도: {fields['체결강도']:,.2f}%"
            )
        except Exception as e:
            return f"데이터 포맷 오류: {str(e)}\n원본 데이터: {data}"

    async def monitor_realtime(self):
        """실시간 체결가 모니터링"""
        try:
            if not await self.connect_websocket():
                return
                
            while True:
                try:
                    message = await self.websocket.recv()
                    
                    # 실시간 데이터 처리
                    if message[0] in ['0', '1']:  # 실시간 데이터
                        trade_info = self.format_trade_data(message)
                        print(trade_info)
                        print("-" * 50)
                    else:  # 기타 메시지 (핑퐁 등)
                        data = json.loads(message)
                        if "cmd" in data and data["cmd"] == "ping":
                            await self.websocket.send(json.dumps({"cmd": "pong"}))
                    
                except json.JSONDecodeError as e:
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
            
        print("\n=== 해외주식 실시간 모니터링 시작 ===")
        print(f"대상 종목: {', '.join(SYMBOLS)}")
        print("-" * 50)
        
        monitor = OverseasMonitor(api)
        await monitor.monitor_realtime()
                
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 