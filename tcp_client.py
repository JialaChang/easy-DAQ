import dearpygui.dearpygui as dpg
import socket
import threading
import platform
import os
import time
from collections import deque


class NetworkClient:
    """ --- 網路通訊 --- """

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
            self.is_connected = True

            
            # 用threading建立多執行緒接收資料
            self.receive_thread = threading.Thread(target=self.receive_data, daemon=True) 
            self.receive_thread.start()

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

    
class DataProcess:
    """資料處理"""
    
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
    

    def extract_force_data(self, data, channel = 1):
        """分析秤重傳感器的數值"""

        # 通道的起始位置
        # AD 1 -> byte 6,7,8
        # AD 2 -> byte 9,10,11
        # AD 3 -> byte 12,13,14
        start_idx = 6 + (channel - 1) * 3
                
        high = data[start_idx]
        mid = data[start_idx + 1]
        low = data[start_idx + 2]

        # 組合成 24bits 的整數
        row_data = (high << 16) | (mid << 8) | low

        # 檢查正負
        if row_data >= (1 << 23):
            force_value = row_data - (1 << 24)
        else:
            force_value = row_data

        # 校正數值 -> 換成公克
        force_value *= (5000.0 / (1 << 23))
        return force_value


class AppWindow:
    """ --- 視窗介面 --- """

    def __init__(self):

        # IP與資料設定
        self.target_ip = ""
        self.target_port = ""
        self.data_format = ""

        # 資料計數器
        self.cnt_persec = 0
        self.curr_cps = 0

        # 繪圖容器
        self.plot_data_x = []
        self.plot_data_y = []
        self.start_time = time.time()
 
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

        # 建立主視窗 UI
        with dpg.window(tag="primary_window"):
            with dpg.tab_bar(tag="main_tab"):

                # 設定與日誌分頁
                with dpg.tab(label="Logs", tag="tab_logs"):
                    dpg.add_spacer(height=5)

                    # 水平輸入欄
                    with dpg.group(horizontal=True):

                        # IP 輸入
                        dpg.add_text("IP :")
                        dpg.add_input_text(tag="entry_ip", width=150, default_value="220.168.8.8")

                        # port 輸入
                        dpg.add_text(" ")
                        dpg.add_text("port :")
                        dpg.add_input_text(tag="entry_port", width=80, default_value="5000")

                        # 輸出格式選擇
                        dpg.add_text(" " * 5)    # 用空格做間距
                        dpg.add_combo(
                            items=["Text(UTF-8)", "Hex", "Binary"],
                            tag="combo_format",
                            width=120,
                            default_value="Hex"
                        )

                        # 儲存設定按鈕
                        dpg.add_text(" " * 5) 
                        dpg.add_button(label="Save", tag="btn_setip", callback=self.save_setting) 

                        # 切換連線按鈕
                        dpg.add_text(" " * 10)
                        dpg.add_button(label="Connect", tag="btn_connect", callback=self.toggle_connection)

                        # 訊息輸出次數顯示
                        dpg.add_text(" " * 10)
                        dpg.add_text("0", tag="display_cps")
                        dpg.add_text("cnt/sec")

                    # 滾動窗
                    # 寬設 -1 填滿剩下的空間
                    # 高設 -200 填滿後留 200px
                    dpg.add_spacer(height=5)
                    with dpg.child_window(tag="log_window", width=-1, height=-200, horizontal_scrollbar=True):
                        pass
                
                # 圖表分頁
                with dpg.tab(label="Plot", tag="tab_plot"):
                    dpg.add_spacer(height=5)

                    # 秤重傳感器圖表
                    with dpg.plot(label="Weight Sensor", width=-1, height=-1):
                        dpg.add_plot_legend()

                        dpg.add_plot_axis(dpg.mvXAxis, label="Time (s)", tag="xaxis_weight")
                        with dpg.plot_axis(dpg.mvYAxis, label="Weight (g)", tag="yaxis_weight"):
                            dpg.add_line_series([], [], label="Value", tag="series_weight")

        # 建立視窗
        dpg.create_viewport(title="Network", width=800, height=500)
        dpg.setup_dearpygui()
        dpg.show_viewport()

        dpg.set_primary_window("primary_window", True)
        dpg.maximize_viewport()


    def load_font(self):
        """ 文字設定 """

        with dpg.font_registry():
            font_path = ""
            if platform.system() == "Windows":
                font_path = "C:/Windows/Fonts/consola.ttf"
            elif platform.system() == "Darwin":
                font_path = "/System/Library/Fonts/Menlo.ttc"

            if font_path and os.path.exists(font_path):
                with dpg.font(font_path, 16) as default_font:    # 字體大小 : 18
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

        # 每接收五筆才輸出一次
        if (self.cnt_persec % 5 == 0):    
            output_data = self.processor.format_output(data, self.data_format)
            self.output_message(output_data)

            # 將數據存入清單
            weight = self.processor.extract_force_data(data)
            self.plot_data_x.append(time.time() - self.start_time)
            self.plot_data_y.append(weight)
            dpg.fit_axis_data("yaxis_weight")
            dpg.fit_axis_data("xaxis_weight")
        

    def update_plot(self):
        """更新圖表數據"""
        if len(self.plot_data_x) > 0:
            dpg.set_value("series_weight", [list(self.plot_data_x), list(self.plot_data_y)])

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
    app = AppWindow()

    while dpg.is_dearpygui_running():
        app.update_plot()
        dpg.render_dearpygui_frame()
    
    dpg.destroy_context()

