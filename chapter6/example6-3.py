import os
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
import sys
import datetime

from loguru import logger
from urllib.request import urlopen
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5 import uic


form_class = uic.loadUiType("main.ui")[0]


class WorkerThread(QThread):
    data_processed = pyqtSignal(dict)  # Signal to send processed data back

    def __init__(self, parent=None):
        super(WorkerThread, self).__init__(parent)

    def process_data(self, req_data_dict):
        if req_data_dict['action_id'] == '크롤링요청':
            try:
                resultXML = urlopen(req_data_dict['url'])
                result = resultXML.read()
                xmlsoup = BeautifulSoup(result, 'xml')
                for t in xmlsoup.findAll("list"):
                    rcept_no = t.rcept_no.string
                    stock_code = t.stock_code.string
                    corp_name = t.corp_name.string
                    report_nm = t.report_nm.string
                    self.data_processed.emit(
                        dict(
                            action_id="크롤링요청",
                            공시번호=rcept_no,
                            종목코드=stock_code,
                            종목명=corp_name,
                            공시제목=report_nm,
                        )
                    )
            except Exception as e:
                logger.exception(e)


class MainWindow(QMainWindow, form_class):
    new_data_signal = pyqtSignal(dict)  # Signal to send data to the worker
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.reqDartPushButton.clicked.connect(self.request_crawling)
        self.worker = WorkerThread()  # Worker instance
        self.thread = QThread()  # Thread instance
        self.worker.moveToThread(self.thread)  # Move worker to the thread
        # Connect signals
        self.worker.data_processed.connect(self.on_data_processed)  # Connect to receive processed data
        self.new_data_signal.connect(self.worker.process_data)
        self.thread.start()

    def request_crawling(self):
        start_date = datetime.datetime.now().strftime("%Y%m%d")
        if len(self.dartAPIKEYLineEdit.text()) < 2:
            return
        for i in range(1, 100):
            url = f"http://opendart.fss.or.kr/api/list.xml?" \
                  f"crtfc_key={self.dartAPIKEYLineEdit.text()}&bgn_de={start_date}&page_count=8&page_no={i}"
            self.new_data_signal.emit(
                dict(
                    action_id="크롤링요청",
                    url=url,
                )
            )

    def on_data_processed(self, processed_data_dict):
        if processed_data_dict['action_id'] == "크롤링요청":
            self.resultTextEdit.append(
                f"공시번호: {processed_data_dict['공시번호']}, 종목코드: {processed_data_dict['종목코드']}, "
                f"종목명: {processed_data_dict['종목명']}, 공시제목: {processed_data_dict['공시제목']}"
            )


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWindow = MainWindow()
    mainWindow.show()
    sys.exit(app.exec_())
