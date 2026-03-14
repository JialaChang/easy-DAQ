import dearpygui.dearpygui as dpg
import socket
import threading
import platform
import os
import time
from collections import deque


""" --- 網路通訊 --- """
class NetworkClient:
    
    def __init__(self, on_receive_callback):
        self.s = None
        self.is_connected = False
        
        # 藉由 callback 的方法調用 AppWindow 的 handle_incoming
        self.on_receive = on_receive_callback   


    def establish_connect(self, ip, port):
        """建立連線"""

        try:

            # AF_INET : IPv4 協定 ; SOCK_STREAM : TCP 協定
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 避免連線超時
            self.s.settimeout(5.0)
            self.s.connect((ip, int(port)))
            
            # 用threading建立多執行緒接收資料
            self.receive_thread = threading.Thread(target=self.receive_data, daemon=True) 
            self.receive_thread.start()

            self.is_connected = True
            return True, ""
            
        except Exception as e:
            self.s.close()
            return False, str(e)


    def stop_connect(self):
        """中斷連線"""

        self.is_connected = False
        if self.s:
            try:
                self.s.shutdown(socket.SHUT_RDWR)
                self.s.close()
            except:
                pass
        

    def receive_data(self):
        """接收資料"""

        while self.is_connected:
            try:      
                data = self.s.recv(1024)    # 1024 bytes
                if not data:
                    # 斷線會在最後傳空的封包
                    self.on_receive(None)
                    break

                # 將資料傳回 AppWindow 內
                self.on_receive(data)

            except Exception as e:
                if self.is_connected:
                    self.on_receive(e)
                break

        self.is_connected = False

    
""" --- 資料處理 --- """
class DataProcess:

    def format_output(self, data , data_format):
        """資料輸出型態"""

        if data_format == "Text(UTF-8)":
            return (f">> {data.decode('utf-8', errors='replace')}")
        elif data_format == "Hex":
            # hex(' ') 的作用是在每個 Byte 之間插空格
            return (f">> {data.hex(' ').upper()}") 
        elif data_format == "Binary":
            # for 跑 bytes (self.data) 會把每個 byte 變成 0~255 的整數
            # '08b' : b -> 二進位, 8 -> 讓字串是八個字元, 0 -> 如果有缺補零
            return (f">> {' '.join(format(byte, '08b') for byte in data)}")
    

