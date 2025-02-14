import os
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
import yaml
import sys
from loguru import logger
from multiprocessing import Process, Queue
from functools import partial

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import Qt, QSettings, QTimer, QAbstractTableModel, QEvent
from PyQt5 import uic, QtGui
import pandas as pd

from utils import KoreaInvestEnv, KoreaInvestAPI
from domestic_websocket import run_websocket


form_class = uic.loadUiType("main.ui")[0]


def send_tr_process(korea_invest_api, tr_req_queue: Queue, tr_result_queue: Queue):
    while True:
        try:
            data = tr_req_queue.get()
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
        req_in_queue: Queue,
        tr_req_in_queue: Queue,
        realtime_data_out_queue: Queue,
        tr_result_queue: Queue,
    ):
        super().__init__()
        self.korea_invest_api = korea_invest_api
        self.req_in_queue = req_in_queue
        self.tr_req_in_queue = tr_req_in_queue
        self.realtime_data_out_queue = realtime_data_out_queue
        self.tr_result_queue = tr_result_queue
        self.setupUi(self)
        self.setWindowIcon(QtGui.QIcon('icon.ico'))  # 아이콘 세팅
        self.settings = QSettings('MyApp', 'myApp')  # UI의 값들을 QSettings를 통해 레지스트리에 저장/불러오기
        self.load_settings()  # 운영시간 등 설정 불러오기
        self.inPushButton.clicked.connect(self.push_to_realtime_tracking_list)
        self.outPushButton.clicked.connect(self.pop_from_realtime_tracking_list)

        self.input_groupbox_items_map_list = []
        self.input_groupbox_list = [
            self.groupBox1, self.groupBox2, self.groupBox3, self.groupBox4, self.groupBox5
        ]
        self.group_to_double_click_target_object_set = dict(
            group1=set(),
            group2=set(),
            group3=set(),
            group4=set(),
            group5=set(),
        )
        self.double_click_targets = [f"buyhogalineEdit{i}" for i in range(1, 11)] + [f"sellhogalineEdit{i}" for i in range(1, 11)]
        self.init_input_groups(self.input_groupbox_list)

        self.index_num_to_stock_code_map = dict()
        self.stock_code_to_index_num_map = dict()
        self.stock_code_to_realtime_price_map = dict()
        self.realtime_registered_codes = set()

        self.account_info_df = pd.DataFrame(
            columns=['종목코드', '종목명', '보유수량', '매도가능수량', '매입단가', '수익률', '현재가', '전일대비', '등락']
        )
        try:
            self.realtime_watchlist_df = pd.read_pickle("realtime_watchlist_df.pkl")
        except FileNotFoundError:
            self.realtime_watchlist_df = pd.DataFrame(
                columns=["현재가", "수익률", "평균단가", "보유수량", "트레일링스탑발동여부", "트레일링스탑발동후고가"]
            )

        self.timer1 = QTimer()
        self.timer1.timeout.connect(self.receive_data_from_websocket)
        self.timer1.start(10)  # 0.01초마다 한번

        self.timer2 = QTimer()
        self.timer2.timeout.connect(self.save_settings)
        self.timer2.start(1000 * 10)  # 10초마다 한번

        self.timer3 = QTimer()
        self.timer3.timeout.connect(self.req_balance)
        self.timer3.start(2000)  # 2초마다 한번

        self.timer4 = QTimer()
        self.timer4.timeout.connect(self.receive_tr_result)
        self.timer4.start(50)  # 0.05초마다 한번

    def pop_from_realtime_tracking_list(self):
        stock_code = self.inOutStockCodeLineEdit.text()
        self.realtime_watchlist_df.drop(stock_code, inplace=True)

    def push_to_realtime_tracking_list(self):
        stock_code = self.inOutStockCodeLineEdit.text()
        self.realtime_watchlist_df.loc[stock_code] = {
            '현재가': None,
            "수익률": None,
            '평균단가': None,
            "보유수량": 0,
            "트레일링스탑발동여부": False,
            "트레일링스탑발동후고가": None,
        }

    def receive_tr_result(self):
        if not self.tr_result_queue.empty():
            data = self.tr_result_queue.get()
            if data['action_id'] == "계좌조회":
                self.on_balance_req(data['total_balance'], data['per_code_balance_df'])

    def req_balance(self):
        self.tr_req_in_queue.put(dict(action_id="계좌조회"))

    def on_balance_req(self, total_balance, per_code_balance_df):
        self.domesticCurrentBalanceLabel.setText(f"현재 평가 잔고: {total_balance: ,}원")
        logger.info(f"현재평가잔고: {total_balance}")
        self.account_info_df = per_code_balance_df[per_code_balance_df['보유수량'] != 0]
        for row in self.account_info_df.itertuples():
            stock_code = getattr(row, "종목코드")
            if stock_code not in self.realtime_registered_codes:
                self.req_in_queue.put(
                    dict(
                        action_id="실시간체결등록",
                        종목코드=stock_code,
                    ),
                )
                self.realtime_registered_codes.add(stock_code)
            if stock_code in self.realtime_watchlist_df.index:
                self.realtime_watchlist_df.loc[stock_code, "보유수량"] = getattr(row, "보유수량")
                self.realtime_watchlist_df.loc[stock_code, "평균단가"] = getattr(row, "매입단가")
        self.account_model = PandasModel(self.account_info_df)
        self.accountInfoTableView.setModel(self.account_model)
        realtime_tracking_model = PandasModel(self.realtime_watchlist_df.copy(deep=True))
        self.watchListTableView.setModel(realtime_tracking_model)

    def receive_data_from_websocket(self):
        try:
            if not self.realtime_data_out_queue.empty():
                data = self.realtime_data_out_queue.get()
                if data['action_id'] == "실시간호가":
                    stock_code = data['종목코드']
                    index = self.stock_code_to_index_num_map.get(stock_code, None)
                    if index is not None:
                        self.update_input_groupbox(index, data['data'])
                elif data['action_id'] == "실시간체결":
                    stock_code = data['종목코드']
                    now_price = data['data']['현재가']
                    self.stock_code_to_realtime_price_map[stock_code] = now_price
                    if stock_code in self.realtime_watchlist_df.index:
                        self.realtime_watchlist_df.loc[stock_code, '현재가'] = now_price
                        mean_buy_price = self.realtime_watchlist_df.loc[stock_code, '평균단가']
                        if mean_buy_price is not None:
                            수익률 = round((now_price - mean_buy_price) / mean_buy_price * 100 - 0.21, 2)
                            self.realtime_watchlist_df.loc[stock_code, '수익률'] = 수익률
                        else:
                            logger.info(f"종목코드: {stock_code} 평균단가: {mean_buy_price}로 return")
                            return
                        보유수량 = int(self.realtime_watchlist_df.loc[stock_code, "보유수량"])
                        트레일링스탑발동여부 = self.realtime_watchlist_df.loc[stock_code, '트레일링스탑발동여부']
                        if self.stopLossGroupBox.isChecked() and 보유수량 > 0 and 수익률 < float(self.stopLossLineEdit.text()):
                            logger.info(f"종목코드: {stock_code} 수익률: {수익률}으로 매도 진행!")
                            self.do_sell(stock_code, 매도주문수량=보유수량, 매도주문가=0, 주문유형="01")  # 시장가 매도
                            self.realtime_watchlist_df.drop(stock_code, inplace=True)
                        elif not 트레일링스탑발동여부 and self.trailingStopGroupBox.isChecked() and 보유수량 > 0 and 수익률 > float(
                                self.trailingStopUpperLineEdit.text()):
                            self.realtime_watchlist_df.loc[stock_code, '트레일링스탑발동여부'] = True
                            self.realtime_watchlist_df.loc[stock_code, '트레일링스탑발동후고가'] = now_price
                            logger.info(
                                f"종목코드: {stock_code} 수익률: {수익률} > {self.trailingStopUpperLineEdit.text()} 으로 트레일링스탑 발동!")
                        elif 트레일링스탑발동여부 and self.trailingStopGroupBox.isChecked() and 보유수량 > 0:
                            트레일링스탑발동후고가 = max(self.realtime_watchlist_df.loc[stock_code, '트레일링스탑발동후고가'], now_price)
                            self.realtime_watchlist_df.loc[stock_code, '트레일링스탑발동후고가'] = 트레일링스탑발동후고가
                            고가대비현재등락률 = (now_price - 트레일링스탑발동후고가) / 트레일링스탑발동후고가 * 100
                            if 고가대비현재등락률 < -float(self.trailingStopLowerLineEdit.text()):
                                logger.info(f"종목코드: {stock_code} 고가대비 현재 등락률: {고가대비현재등락률: .2f} < {self.trailingStopLowerLineEdit.text()} 으로 트레일링스탑 매도 발동!")
                                self.do_sell(stock_code, 매도주문수량=보유수량, 매도주문가=0, 주문유형="01")  # 시장가 매도
                                self.realtime_watchlist_df.drop(stock_code, inplace=True)
        except Exception as e:
            logger.exception(e)
        self.timer1.start(10)  # 0.01초마다 한번 (중복실행 방지)

    def update_input_groupbox(self, index, data):
        for i in range(1, 11):  # 매도호가 1부터 10까지 반복
            key_price = f"매도{i}호가"
            key_quantity = f"매도{i}호가수량"
            key_price2 = f"매수{i}호가"
            key_quantity2 = f"매수{i}호가수량"
            # 해당 인덱스의 GUI 요소에 값을 설정
            self.input_groupbox_items_map_list[index][f"sellhogalineEdit{i}"].setText(data[key_price])
            self.input_groupbox_items_map_list[index][f"sellhogalineEdit{i + 10}"].setText(data[key_quantity])
            self.input_groupbox_items_map_list[index][f"buyhogalineEdit{i}"].setText(data[key_price2])
            self.input_groupbox_items_map_list[index][f"buyhogalineEdit{i + 10}"].setText(data[key_quantity2])

    def on_auto_trade_on_button_clicked(self, index):
        try:
            stock_code = self.input_groupbox_items_map_list[index]["stockCodeLineEdit"].text().replace(' ', '')
            self.req_in_queue.put(
                dict(
                    action_id="실시간호가등록",
                    종목코드=stock_code,
                ),
            )
            if stock_code not in self.realtime_registered_codes:
                self.req_in_queue.put(
                    dict(
                        action_id="실시간체결등록",
                        종목코드=stock_code,
                    ),
                )
                self.realtime_registered_codes.add(stock_code)
            if self.index_num_to_stock_code_map.get(index) is not None:
                pre_stock_code = self.index_num_to_stock_code_map.get(index)
                self.req_in_queue.put(
                    dict(
                        action_id="실시간호가해제",
                        종목코드=pre_stock_code,
                    ),
                )
                if pre_stock_code not in self.realtime_watchlist_df.index:
                    self.req_in_queue.put(
                        dict(
                            action_id="실시간체결해제",
                            종목코드=pre_stock_code,
                        ),
                    )
                    self.realtime_registered_codes.remove(pre_stock_code)

            pre_idx = self.stock_code_to_index_num_map.get(stock_code)
            if pre_idx is not None:
                self.stock_code_to_index_num_map.pop(self.index_num_to_stock_code_map[pre_idx])
                self.index_num_to_stock_code_map.pop(pre_idx)
            self.index_num_to_stock_code_map[index] = stock_code
            self.stock_code_to_index_num_map[stock_code] = index
        except Exception as e:
            logger.exception(e)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonDblClick:
            target_group = None
            for group_num, double_click_target_object_set in self.group_to_double_click_target_object_set.items():
                if obj in double_click_target_object_set:
                    target_group = group_num
                    break

            if target_group is not None:
                try:
                    # 더블 클릭 이벤트 처리
                    target_index = int(target_group.replace("group", "")) - 1
                    logger.debug(f"target_index: {target_index}")
                    종목코드 = self.input_groupbox_items_map_list[target_index]["stockCodeLineEdit"].text().replace(' ', '')
                    주문수량금액 = int(self.input_groupbox_items_map_list[target_index]["perOrderLineEdit"].text())
                    주문유형 = self.input_groupbox_items_map_list[target_index]["orderAmountTypeComboBox"].currentText()
                    주문가격 = int(obj.text())
                    if 주문유형 == "금액(원)":
                        주문수량 = 주문수량금액 // 주문가격
                    else:
                        주문수량 = 주문수량금액
                    if self.input_groupbox_items_map_list[target_index]["buyRadioButton"].isChecked():
                        self.do_buy(종목코드, 주문수량, 주문가격)
                    else:
                        self.do_sell(종목코드, 주문수량, 주문가격)
                    return True  # 이벤트 처리를 표시
                except Exception as e:
                    logger.exception(e)
        return super(KoreaInvestAPIForm, self).eventFilter(obj, event)

    def init_input_groups(self, input_groupbox_list):
        for index, groupbox in enumerate(input_groupbox_list):
            input_group_basic_items_map = self.get_input_group_basic_items_map()
            for widget in groupbox.children():
                widget_basic_name = widget.objectName().split("_")[0]
                if widget_basic_name == "pushButton":
                    widget.clicked.connect(partial(self.on_auto_trade_on_button_clicked, index))
                    input_group_basic_items_map[widget_basic_name] = widget
                elif widget_basic_name in ("buyRadioButton", "sellRadioButton"):
                    input_group_basic_items_map[widget_basic_name] = widget
                if widget_basic_name in self.double_click_targets:
                    self.group_to_double_click_target_object_set[f"group{index + 1}"].add(widget)
                    widget.installEventFilter(self)
                input_group_basic_items_map[widget_basic_name] = widget

                layout = widget.layout()
                if layout:
                    for i in range(layout.count()):
                        item = layout.itemAt(i)
                        widget = item.widget()
                        if widget is not None:
                            widget_basic_name = widget.objectName().split("_")[0]
                            input_group_basic_items_map[widget_basic_name] = widget
            if all(input_group_basic_items_map.values()):  # 모든 값들이 None 이 아니어야 성공
                self.input_groupbox_items_map_list.append(input_group_basic_items_map)
            else:
                raise ModuleNotFoundError("GroupBox -> dictionary Transfer Process Failed!")

    @staticmethod
    def get_input_group_basic_items_map():
        return dict(
            stockCodeLineEdit=None,
            perOrderLineEdit=None,
            orderAmountTypeComboBox=None,
            pushButton=None,
            buyRadioButton=None,
            sellRadioButton=None,
        )

    def load_settings(self):
        self.resize(self.settings.value("size", self.size()))
        self.move(self.settings.value("pos", self.pos()))
        self.stockCodeLineEdit_2.setText(self.settings.value('stockCodeLineEdit_2', type=str))
        self.perOrderLineEdit_2.setText(self.settings.value('perOrderLineEdit_2', type=str))
        self.stockCodeLineEdit_3.setText(self.settings.value('stockCodeLineEdit_3', type=str))
        self.perOrderLineEdit_3.setText(self.settings.value('perOrderLineEdit_3', type=str))
        self.stockCodeLineEdit_4.setText(self.settings.value('stockCodeLineEdit_4', type=str))
        self.perOrderLineEdit_4.setText(self.settings.value('perOrderLineEdit_4', type=str))
        self.stockCodeLineEdit_5.setText(self.settings.value('stockCodeLineEdit_5', type=str))
        self.perOrderLineEdit_5.setText(self.settings.value('perOrderLineEdit_5', type=str))
        self.stockCodeLineEdit_6.setText(self.settings.value('stockCodeLineEdit_6', type=str))
        self.perOrderLineEdit_6.setText(self.settings.value('perOrderLineEdit_6', type=str))
        self.orderAmountTypeComboBox_2.setCurrentIndex(self.settings.value("orderAmountTypeComboBox_2", 0, type=int))
        self.orderAmountTypeComboBox_3.setCurrentIndex(self.settings.value("orderAmountTypeComboBox_3", 0, type=int))
        self.orderAmountTypeComboBox_4.setCurrentIndex(self.settings.value("orderAmountTypeComboBox_4", 0, type=int))
        self.orderAmountTypeComboBox_5.setCurrentIndex(self.settings.value("orderAmountTypeComboBox_5", 0, type=int))
        self.orderAmountTypeComboBox_6.setCurrentIndex(self.settings.value("orderAmountTypeComboBox_6", 0, type=int))

    def save_settings(self):
        # Write window size and position to config file
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.settings.setValue('stockCodeLineEdit_2', self.stockCodeLineEdit_2.text())
        self.settings.setValue('perOrderLineEdit_2', self.perOrderLineEdit_2.text())
        self.settings.setValue('stockCodeLineEdit_3', self.stockCodeLineEdit_3.text())
        self.settings.setValue('perOrderLineEdit_3', self.perOrderLineEdit_3.text())
        self.settings.setValue('stockCodeLineEdit_4', self.stockCodeLineEdit_4.text())
        self.settings.setValue('perOrderLineEdit_4', self.perOrderLineEdit_4.text())
        self.settings.setValue('stockCodeLineEdit_5', self.stockCodeLineEdit_5.text())
        self.settings.setValue('perOrderLineEdit_5', self.perOrderLineEdit_5.text())
        self.settings.setValue('stockCodeLineEdit_6', self.stockCodeLineEdit_6.text())
        self.settings.setValue('perOrderLineEdit_6', self.perOrderLineEdit_6.text())
        self.settings.setValue("orderAmountTypeComboBox_2", self.orderAmountTypeComboBox_2.currentIndex())
        self.settings.setValue("orderAmountTypeComboBox_3", self.orderAmountTypeComboBox_3.currentIndex())
        self.settings.setValue("orderAmountTypeComboBox_4", self.orderAmountTypeComboBox_4.currentIndex())
        self.settings.setValue("orderAmountTypeComboBox_5", self.orderAmountTypeComboBox_5.currentIndex())
        self.settings.setValue("orderAmountTypeComboBox_6", self.orderAmountTypeComboBox_6.currentIndex())
        self.realtime_watchlist_df.to_pickle("realtime_watchlist_df.pkl")
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
        self.req_in_queue.put(
            dict(action_id="종료")
        )
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
    req_in_queue = Queue()
    tr_req_in_queue = Queue()
    tr_result_queue = Queue()
    realtime_data_out_queue = Queue()
    # 주문을 위한 Process 생성
    send_order_p = Process(
        target=send_tr_process,
        args=(
            korea_invest_api,
            tr_req_in_queue,
            tr_result_queue,
        )
    )
    send_order_p.start()
    # 웹소켓을 위한 Process 생성
    websocket_url = cfg['paper_websocket_url'] if cfg['is_paper_trading'] else cfg['websocket_url']
    korea_invest_websocket_p = Process(
        target=run_websocket,
        args=(
            korea_invest_api,
            websocket_url,
            req_in_queue,
            realtime_data_out_queue,
        ),
    )
    korea_invest_websocket_p.start()

    app = QApplication(sys.argv)
    main_app = KoreaInvestAPIForm(
        korea_invest_api,
        req_in_queue,
        tr_req_in_queue,
        realtime_data_out_queue,
        tr_result_queue,
    )
    main_app.show()
    sys.exit(app.exec_())
