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


def receive_signing_notice(data, key, iv, account_num=''):
    """
    상세 메뉴는 아래 링크 참조
    https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic%2Boverseas_stock.py#L127
    """
    # AES256 처리 단계
    aes_dec_str = aes_cbc_base64_dec(key, iv, data)
    values = aes_dec_str.split('^')
    계좌번호 = values[1]  #
    if 계좌번호[:8] != account_num:
        return
    거부여부 = values[12]
    if 거부여부 != "0":
        logger.info(f"Got 거부 TR!")
        return
    체결여부 = values[13]
    종목코드 = values[8]
    종목명 = values[18]
    시간 = values[11]
    주문수량 = 0 if len(values[16]) == 0 else int(values[16])
    if values[13] == '1':
        주문가격 = 0 if len(values[10]) == 0 else int(values[10])
    else:
        주문가격 = 0 if len(values[22]) == 0 else int(values[22])
    체결수량 = 0 if len(values[9]) == 0 or 체결여부 == "1" else int(values[9])
    if values[13] == '1':
        체결가격 = 0
    else:
        체결가격 = 0 if len(values[10]) == 0 else int(values[10])
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

    주문번호 = values[2]
    원주문번호 = values[3]
    logger.info(f"Received chejandata! 시간: {시간}, "
                f"종목코드: {종목코드}, 종목명: {종목명}, 주문수량: {주문수량}, "
                f"주문가격: {주문가격}, 체결수량: {체결수량}, 체결가격: {체결가격}, "
                f"주문구분: {주문구분},  주문번호: {주문번호}, "
                f"원주문번호: {원주문번호}, 체결여부: {체결여부}")


async def connect(korea_invest_api, url):
    running_account_num = korea_invest_api.account_num
    logger.info("한국투자증권 API 웹소켓 연결 시도!")
    async with websockets.connect(url, ping_interval=None) as websocket:
        send_data = korea_invest_api.get_send_data(cmd=5, stockcode=None)  # 주문 접수/체결 통보 등록
        logger.info("체결 통보 등록!")
        await websocket.send(send_data)
        while True:
            data = await websocket.recv()
            if data[0] == '0':
                pass
            elif data[0] == '1':
                recvstr = data.split('|')  # 수신데이터가 실데이터 이전은 '|'로 나뉘어져있어 split
                trid0 = recvstr[1]
                if trid0 in ("H0STCNI0", "H0STCNI9"):  # 주식 체결 통보 처리
                    receive_signing_notice(recvstr[3], aes_key, aes_iv, running_account_num)
            else:
                jsonObject = json.loads(data)
                trid = jsonObject["header"]["tr_id"]

                if trid != "PINGPONG":
                    rt_cd = jsonObject["body"]["rt_cd"]
                    if rt_cd == '1':  # 에러일 경우 처리
                        logger.info(f"### ERROR RETURN CODE [{rt_cd}] MSG [{jsonObject['body']['msg1']}]")
                    elif rt_cd == '0':  # 정상일 경우 처리
                        logger.info(f"### RETURN CODE [{rt_cd}] MSG [{jsonObject['body']['msg1']}]")
                        # 체결통보 처리를 위한 AES256 KEY, IV 처리 단계
                        if trid in ("H0STCNI0", "H0STCNI9"):
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
