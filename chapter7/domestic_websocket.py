import json
import websockets
import asyncio
from queue import Queue

from loguru import logger
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode


def run_websocket(korea_invest_api, websocket_url, req_in_queue: Queue, realtime_data_out_queue: Queue):
    # 이벤트 루프 초기화
    loop = asyncio.get_event_loop()
    loop.run_until_complete(connect(korea_invest_api, websocket_url, req_in_queue, realtime_data_out_queue))


def aes_cbc_base64_dec(key, iv, cipher_text):
    """
    :param key:  str type AES256 secret key value
    :param iv: str type AES256 Initialize Vector
    :param cipher_text: Base64 encoded AES256 str
    :return: Base64-AES256 decodec str
    """
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    return bytes.decode(unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size))


def receive_realtime_hoga_domestic(data):
    """
    상세 메뉴는 아래의 링크 참조
    https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py#L53
    """
    values = data.split('^')  # 수신데이터를 split '^'
    data_dict = dict()
    data_dict["종목코드"] = values[0]
    for i in range(1, 11):
        data_dict[f"매수{i}호가"] = values[i + 12]
        data_dict[f"매수{i}호가수량"] = values[i + 32]
        data_dict[f"매도{i}호가"] = values[2 + i]
        data_dict[f"매도{i}호가수량"] = values[22 + i]
    return data_dict


def receive_realtime_tick_domestic(data):
    """
    메뉴 순서는 다음과 같음 '|' 으로 분리해서 아래와 같이 하나씩 접근하면 됩니다.
    유가증권단축종목코드|주식체결시간|주식현재가|전일대비부호|전일대비|전일대비율|가중평균주식가격|주식시가|주식최고가|주식최저가|
    매도호가1|매수호가1|체결거래량|누적거래량|누적거래대금|매도체결건수|매수체결건수|순매수체결건수|체결강도|총매도수량|총매수수량|체결구분|
    매수비율|전일거래량대비등락율|시가시간|시가대비구분|시가대비|최고가시간|고가대비구분|고가대비|최저가시간|저가대비구분|저가대비|영업일자|
    신장운영구분코드|거래정지여부|매도호가잔량|매수호가잔량|총매도호가잔량|총매수호가잔량|거래량회전율|전일동시간누적거래량|전일동시간누적거래량비율|
    시간구분코드|임의종료구분코드|정적VI발동기준가
    """
    values = data.split('^')
    종목코드 = values[0]
    체결시간 = values[1]
    현재가 = int(values[2])
    return dict(
        종목코드=종목코드,
        체결시간=체결시간,
        현재가=현재가,
    )


def receive_signing_notice(data, key, iv, account_num='', realtime_data_out_queue=None):
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
    realtime_data_out_queue.put(
        dict(
            action_id='주문체결통보',
            시간=시간,
            종목코드=종목코드,
            종목명=종목명,
            주문수량=주문수량,
            체결가격=체결가격,
            체결수량=체결수량,
            주문구분=주문구분,
            주문번호=주문번호,
            원주문번호=원주문번호,
            체결여부=체결여부,
        )
    )


async def connect(korea_invest_api, url, req_in_queue, realtime_data_out_queue):
    running_account_num = korea_invest_api.account_num
    logger.info("한국투자증권 API 웹소켓 연결 시도!")
    async with websockets.connect(url, ping_interval=None) as websocket:
        send_data = korea_invest_api.get_send_data(cmd=5, stockcode=None)  # 주문 접수/체결 통보 등록
        logger.info("체결 통보 등록!")
        await websocket.send(send_data)
        while True:
            if not req_in_queue.empty():
                req_data_dict = req_in_queue.get()
                action_id = req_data_dict['action_id']
                if action_id == "실시간체결등록":
                    stock_code = req_data_dict['종목코드']
                    send_data = korea_invest_api.get_send_data(cmd=3, stockcode=stock_code)  # 체결 등록
                    logger.info(f"[실시간 체결 등록] 종목코드: {stock_code}")
                    await websocket.send(send_data)
                elif action_id == "실시간호가등록":
                    stock_code = req_data_dict['종목코드']
                    send_data = korea_invest_api.get_send_data(cmd=1, stockcode=stock_code)  # 호가 등록
                    logger.info(f"[실시간 호가 등록] 종목코드: {stock_code}")
                    await websocket.send(send_data)
                elif action_id == "실시간체결해제":
                    stock_code = req_data_dict['종목코드']
                    send_data = korea_invest_api.get_send_data(cmd=4, stockcode=stock_code)  # 체결 해제
                    logger.info(f"[실시간 체결 해제] 종목코드: {stock_code}")
                    await websocket.send(send_data)
                elif action_id == "실시간호가해제":
                    stock_code = req_data_dict['종목코드']
                    send_data = korea_invest_api.get_send_data(cmd=2, stockcode=stock_code)  # 호가 해제
                    logger.info(f"[실시간 호가 해제] 종목코드: {stock_code}")
                    await websocket.send(send_data)
                elif action_id == "종료":
                    logger.info("종료 이벤트 발생으로 WebSocket 종료!")
                    break

            data = await websocket.recv()
            if data[0] == '0':
                recvstr = data.split('|')  # 수신데이터가 실데이터 이전은 '|'로 나뉘어져있어 split
                trid0 = recvstr[1]
                if trid0 == "H0STCNT0":  # 주식체결 데이터 처리
                    data_cnt = int(recvstr[2])  # 체결데이터 개수
                    for cnt in range(data_cnt):
                        data_dict = receive_realtime_tick_domestic(recvstr[3])
                        # logger.info(f"주식 체결 데이터: {data_dict}")
                        realtime_data_out_queue.put(
                            dict(
                                action_id="실시간체결",
                                종목코드=data_dict["종목코드"],
                                data=data_dict,
                            )
                        )
                elif trid0 == "H0STASP0":  # 주식호가 데이터 처리
                    data_dict = receive_realtime_hoga_domestic(recvstr[3])
                    # logger.info(f"주식 호가 데이터: {data_dict}")
                    realtime_data_out_queue.put(
                        dict(
                            action_id="실시간호가",
                            종목코드=data_dict["종목코드"],
                            data=data_dict,
                        )
                    )
            elif data[0] == '1':
                recvstr = data.split('|')  # 수신데이터가 실데이터 이전은 '|'로 나뉘어져있어 split
                trid0 = recvstr[1]
                if trid0 in ("H0STCNI0", "H0STCNI9"):  # 주실체결 통보 처리
                    receive_signing_notice(recvstr[3], aes_key, aes_iv, running_account_num, realtime_data_out_queue)
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
