# TCPClient.py
# Client for the hybrid TCP message/file distribution server.
#
# Usage:
#   python3 TCPClient.py demo3            -> sends 3 TEXT frames back-to-back
#                                             with no delay (see report 2.B.1)
#   python3 TCPClient.py text "hello"      -> sends a single TEXT frame
#   python3 TCPClient.py file <path>       -> sends a FILE frame
#   python3 TCPClient.py multi <id>        -> connects, sends one TEXT frame,
#                                             then holds the connection open
#                                             for a few seconds before closing
#                                             (used to demonstrate the server
#                                             handling several clients at the
#                                             same time -- see report 2.A.1)
#
# Uses the same length-prefixed framing as TCPServer.py so the server can
# always tell where one message ends and the next begins, even though TCP
# itself has no concept of message boundaries.

from socket import *
import sys
import os
import time

SERVER_NAME = 'localhost'
SERVER_PORT = 12000


def make_text_frame(text: str) -> bytes:
    return b'TEXT' + text.encode('utf-8')


def make_file_frame(path: str) -> bytes:
    filename = os.path.basename(path)
    with open(path, 'rb') as f:
        content = f.read()
    name_bytes = filename.encode('utf-8')
    return b'FILE' + len(name_bytes).to_bytes(2, 'big') + name_bytes + content


def send_frame(sock, payload: bytes):
    length_prefix = len(payload).to_bytes(4, 'big')
    sock.sendall(length_prefix + payload)


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 TCPClient.py [demo3 | text <message> | file <path>]')
        sys.exit(1)

    mode = sys.argv[1]
    clientSocket = socket(AF_INET, SOCK_STREAM)
    clientSocket.connect((SERVER_NAME, SERVER_PORT))
    print(f'Connected to {SERVER_NAME}:{SERVER_PORT}')

    if mode == 'demo3':
        # Sends 3 messages back-to-back with send(), with no delay in
        # between. Because each is wrapped in its own length-prefixed
        # frame, the server can still separate them cleanly even if TCP
        # coalesces them into a single segment on the wire.
        messages = ['Pesan pertama', 'Pesan kedua', 'Pesan ketiga']
        for m in messages:
            send_frame(clientSocket, make_text_frame(m))
            print(f'Sent (no delay): {m}')

    elif mode == 'text':
        if len(sys.argv) < 3:
            print('Usage: python3 TCPClient.py text "<message>"')
            sys.exit(1)
        text = sys.argv[2]
        send_frame(clientSocket, make_text_frame(text))
        print(f'Sent TEXT frame: {text}')

    elif mode == 'file':
        if len(sys.argv) < 3:
            print('Usage: python3 TCPClient.py file <path>')
            sys.exit(1)
        path = sys.argv[2]
        send_frame(clientSocket, make_file_frame(path))
        print(f'Sent FILE frame: {path}')

    elif mode == 'multi':
        client_id = sys.argv[2] if len(sys.argv) >= 3 else '?'
        HOLD_SECONDS = 4
        text = f'Halo dari client {client_id}'
        send_frame(clientSocket, make_text_frame(text))
        print(f'Sent TEXT frame: {text}')
        print(f'Holding connection open for {HOLD_SECONDS}s to overlap '
              f'with other clients...')
        time.sleep(HOLD_SECONDS)

    else:
        print(f'Unknown mode: {mode}')
        sys.exit(1)

    clientSocket.close()
    print('Connection closed.')


if __name__ == '__main__':
    main()
