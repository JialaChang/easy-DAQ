import socket
import threading

current_conn = None # 偵測客戶端IP有沒有換 

def handle_client(conn, addr):

    global current_conn

    if current_conn:
        try:
            current_conn.close()
        except:
            pass
    
    current_conn = conn

    print(f"\nConnected to {addr}")

    def send_message():
        try:
            while True:
                msg = input(f"[Send message to {addr}] : ")
                if msg == "QUIT":
                    print("Closing sever...")
                    print("==================================")                    
                    import os
                    os._exit(0)
                conn.send(msg.encode())

        except:
            pass

    st = threading.Thread(target=send_message, daemon=True)
    st.start()

    # 接收客戶端發送的訊息
    try:
        while True:
            indata = conn.recv(1024)
            if not indata:  # indata 為空代表斷線
                break
            print(f"\n[Receive from {addr}] : {indata.decode(errors='ignore')}")
    except:
        pass
    finally:
        print("\nDisconnected...")
        current_conn = None
        conn.close()

# 伺服端IP
HOST = '0.0.0.0'
PORT = 8888

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((HOST, PORT))
s.listen(5)

print("==================================")
print("(Type 'QUIT' to leave)")
print(f'Server start at: {HOST}:{PORT}')
print("Waiting connect...")

while True:
    """"用迴圈一直接收客戶端的IP"""

    conn, addr = s.accept() # accept() -> 接收到才會繼續
    client_t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
    client_t.start()