# TCPServer.py
# Multi-threaded TCP server for the hybrid message/file distribution system.
#
# Concurrency model:
#   - serverSocket is the "welcoming socket": created once, bound to a port,
#     and only ever used to listen()/accept() new connections. It never
#     exchanges application data.
#   - Each accept() call returns a brand new "connection socket"
#     (connectionSocket), dedicated to exactly one client for the lifetime
#     of that client's session. The welcoming socket keeps living in the
#     main thread's accept() loop so new clients can keep connecting while
#     existing clients are served concurrently in their own threads.
#
# Application-layer framing protocol (solves TCP's lack of message
# boundaries -- see Kurose & Ross section 2.6 / 2.B.1 in the report):
#   Every frame sent over the TCP connection is:
#     [4-byte big-endian length N][N bytes of payload]
#   The payload itself starts with a 4-byte ASCII type tag:
#     b'TEXT' + utf-8 text bytes
#     b'FILE' + 2-byte filename length + filename bytes + file content bytes
#   Because the receiver always knows exactly how many bytes to read (the
#   length prefix), multiple messages sent back-to-back with send() can
#   never be merged or split incorrectly, regardless of how TCP happens to
#   segment them on the wire.

from socket import *
import sys
import threading
import os

SERVER_PORT = 12000
RECV_DIR = os.path.join(os.path.dirname(__file__), 'received_files')


def recv_exact(sock, n):
    """Read exactly n bytes from sock, or return None if the peer closed
    the connection before n bytes arrived."""
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_frame(sock):
    """Read one complete application-layer frame: 4-byte length prefix
    followed by that many bytes of payload. Returns the payload bytes,
    or None if the connection was closed."""
    length_prefix = recv_exact(sock, 4)
    if length_prefix is None:
        return None
    length = int.from_bytes(length_prefix, 'big')
    return recv_exact(sock, length)


def handle_client(connectionSocket, addr):
    """Serves one client for as long as its connection stays open.
    Runs entirely in its own thread, independent from the main thread's
    accept() loop, so multiple clients are served concurrently."""
    print(f'[+] Client connected from {addr}')
    os.makedirs(RECV_DIR, exist_ok=True)

    try:
        while True:
            payload = recv_frame(connectionSocket)
            if payload is None:
                print(f'[-] Client {addr} disconnected.')
                break

            msg_type = payload[:4]

            if msg_type == b'TEXT':
                text = payload[4:].decode('utf-8')
                print(f'[TEXT from {addr}] {text}')

            elif msg_type == b'FILE':
                name_len = int.from_bytes(payload[4:6], 'big')
                filename = payload[6:6 + name_len].decode('utf-8')
                content = payload[6 + name_len:]
                dest_path = os.path.join(RECV_DIR, os.path.basename(filename))
                with open(dest_path, 'wb') as f:
                    f.write(content)
                print(f'[FILE from {addr}] saved "{filename}" '
                      f'({len(content)} bytes) -> {dest_path}')

            else:
                print(f'[?] Unknown frame type {msg_type!r} from {addr}, ignoring.')

    except ConnectionResetError:
        print(f'[-] Connection reset by {addr}')
    finally:
        connectionSocket.close()


def main():
    serverSocket = socket(AF_INET, SOCK_STREAM)
    serverSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    serverSocket.bind(('', SERVER_PORT))
    serverSocket.listen(5)

    print(f'TCP hybrid server ready, listening on port {SERVER_PORT}...')

    while True:
        # The welcoming socket's only job: block until a new client shows
        # up, then hand off the resulting connection socket to a worker
        # thread and immediately go back to listening for the next one.
        connectionSocket, addr = serverSocket.accept()
        clientThread = threading.Thread(
            target=handle_client,
            args=(connectionSocket, addr),
            daemon=True
        )
        clientThread.start()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServer shutting down...')
        sys.exit(0)
