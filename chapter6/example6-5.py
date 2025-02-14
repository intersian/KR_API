import os
import time

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
import sys
import datetime
from multiprocessing import Process, Queue, Event

from loguru import logger
from urllib.request import urlopen
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import QTimer, QCoreApplication
from PyQt5 import uic


form_class = uic.loadUiType("main.ui")[0]


def request_crawling(req_in_queue: Queue, req_out_queue: Queue, process_event: Event):
    logger.info(f"Crawling process started!")
    while not process_event.is_set():
        if req_in_queue.empty():
            time.sleep(0.1)  # 프로세스가 과도하게 돌아가지 않게 방지
            continue
        req_data_dict = req_in_queue.get()
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
                    req_out_queue.put(
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
    logger.info(f"Crawling process exited!")


class MainWindow(QMainWindow, form_class):
    def __init__(self, req_in_queue: Queue, req_out_queue: Queue, process_event: Event):
        super().__init__()
        self.setupUi(self)
        self.reqDartPushButton.clicked.connect(self.request_crawling)
        self.req_in_queue = req_in_queue
        self.req_out_queue = req_out_queue
        self.process_event = process_event

        self.timer1 = QTimer()
        self.timer1.timeout.connect(self.check_result_queue)
        self.timer1.start(100)  # 0.1 초마다 실행

    def check_result_queue(self):
        if not self.req_out_queue.empty():
            processed_data_dict = self.req_out_queue.get()
            self.resultTextEdit.append(
                f"공시번호: {processed_data_dict['공시번호']}, 종목코드: {processed_data_dict['종목코드']}, "
                f"종목명: {processed_data_dict['종목명']}, 공시제목: {processed_data_dict['공시제목']}"
            )

    def request_crawling(self):
        start_date = datetime.datetime.now().strftime("%Y%m%d")
        if len(self.dartAPIKEYLineEdit.text()) < 2:
            return
        for i in range(1, 100):
            url = f"http://opendart.fss.or.kr/api/list.xml?" \
                  f"crtfc_key={self.dartAPIKEYLineEdit.text()}&bgn_de={start_date}&page_count=8&page_no={i}"
            self.req_in_queue.put(
                dict(
                    action_id="크롤링요청",
                    url=url,
                )
            )

    def closeEvent(self, event):
        self.process_event.set()  # 이벤트 설정하여 스레드가 종료할 수 있도록 함
        QCoreApplication.quit()  # QApplication.instance().quit() 이 먹히지 않을 경우 차선책


if __name__ == '__main__':
    crawling_req_in_queue = Queue()
    crawling_out_queue = Queue()
    process_event = Event()
    crawling_process = Process(
        target=request_crawling,
        args=(
            crawling_req_in_queue,
            crawling_out_queue,
            process_event,
        )
    )
    crawling_process.start()
    app = QApplication(sys.argv)
    mainWindow = MainWindow(crawling_req_in_queue, crawling_out_queue, process_event)
    mainWindow.show()
    sys.exit(app.exec_())
