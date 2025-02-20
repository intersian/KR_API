import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta
import os

import aiohttp
import requests

class KISApi:
    def __init__(self, api_key, api_secret, account_number, is_paper_trading=True):
        """
        한국투자증권 API 클래스 초기화
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.account_number = account_number
        
        # 환경 설정
        if is_paper_trading:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"
            
        self.access_token = None
        self.token_expired_at = None
        self.last_token_request = None
        
        # 웹소켓 승인키 관련
        self.approval_key = None
        self.approval_key_expired_at = None
        
        # 토큰 파일 경로
        self.token_file = "shv_alarm/token_info.json"
        # 저장된 토큰 로드
        self._load_token()
        
    def _load_token(self):
        """저장된 토큰 정보 로드"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    token_info = json.load(f)
                    
                    # 토큰 유효성 검사
                    if (token_info.get("base_url") == self.base_url and  # 같은 환경인지 확인
                        token_info.get("api_key") == self.api_key and    # 같은 API 키인지 확인
                        token_info.get("expired_at", 0) > time.time()):  # 만료되지 않았는지 확인
                        
                        self.access_token = token_info.get("access_token")
                        self.token_expired_at = token_info.get("expired_at")
                        self.approval_key = token_info.get("approval_key")
                        self.approval_key_expired_at = token_info.get("approval_key_expired_at")
                        print("저장된 토큰을 로드했습니다.")
                        return True
                    else:
                        print("저장된 토큰이 만료되었거나 유효하지 않습니다.")
        except Exception as e:
            print(f"토큰 로드 중 오류 발생: {str(e)}")
        return False
    
    def _save_token(self):
        """토큰 정보 저장"""
        try:
            token_info = {
                "access_token": self.access_token,
                "expired_at": self.token_expired_at,
                "approval_key": self.approval_key,
                "approval_key_expired_at": self.approval_key_expired_at,
                "base_url": self.base_url,
                "api_key": self.api_key
            }
            
            with open(self.token_file, 'w') as f:
                json.dump(token_info, f)
                print("토큰 정보를 저장했습니다.")
        except Exception as e:
            print(f"토큰 저장 중 오류 발생: {str(e)}")

    async def check_connection(self):
        """API 연결 상태 확인"""
        try:
            access_token = await self._get_access_token()
            print(f"API 연결 성공!")
            print(f"토큰: {access_token[:20]}...")  # 토큰 일부만 출력
            return True
        except Exception as e:
            print(f"API 연결 실패: {e}")
            return False

    async def _get_access_token(self):
        """접근 토큰 발급"""
        now = datetime.now()
        
        # 기존 토큰이 유효한 경우 재사용
        if (self.access_token and self.token_expired_at and 
            now.timestamp() < self.token_expired_at - 300):  # 만료 5분 전까지 재사용
            return self.access_token
        
        # 토큰이 만료되었거나 없는 경우에만 새로 발급
        try:
            # 1분 이내 재요청 방지
            if (self.last_token_request and 
                now - self.last_token_request < timedelta(minutes=1)):
                wait_seconds = 60 - (now - self.last_token_request).seconds
                print(f"이전 요청으로부터 {wait_seconds}초 대기 필요")
                await asyncio.sleep(wait_seconds)
            
            url = f"{self.base_url}/oauth2/tokenP"
            
            data = {
                "grant_type": "client_credentials",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "expires_in": 86400  # 24시간으로 설정
            }
            
            headers = {
                "content-type": "application/json"
            }
            
            self.last_token_request = datetime.now()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    result = await response.json()
                    
                    if response.status != 200:
                        if result.get('error_code') == 'EGW00133':  # 토큰 발급 빈도 제한
                            print("1분 후 재시도합니다.")
                            await asyncio.sleep(60)
                            return await self._get_access_token()
                            
                        raise Exception(f"토큰 발급 실패: {result}")
                    
                    self.access_token = result.get("access_token")
                    self.token_expired_at = now.timestamp() + 86400  # 24시간 후 만료
                    
                    # 토큰 정보 저장
                    self._save_token()
                    
                    return self.access_token
                    
        except Exception as e:
            # 오류 발생 시 기존 토큰이 있고 아직 완전히 만료되지 않았다면 재사용
            if (self.access_token and self.token_expired_at and 
                now.timestamp() < self.token_expired_at):
                print(f"토큰 발급 오류, 기존 토큰 재사용: {str(e)}")
                return self.access_token
            raise

    def _get_headers(self, access_token, tr_id=None):
        """API 요청 헤더 생성"""
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {access_token}",
            "appkey": self.api_key,
            "appsecret": self.api_secret,
        }
        if tr_id:
            headers["tr_id"] = tr_id
            
        # 해외주식의 경우 추가 헤더
        if tr_id and tr_id.startswith("H"):
            headers["custtype"] = "P"  # 개인
            headers["hashkey"] = self._generate_hashkey(headers)
            
        return headers
        
    def _generate_hashkey(self, headers):
        """해시키 생성"""
        path = "uapi/hashkey"
        url = f"{self.base_url}/{path}"
        
        headers = {
            "content-type": "application/json",
            "appkey": self.api_key,
            "appsecret": self.api_secret
        }
        
        return ""  # 실제 해시키 생성 로직 필요시 구현

    async def get_overseas_stock_price(self, symbol):
        """해외주식 실시간 시세 조회"""
        access_token = await self._get_access_token()
        url = "https://openapi.koreainvestment.com:9443/uapi/overseas-price/v1/quotations/price"
        
        params = {
            "AUTH": "",
            "EXCD": "NAS",  # NASDAQ
            "SYMB": symbol,
            "OVRS_EXCG_CD": "NASD"  # NASDAQ 거래소 코드
        }
        
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {access_token}",
            "appkey": self.api_key,
            "appsecret": self.api_secret,
            "tr_id": "HHDFS00000300"  # 해외주식 현재가/기본정보
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                result = await response.json()
                
                if response.status != 200 or result.get("rt_cd") != "0":
                    raise Exception(f"시세 조회 실패: {result}")
                
                output = result.get("output", {})
                return {
                    "symbol": symbol,
                    "현재가": float(output.get("last", 0)),  # 현재가
                    "거래량": int(output.get("tvol", 0))    # 거래량
                }

    async def get_overseas_stock_trade(self, symbol):
        """해외주식 실시간 체결량 조회"""
        access_token = await self._get_access_token()
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/volume"
        
        params = {
            "AUTH": "",
            "EXCD": "NAS",  # NASDAQ
            "SYMB": symbol,
            "OVRS_EXCG_CD": "NASD"  # NASDAQ 거래소 코드
        }
        
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {access_token}",
            "appkey": self.api_key,
            "appsecret": self.api_secret,
            "tr_id": "HHDFS76200200"  # 해외주식 거래량
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                result = await response.json()
                
                if response.status != 200 or result.get("rt_cd") != "0":
                    raise Exception(f"거래량 조회 실패: {result}")
                
                output = result.get("output", {})
                return {
                    "symbol": symbol,
                    "volume": int(output.get("acml_vol", 0)),  # 누적 거래량
                    "value": float(output.get("acml_tr_pbmn", 0))  # 누적 거래대금
                }

    async def get_domestic_stock_price(self, symbol):
        """국내주식 실시간 시세 조회"""
        access_token = await self._get_access_token()
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        
        headers = self._get_headers(access_token, tr_id="FHKST01010100")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                result = await response.json()
                
                if response.status != 200:
                    raise Exception(f"국내 시세 조회 실패: {result}")
                
                try:
                    output_data = result["output"][0] if isinstance(result["output"], list) else result["output"]
                    
                    output = {
                        "symbol": symbol,
                        "last": float(output_data["stck_prpr"]),  # 현재가
                        "high": float(output_data["stck_hgpr"]),  # 고가
                        "low": float(output_data["stck_lwpr"])    # 저가
                    }
                    return output
                except KeyError as e:
                    raise Exception(f"데이터 파싱 오류: {e}")
                except ValueError as e:
                    raise Exception(f"데이터 형식 오류: {e}")

    async def get_domestic_stock_trade(self, symbol):
        """국내주식 실시간 체결량 조회"""
        access_token = await self._get_access_token()
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-ccnl"
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        
        headers = self._get_headers(access_token, tr_id="FHKST01010300")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                result = await response.json()
                
                if response.status != 200:
                    raise Exception(f"국내 체결량 조회 실패: {result}")
                
                output = {
                    "symbol": symbol,
                    "volume": int(result["output"]["acml_vol"]),  # 누적 거래량
                    "value": float(result["output"]["acml_tr_pbmn"])  # 누적 거래대금
                }
                return output

    async def get_stock_basic_info(self, symbol):
        """국내주식 종목 기본 정보 조회"""
        access_token = await self._get_access_token()
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": datetime.now().strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": datetime.now().strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
        
        headers = self._get_headers(access_token, tr_id="FHKST03010100")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                result = await response.json()
                
                if response.status != 200:
                    raise Exception(f"종목 정보 조회 실패: {result}")
                
                try:
                    output_data = result["output1"]  # 종목 정보
                    price_data = result["output2"][0] if result["output2"] else {}  # 가격 정보
                    
                    output = {
                        "종목코드": symbol,
                        "한글명": output_data.get("hts_kor_isnm", ""),  # 종목명
                        "시장구분": output_data.get("bstp_kor_isnm", ""),  # 시장구분
                        "현재가": float(price_data.get("stck_clpr", "0")),  # 종가
                        "전일대비": float(price_data.get("prdy_vrss", "0")),  # 전일대비
                        "등락률": float(price_data.get("prdy_ctrt", "0")),  # 등락률
                        "거래량": int(price_data.get("acml_vol", "0")),  # 거래량
                    }
                    return output
                except KeyError as e:
                    raise Exception(f"데이터 파싱 오류: {e}")
                except ValueError as e:
                    raise Exception(f"데이터 형식 오류: {e}")
                except Exception as e:
                    raise Exception(f"예기치 않은 오류: {e}")

    async def get_approval_key(self):
        """웹소켓 승인키 발급"""
        now = time.time()
        
        # 기존 승인키가 유효한 경우 재사용
        if (self.approval_key and self.approval_key_expired_at and 
            now < self.approval_key_expired_at - 300):  # 만료 5분 전까지 재사용
            return self.approval_key
        
        # 승인키가 만료되었거나 없는 경우 새로 발급
        url = f"{self.base_url}/oauth2/Approval"
        
        data = {
            "grant_type": "client_credentials",
            "appkey": self.api_key,
            "secretkey": self.api_secret,
            "expires_in": 86400  # 24시간으로 설정
        }
        
        headers = {
            "content-type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as response:
                result = await response.json()
                
                if response.status != 200:
                    raise Exception(f"승인키 발급 실패: {result}")
                
                self.approval_key = result.get("approval_key")
                self.approval_key_expired_at = now + 86400  # 24시간 후 만료
                
                # 토큰 정보 저장
                self._save_token()
                
                return self.approval_key 

    async def request(self, method, url, params=None, headers=None, data=None):
        """API 요청 공통 메서드"""
        try:
            # 액세스 토큰 가져오기
            access_token = await self._get_access_token()
            
            # 기본 헤더에 추가 헤더 병합
            request_headers = self._get_headers(access_token)
            if headers:
                request_headers.update(headers)
            
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method, 
                    url, 
                    params=params,
                    headers=request_headers,
                    json=data
                ) as response:
                    result = await response.json()
                    
                    if response.status != 200:
                        raise Exception(f"API 요청 실패: {result}")
                        
                    return result
                    
        except Exception as e:
            raise Exception(f"API 요청 오류: {str(e)}") 