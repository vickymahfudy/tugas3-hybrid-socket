# UDPPingerServer.py
# UDP "ping" server for the hybrid message/file distribution system
# (Bagian A.2 of Tugas_3).
#
# A UDP server only ever needs a single socket, no matter how many
# different clients send it datagrams: unlike TCP, UDP is connectionless,
# so there is no per-client "connection socket" to accept() and no
# listen() backlog. recvfrom() simply hands back both the payload and the
# sender's (IP, port) tuple for whichever client happened to send a
# datagram next, and the server replies straight to that address with
# sendto(). This is why a single UDP socket can transparently serve N
# different clients (see report 2.B.2 for the deeper analysis).
#
# To make the demo more realistic, this server randomly drops about 30%
# of incoming pings (never replies to them), so the client's
# settimeout(1.0) + retry/loss-counting logic in UDPPingerClient.py has
# something real to detect.

from socket import *
import random

SERVER_PORT = 12000
DROP_PROBABILITY = 0.3

serverSocket = socket(AF_INET, SOCK_DGRAM)
serverSocket.bind(('', SERVER_PORT))

print(f'UDP ping server ready, listening on port {SERVER_PORT}...')

while True:
    # A single socket serves every client; recvfrom() blocks until any
    # datagram arrives, from any address.
    message, address = serverSocket.recvfrom(1024)

    if random.random() < DROP_PROBABILITY:
        print(f'Simulated loss: dropped ping from {address}: '
              f'{message.decode()!r}')
        continue

    print(f'Received ping from {address}: {message.decode()!r}')
    serverSocket.sendto(message, address)
