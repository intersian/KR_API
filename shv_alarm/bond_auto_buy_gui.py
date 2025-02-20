import sys
import asyncio
import logging
from datetime import datetime
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QTextEdit, QGroupBox, QCheckBox, QMessageBox,
                            QSplitter, QMenuBar, QMenu, QFileDialog, QGridLayout)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSize
from PyQt6.QtGui import QAction
from kis import KISApi

# 기본 설정값
DEFAULT_CONFIG = {
    # API 설정
    'api_key': 'PSOuaQp3WA0klz1bE0kECtUpz3R8TTRqqgt8',
    'api_secret': 'Of/V65xsBs9ehwdZRaqf4z4HHx5zP93WbNYUp0827+FpgNkMZzVEtIvLk0tWzqKTIvxapMktmJy9fSpsakpdoXUTikETIRL5VOBVOWDi84yCxRrLbiobmKHjgiThi4ERDVqFk5og/pKfKxTDT2jLsHmg+oUPwO9vs9csBkTSftmbHWcQdMQ=',
    'account_number': '4680572501',
    'is_paper_trading': False,
    
    # 목표 설정
    'symbol': 'KR6036422E29',  # 목표 종목코드
    'target_quantity': 1,     # 목표 보유수량
    'order_quantity': 1,       # 1회 매수수량
    'min_price': 10000.0,      # 최소 매수가격
    'max_price': 10150.0,      # 최대 매수가격
    'interval': 10             # 조회 간격 (초)
}

# GUI 설정
GUI_CONFIG = {
    'window_title': '채권 자동 매수',
    'window_width': 800,
    'window_height': 850,
    'font_size': 10
}

# API URL 설정
API_URLS = {
    'balance': 'https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/inquire-balance',
    'orders': 'https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/inquire-psbl-rvsecncl',
    'quote': 'https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/inquire-asking-price',
    'issue_info': 'https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/issue-info',
    'order': 'https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/buy',
    'modify': 'https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/order-rvsecncl'
}

# TR ID 설정
TR_ID = {
    'balance': 'CTSC8407R',     # 잔고 조회
    'orders': 'CTSC8035R',      # 주문 조회
    'quote': 'FHKBJ773401C0',   # 호가 조회
    'issue_info': 'CTPF1101R',  # 발행정보 조회
    'order': 'TTTC0952U',       # 주문
    'modify': 'TTTC0953U'       # 정정
}

# 로그 구분선
LOG_SEPARATOR = "-" * 50

class LogHandler(logging.Handler):
    """로그 핸들러"""
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)

