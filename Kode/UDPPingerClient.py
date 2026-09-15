# UDPPingerClient.py
# UDP ping client for the hybrid message/file distribution system
# (Bagian A.2 of Tugas_3).
#
# Sends 10 ping messages to the server. Because UDP delivery is
# unreliable, a datagram (or its reply) may be lost in transit; this
# client uses clientSocket.settimeout(1.0) so it never blocks forever
# waiting for a reply that will never come. Each lost ping is counted,
# and the final summary reports min/max/average RTT plus the packet loss
# rate, similar to how the standard "ping" command line tool summarizes
# a run.

from socket import *
import time

serverName = 'localhost'
serverPort = 12000

clientSocket = socket(AF_INET, SOCK_DGRAM)

# Give up waiting for a reply after 1 second: this is the client-side
# defense against unreliable packet delivery required by the brief.
clientSocket.settimeout(1.0)

NUM_PINGS = 10
rtt_list = []
lost_count = 0

for sequence_number in range(1, NUM_PINGS + 1):
    sendTime = time.time()
    message = f'Ping {sequence_number} {sendTime}'

    try:
        startTime = time.time()
        clientSocket.sendto(message.encode(), (serverName, serverPort))

        rttMessage, serverAddress = clientSocket.recvfrom(1024)
        endTime = time.time()

        rtt = endTime - startTime
        rtt_list.append(rtt)
        print(f'Reply from {serverAddress}: {rttMessage.decode()!r}, '
              f'RTT = {rtt:.6f} s')
    except timeout:
        lost_count += 1
        print(f'Ping {sequence_number}: Request timed out (no reply within 1.0 s)')

clientSocket.close()

print('\n--- Ping statistics ---')
packet_loss_rate = (lost_count / NUM_PINGS) * 100
print(f'{NUM_PINGS} packets transmitted, {NUM_PINGS - lost_count} received, '
      f'{packet_loss_rate:.1f}% packet loss')

if rtt_list:
    print(f'Minimum RTT = {min(rtt_list):.6f} s')
    print(f'Average RTT = {sum(rtt_list) / len(rtt_list):.6f} s')
    print(f'Maximum RTT = {max(rtt_list):.6f} s')
else:
    print('RTT statistics: N/A (no packets received)')
