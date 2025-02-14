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


def receive_realtime_tick_overseas(data):
	"""
	실시간종목코드|종목코드|수수점자리수|현지영업일자|현지일자|현지시간|한국일자|한국시간|시가|고가|저가|
	현재가|대비구분|전일대비|등락율|매수호가|매도호가|매수잔량|매도잔량|체결량|거래량|거래대금|매도체결량|매수체결량|체결강도|시장구분
	"""
	values = data.split('^')
	종목코드 = values[0]
	현지시간 = values[5]
	한국시간 = values[7]
	현재가 = float(values[11])
	return dict(
		종목코드=종목코드,
		현지시간=현지시간,
		한국시간=한국시간,
		현재가=현재가,
	)


async def connect(korea_invest_api, url):
	logger.info("한국투자증권 API 웹소켓 연결 시도!")
	async with websockets.connect(url, ping_interval=None) as websocket:
		stock_code = "DNASAAPL"
		send_data = korea_invest_api.overseas_get_send_data(cmd=3, stockcode=stock_code)
		logger.info(f"[실시간 체결 등록] 종목코드: {stock_code}")
		await websocket.send(send_data)
		while True:
			data = await websocket.recv()
			if data[0] == '0':
				recvstr = data.split('|')  # 수신데이터가 실데이터 이전은 '|'로 나뉘어져있어 split
				trid0 = recvstr[1]
				if trid0 == "HDFSCNT0":  # 주식체결 데이터 처리
					data_cnt = int(recvstr[2])  # 체결데이터 개수
					for cnt in range(data_cnt):
						data_dict = receive_realtime_tick_overseas(recvstr[3])
						logger.info(f"주식 체결 데이터: {data_dict}")
						send_data = korea_invest_api.overseas_get_send_data(cmd=4, stockcode=stock_code)
						logger.info(f"[실시간 체결 해제] 종목코드: {stock_code}")
						await websocket.send(send_data)
			elif data[0] == '1':
				pass
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
