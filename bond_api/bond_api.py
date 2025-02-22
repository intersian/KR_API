import asyncio
import json
import os
import time
from datetime import datetime
import aiohttp

class TokenManager:
    """토큰 관리 클래스"""
    def __init__(self):
        self.token_file = "token.json"
        
    def load_token(self, api_key):
        """저장된 토큰 로드"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    token_info = json.load(f)
                    if token_info.get('api_key') == api_key:  # API 키가 같은 경우만
                        expired_at = token_info.get('expired_at', 0)
                        now = time.time()
                        if now < expired_at - 300:  # 만료 5분 전까지 재사용
                            return token_info.get('access_token')
            return None
        except Exception:
            return None
            
    def save_token(self, api_key, token):
        """토큰 정보 저장"""
        try:
            token_info = {
                'api_key': api_key,
                'access_token': token,
                'expired_at': time.time() + 86400  # 24시간
            }
            with open(self.token_file, 'w') as f:
                json.dump(token_info, f)
            return True
        except Exception:
            return False

async def get_bond_name(api, symbol):
    """채권 종목명 조회"""
    try:
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/issue-info"
        
        params = {
            "PDNO": symbol,  # 시장구분: 채권
            "PRDT_TYPE_CD": "302"         # 종목코드
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "CTPF1101R",  # TR ID 변경
            "custtype": "P"
        }
        
        result = await api.request("get", url, params=params, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"조회 실패: {result.get('msg1')}")
            
        bond_name = result.get("output", {}).get("prdt_name", "-")
        return bond_name
        
    except Exception as e:
        return f"조회 실패: {str(e)}"

class BondApi:
    """채권 API 클래스"""
    
    def __init__(self, api_key, api_secret, account_number, is_paper=False):
        """초기화"""
        self.api_key = api_key
        self.api_secret = api_secret
        self.account_number = account_number
        self.is_paper = is_paper
        
        # API 기본 설정
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.token_file = "token.json"
        
        # 토큰 정보
        self.access_token = None
        self.token_expired_at = None
        
    async def request(self, method, url, **kwargs):
        """API 요청 공통 메서드"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, **kwargs) as response:
                    result = await response.json()
                    return result
        except Exception as e:
            raise Exception(f"API 요청 실패: {str(e)}")
        
    async def _get_access_token(self):
        """액세스 토큰 조회 (24시간 유효)"""
        try:
            # 1. 기존 토큰이 있고 유효한지 확인
            if self.access_token and self.token_expired_at:
                now = time.time()
                if now < self.token_expired_at - 300:  # 만료 5분 전까지 재사용
                    return self.access_token
            
            # 2. 저장된 토큰 확인
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    token_info = json.load(f)
                    if token_info.get('api_key') == self.api_key:  # API 키가 같은 경우만
                        expired_at = token_info.get('expired_at', 0)
                        now = time.time()
                        if now < expired_at - 300:  # 만료 5분 전까지 재사용
                            self.access_token = token_info['access_token']
                            self.token_expired_at = expired_at
                            return self.access_token
            
            # 3. 새로운 토큰 발급
            url = f"{self.base_url}/oauth2/tokenP"
            
            data = {
                "grant_type": "client_credentials",
                "appkey": self.api_key,
                "appsecret": self.api_secret
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    
                    if response.status != 200:
                        raise Exception(f"토큰 발급 실패: {result}")
                    
                    self.access_token = result.get('access_token')
                    self.token_expired_at = time.time() + result.get('expires_in', 86400)
                    
                    # 토큰 정보 저장
                    token_info = {
                        'api_key': self.api_key,
                        'access_token': self.access_token,
                        'expired_at': self.token_expired_at
                    }
                    with open(self.token_file, 'w') as f:
                        json.dump(token_info, f)
                    
                    return self.access_token
                    
        except Exception as e:
            raise Exception(f"토큰 조회 실패: {str(e)}")
            
    async def get_bond_info(self, symbol):
        """채권 기본 정보 조회"""
        try:
            url = f"{self.base_url}/uapi/domestic-bond/v1/quotations/issue-info"
            
            params = {
                "PDNO": symbol,           # 종목코드
                "PRDT_TYPE_CD": "302"     # 상품유형코드 (302: 채권)
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await self._get_access_token()}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "CTPF1101R",     # 채권 발행정보 조회
                "custtype": "P"           # 개인
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"조회 실패: {result.get('msg1')}")
                        
                    return result.get("output", {})
                    
        except Exception as e:
            raise Exception(f"채권 정보 조회 실패: {str(e)}")
            
    async def get_bond_quote(self, symbol):
        """채권 호가 조회"""
        try:
            url = f"{self.base_url}/uapi/domestic-bond/v1/quotations/inquire-asking-price"
            
            params = {
                "FID_COND_MRKT_DIV_CODE": "B",  # 시장구분: B(채권)
                "FID_INPUT_ISCD": symbol,        # 종목코드
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await self._get_access_token()}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHKBJ773401C0",  # 채권 호가 조회
                "custtype": "P"            # 개인
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"조회 실패: {result.get('msg1')}")
                        
                    return result.get("output", {})
                    
        except Exception as e:
            raise Exception(f"채권 호가 조회 실패: {str(e)}")
            
    async def get_bond_balance(self):
        """채권 잔고 조회"""
        try:
            url = f"{self.base_url}/uapi/domestic-bond/v1/trading/inquire-balance"
            
            params = {
                "CANO": self.account_number[:8],           # 종합계좌번호
                "ACNT_PRDT_CD": self.account_number[8:],  # 계좌상품코드
                "INQR_CNDT": "00",
                "PDNO": "",
                "BUY_DT": "",
                "CTX_AREA_FK200": "",         # 연속조회검색조건
                "CTX_AREA_NK200": ""          # 연속조회키
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await self._get_access_token()}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "CTSC8407R",         # 채권 잔고 조회
                "custtype": "P"               # 개인
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"조회 실패: {result.get('msg1')}")
                        
                    return result.get("output", [])
                    
        except Exception as e:
            raise Exception(f"채권 잔고 조회 실패: {str(e)}")
            
    async def get_bond_orders(self):
        """정정취소가능한 채권 주문 조회"""
        try:
            url = f"{self.base_url}/uapi/domestic-bond/v1/trading/inquire-psbl-rvsecncl"
            
            params = {
                "CANO": self.account_number[:8],           # 종합계좌번호
                "ACNT_PRDT_CD": self.account_number[8:],  # 계좌상품코드
                "ORD_DT": "",
                "ODNO": "",
                "CTX_AREA_FK200": "",         # 연속조회검색조건
                "CTX_AREA_NK200": ""          # 연속조회키
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await self._get_access_token()}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "CTSC8035R",         # 채권 주문 조회
                "custtype": "P"               # 개인
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"조회 실패: {result.get('msg1')}")
                        
                    return result.get("output", [])
                    
        except Exception as e:
            raise Exception(f"채권 주문 조회 실패: {str(e)}")
            
    async def modify_bond_order(self, order_no, symbol, new_price):
        """채권 주문 정정"""
        try:
            url = f"{self.base_url}/uapi/domestic-bond/v1/trading/order-rvsecncl"
            
            data = {
                "CANO": self.account_number[:8],           # 종합계좌번호
                "ACNT_PRDT_CD": self.account_number[8:],  # 계좌상품코드
                "PDNO": symbol,              # 종목코드
                "ORGN_ODNO": order_no,       # 원주문번호
                "RVSE_CNCL_DVSN_CD": "01",   # 정정취소구분코드 (01: 정정)
                "ORD_QTY2": "0",             # 주문수량2 (0: 전량)
                "BOND_ORD_UNPR": str(new_price),  # 채권주문단가
                "QTY_ALL_ORD_YN": "Y",       # 주문수량전체여부
                "MGCO_APTM_ODNO": "",        # 운용사지정주문번호
                "ORD_SVR_DVSN_CD": "0",      # 주문서버구분코드
                "CTAC_TLNO": "",             # 연락전화번호
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await self._get_access_token()}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "TTTC0953U",         # 채권 주문 정정
                "custtype": "P"               # 개인
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"정정 실패: {result.get('msg1')}")
                        
                    return result.get("output", {})
                    
        except Exception as e:
            raise Exception(f"채권 주문 정정 실패: {str(e)}")
            
    async def cancel_bond_order(self, order_no, symbol):
        """채권 주문 취소"""
        try:
            url = f"{self.base_url}/uapi/domestic-bond/v1/trading/order-rvsecncl"
            
            data = {
                "CANO": self.account_number[:8],           # 종합계좌번호
                "ACNT_PRDT_CD": self.account_number[8:],  # 계좌상품코드
                "PDNO": symbol,              # 종목코드
                "ORGN_ODNO": order_no,       # 원주문번호
                "ORD_QTY2": "0",             # 주문수량2 (0: 전량)
                "BOND_ORD_UNPR": "0",        # 채권주문단가 (취소 시 0)
                "QTY_ALL_ORD_YN": "Y",       # 주문수량전체여부
                "RVSE_CNCL_DVSN_CD": "02",   # 정정취소구분코드 (02: 취소)
                "MGCO_APTM_ODNO": "",        # 운용사지정주문번호
                "ORD_SVR_DVSN_CD": "0",      # 주문서버구분코드
                "CTAC_TLNO": "",             # 연락전화번호
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await self._get_access_token()}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "TTTC0953U",         # 채권 주문 취소
                "custtype": "P"               # 개인
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"취소 실패: {result.get('msg1')}")
                        
                    return result.get("output", {})
                    
        except Exception as e:
            raise Exception(f"채권 주문 취소 실패: {str(e)}")
            
    async def place_bond_order(self, symbol, quantity, price):
        """채권 매수 주문"""
        try:
            url = f"{self.base_url}/uapi/domestic-bond/v1/trading/buy"
            
            data = {
                "CANO": self.account_number[:8],           # 종합계좌번호
                "ACNT_PRDT_CD": self.account_number[8:],  # 계좌상품코드
                "PDNO": symbol,                 # 상품번호
                "ORD_QTY2": str(quantity),      # 주문수량2
                "BOND_ORD_UNPR": str(price),    # 채권주문단가
                "SAMT_MKET_PTCI_YN": "N",       # 소액시장접근여부
                "BOND_RTL_MKET_YN": "N",        # 채권소매시장여부
                "IDCR_STFNO": "",               # 유치자직원번호
                "MGCO_APTM_ODNO": "",           # 운용사지정주문번호
                "ORD_SVR_DVSN_CD": "0",         # 주문서버구분코드
                "CTAC_TLNO": ""                 # 연락전화번호
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await self._get_access_token()}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "TTTC0952U",  # 채권 매수 주문
                "custtype": "P"        # 개인
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("rt_cd") != "0":
                        raise Exception(f"주문 실패: {result.get('msg1')}")
                        
                    return result.get("output", {})
                    
        except Exception as e:
            raise Exception(f"채권 매수 주문 실패: {str(e)}") 