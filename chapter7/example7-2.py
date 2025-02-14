import os

from ta.trend import macd_signal

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
import yaml
import sys
import time
from loguru import logger
from multiprocessing import Process, Queue

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import Qt, QSettings, QTimer, QAbstractTableModel
from PyQt5 import uic, QtGui
import pandas as pd
import talib as ta

from utils import KoreaInvestEnv, KoreaInvestAPI


form_class = uic.loadUiType("main2.ui")[0]


def send_tr_process(korea_invest_api, tr_req_queue: Queue, tr_result_queue: Queue):
    while True:
        try:
            data = tr_req_queue.get()
            time.sleep(0.01)
            logger.debug(f"data: {data}")
            if data['action_id'] == "종료":
                logger.info(f"Order Process 종료!")
                break
            elif data['action_id'] == "매수":
                korea_invest_api.do_buy(
                    data['종목코드'],
                    order_qty=data['매수주문수량'],
                    order_price=data['매수주문가'],
                    order_type=data['주문유형'],
                )
                logger.debug(f"매수주문 데이터: {data}")
            elif data['action_id'] == "매도":
                korea_invest_api.do_sell(
                    data['종목코드'],
                    order_qty=data['매도주문수량'],
                    order_price=data['매도주문가'],
                    order_type=data['주문유형'],
                )
                logger.debug(f"매도주문 데이터: {data}")
            elif data['action_id'] == "계좌조회":
                total_balance, per_code_balance_df = korea_invest_api.get_acct_balance()
                tr_result_queue.put(
                    dict(
                        action_id="계좌조회",
                        total_balance=total_balance,
                        per_code_balance_df=per_code_balance_df,
                    )
                )
            elif data['action_id'] == "1분봉조회":
                df = korea_invest_api.get_minute_chart_data(data['종목코드'])
                df['EMA_fast'] = df['종가'].ewm(span=9, adjust=False).mean()
                df['EMA_slow'] = df['종가'].ewm(span=18, adjust=False).mean()
                df['MACD'] = df['EMA_fast'] - df['EMA_slow']
                df['MACD_signal'] = df['MACD'].ewm(span=6, adjust=False).mean()
                df['RSI'] = ta.RSI(df['종가'], timeperiod=14)
                tr_result_queue.put(
                    dict(
                        action_id="1분봉조회",
                        df=df,
                        종목코드=data['종목코드']
                    )
                )
            elif data['action_id'] == "등락률상위":
                df = korea_invest_api.get_fluctuation_ranking()  # 전일대비 등락률 순위 (부호 절댓값 적용)
                tr_result_queue.put(
                    dict(
                        action_id="등락률상위",
                        df=df,
                    )
                )
        except Exception as e:
            logger.exception(e)


class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._data.columns[section]
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return self._data.index[section]
        return None

    def setData(self, index, value, role):
        # 항상 False를 반환하여 편집을 비활성화
        return False

    def flags(self, index):
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable


