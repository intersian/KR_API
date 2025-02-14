import json
import websockets
import asyncio

from loguru import logger
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode


def run_websocket(korea_invest_api, websocket_url):
	# 이벤트 루프 초기화
	loop = asyncio.get_event_loop()
	loop.run_until_complete(connect(korea_invest_api, websocket_url))


def aes_cbc_base64_dec(key, iv, cipher_text):
	"""
	:param key:  str type AES256 secret key value
	:param iv: str type AES256 Initialize Vector
	:param cipher_text: Base64 encoded AES256 str
	:return: Base64-AES256 decodec str
	"""
	cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
	return bytes.decode(unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size))


async def connect(korea_invest_api, url):
	logger.info("한국투자증권 API 웹소켓 연결 시도!")
	async with websockets.connect(url, ping_interval=None) as websocket:
		send_data = korea_invest_api.overseas_get_send_data(cmd=5, stockcode=None)  # 체결 통보 등록!
		logger.info("체결 통보 등록!")
		await websocket.send(send_data)
		while True:
			data = await websocket.recv()
			if data[0] == '0':
				pass
			elif data[0] == '1':
				recvstr = data.split('|')  # 수신데이터가 실데이터 이전은 '|'로 나뉘어져있어 split
				trid0 = recvstr[1]
				if trid0 == "H0GSCNI0":  # 주식체결 통보 처리
					receive_signing_notice(recvstr[3], aes_key, aes_iv)
			else:
				jsonObject = json.loads(data)
				trid = jsonObject["header"]["tr_id"]
				if trid != "PINGPONG":
					rt_cd = jsonObject["body"]["rt_cd"]
					if rt_cd == '1':  # 에러일 경우 처리
						logger.debug(f"### ERROR RETURN CODE [{rt_cd}] MSG [{jsonObject['body']['msg1']}]")
					elif rt_cd == '0':  # 정상일 경우 처리
						logger.info(f"### RETURN CODE [{rt_cd}] MSG [{jsonObject['body']['msg1']}]")
						# 체결통보 처리를 위한 AES256 KEY, IV 처리 단계
						if trid == "H0GSCNI0":
							aes_key = jsonObject["body"]["output"]["key"]
							aes_iv = jsonObject["body"]["output"]["iv"]
							logger.info(f"### TRID [{trid}] KEY[{aes_key}] IV[{aes_iv}]")
				elif trid == "PINGPONG":
					logger.info(f"### RECV [PINGPONG] [{data}]")
					await websocket.send(data)
					logger.info(f"### SEND [PINGPONG] [{data}]")


def receive_signing_notice(data, key, iv):
	"""
	전체 메뉴는 아래 참조
	https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py#L482
	"""
	# AES256 처리 단계
	aes_dec_str = aes_cbc_base64_dec(key, iv, data)
	values = aes_dec_str.split('^')
	고객ID = values[0]  # HTS ID
	계좌번호 = values[1]
	거부여부 = values[11]
	if 거부여부 != "0":
		logger.info("Got 거부 TR!")
		return
	체결여부 = values[12]
	종목코드 = values[7]
	종목명 = values[17]
	주문체결시간 = values[10]
	주문수량 = 0 if len(values[8]) == 0 else int(values[8])
	체결가격 = 0 if len(values[9]) == 0 else int(values[9]) / 10000
	매도매수구분 = values[4]
	정정구분 = values[5]
	if 매도매수구분 == "02" and 정정구분 != "0":
		주문구분 = "매수정정"
	elif 매도매수구분 == "01" and 정정구분 != "0":
		주문구분 = "매도정정"
	elif 매도매수구분 == "02":
		주문구분 = "매수"
	elif 매도매수구분 == "01":
		주문구분 = "매도"
	else:
		raise ValueError(f"주문구분 실패! 매도매수구분: {매도매수구분}, 정정구분: {정정구분}")
	단위체결수량 = 주문수량 if 체결여부 == '2' else 0

	주문번호 = values[2]
	원주문번호 = values[3]
	logger.info(f"체결 데이터 수신! 고객ID: {고객ID}, 계좌번호: {계좌번호}, 주문체결시간: {주문체결시간}, "
	            f"종목코드: {종목코드}, 종목명: {종목명}, 주문수량: {주문수량}, "
	            f"단위체결수량: {단위체결수량}, 체결가격: {체결가격}, "
	            f"주문구분: {주문구분},  주문번호: {주문번호}, "
	            f"원주문번호: {원주문번호}, 체결여부: {체결여부}")


if __name__ == "__main__":
	import yaml
	from utils import KoreaInvestEnv, KoreaInvestAPI
	with open("./config.yaml", encoding='UTF-8') as f:
		cfg = yaml.load(f, Loader=yaml.FullLoader)
	env_cls = KoreaInvestEnv(cfg)
	base_headers = env_cls.get_base_headers()
	cfg = env_cls.get_full_config()
	korea_invest_api = KoreaInvestAPI(cfg, base_headers=base_headers)
	websocket_url = cfg['paper_websocket_url'] if cfg['is_paper_trading'] else cfg['websocket_url']
	run_websocket(korea_invest_api, websocket_url)