""" --- 視窗介面 --- """
class AppWindow:

    def __init__(self):
        self.target_ip = ""
        self.target_port = ""
        self.data_format = ""

        self.cnt_persec = 0
        self.curr_cps = 0

        self.processor = DataProcess()
        
        # 將 handle_incoming 這個函式透過 on_receive_callback 交給 NetworkClient
        self.network = NetworkClient(on_receive_callback=self.handle_incoming)

        # 接收資料的執行緒
        self.cps_thread = threading.Thread(target=self.cps_monitor, daemon=True)
        self.cps_thread.start()

        self.setup_gui()


    def setup_gui(self):
        """建立視窗 UI """

        dpg.create_context()
        self.load_font()

        # 建立主視窗 UI, DearPyGui 底層是 C++ 因此不用 (用self) 儲存 Python 物件
        with dpg.window(tag="primary_window"):
            with dpg.tab_bar(tag="main_tab"):

                # 設定與日誌分頁
                with dpg.tab(label="Logs", tag="tab_logs"):
                    dpg.add_spacer(height=5)

                    # 水平輸入欄
                    with dpg.group(horizontal=True):

                        # IP 輸入
                        dpg.add_text("IP :")
                        dpg.add_input_text(tag="entry_ip", width=150)

                        # port 輸入
                        dpg.add_text("port :")
                        dpg.add_input_text(tag="entry_port", width=80)

                        # 輸出格式選擇
                        dpg.add_text(" " * 5)    # 用空格做間距
                        dpg.add_combo(
                            items=["Text(UTF-8)", "Hex", "Binary"],
                            tag="combo_format",
                            width=120
                        )

                        # 儲存設定按鈕
                        dpg.add_text(" " * 5) 
                        dpg.add_button(label="Save", tag="btn_setip", callback=self.save_setting) 

                        # 切換連線按鈕
                        dpg.add_text(" " * 20)
                        dpg.add_button(label="Connect", tag="btn_connect", callback=self.toggle_connection)

                        # 訊息輸出次數顯示
                        dpg.add_text(" " * 20)
                        dpg.add_text("0", tag="display_cps")
                        dpg.add_text("cnt/sec")

                    # 滾動窗
                    # 寬設 -1 填滿剩下的空間
                    # 高設 -40 填滿後留 200px
                    dpg.add_spacer(height=5)
                    with dpg.child_window(tag="log_window", width=-1, height=-200):
                        pass
                
                # 圖表分頁
                with dpg.tab(label="Plot", tag="tab_plot"):
                    dpg.add_spacer(height=5)

                    # 壓力傳感器圖表
                    with dpg.plot(label="Pressure Sensor", width=-1, height=-1):
                        dpg.add_plot_legend()

                        dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="pressure_xaxis")
                        with dpg.plot_axis(dpg.mvYAxis, label="Value", tag="pressure_yaxis"):
                            pass

        # 建立視窗
        dpg.create_viewport(title="Network", width=800, height=500)
        dpg.setup_dearpygui()
        dpg.show_viewport()

        dpg.set_primary_window("primary_window", True)
        dpg.maximize_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()


    def load_font(self):
        """ 文字設定 """

        with dpg.font_registry():
            font_path = ""
            if platform.system() == "Windows":
                font_path = "C:/Windows/Fonts/msjh.ttc"    # 微軟正黑體
            elif platform.system() == "Darwin":
                font_path = "/System/Library/Fonts/PingFang.ttc"    # Mac 蘋方體

            if font_path and os.path.exists(font_path):
                with dpg.font(font_path, 18) as default_font:    # 字體大小 : 18
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)

                dpg.bind_font(default_font)


    def save_setting(self, *args):    # args 接收傳來的其他參數
        """儲存設定"""

        self.target_ip = dpg.get_value("entry_ip")
        self.target_port = dpg.get_value("entry_port")
        self.data_format = dpg.get_value("combo_format")

        self.output_message(f"[System] : IP saved -- {self.target_ip}:{self.target_port}")
        self.output_message(f"[System] : Data formate set to {self.data_format}")


    def toggle_connection(self):
        """切換連線按鈕"""

        # 沒連線
        if not self.network.is_connected:
            self.output_message("[System] : Trying to connect...")
            connect_success, msg = self.network.establish_connect(self.target_ip, self.target_port)
        
            if connect_success:
                dpg.set_item_label("btn_connect", "Disconnect")
                self.output_message("[System] : Connect sucessfully")
            else:
                self.output_message(f"[System] : Connect failed -- {msg}")

        # 有連線
        else:
            self.network.stop_connect()
            dpg.set_item_label("btn_connect", "Connect")        
            self.output_message("[System] : Disconnected")


    def handle_incoming(self, data):
        """處理 NetworkClient 接收的資料"""

        # 檢查斷線或錯誤
        if data == None:
            dpg.set_item_label("btn_connect", "Connect")        
            self.output_message("[System] : Sever disconnect")
            return
        
        if isinstance(data, Exception):
            self.output_message(f"[System] : Error -- {data}")
            return
        
        self.cnt_persec += 1

        # 每接收十筆才輸出一次
        if (self.cnt_persec % 10 == 0):    
            output_data = self.processor.format_output(data, self.data_format)
            self.output_message(output_data)


    def cps_monitor(self):
        """更新 cnt/sec 的數值"""
        while True:
            time.sleep(1.0)

            self.curr_cps = self.cnt_persec
            self.cnt_persec = 0

            dpg.set_value("display_cps", str(self.curr_cps))


    def output_message(self, message):
        """"滾動窗輸出訊息 & 整理頁面"""

        dpg.add_text(message, parent="log_window")
        dpg.set_y_scroll("log_window", 999999)

        # 最多顯示 500 筆
        if len(dpg.get_item_children("log_window", 1)) > 500:
            dpg.delete_item(dpg.get_item_children("log_window", 1)[0])    # [0] -> 最上面的一行


# 執行程式
if __name__ == "__main__":
    AppWindow()