class KoreaInvestAPIForm(QMainWindow, form_class):
    def __init__(
        self,
        korea_invest_api,
        tr_req_in_queue: Queue,
        tr_result_queue: Queue,
    ):
        super().__init__()
        self.korea_invest_api = korea_invest_api
        self.tr_req_in_queue = tr_req_in_queue
        self.tr_result_queue = tr_result_queue
        self.setupUi(self)
        self.setWindowIcon(QtGui.QIcon('icon.ico'))  # 아이콘 세팅
        self.settings = QSettings('MyApp20241018', 'myApp20241018')  # UI의 값들을 QSettings를 통해 레지스트리에 저장/불러오기
        self.load_settings()  # 운영시간 등 설정 불러오기

        self.account_info_df = pd.DataFrame(
            columns=['종목코드', '종목명', '보유수량', '매도가능수량', '매입단가', '수익률', '현재가', '전일대비', '등락']
        )
        try:
            self.realtime_watchlist_df = pd.read_pickle("realtime_watchlist_df2.pkl")
        except FileNotFoundError:
            self.realtime_watchlist_df = pd.DataFrame(
                columns=["현재가", "수익률", "평균단가", "보유수량", "MACD", "MACD시그널", "RSI"]
            )

        self.timer2 = QTimer()
        self.timer2.timeout.connect(self.save_settings)
        self.timer2.start(1000 * 10)  # 10초마다 한번

        self.timer3 = QTimer()
        self.timer3.timeout.connect(self.req_balance)
        self.timer3.start(2000)  # 2초마다 한번

        self.timer4 = QTimer()
        self.timer4.timeout.connect(self.receive_tr_result)
        self.timer4.start(50)  # 0.05초마다 한번

        self.timer5 = QTimer()
        self.timer5.timeout.connect(self.req_ranking)
        self.timer5.start(5000)  # 2초마다 한번

    def req_ranking(self):
        self.tr_req_in_queue.put(dict(action_id="등락률상위"))

    def receive_tr_result(self):
        if not self.tr_result_queue.empty():
            data = self.tr_result_queue.get()
            if data['action_id'] == "계좌조회":
                self.on_balance_req(data['total_balance'], data['per_code_balance_df'])
            elif data['action_id'] == "1분봉조회":
                종목코드 = data['종목코드']
                df = data['df']
                if 종목코드 in self.realtime_watchlist_df.index:
                    종가 = df['종가'].iloc[-1]
                    전MACD = df['MACD'].iloc[-2]
                    현MACD = df['MACD'].iloc[-1]
                    전MACD_signal = df['MACD_signal'].iloc[-2]
                    현MACD_signal = df['MACD_signal'].iloc[-1]
                    전RSI = df['RSI'].iloc[-2]
                    현RSI = df['RSI'].iloc[-1]
                    self.realtime_watchlist_df.loc[종목코드, "현재가"] = 종가
                    평균단가 = self.realtime_watchlist_df.loc[종목코드, "평균단가"]
                    if not pd.isnull(평균단가):
                        수익률 = round((종가 - 평균단가) / 평균단가 * 100, 2)
                        self.realtime_watchlist_df.loc[종목코드, "수익률"] = 수익률
                    self.realtime_watchlist_df.loc[종목코드, "MACD"] = round(현MACD, 2)
                    self.realtime_watchlist_df.loc[종목코드, "MACD시그널"] = round(현MACD_signal, 2)
                    self.realtime_watchlist_df.loc[종목코드, "RSI"] = round(현RSI, 2)

                    # 매도 조건 체크
                    if self.sellMACDTypeComboBox.currentText() == "상향돌파":
                        macd_signal = 현MACD >= 현MACD_signal and 전MACD < 전MACD_signal
                    elif self.sellMACDTypeComboBox.currentText() == "하향돌파":
                        macd_signal = 현MACD <= 현MACD_signal and 전MACD > 전MACD_signal
                    elif self.sellMACDTypeComboBox.currentText() == "이상":
                        macd_signal = 현MACD >= 현MACD_signal
                    elif self.sellMACDTypeComboBox.currentText() == "이하":
                        macd_signal = 현MACD <= 현MACD_signal
                    else:
                        raise NotImplementedError

                    rsi_value = self.sellRSIValueSpinBox.value()
                    if self.sellRSITypeComboBox.currentText() == "상향돌파":
                        rsi_signal = 현RSI >= rsi_value and 전RSI < rsi_value
                    elif self.sellRSITypeComboBox.currentText() == "하향돌파":
                        rsi_signal = 현RSI <= rsi_value and 전RSI > rsi_value
                    elif self.sellRSITypeComboBox.currentText() == "이상":
                        rsi_signal = 현RSI >= rsi_value
                    elif self.sellRSITypeComboBox.currentText() == "이하":
                        rsi_signal = 현RSI <= rsi_value
                    else:
                        raise NotImplementedError

                    if macd_signal and rsi_signal:
                        logger.info(f"종목코드: {종목코드} 매도 주문!")
                        매도주문수량 = self.realtime_watchlist_df.loc[종목코드, "보유수량"]
                        if 매도주문수량 == 0:
                            logger.info(f"종목코드: {종목코드} 매도주문수량: {매도주문수량}으로 매도 주문 실패!")
                            return
                        self.do_sell(종목코드, 매도주문수량, 0, 주문유형="01")
                        self.realtime_watchlist_df.drop(종목코드, inplace=True)
                else:
                    전MACD = df['MACD'].iloc[-2]
                    현MACD = df['MACD'].iloc[-1]
                    전MACD_signal = df['MACD_signal'].iloc[-2]
                    현MACD_signal = df['MACD_signal'].iloc[-1]
                    전RSI = df['RSI'].iloc[-2]
                    현RSI = df['RSI'].iloc[-1]
                    if self.buyMACDTypeComboBox.currentText() == "상향돌파":
                        macd_signal = 현MACD >= 현MACD_signal and 전MACD < 전MACD_signal
                    elif self.buyMACDTypeComboBox.currentText() == "하향돌파":
                        macd_signal = 현MACD <= 현MACD_signal and 전MACD > 전MACD_signal
                    elif self.buyMACDTypeComboBox.currentText() == "이상":
                        macd_signal = 현MACD >= 현MACD_signal
                    elif self.buyMACDTypeComboBox.currentText() == "이하":
                        macd_signal = 현MACD <= 현MACD_signal
                    else:
                        raise NotImplementedError

                    rsi_value = self.buyRSIValueSpinBox.value()
                    if self.buyRSITypeComboBox.currentText() == "상향돌파":
                        rsi_signal = 현RSI >= rsi_value and 전RSI < rsi_value
                    elif self.buyRSITypeComboBox.currentText() == "하향돌파":
                        rsi_signal = 현RSI <= rsi_value and 전RSI > rsi_value
                    elif self.buyRSITypeComboBox.currentText() == "이상":
                        rsi_signal = 현RSI >= rsi_value
                    elif self.buyRSITypeComboBox.currentText() == "이하":
                        rsi_signal = 현RSI <= rsi_value
                    else:
                        raise NotImplementedError

                    if macd_signal and rsi_signal:
                        logger.info(f"종목코드: {종목코드} 매수 주문!")
                        현재가 = df['종가'].iloc[-1]
                        매수주문금액 = int(self.buyAmountLineEdit.text())
                        매수주문수량 = 매수주문금액 // 현재가
                        if 매수주문수량 == 0:
                            logger.info(f"종목코드: {종목코드} 매수주문수량: {매수주문수량}으로 매수 주문 실패!")
                            return
                        self.do_buy(종목코드, 매수주문수량, 0, 주문유형="01")
                        self.realtime_watchlist_df.loc[종목코드] = {
                            "현재가": 현재가,
                            "수익률": 0,
                            "평균단가": None,
                            "보유수량": 0,
                            "MACD": 현MACD,
                            "MACD시그널": 현MACD_signal,
                            "RSI": 현RSI,
                        }
            elif data['action_id'] == "등락률상위":
                df = data['df']
                for code in df['종목코드']:
                    self.tr_req_in_queue.put(
                        dict(
                            action_id="1분봉조회",
                            종목코드=code,
                        )
                    )

    def req_balance(self):
        self.tr_req_in_queue.put(dict(action_id="계좌조회"))

    def on_balance_req(self, total_balance, per_code_balance_df):
        self.domesticCurrentBalanceLabel.setText(f"현재 평가 잔고: {total_balance: ,}원")
        logger.info(f"현재평가잔고: {total_balance}")
        self.account_info_df = per_code_balance_df[per_code_balance_df['보유수량'] != 0]
        for row in self.account_info_df.itertuples():
            stock_code = getattr(row, "종목코드")
            if stock_code in self.realtime_watchlist_df.index:
                self.realtime_watchlist_df.loc[stock_code, "보유수량"] = getattr(row, "보유수량")
                self.realtime_watchlist_df.loc[stock_code, "평균단가"] = getattr(row, "매입단가")
        self.account_model = PandasModel(self.account_info_df)
        self.accountTableView.setModel(self.account_model)
        realtime_tracking_model = PandasModel(self.realtime_watchlist_df.copy(deep=True))
        self.watchListTableView.setModel(realtime_tracking_model)

    def load_settings(self):
        self.resize(self.settings.value("size", self.size()))
        self.move(self.settings.value("pos", self.pos()))
        self.buyAmountLineEdit.setText(self.settings.value('buyAmountLineEdit', 100000, type=str))
        self.buyMACDTypeComboBox.setCurrentIndex(self.settings.value("buyMACDTypeComboBox", 0, type=int))
        self.buyRSITypeComboBox.setCurrentIndex(self.settings.value("buyRSITypeComboBox", 0, type=int))
        self.sellMACDTypeComboBox.setCurrentIndex(self.settings.value("sellMACDTypeComboBox", 0, type=int))
        self.sellRSITypeComboBox.setCurrentIndex(self.settings.value("sellRSITypeComboBox", 0, type=int))
        self.buyRSIValueSpinBox.setValue(self.settings.value("buyRSIValueSpinBox", 0, type=int))
        self.sellRSIValueSpinBox.setValue(self.settings.value("sellRSIValueSpinBox", 0, type=int))

    def save_settings(self):
        # Write window size and position to config file
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.settings.setValue('buyAmountLineEdit', self.buyAmountLineEdit.text())
        self.settings.setValue("buyMACDTypeComboBox", self.buyMACDTypeComboBox.currentIndex())
        self.settings.setValue("buyRSITypeComboBox", self.buyRSITypeComboBox.currentIndex())
        self.settings.setValue("sellMACDTypeComboBox", self.sellMACDTypeComboBox.currentIndex())
        self.settings.setValue("sellRSITypeComboBox", self.sellRSITypeComboBox.currentIndex())
        self.settings.setValue("buyRSIValueSpinBox", self.buyRSIValueSpinBox.value())
        self.settings.setValue("sellRSIValueSpinBox", self.sellRSIValueSpinBox.value())
        self.realtime_watchlist_df.to_pickle("realtime_watchlist_df2.pkl")
        self.timer2.start(1000 * 10)  # 10초마다 한번

    def do_buy(self, 종목코드, 매수주문수량, 매수주문가, 주문유형="00"):
        self.tr_req_in_queue.put(
            dict(
                action_id="매수",
                종목코드=종목코드,
                매수주문수량=매수주문수량,
                매수주문가=매수주문가,
                주문유형=주문유형,
            )
        )

    def do_sell(self, 종목코드, 매도주문수량, 매도주문가, 주문유형="00"):
        self.tr_req_in_queue.put(
            dict(
                action_id="매도",
                종목코드=종목코드,
                매도주문수량=매도주문수량,
                매도주문가=매도주문가,
                주문유형=주문유형,
            )
        )

    def closeEvent(self, e):
        self.tr_req_in_queue.put(
            dict(action_id="종료")
        )
        e.accept()


sys._excepthook = sys.excepthook

def my_exception_hook(exctype, value, traceback):
    # Print the error and traceback
    logger.info(f"exctype: {exctype}, value: {value}, traceback: {traceback}")
    # Call the normal Exception hook after
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)

# Set the exception hook to our wrapping function
sys.excepthook = my_exception_hook


if __name__ == "__main__":
    with open("./config.yaml", encoding='UTF-8') as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)
    env_cls = KoreaInvestEnv(cfg)
    base_headers = env_cls.get_base_headers()
    cfg = env_cls.get_full_config()
    korea_invest_api = KoreaInvestAPI(cfg, base_headers=base_headers)
    tr_req_in_queue = Queue()
    tr_result_queue = Queue()
    # 주문을 위한 Process 생성
    send_tr_p = Process(
        target=send_tr_process,
        args=(
            korea_invest_api,
            tr_req_in_queue,
            tr_result_queue,
        )
    )
    send_tr_p.start()

    app = QApplication(sys.argv)
    main_app = KoreaInvestAPIForm(
        korea_invest_api,
        tr_req_in_queue,
        tr_result_queue,
    )
    main_app.show()
    sys.exit(app.exec_())
