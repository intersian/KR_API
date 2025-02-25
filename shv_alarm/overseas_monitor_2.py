import asyncio
from datetime import datetime
from kis import KISApi
import json
import websockets
import aiohttp  # 텔레그램 API 호출용
from dataclasses import dataclass
from typing import List
from pathlib import Path

# 모니터링할 종목 리스트
SYMBOLS = [
    "RNASSHV"
]

# 모니터링 설정
INTERVAL = 3  # 조회 간격 (초)

# 웹소켓 설정
WEBSOCKET_URL = "ws://ops.koreainvestment.com:31000"  # 해외주식 실시간 포트

# 가격별 첫 체결 시간을 저장할 딕셔너리
price_first_time = {}
current_price = None
max_duration = 0  # 최장 연속체결 시간
max_duration_price = None  # 최장 연속체결 가격

# 텔레그램 설정
TELEGRAM_ALERT_THRESHOLD = 120  # 알림 기준 시간 (초)
last_alert_time = {}  # 가격별 마지막 알림 시간

@dataclass
class TradeRecord:
    price: float
    duration: float
    start_time: str
    end_time: str

class RecordKeeper:
    def __init__(self, max_records=200):
        self.max_records = max_records
        self.records: List[TradeRecord] = []
        self.file_path = Path('shv_alarm/trade_records.json')
        self.load_records()
    
    def load_records(self):
        """기존 기록 파일 로드"""
        try:
            if self.file_path.exists():
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
                    self.records = [TradeRecord(**record) for record in data]
                    # 기존 기록을 지속시간 기준으로 정렬
                    self.records.sort(key=lambda x: x.duration, reverse=True)
                    # 최대 개수 유지
                    if len(self.records) > self.max_records:
                        self.records = self.records[:self.max_records]
        except Exception as e:
            print(f"기록 파일 로드 실패: {e}")
    
    def save_records(self):
        """기록 파일 저장"""
        try:
            with open(self.file_path, 'w') as f:
                json.dump([record.__dict__ for record in self.records], f, indent=2)
        except Exception as e:
            print(f"기록 파일 저장 실패: {e}")
    
    def add_record(self, price: float, duration: float, start_time: str, end_time: str):
        """새로운 기록 추가"""
        record = TradeRecord(price=price, duration=duration, start_time=start_time, end_time=end_time)
        
        # 기존 기록에 추가하고 정렬
        self.records.append(record)
        self.records.sort(key=lambda x: x.duration, reverse=True)
        
        # 최대 개수 유지
        if len(self.records) > self.max_records:
            self.records = self.records[:self.max_records]
        
        # 파일에 전체 기록 저장
        self.save_records()
        
    def get_records_text(self) -> str:
        """기록 문자열 생성"""
        if not self.records:
            return "기록 없음"
        
        text = "=== 최장 연속체결 기록 ===\n"
        for i, record in enumerate(self.records, 1):
            text += f"{i}위: ${record.price:,.4f} ({record.duration:.1f}초)\n"
            text += f"    {record.start_time} ~ {record.end_time}\n"
        return text

# RecordKeeper 인스턴스 생성
record_keeper = RecordKeeper()

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

async def send_telegram_message(bot_token, chat_id, message):
    """텔레그램 메시지 전송"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }) as response:
                return await response.json()
    except Exception as e:
        print(f"텔레그램 메시지 전송 실패: {e}")

class OverseasMonitor:
    def __init__(self, api):
        self.api = api
        self.websocket = None
        self.config = load_config()
        self.start_times = {}  # 가격별 시작 시간 저장
        
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
                
            current_time = datetime.now()
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
            
            # 연속 체결 시간 계산
            global current_price, price_first_time, max_duration, max_duration_price, last_alert_time
            trade_price = fields["현재가"]
            current_time_str = f"{fields['한국시간'][:2]}:{fields['한국시간'][2:4]}:{fields['한국시간'][4:]}"
            
            if current_price != trade_price:
                # 이전 가격의 연속체결이 끝난 경우, 기록 저장
                if current_price is not None and current_price in price_first_time:
                    end_time = current_time_str
                    start_time = self.start_times.get(current_price, end_time)
                    duration = (current_time - price_first_time[current_price]).total_seconds()
                    if duration >= 5:  # 5초 이상인 경우만 기록
                        record_keeper.add_record(
                            price=current_price,
                            duration=duration,
                            start_time=start_time,
                            end_time=end_time
                        )
                
                # 새로운 가격 시작
                current_price = trade_price
                price_first_time = {trade_price: current_time}
                self.start_times[trade_price] = current_time_str
                duration_str = "최초 체결"
            else:
                # 동일 가격이 유지되는 경우
                first_time = price_first_time.get(trade_price)
                if first_time:
                    duration = current_time - first_time
                    duration_seconds = duration.total_seconds()
                    duration_str = f"연속 체결 시간: {duration_seconds:.1f}초"
                    
                    # 최장 기록 갱신 확인
                    if duration_seconds > max_duration:
                        max_duration = duration_seconds
                        max_duration_price = trade_price
                    
                    # 텔레그램 알림 조건 확인
                    if duration_seconds >= TELEGRAM_ALERT_THRESHOLD:
                        # 마지막 알림 시간 확인
                        last_alert = last_alert_time.get(trade_price, 0)
                        if current_time.timestamp() - last_alert >= TELEGRAM_ALERT_THRESHOLD:
                            # 알림 메시지 생성
                            alert_message = (
                                f"🔔 <b>동일가격 연속체결 알림</b>\n\n"
                                f"종목: {fields['종목코드']}\n"
                                f"가격: ${trade_price:,.4f}\n"
                                f"연속체결시간: {duration_seconds:.1f}초\n"
                                f"체결량: {fields['체결량']:,}\n"
                                f"체결강도: {fields['체결강도']:,.2f}%"
                            )
                            
                            # 텔레그램 전송
                            asyncio.create_task(send_telegram_message(
                                self.config.get("TELEGRAM_BOT_TOKEN"),
                                self.config.get("TELEGRAM_CHAT_ID"),
                                alert_message
                            ))
                            
                            # 마지막 알림 시간 업데이트
                            last_alert_time[trade_price] = current_time.timestamp()
                else:
                    price_first_time[trade_price] = current_time
                    duration_str = "최초 체결"
            
            # 전일대비구분에 따른 부호
            diff_sign = "+" if fields["대비구분"] in ["1", "2"] else "-" if fields["대비구분"] in ["4", "5"] else ""
            
            # 최장 기록 문자열 제거 (터미널 출력에서 제외)
            return (
                f"\n=== {fields['종목코드']} 실시간 체결 정보 ===\n"
                f"시간: {fields['한국시간'][:2]}:{fields['한국시간'][2:4]}:{fields['한국시간'][4:]} (한국시간)\n"
                f"현재가: ${fields['현재가']:,.4f} ({duration_str})\n"
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