class MonitorThread(QThread):
    """모니터링 스레드"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    target_achieved_signal = pyqtSignal(str)
    price_error_signal = pyqtSignal(str)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.is_running = False
        self.loop = None
        
        # 로거 설정
        self.logger = logging.getLogger('Monitor')
        self.logger.setLevel(logging.INFO)
        handler = LogHandler(self.log_signal)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def get_bond_name(self, api, symbol):
        """채권 종목명 조회"""
        try:
            url = API_URLS['issue_info']
            
            params = {
                "PDNO": symbol,                 # 채권종목코드
                "PRDT_TYPE_CD": "302"          # 상품유형코드 (302: 채권)
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['issue_info'],
                "custtype": "P"
            }
            
            result = await api.request("get", url, params=params, headers=headers)
            return result.get("output", {}).get("prdt_name", "-")
            
        except Exception as e:
            return f"조회 실패: {str(e)}"

    async def get_bond_balance(self, api):
        """채권 잔고 조회"""
        try:
            url = API_URLS['balance']
            
            params = {
                "CANO": self.config['account_number'][:8],
                "ACNT_PRDT_CD": self.config['account_number'][8:],
                "INQR_CNDT": "00",
                "PDNO": "",
                "BUY_DT": "",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['balance'],
                "custtype": "P"
            }
            
            result = await api.request("get", url, params=params, headers=headers)
            
            if result.get("rt_cd") != "0":
                raise Exception(f"조회 실패: {result.get('msg1')}")
                
            output = result.get("output", [])
            current_time = datetime.now().strftime('%H:%M:%S')
            
            self.logger.info(f"\n=== 채권 잔고 현황 ({current_time}) ===")
            self.logger.info(LOG_SEPARATOR)
            
            # 목표 종목의 보유수량 확인
            current_quantity = 0
            target_found = False
            
            for bond in output:
                if bond.get('pdno') == self.config['symbol']:
                    target_found = True
                    current_quantity += int(bond.get('cblc_qty', '0'))
                    
                    self.logger.info(f"종목명: {bond.get('prdt_name', '-')}")
                    self.logger.info(f"매수일자: {bond.get('buy_dt', '-')}")
                    self.logger.info(f"잔고수량: {int(bond.get('cblc_qty', '0')):,}")
                    self.logger.info(f"주문가능수량: {int(bond.get('ord_psbl_qty', '0')):,}")
                    self.logger.info(LOG_SEPARATOR)
            
            if not target_found:
                self.logger.info("목표 종목 보유내역이 없습니다.")
                self.logger.info(LOG_SEPARATOR)
            
            # 목표 수량 달성 확인
            if current_quantity >= self.config['target_quantity']:
                # 정정가능 주문 조회 및 취소
                url = API_URLS['orders']
                params = {
                    "CANO": self.config['account_number'][:8],
                    "ACNT_PRDT_CD": self.config['account_number'][8:],
                    "ORD_DT": "",
                    "ODNO": "",
                    "CTX_AREA_FK200": "",
                    "CTX_AREA_NK200": ""
                }
                
                headers = {
                    "content-type": "application/json; charset=utf-8",
                    "authorization": f"Bearer {await api._get_access_token()}",
                    "appkey": api.api_key,
                    "appsecret": api.api_secret,
                    "tr_id": TR_ID['orders'],
                    "custtype": "P"
                }
                
                result = await api.request("get", url, params=params, headers=headers)
                
                if result.get("rt_cd") == "0":
                    output_list = result.get("output", [])
                    
                    # 목표 종목의 정정가능 주문 취소
                    for order in output_list:
                        if (order.get('pdno') == self.config['symbol'] and 
                            int(order.get('ord_psbl_qty', '0')) > 0):
                            
                            order_no = order.get('odno', '')
                            self.logger.info(f"\n미체결 주문 취소 시도")
                            self.logger.info(f"주문번호: {order_no}")
                            
                            # 주문 취소
                            cancel_url = API_URLS['modify']
                            cancel_body = {
                                "CANO": self.config['account_number'][:8],
                                "ACNT_PRDT_CD": self.config['account_number'][8:],
                                "PDNO": self.config['symbol'],
                                "ORGN_ODNO": order_no,
                                "ORD_QTY2": "0",
                                "BOND_ORD_UNPR": "0",
                                "QTY_ALL_ORD_YN": "Y",
                                "RVSE_CNCL_DVSN_CD": "02",  # 02: 취소
                                "MGCO_APTM_ODNO": "",
                                "ORD_SVR_DVSN_CD": "0",
                                "CTAC_TLNO": ""
                            }
                            
                            cancel_headers = {
                                "content-type": "application/json; charset=utf-8",
                                "authorization": f"Bearer {await api._get_access_token()}",
                                "appkey": api.api_key,
                                "appsecret": api.api_secret,
                                "tr_id": TR_ID['modify'],
                                "custtype": "P"
                            }
                            
                            cancel_result = await api.request("post", cancel_url, data=cancel_body, headers=cancel_headers)
                            
                            if cancel_result.get("rt_cd") == "0":
                                self.logger.info("주문 취소 완료")
                            else:
                                self.logger.error(f"주문 취소 실패: {cancel_result.get('msg1')}")
                            
                            self.logger.info(LOG_SEPARATOR)
                
                # 목표 달성 메시지 출력 및 프로그램 종료
                message = (f"\n=== 자동 매수 완료 ===\n"
                          f"목표 종목의 보유수량({current_quantity:,})이\n"
                          f"목표수량({self.config['target_quantity']:,})에 도달했습니다.")
                self.logger.info(message)
                self.logger.info(LOG_SEPARATOR)
                
                # 목표 달성 시그널 발생
                self.target_achieved_signal.emit(message)
                self.is_running = False
            
            return current_quantity
            
        except Exception as e:
            self.logger.error(f"잔고 조회 실패: {e}")
            return 0

    async def get_bond_orders(self, api):
        """정정취소가능한 채권 주문 조회"""
        try:
            url = API_URLS['orders']
            
            params = {
                "CANO": self.config['account_number'][:8],
                "ACNT_PRDT_CD": self.config['account_number'][8:],
                "ORD_DT": "",
                "ODNO": "",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['orders'],
                "custtype": "P"
            }
            
            result = await api.request("get", url, params=params, headers=headers)
            
            if result.get("rt_cd") != "0":
                raise Exception(f"조회 실패: {result.get('msg1')}")
                
            output_list = result.get("output", [])
            current_time = datetime.now().strftime('%H:%M:%S')
            
            self.logger.info(f"\n=== 채권 주문 내역 조회 ({current_time}) ===")
            self.logger.info(LOG_SEPARATOR)
            
            has_target_order = False  # 목표 종목의 정정가능 주문 여부
            target_orders_found = False  # 목표 종목의 주문 존재 여부
            
            for order in output_list:
                if order.get('pdno') == self.config['symbol']:
                    target_orders_found = True
                    
                    # 주문시각 포맷팅 (HHMMSS -> HH:MM:SS)
                    ord_time = order.get('ord_tmd', '-')
                    if ord_time != '-':
                        ord_time = f"{ord_time[:2]}:{ord_time[2:4]}:{ord_time[4:]}"
                    
                    order_no = order.get('odno', '-')
                    current_price = float(order.get('bond_ord_unpr', '0'))
                    
                    self.logger.info(f"주문번호: {order_no}")
                    self.logger.info(f"주문수량: {int(order.get('ord_qty', '0')):,}")
                    self.logger.info(f"주문단가: {current_price:,.1f}")
                    self.logger.info(f"주문시각: {ord_time}")
                    self.logger.info(f"총체결수량: {int(order.get('tot_ccld_qty', '0')):,}")
                    self.logger.info(f"정정가능수량: {int(order.get('ord_psbl_qty', '0')):,}")
                    
                    # 미체결 수량이 있는 경우 정정 주문 검토
                    if int(order.get('ord_psbl_qty', '0')) > 0:
                        has_target_order = True
                        self.logger.info(f"\n미체결 주문 발견 - 정정 검토")
                        
                        # 호가 조회
                        quote_url = API_URLS['quote']
                        quote_params = {
                            "FID_COND_MRKT_DIV_CODE": "B",
                            "FID_INPUT_ISCD": self.config['symbol']
                        }
                        quote_headers = {
                            "content-type": "application/json; charset=utf-8",
                            "authorization": f"Bearer {await api._get_access_token()}",
                            "appkey": api.api_key,
                            "appsecret": api.api_secret,
                            "tr_id": TR_ID['quote'],
                            "custtype": "P"
                        }
                        
                        quote_result = await api.request("get", quote_url, params=quote_params, headers=quote_headers)
                        
                        if quote_result.get("rt_cd") == "0":
                            output = quote_result.get("output", {})
                            current_bid_price = float(output.get('bond_bidp1', '0'))  # 매수1호가
                            current_ask_price = float(output.get('bond_askp1', '0'))  # 매도1호가
                            
                            self.logger.info(f"현재 매수1호가: {current_bid_price:,.1f}")
                            self.logger.info(f"현재 매도1호가: {current_ask_price:,.1f}")
                            
                            # 정정 주문가격 결정
                            if current_price != current_bid_price:  # 주문가격이 매수1호가와 다르면
                                new_price = current_bid_price + 1  # 매수1호가 + 1원
                                
                                if new_price >= current_ask_price:  # 매도1호가 이상이면
                                    new_price = current_bid_price   # 매수1호가로 정정
                                
                                # 가격 범위 확인
                                if not (self.config['min_price'] <= new_price <= self.config['max_price']):
                                    error_msg = (f"\n=== 정정가격 범위 초과 ===\n"
                                               f"정정가격({new_price:,.1f})이\n"
                                               f"허용범위({self.config['min_price']:,.1f} ~ {self.config['max_price']:,.1f})를\n"
                                               f"벗어났습니다.")
                                    self.logger.error(error_msg)
                                    self.logger.info(LOG_SEPARATOR)
                                    
                                    # 가격 오류 시그널 발생
                                    self.price_error_signal.emit(error_msg)
                                    self.is_running = False
                                    return False
                                
                                # 정정 주문 실행
                                await self.modify_bond_order(api, order_no, self.config['symbol'], new_price)
                            else:
                                self.logger.info("주문가격이 현재 매수1호가와 동일하여 정정하지 않습니다.")
                    
                    self.logger.info(LOG_SEPARATOR)
            
            if not target_orders_found:
                self.logger.info("목표 종목의 주문내역이 없습니다.")
                self.logger.info(LOG_SEPARATOR)
            
            # 정정가능 주문이 없으면 매수 주문 시도
            if not has_target_order:
                self.logger.info("목표 종목의 정정가능 주문이 없습니다.")
                await self.check_and_order(api)
            
            return True
            
        except Exception as e:
            self.logger.error(f"주문 조회 실패: {e}")
            return False

    async def modify_bond_order(self, api, order_no, symbol, new_price):
        """채권 주문 정정"""
        try:
            # 호가 조회로 매수1호가 확인
            quote_url = API_URLS['quote']
            quote_params = {
                "FID_COND_MRKT_DIV_CODE": "B",  # 시장구분: B(채권)
                "FID_INPUT_ISCD": symbol,        # 종목코드
            }
            quote_headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['quote'],  # 채권 호가 조회
                "custtype": "P"            # 개인
            }
            
            quote_result = await api.request("get", quote_url, params=quote_params, headers=quote_headers)
            
            if quote_result.get("rt_cd") != "0":
                raise Exception(f"호가 조회 실패: {quote_result.get('msg1')}")
                
            output = quote_result.get("output", {})
            bid_price = float(output.get('bond_bidp1', '0'))  # 매수1호가
            
            # 정정 주문
            url = API_URLS['modify']
            
            body = {
                "CANO": api.account_number[:8],
                "ACNT_PRDT_CD": api.account_number[8:],
                "PDNO": symbol,
                "ORGN_ODNO": order_no,
                "RVSE_CNCL_DVSN_CD": "01",   # 정정취소구분코드 (01: 정정)
                "ORD_QTY2": "0",             # 주문수량2 (0: 전량)
                "BOND_ORD_UNPR": str(new_price),  # 채권주문단가 (매수1호가 + 1)
                "QTY_ALL_ORD_YN": "Y",       # 주문수량전체여부
                "MGCO_APTM_ODNO": "",        # 운용사지정주문번호
                "ORD_SVR_DVSN_CD": "0",      # 주문서버구분코드
                "CTAC_TLNO": "",             # 연락전화번호
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['modify'],
                "custtype": "P"
            }
            
            result = await api.request("post", url, data=body, headers=headers)
            
            if result.get("rt_cd") != "0":
                raise Exception(f"정정 실패: {result.get('msg1')}")
                
            self.logger.info(f"\n주문번호 {order_no} 정정 완료")
            self.logger.info(f"기존 매수1호가: {bid_price:,.1f}")
            self.logger.info(f"정정 주문가격: {new_price:,.1f}")
            self.logger.info(LOG_SEPARATOR)
            
            return True
            
        except Exception as e:
            self.logger.error(f"주문 정정 실패: {e}")
            return False

    async def check_and_order(self, api):
        """호가 확인 후 주문"""
        try:
            # 호가 조회
            quote_url = API_URLS['quote']
            quote_params = {
                "FID_COND_MRKT_DIV_CODE": "B",
                "FID_INPUT_ISCD": self.config['symbol']
            }
            quote_headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['quote'],
                "custtype": "P"
            }
            
            quote_result = await api.request("get", quote_url, params=quote_params, headers=quote_headers)
            
            if quote_result.get("rt_cd") != "0":
                raise Exception(f"호가 조회 실패: {quote_result.get('msg1')}")
                
            output = quote_result.get("output", {})
            bid_price = float(output.get('bond_bidp1', '0'))  # 매수1호가
            ask_price = float(output.get('bond_askp1', '0'))  # 매도1호가
            
            # 주문가격 결정
            order_price = bid_price + 1  # 매수1호가 + 1원
            if order_price >= ask_price:  # 매도1호가 이상이면
                order_price = bid_price   # 매수1호가로 주문
                price_msg = "(매수1호가와 동일)"
            else:
                price_msg = "(매수1호가 + 1)"
            
            # 가격 범위 확인
            if not (self.config['min_price'] <= order_price <= self.config['max_price']):
                error_msg = (f"\n=== 주문가격 범위 초과 ===\n"
                           f"주문가격({order_price:,.1f})이\n"
                           f"허용범위({self.config['min_price']:,.1f} ~ {self.config['max_price']:,.1f})를\n"
                           f"벗어났습니다.")
                self.logger.error(error_msg)
                self.logger.info(LOG_SEPARATOR)
                
                # 가격 오류 시그널 발생
                self.price_error_signal.emit(error_msg)
                self.is_running = False
                return False
            
            # 매수 주문
            url = API_URLS['order']
            
            body = {
                "CANO": self.config['account_number'][:8],
                "ACNT_PRDT_CD": self.config['account_number'][8:],
                "PDNO": self.config['symbol'],
                "ORD_QTY2": str(self.config['order_quantity']),
                "BOND_ORD_UNPR": str(order_price),
                "SAMT_MKET_PTCI_YN": "N",
                "BOND_RTL_MKET_YN": "N",
                "IDCR_STFNO": "",
                "MGCO_APTM_ODNO": "",
                "ORD_SVR_DVSN_CD": "0",
                "CTAC_TLNO": ""
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['order'],
                "custtype": "P"
            }
            
            result = await api.request("post", url, data=body, headers=headers)
            
            if result.get("rt_cd") != "0":
                raise Exception(f"주문 실패: {result.get('msg1')}")
                
            order_no = result.get("output", {}).get("ODNO", "")
            self.logger.info(f"\n=== 채권 매수 주문 완료 ===")
            self.logger.info(f"주문번호: {order_no}")
            self.logger.info(f"매수1호가: {bid_price:,.1f}")
            self.logger.info(f"매도1호가: {ask_price:,.1f}")
            self.logger.info(f"주문가격: {order_price:,.1f} {price_msg}")
            self.logger.info(f"주문수량: {self.config['order_quantity']:,}")
            self.logger.info(LOG_SEPARATOR)
            
            return True
            
        except Exception as e:
            self.logger.error(f"매수 주문 실패: {e}")
            return False

    def run(self):
        """스레드 실행"""
        self.is_running = True
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.monitor_balance())
        self.finished_signal.emit()  # 종료 시그널 발생

    def stop(self):
        """스레드 중지"""
        self.is_running = False
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

    async def monitor_balance(self):
        """채권 잔고 모니터링"""
        try:
            api = KISApi(
                api_key=self.config['api_key'],
                api_secret=self.config['api_secret'],
                account_number=self.config['account_number'],
                is_paper_trading=self.config['is_paper_trading']
            )
            
            target_name = await self.get_bond_name(api, self.config['symbol'])
            
            self.logger.info("\n=== 채권 자동 매수 시작 ===")
            self.logger.info(f"목표 종목: {target_name} ({self.config['symbol']})")
            self.logger.info(f"목표 수량: {self.config['target_quantity']:,}")
            self.logger.info(f"매수 범위: {self.config['min_price']:,.1f} ~ {self.config['max_price']:,.1f}")
            self.logger.info(f"조회 간격: {self.config['interval']}초")
            self.logger.info(LOG_SEPARATOR)
            
            while self.is_running:
                try:
                    await self.get_bond_balance(api)
                    await self.get_bond_orders(api)
                    await asyncio.sleep(self.config['interval'])
                    
                except Exception as e:
                    self.logger.error(f"모니터링 오류: {e}")
                    await asyncio.sleep(self.config['interval'])
                    
        except Exception as e:
            self.logger.error(f"초기화 오류: {e}")

class MainWindow(QMainWindow):
    """메인 윈도우"""
    def __init__(self):
        super().__init__()
        
        # 메뉴바 추가
        self.create_menu_bar()
        
        self.initUI()
        self.monitor_thread = None

    def create_menu_bar(self):
        """메뉴바 생성"""
        menubar = self.menuBar()
        
        # 파일 메뉴
        file_menu = menubar.addMenu('파일')
        
        # 설정 저장 액션
        save_action = QAction('설정 저장', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_settings)
        file_menu.addAction(save_action)
        
        # 설정 불러오기 액션
        load_action = QAction('설정 불러오기', self)
        load_action.setShortcut('Ctrl+O')
        load_action.triggered.connect(self.load_settings)
        file_menu.addAction(load_action)
        
        # 구분선 추가
        file_menu.addSeparator()
        
        # 종료 액션
        exit_action = QAction('종료', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def save_settings(self):
        """설정 저장"""
        try:
            # 파일 선택 다이얼로그
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "설정 저장",
                "",
                "JSON 파일 (*.json);;모든 파일 (*.*)"
            )
            
            if filename:
                # 현재 설정 가져오기
                settings = {
                    'api_key': self.api_key_edit.text(),
                    'api_secret': self.api_secret_edit.text(),
                    'account_number': self.account_edit.text(),
                    'is_paper_trading': self.paper_check.isChecked(),
                    'symbol': self.symbol_edit.text(),
                    'target_quantity': self.target_qty_edit.text(),
                    'order_quantity': self.order_qty_edit.text(),
                    'min_price': self.min_price_edit.text(),
                    'max_price': self.max_price_edit.text(),
                    'interval': self.interval_edit.text()
                }
                
                # JSON 파일로 저장
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=4, ensure_ascii=False)
                
                self.statusBar.showMessage(f'설정이 저장되었습니다: {filename}')
                
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"설정 저장 중 오류가 발생했습니다:\n{str(e)}")

    def load_settings(self):
        """설정 불러오기"""
        try:
            # 파일 선택 다이얼로그
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "설정 불러오기",
                "",
                "JSON 파일 (*.json);;모든 파일 (*.*)"
            )
            
            if filename:
                # JSON 파일 읽기
                with open(filename, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 설정 적용
                self.api_key_edit.setText(settings.get('api_key', ''))
                self.api_secret_edit.setText(settings.get('api_secret', ''))
                self.account_edit.setText(settings.get('account_number', ''))
                self.paper_check.setChecked(settings.get('is_paper_trading', False))
                self.symbol_edit.setText(settings.get('symbol', ''))
                self.target_qty_edit.setText(str(settings.get('target_quantity', '')))
                self.order_qty_edit.setText(str(settings.get('order_quantity', '')))
                self.min_price_edit.setText(str(settings.get('min_price', '')))
                self.max_price_edit.setText(str(settings.get('max_price', '')))
                self.interval_edit.setText(str(settings.get('interval', '')))
                
                self.statusBar.showMessage(f'설정을 불러왔습니다: {filename}')
                
        except Exception as e:
            QMessageBox.critical(self, "불러오기 오류", f"설정을 불러오는 중 오류가 발생했습니다:\n{str(e)}")

    def initUI(self):
        """UI 초기화"""
        # 전체 스타일 시트 정의 (버튼 제외)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                margin-top: 1.2em;  /* 제목 여백 증가 */
                font-weight: bold;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px;  /* 좌우 패딩 증가 */
                color: #1976D2;  /* 제목 색상 변경 */
                font-size: 14px;  /* 제목 크기 증가 */
                font-weight: bold;
            }
            QLineEdit {
                padding: 6px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 2px solid #2196F3;
            }
            QTextEdit {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                padding: 4px;
            }
            QLabel {
                color: #424242;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #e0e0e0;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #2196F3;
                border: 2px solid #2196F3;
                border-radius: 3px;
            }
        """)

        # 대시보드 레이블 스타일 업데이트
        label_style = """
            QLabel {
                background-color: white;
                padding: 10px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                color: #424242;
                font-weight: bold;
            }
        """

        self.setWindowTitle(GUI_CONFIG['window_title'])
        self.setGeometry(100, 100, GUI_CONFIG['window_width'], GUI_CONFIG['window_height'])

        # 상태 표시줄 추가
        self.statusBar = self.statusBar()
        self.statusBar.showMessage('준비')

        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 메인 레이아웃을 수평 분할
        main_layout = QHBoxLayout(central_widget)
        
        # 왼쪽 패널 (설정 + 잔고)
        left_panel = QVBoxLayout()
        
        # API 설정 그룹
        api_group = QGroupBox('API 설정')
        api_layout = QVBoxLayout()
        
        # API Key
        api_key_layout = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setText(DEFAULT_CONFIG['api_key'])
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)  # 비밀번호 모드로 설정
        api_key_layout.addWidget(QLabel('API Key:'))
        api_key_layout.addWidget(self.api_key_edit)
        
        # API Secret
        api_secret_layout = QHBoxLayout()
        self.api_secret_edit = QLineEdit()
        self.api_secret_edit.setText(DEFAULT_CONFIG['api_secret'])
        self.api_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)  # 비밀번호 모드로 설정
        api_secret_layout.addWidget(QLabel('API Secret:'))
        api_secret_layout.addWidget(self.api_secret_edit)
        
        # 계좌번호
        account_layout = QHBoxLayout()
        self.account_edit = QLineEdit()
        self.account_edit.setText(DEFAULT_CONFIG['account_number'])
        account_layout.addWidget(QLabel('계좌번호:'))
        account_layout.addWidget(self.account_edit)
        
        # 모의투자 여부
        paper_layout = QHBoxLayout()
        self.paper_check = QCheckBox('모의투자')
        self.paper_check.setChecked(DEFAULT_CONFIG['is_paper_trading'])
        paper_layout.addWidget(self.paper_check)
        
        # API 설정 잠금
        lock_layout = QHBoxLayout()
        self.lock_button = QPushButton('🔒 Lock')
        self.lock_button.setCheckable(True)
        self.lock_button.clicked.connect(self.toggle_lock)
        lock_layout.addWidget(self.lock_button)
        
        api_layout.addLayout(api_key_layout)
        api_layout.addLayout(api_secret_layout)
        api_layout.addLayout(account_layout)
        api_layout.addLayout(paper_layout)
        api_layout.addLayout(lock_layout)
        api_group.setLayout(api_layout)

        # 매수 설정 그룹
        order_group = QGroupBox('매수 설정')
        order_layout = QVBoxLayout()
        
        # 종목코드 레이블과 종목명 레이블을 동일한 너비로 설정
        label_width = 80  # 레이블 너비 지정
        
        # 종목코드
        symbol_layout = QHBoxLayout()
        symbol_label = QLabel('종목코드:')
        symbol_label.setFixedWidth(label_width)  # 레이블 너비 고정
        self.symbol_edit = QLineEdit()
        self.symbol_edit.setText(DEFAULT_CONFIG['symbol'])
        symbol_layout.addWidget(symbol_label)
        symbol_layout.addWidget(self.symbol_edit)
        
        # 조회 버튼 추가
        self.lookup_button = QPushButton('조회')
        self.lookup_button.clicked.connect(self.lookup_bond_name)
        symbol_layout.addWidget(self.lookup_button)
        
        # 종목명 표시 레이블 추가
        name_layout = QHBoxLayout()
        name_label = QLabel('종목명:')
        name_label.setFixedWidth(label_width)  # 레이블 너비 고정
        self.bond_name_label = QLabel('-')
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.bond_name_label)
        name_layout.addStretch()  # 오른쪽 여백 추가
        
        # 레이아웃에 종목명 추가
        order_layout.addLayout(symbol_layout)
        order_layout.addLayout(name_layout)  # 종목코드 바로 아래에 종목명 추가
        
        # 목표수량
        target_qty_layout = QHBoxLayout()
        self.target_qty_edit = QLineEdit()
        self.target_qty_edit.setText(str(DEFAULT_CONFIG['target_quantity']))
        target_qty_layout.addWidget(QLabel('목표수량:'))
        target_qty_layout.addWidget(self.target_qty_edit)
        
        # 1회 매수수량
        order_qty_layout = QHBoxLayout()
        self.order_qty_edit = QLineEdit()
        self.order_qty_edit.setText(str(DEFAULT_CONFIG['order_quantity']))
        order_qty_layout.addWidget(QLabel('1회 매수수량:'))
        order_qty_layout.addWidget(self.order_qty_edit)
        
        # 매수가격 범위
        price_layout = QHBoxLayout()
        self.min_price_edit = QLineEdit()
        self.min_price_edit.setText(str(DEFAULT_CONFIG['min_price']))
        self.max_price_edit = QLineEdit()
        self.max_price_edit.setText(str(DEFAULT_CONFIG['max_price']))
        price_layout.addWidget(QLabel('매수가격 범위:'))
        price_layout.addWidget(self.min_price_edit)
        price_layout.addWidget(QLabel('~'))
        price_layout.addWidget(self.max_price_edit)
        
        # 조회간격
        interval_layout = QHBoxLayout()
        self.interval_edit = QLineEdit()
        self.interval_edit.setText(str(DEFAULT_CONFIG['interval']))
        interval_layout.addWidget(QLabel('조회간격(초):'))
        interval_layout.addWidget(self.interval_edit)
        
        order_layout.addLayout(target_qty_layout)
        order_layout.addLayout(order_qty_layout)
        order_layout.addLayout(price_layout)
        order_layout.addLayout(interval_layout)
        order_group.setLayout(order_layout)

        # 잔고 조회 그룹 추가
        quote_group = QGroupBox('호가 정보')
        quote_layout = QVBoxLayout()
        
        # 호가 표시 영역
        self.quote_text = QTextEdit()
        self.quote_text.setReadOnly(True)
        self.quote_text.setMinimumHeight(150)
        
        # 호가 조회 버튼
        quote_button_layout = QHBoxLayout()
        self.quote_button = QPushButton('호가 조회')
        self.quote_button.clicked.connect(self.lookup_quote)
        quote_button_layout.addWidget(self.quote_button)
        
        quote_layout.addWidget(self.quote_text)
        quote_layout.addLayout(quote_button_layout)
        quote_group.setLayout(quote_layout)
        
        # 왼쪽 패널에 위젯 추가
        left_panel.addWidget(api_group)
        left_panel.addWidget(order_group)
        left_panel.addWidget(quote_group)
        
        # 시작/긴급중지 버튼
        button_layout = QHBoxLayout()
        
        # 시작 버튼 스타일 설정
        self.start_button = QPushButton('시작')
        self.start_button.clicked.connect(self.start_monitoring)
        
        # 긴급 중지 버튼 스타일 설정
        self.emergency_button = QPushButton('긴급 중지')
        self.emergency_button.clicked.connect(self.emergency_stop)
        self.emergency_button.setEnabled(False)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.emergency_button)
        
        left_panel.addLayout(button_layout)
        
        # 오른쪽 패널 (잔고 + 대시보드 + 로그)
        right_panel = QVBoxLayout()
        
        # 잔고 현황 그룹
        balance_group = QGroupBox('잔고 현황')
        balance_layout = QVBoxLayout()
        self.balance_text = QTextEdit()
        self.balance_text.setReadOnly(True)
        
        # 잔고 조회 버튼
        balance_button_layout = QHBoxLayout()
        self.balance_button = QPushButton('잔고 조회')
        self.balance_button.clicked.connect(self.lookup_balance)
        balance_button_layout.addWidget(self.balance_button)
        
        balance_layout.addWidget(self.balance_text)
        balance_layout.addLayout(balance_button_layout)
        balance_group.setLayout(balance_layout)
        
        # 대시보드 그룹
        dashboard_group = QGroupBox('대시보드')
        dashboard_layout = QGridLayout()
        
        # 대시보드 레이블 스타일
        label_style = """
            QLabel {
                background-color: white;
                padding: 10px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                color: #424242;
                font-weight: bold;
            }
        """
        
        # 목표 종목 정보
        target_info = QLabel('목표 종목: -')
        target_info.setStyleSheet(label_style)
        dashboard_layout.addWidget(target_info, 0, 0, 1, 2)
        self.target_info = target_info
        
        # 현재가
        current_price = QLabel('현재가: -')
        current_price.setStyleSheet(label_style)
        dashboard_layout.addWidget(current_price, 1, 0)
        self.current_price = current_price
        
        # 보유수량
        holding_qty = QLabel('보유수량: -')
        holding_qty.setStyleSheet(label_style)
        dashboard_layout.addWidget(holding_qty, 1, 1)
        self.holding_qty = holding_qty
        
        # 매수 진행률
        progress = QLabel('매수 진행률: -')
        progress.setStyleSheet(label_style)
        dashboard_layout.addWidget(progress, 2, 0)
        self.progress = progress
        
        # 주문 상태
        order_status = QLabel('주문 상태: -')
        order_status.setStyleSheet(label_style)
        dashboard_layout.addWidget(order_status, 2, 1)
        self.order_status = order_status
        
        dashboard_group.setLayout(dashboard_layout)
        
        # 로그 그룹
        log_group = QGroupBox('로그')
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        # 스플리터 생성 및 위젯 추가
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(balance_group)
        splitter.addWidget(dashboard_group)  # 대시보드를 중간에 추가
        splitter.addWidget(log_group)
        
        # 스플리터 비율 설정 (3:2:5)
        splitter.setSizes([300, 200, 500])
        
        # 오른쪽 패널에 스플리터 추가
        right_panel.addWidget(splitter)
        
        # 메인 레이아웃에 패널 추가 (비율 수정: 40:60 -> 40:60)
        main_layout.addLayout(left_panel, 40)  # 40% 너비
        main_layout.addLayout(right_panel, 60)  # 60% 너비
        
        # UI 요소 생성이 완료된 후 스타일 적용
        # 시작 버튼 스타일
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                padding: 10px 20px;
                font-size: 14px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)

        # 긴급 중지 버튼 스타일
        self.emergency_button.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                padding: 10px 20px;
                font-size: 14px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
        """)

        # 조회 버튼 스타일
        lookup_button_style = """
            QPushButton {
                background-color: #607D8B;
                padding: 6px 12px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #455A64;
            }
        """
        
        self.quote_button.setStyleSheet(lookup_button_style)
        self.balance_button.setStyleSheet(lookup_button_style)
        self.lookup_button.setStyleSheet(lookup_button_style)

        # Lock 버튼 스타일
        self.lock_button.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                padding: 6px 12px;
                color: white;
                font-weight: bold;
                min-width: 100px;  /* 버튼 최소 너비 증가 */
                font-size: 13px;   /* 글자 크기 조정 */
            }
            QPushButton:checked {
                background-color: #FF5722;
                border: none;      /* 테두리 제거 */
            }
            QPushButton:hover {
                background-color: #757575;
            }
            QPushButton:checked:hover {
                background-color: #D84315;
            }
        """)

    def toggle_lock(self):
        """API 설정 잠금/해제"""
        is_locked = self.lock_button.isChecked()
        
        # 잠금 상태에 따른 색상 설정
        color = Qt.GlobalColor.darkGray if is_locked else Qt.GlobalColor.black
        
        # API Key 설정
        self.api_key_edit.setReadOnly(is_locked)
        palette = self.api_key_edit.palette()
        palette.setColor(palette.ColorRole.Text, color)
        self.api_key_edit.setPalette(palette)
        
        # API Secret 설정
        self.api_secret_edit.setReadOnly(is_locked)
        palette = self.api_secret_edit.palette()
        palette.setColor(palette.ColorRole.Text, color)
        self.api_secret_edit.setPalette(palette)
        
        # 계좌번호 설정
        self.account_edit.setReadOnly(is_locked)
        palette = self.account_edit.palette()
        palette.setColor(palette.ColorRole.Text, color)
        self.account_edit.setPalette(palette)
        
        # 모의투자 체크박스 설정
        self.paper_check.setEnabled(not is_locked)
        palette = self.paper_check.palette()
        palette.setColor(palette.ColorRole.WindowText, color)
        self.paper_check.setPalette(palette)
        
        # 버튼 텍스트 및 스타일 변경
        if is_locked:
            self.lock_button.setText('🔓 Unlock')
            self.statusBar.showMessage('API 설정이 잠겼습니다')
        else:
            self.lock_button.setText('🔒 Lock')
            self.statusBar.showMessage('API 설정이 해제되었습니다')

    def get_config(self):
        """설정값 가져오기"""
        return {
            'api_key': self.api_key_edit.text(),
            'api_secret': self.api_secret_edit.text(),
            'account_number': self.account_edit.text(),
            'is_paper_trading': self.paper_check.isChecked(),
            'symbol': self.symbol_edit.text(),
            'target_quantity': int(self.target_qty_edit.text()),
            'order_quantity': int(self.order_qty_edit.text()),
            'min_price': float(self.min_price_edit.text()),
            'max_price': float(self.max_price_edit.text()),
            'interval': int(self.interval_edit.text())
        }

    async def cancel_all_orders(self, api):
        """진행중인 모든 주문 취소"""
        try:
            # 미체결 주문 조회
            url = API_URLS['orders']
            params = {
                "CANO": self.account_edit.text()[:8],
                "ACNT_PRDT_CD": self.account_edit.text()[8:],
                "ORD_DT": "",
                "ODNO": "",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['orders'],
                "custtype": "P"
            }
            
            result = await api.request("get", url, params=params, headers=headers)
            orders = result.get("output", [])
            
            # 각 미체결 주문에 대해 취소 요청
            for order in orders:
                cancel_url = API_URLS['modify']
                cancel_data = {
                    "CANO": self.account_edit.text()[:8],
                    "ACNT_PRDT_CD": self.account_edit.text()[8:],
                    "PDNO": order.get('pdno', ''),
                    "ORGN_ODNO": order.get('odno', ''),
                    "ORD_QTY2": order.get('ord_qty', '0'),
                    "PRDT_TYPE_CD": "302"
                }
                
                cancel_headers = {
                    "content-type": "application/json; charset=utf-8",
                    "authorization": f"Bearer {await api._get_access_token()}",
                    "appkey": api.api_key,
                    "appsecret": api.api_secret,
                    "tr_id": TR_ID['modify'],
                    "custtype": "P"
                }
                
                await api.request("post", cancel_url, data=cancel_data, headers=cancel_headers)
                
            return len(orders)
            
        except Exception as e:
            raise Exception(f"주문 취소 실패: {str(e)}")

    def emergency_stop(self):
        """긴급 중지 처리"""
        try:
            # API 인스턴스 생성
            api = KISApi(
                api_key=self.api_key_edit.text(),
                api_secret=self.api_secret_edit.text(),
                account_number=self.account_edit.text(),
                is_paper_trading=self.paper_check.isChecked()
            )
            
            async def emergency_process():
                try:
                    # 진행중인 주문 취소
                    cancelled_count = await self.cancel_all_orders(api)
                    
                    # 모니터링 중지
                    if self.monitor_thread:
                        self.monitor_thread.stop()
                    
                    # 상태 업데이트
                    self.start_button.setEnabled(True)
                    self.emergency_button.setEnabled(False)
                    self.lock_button.setEnabled(True)
                    
                    # 결과 메시지
                    msg = f"긴급 중지 완료\n- 취소된 주문: {cancelled_count}건"
                    self.append_log(f"\n{msg}")
                    self.statusBar.showMessage("긴급 중지 완료")
                    
                    # 알림창 표시
                    QMessageBox.information(self, "긴급 중지", msg)
                    
                except Exception as e:
                    error_msg = f"긴급 중지 처리 실패: {str(e)}"
                    self.append_log(f"\n{error_msg}")
                    QMessageBox.critical(self, "오류", error_msg)
            
            # 비동기 실행
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(emergency_process())
            loop.close()
            
        except Exception as e:
            error_msg = f"긴급 중지 오류: {str(e)}"
            self.append_log(f"\n{error_msg}")
            QMessageBox.critical(self, "오류", error_msg)

    def start_monitoring(self):
        """모니터링 시작"""
        try:
            config = self.get_config()
            self.monitor_thread = MonitorThread(config)
            self.monitor_thread.log_signal.connect(self.append_log)
            self.monitor_thread.finished_signal.connect(self.on_monitoring_finished)
            self.monitor_thread.target_achieved_signal.connect(self.show_target_achieved)
            self.monitor_thread.price_error_signal.connect(self.show_price_error)
            
            # 대시보드 초기화
            self.update_dashboard({
                'target_info': f"{config['symbol']} (목표: {config['target_quantity']:,})",
                'current_price': 0.0,
                'holding_qty': 0,
                'progress': 0,
                'order_status': '모니터링 시작'
            })
            
            self.monitor_thread.start()
            
            self.start_button.setEnabled(False)
            self.emergency_button.setEnabled(True)
            self.lock_button.setEnabled(False)
            
        except Exception as e:
            self.append_log(f"시작 오류: {e}")
            
    def on_monitoring_finished(self):
        """모니터링 종료 처리"""
        self.monitor_thread = None
        self.start_button.setEnabled(True)
        self.emergency_button.setEnabled(False)
        self.lock_button.setEnabled(True)

    def append_log(self, message):
        """로그 추가"""
        self.log_text.append(message)
        # 스크롤을 항상 아래로
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_target_achieved(self, message):
        """목표 달성 경고창 표시"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("목표 달성")
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        
        # 프로그램 종료
        QApplication.quit()

    def show_price_error(self, message):
        """가격 오류 경고창 표시"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("가격 범위 초과")
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        
        # 프로그램 종료
        QApplication.quit()

    async def get_bond_name(self, api, symbol):
        """채권 종목명 조회"""
        try:
            url = API_URLS['issue_info']
            
            params = {
                "PDNO": symbol,                 # 채권종목코드
                "PRDT_TYPE_CD": "302"          # 상품유형코드 (302: 채권)
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": TR_ID['issue_info'],
                "custtype": "P"
            }
            
            result = await api.request("get", url, params=params, headers=headers)
            return result.get("output", {}).get("prdt_name", "-")
            
        except Exception as e:
            return f"조회 실패: {str(e)}"

    def lookup_bond_name(self):
        """종목명 조회 버튼 클릭 핸들러"""
        try:
            # API 설정 가져오기
            config = {
                'api_key': self.api_key_edit.text(),
                'api_secret': self.api_secret_edit.text(),
                'account_number': self.account_edit.text(),
                'is_paper_trading': self.paper_check.isChecked()
            }
            
            # API 인스턴스 생성
            api = KISApi(
                api_key=config['api_key'],
                api_secret=config['api_secret'],
                account_number=config['account_number'],
                is_paper_trading=config['is_paper_trading']
            )
            
            # 종목코드 가져오기
            symbol = self.symbol_edit.text().strip()
            if not symbol:
                self.bond_name_label.setText("종목코드를 입력하세요")
                return
            
            # 비동기 조회 실행
            async def lookup():
                name = await self.get_bond_name(api, symbol)
                self.bond_name_label.setText(name)
                self.append_log(f"\n종목코드 {symbol} 조회 결과: {name}")
            
            # 비동기 실행을 위한 이벤트 루프 생성
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(lookup())
            loop.close()
            
        except Exception as e:
            self.bond_name_label.setText(f"조회 오류: {str(e)}")
            self.append_log(f"\n종목코드 조회 중 오류 발생: {str(e)}")

    def lookup_balance(self):
        """잔고 조회 버튼 클릭 핸들러"""
        try:
            config = self.get_config()
            api = KISApi(
                api_key=config['api_key'],
                api_secret=config['api_secret'],
                account_number=config['account_number'],
                is_paper_trading=config['is_paper_trading']
            )
            
            async def check_balance():
                try:
                    url = API_URLS['balance']
                    params = {
                        "CANO": config['account_number'][:8],
                        "ACNT_PRDT_CD": config['account_number'][8:],
                        "INQR_CNDT": "00",
                        "PDNO": "",
                        "BUY_DT": "",
                        "CTX_AREA_FK200": "",
                        "CTX_AREA_NK200": ""
                    }
                    
                    headers = {
                        "content-type": "application/json; charset=utf-8",
                        "authorization": f"Bearer {await api._get_access_token()}",
                        "appkey": api.api_key,
                        "appsecret": api.api_secret,
                        "tr_id": TR_ID['balance'],
                        "custtype": "P"
                    }
                    
                    result = await api.request("get", url, params=params, headers=headers)
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"조회 실패: {result.get('msg1')}")
                    
                    output = result.get("output", [])
                    current_time = datetime.now().strftime('%H:%M:%S')
                    
                    balance_text = f"=== 채권 잔고 현황 ({current_time}) ===\n"
                    balance_text += "-" * 40 + "\n"
                    
                    if not output:
                        balance_text += "보유중인 채권이 없습니다.\n"
                    else:
                        for bond in output:
                            balance_text += f"종목명: {bond.get('prdt_name', '-')}\n"
                            balance_text += f"매수일자: {bond.get('buy_dt', '-')}\n"
                            balance_text += f"잔고수량: {int(bond.get('cblc_qty', '0')):,}\n"
                            balance_text += f"주문가능수량: {int(bond.get('ord_psbl_qty', '0')):,}\n"
                            balance_text += "-" * 40 + "\n"
                    
                    self.balance_text.setText(balance_text)
                    
                except Exception as e:
                    self.balance_text.setText(f"잔고 조회 실패: {str(e)}")
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(check_balance())
            loop.close()
            
        except Exception as e:
            self.balance_text.setText(f"잔고 조회 오류: {str(e)}")

    def lookup_quote(self):
        """호가 조회 버튼 클릭 핸들러"""
        try:
            config = self.get_config()
            api = KISApi(
                api_key=config['api_key'],
                api_secret=config['api_secret'],
                account_number=config['account_number'],
                is_paper_trading=config['is_paper_trading']
            )
            
            async def check_quote():
                try:
                    symbol = self.symbol_edit.text().strip()
                    if not symbol:
                        raise Exception("종목코드를 입력하세요")

                    url = API_URLS['quote']
                    params = {
                        "FID_COND_MRKT_DIV_CODE": "B",  # 시장구분: B(채권)
                        "FID_INPUT_ISCD": symbol,        # 종목코드
                    }
                    
                    headers = {
                        "content-type": "application/json; charset=utf-8",
                        "authorization": f"Bearer {await api._get_access_token()}",
                        "appkey": api.api_key,
                        "appsecret": api.api_secret,
                        "tr_id": TR_ID['quote'],
                        "custtype": "P"
                    }
                    
                    result = await api.request("get", url, params=params, headers=headers)
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"조회 실패: {result.get('msg1')}")
                    
                    output = result.get("output", {})
                    current_time = datetime.now().strftime('%H:%M:%S')
                    
                    # 매도호가와 매수호가를 리스트로 정리
                    ask_prices = [
                        (float(output.get(f'bond_askp{i}', '0')), 
                         int(output.get(f'askp_rsqn{i}', '0')))
                        for i in range(1, 6)
                    ]
                    
                    bid_prices = [
                        (float(output.get(f'bond_bidp{i}', '0')), 
                         int(output.get(f'bidp_rsqn{i}', '0')))
                        for i in range(1, 6)
                    ]
                    
                    # 가격 내림차순 정렬
                    ask_prices.sort(reverse=True)
                    bid_prices.sort(reverse=True)
                    
                    quote_text = f"=== 호가 정보 ({current_time}) ===\n"
                    quote_text += "-" * 40 + "\n"
                    quote_text += "\n매도호가\n"
                    quote_text += "-" * 40 + "\n"
                    
                    for price, volume in ask_prices:
                        if price > 0:
                            quote_text += f"{price:>10,.3f}  {volume:>8,}\n"
                    
                    quote_text += "\n매수호가\n"
                    quote_text += "-" * 40 + "\n"
                    
                    for price, volume in bid_prices:
                        if price > 0:
                            quote_text += f"{price:>10,.3f}  {volume:>8,}\n"
                    
                    self.quote_text.setText(quote_text)
                    self.statusBar.showMessage('호가 조회 완료')
                    
                except Exception as e:
                    error_msg = f"호가 조회 실패: {str(e)}"
                    self.quote_text.setText(error_msg)
                    self.statusBar.showMessage(error_msg)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(check_quote())
            loop.close()
            
        except Exception as e:
            error_msg = f"호가 조회 오류: {str(e)}"
            self.quote_text.setText(error_msg)
            self.statusBar.showMessage(error_msg)

    def update_dashboard(self, data):
        """대시보드 업데이트"""
        try:
            # 목표 종목 정보 업데이트
            if 'target_info' in data:
                self.target_info.setText(f"목표 종목: {data['target_info']}")
            
            # 현재가 업데이트
            if 'current_price' in data:
                self.current_price.setText(f"현재가: {data['current_price']:,.2f}")
            
            # 보유수량 업데이트
            if 'holding_qty' in data:
                self.holding_qty.setText(f"보유수량: {data['holding_qty']:,}")
            
            # 매수 진행률 업데이트
            if 'progress' in data:
                self.progress.setText(f"매수 진행률: {data['progress']}%")
            
            # 주문 상태 업데이트
            if 'order_status' in data:
                self.order_status.setText(f"주문 상태: {data['order_status']}")
                
        except Exception as e:
            self.append_log(f"\n대시보드 업데이트 오류: {str(e)}")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 