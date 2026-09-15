# Tugas 3: Pengembangan dan Analisis Sistem Distribusi Pesan & File Berbasis Hybrid Socket

Mata Kuliah: Jaringan Komputer Lanjut (S2 Ilmu Komputer)

Repo ini memuat source code sekaligus laporan analisis Tugas 3. README ini
adalah laporan analisis lengkap : source code di
`Kode/`, jawaban Bagian A (implementasi) dan Bagian B (analisis) ada di
bawah, lengkap dengan bukti tangkapan layar Wireshark dan terminal.

Sistem hybrid socket yang menggabungkan:
- **TCP multi-threaded server** untuk transmisi teks/pesan (dan file) secara konkuren,
  dengan protokol layer aplikasi buatan sendiri (length-prefixed framing) untuk
  mengatasi masalah byte-stream boundary pada TCP.
- **UDP Pinger** untuk mengukur RTT dan packet loss antara client dan server.

## Struktur Repo

```
Kode/
  TCPServer.py           # Multi-threaded TCP server (welcoming + connection socket)
  TCPClient.py            # TCP client: text, file, demo3 (no-delay), multi (concurrency demo)
  UDPPingerServer.py      # UDP ping server (single socket, simulasi packet loss)
  UDPPingerClient.py      # UDP ping client (settimeout 1.0, RTT & loss statistics)
README.md                 # Laporan analisis lengkap (dokumen ini)
```

## Cara Menjalankan

Semua skrip menggunakan Python 3 standar (modul `socket`, `threading`), tidak ada
dependency eksternal.

### 1. TCP: layanan pesan/file multi-client

Jalankan server:
```bash
cd Kode
python3 TCPServer.py
```

Di terminal lain, jalankan client sesuai mode yang diinginkan:
```bash
# Kirim satu pesan teks
python3 TCPClient.py text "Halo dari client"

# Kirim file (disimpan server ke Kode/received_files/)
python3 TCPClient.py file /path/ke/file.txt

# Demo byte-stream boundary: kirim 3 pesan tanpa delay
python3 TCPClient.py demo3

# Demo multi-client: connect, kirim 1 pesan, tahan koneksi 4 detik
# (jalankan beberapa instance dengan id berbeda untuk lihat konkurensi)
python3 TCPClient.py multi A
```

### 2. UDP: ping server/client

Jalankan server (di port yang sama, 12000, tetapi UDP dan TCP punya namespace
port terpisah di OS sehingga bisa dijalankan bersamaan dengan TCPServer.py):
```bash
python3 UDPPingerServer.py
```

Jalankan client (mengirim 10 ping, timeout 1 detik per ping, lalu menampilkan
ringkasan RTT min/avg/max dan packet loss rate):
```bash
python3 UDPPingerClient.py
```

## Protokol Framing TCP

Setiap frame yang dikirim lewat koneksi TCP berbentuk:

```
[4 byte panjang N (big-endian)] [N byte payload]
```

Payload dimulai dengan 4 byte tag ASCII:
- `TEXT` + teks UTF-8
- `FILE` + 2 byte panjang nama file + nama file + isi file

Karena penerima selalu tahu persis berapa byte yang harus dibaca (length
prefix), beberapa pesan yang dikirim berturut-turut lewat `send()` tanpa
delay tidak akan pernah tergabung atau terpotong secara salah, terlepas dari
bagaimana TCP menyegmentasikannya di level transport.

---

## Laporan Analisis

### Bagian A.1: Layanan TCP Multi-Client (Bobot 20%)

#### Kode Welcoming Socket dan accept()

Diambil dari `Kode/TCPServer.py`:

```python
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
```

Setiap client dilayani di thread terpisah oleh `handle_client()`, yang membaca
frame demi frame lewat protokol framing custom (lihat bagian Protokol Framing
TCP di atas) sampai client memutus koneksi:

```python
def handle_client(connectionSocket, addr):
    print(f'[+] Client connected from {addr}')
    try:
        while True:
            payload = recv_frame(connectionSocket)
            if payload is None:
                print(f'[-] Client {addr} disconnected.')
                break
            # ... proses payload (TEXT / FILE) ...
    finally:
        connectionSocket.close()
```

#### Perbedaan Lifecycle: Welcoming Socket vs Connection Socket

**Welcoming socket (`serverSocket`)**

- Dibuat sekali saja, di awal program (`socket()`, `bind()`, `listen()`).
- Terikat ke port tetap yang sudah diketahui client sebelumnya (12000).
- Tidak pernah digunakan untuk mengirim/menerima data aplikasi. Fungsinya
  murni menerima permintaan koneksi baru lewat `accept()`.
- Hidup selama proses server berjalan, tidak pernah ditutup sampai server
  dimatikan (di kode ini, sampai `KeyboardInterrupt`).
- Hanya ada **satu** welcoming socket, terlepas dari berapa banyak client
  yang terhubung.

**Connection socket (`connectionSocket`)**

- Dibuat baru setiap kali `accept()` berhasil menerima satu koneksi. Tiap
  panggilan `accept()` menghasilkan connection socket yang berbeda.
- Terikat secara implisit ke pasangan (IP lokal, port lokal, IP client,
  port client) yang unik untuk sesi tersebut; port lokalnya tetap sama
  dengan welcoming socket (12000), tapi kombinasi dengan alamat client yang
  berbeda-beda membuat tiap socket ini unik di level OS.
- Digunakan untuk seluruh pertukaran data aplikasi (kirim/terima frame)
  dengan client yang bersangkutan, di dalam thread khusus milik client itu.
- Hidup hanya selama sesi client tersebut berlangsung, ditutup begitu
  client disconnect (`connectionSocket.close()`), lalu thread-nya selesai.
- Ada **N** connection socket berjalan bersamaan, satu untuk setiap client
  yang sedang aktif terhubung.

Karena welcoming socket dan connection socket adalah objek socket yang
berbeda, main thread bisa terus memanggil `accept()` untuk menerima client
baru tanpa harus menunggu client-client yang sudah ada selesai dilayani.
Inilah dasar dari konkurensi: satu welcoming socket yang berumur panjang,
dipasangkan dengan banyak connection socket yang berumur pendek dan
dijalankan paralel di thread masing-masing.

#### Bukti Konkurensi (Screenshot Wireshark + Terminal)

Tiga client (A, B, C) dijalankan hampir bersamaan, masing-masing:
1. Connect ke server (three-way handshake ke port 12000, dari port
   ephemeral berbeda: 65467, 65468, 65469).
2. Mengirim satu pesan TEXT.
3. Menahan koneksi terbuka 4 detik sebelum menutup.

Log server menunjukkan urutan connect A, B, C yang saling menyusul sebelum
satu pun disconnect, membuktikan ketiganya dilayani secara konkuren (bukan
satu per satu bergantian):

```
[+] Client connected from ('127.0.0.1', 65467)
[TEXT from ('127.0.0.1', 65467)] Halo dari client A
[+] Client connected from ('127.0.0.1', 65468)
[TEXT from ('127.0.0.1', 65468)] Halo dari client B
[+] Client connected from ('127.0.0.1', 65469)
[TEXT from ('127.0.0.1', 65469)] Halo dari client C
[-] Client ('127.0.0.1', 65467) disconnected.
[-] Client ('127.0.0.1', 65468) disconnected.
[-] Client ('127.0.0.1', 65469) disconnected.
```

Wireshark capture pada interface loopback (`lo0`) memperlihatkan tiga
three-way handshake terpisah (SYN, SYN/ACK, ACK) dari tiga port ephemeral
yang berbeda, semuanya menuju port 12000 yang sama, mengonfirmasi bahwa
welcoming socket di port 12000 tetap satu sementara tiap client mendapat
connection socket sendiri.

*(Screenshot bukti: lihat lampiran gambar yang disertakan terpisah saat
pengumpulan tugas.)*

### Bagian A.2: Layanan UDP Pinger (Bobot 20%)

#### Kode Client UDP dengan settimeout(1.0)

Diambil dari `Kode/UDPPingerClient.py`:

```python
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
```

Karena UDP tidak menjamin pengiriman, balasan dari server bisa saja tidak
pernah datang (baik karena request atau reply-nya hilang). `settimeout(1.0)`
memastikan `recvfrom()` tidak menunggu selamanya: kalau tidak ada balasan
dalam 1 detik, exception `timeout` ditangkap, ping tersebut dihitung sebagai
paket hilang, dan loop lanjut ke ping berikutnya. Di akhir 10 kali kirim,
client menghitung RTT minimum, rata-rata, maksimum (dari ping yang berhasil)
serta packet loss rate.

Untuk mendemonstrasikan penanganan packet loss secara nyata,
`UDPPingerServer.py` sengaja men-drop sekitar 30% ping yang masuk secara
acak (tidak membalas sama sekali), sehingga client benar-benar mengalami
timeout pada sebagian ping.

#### Hasil Uji Coba

Log server (`UDPPingerServer.py`):

```
UDP ping server ready, listening on port 12000...
Simulated loss: dropped ping from ('127.0.0.1', 64006): 'Ping 1 1789447772.172032'
Simulated loss: dropped ping from ('127.0.0.1', 64006): 'Ping 2 1789447773.184542'
Received ping from ('127.0.0.1', 64006): 'Ping 3 1789447774.18665'
Received ping from ('127.0.0.1', 64006): 'Ping 4 1789447774.187785'
Received ping from ('127.0.0.1', 64006): 'Ping 5 1789447774.1883678'
Received ping from ('127.0.0.1', 64006): 'Ping 6 1789447774.1891909'
Received ping from ('127.0.0.1', 64006): 'Ping 7 1789447774.190277'
Received ping from ('127.0.0.1', 64006): 'Ping 8 1789447774.190725'
Received ping from ('127.0.0.1', 64006): 'Ping 9 1789447774.191124'
Simulated loss: dropped ping from ('127.0.0.1', 64006): 'Ping 10 1789447774.191492'
```

Log client (`UDPPingerClient.py`):

```
Ping 1: Request timed out (no reply within 1.0 s)
Ping 2: Request timed out (no reply within 1.0 s)
Reply from ('127.0.0.1', 12000): 'Ping 3 1789447774.18665', RTT = 0.000991 s
Reply from ('127.0.0.1', 12000): 'Ping 4 1789447774.187785', RTT = 0.000551 s
Reply from ('127.0.0.1', 12000): 'Ping 5 1789447774.1883678', RTT = 0.000559 s
Reply from ('127.0.0.1', 12000): 'Ping 6 1789447774.1891909', RTT = 0.001042 s
Reply from ('127.0.0.1', 12000): 'Ping 7 1789447774.190277', RTT = 0.000411 s
Reply from ('127.0.0.1', 12000): 'Ping 8 1789447774.190725', RTT = 0.000354 s
Reply from ('127.0.0.1', 12000): 'Ping 9 1789447774.191124', RTT = 0.000343 s
Ping 10: Request timed out (no reply within 1.0 s)

--- Ping statistics ---
10 packets transmitted, 7 received, 30.0% packet loss
Minimum RTT = 0.000343 s
Average RTT = 0.000607 s
Maximum RTT = 0.001042 s
```

Ping 1, 2, dan 10 di-drop oleh server sehingga client mengalami timeout
tepat pada ketiga ping tersebut, sedangkan ping 3-9 berhasil dibalas dengan
RTT di kisaran sub-milidetik (wajar untuk komunikasi loopback). Hasil ini
konsisten satu sama lain antara log server dan log client, membuktikan
mekanisme timeout dan penghitungan RTT/packet loss di sisi client bekerja
sesuai spesifikasi.

*(Bukti tangkapan layar packet capture Wireshark untuk sesi UDP ini tidak
disertakan: pada environment pengujian, Wireshark salah mendekode sebagian
trafik loopback sebagai frame LLC alih-alih UDP, sebuah isu dekode yang
diketahui terjadi pada beberapa versi macOS. Bukti fungsional yang
disertakan berupa log terminal server dan client di atas, yang saling
berkorespondensi satu sama lain per nomor ping.)*

### Bagian B.1: Byte-Stream vs Message Boundary (Bobot 15%)

#### Mengapa TCP adalah byte-stream channel tanpa message boundary, sedangkan UDP mempertahankannya

TCP (`SOCK_STREAM`) memandang data yang dikirim lewat `send()` hanya sebagai
aliran byte yang berurutan (byte stream), bukan sebagai unit pesan yang
diskrit. Tidak ada informasi "di mana satu pesan berakhir dan pesan
berikutnya mulai" yang disimpan oleh TCP itu sendiri. Ini konsekuensi
langsung dari cara TCP bekerja di level transport:

- TCP boleh menggabungkan (coalesce) beberapa pemanggilan `send()` yang
  berurutan menjadi satu segmen TCP jika keduanya terjadi cukup berdekatan
  waktunya, demi efisiensi (mengurangi overhead header per segmen).
- TCP juga boleh memecah (fragment) satu pemanggilan `send()` yang besar
  menjadi beberapa segmen, tergantung MTU/MSS jaringan.
- Di sisi penerima, `recv()` hanya mengembalikan sejumlah byte yang
  tersedia di buffer saat itu, sebanyak yang diminta atau kurang. Tidak ada
  jaminan satu `recv()` = satu `send()` dari pengirim.

Sebaliknya, UDP (`SOCK_DGRAM`) memang menjaga message boundary: setiap
pemanggilan `sendto()` menghasilkan satu datagram utuh, dan setiap
pemanggilan `recvfrom()` yang berhasil akan mengembalikan tepat satu
datagram tersebut secara utuh (atau tidak sama sekali, jika hilang). UDP
tidak pernah menggabungkan dua datagram terpisah menjadi satu, atau
memecah satu datagram menjadi beberapa balasan `recvfrom()`. Ini karena UDP
tidak memiliki abstraksi byte stream sama sekali; setiap `sendto()`
langsung dipetakan satu-satu ke satu paket di level jaringan (kecuali
dipecah oleh fragmentasi IP, yang transparan dan tetap disatukan ulang
sebelum diserahkan ke aplikasi).

#### Dampak Teknis: 3 String Dikirim Berturut-turut Tanpa Delay

Untuk membuktikan hal ini secara empiris, `TCPClient.py` mode `demo3`
mengirim tiga pesan teks ("Pesan pertama", "Pesan kedua", "Pesan ketiga")
lewat tiga pemanggilan `send()` berurutan tanpa delay sama sekali.

Log terminal server (`TCPServer.py`):
```
[+] Client connected from ('127.0.0.1', 65355)
[TEXT from ('127.0.0.1', 65355)] Pesan pertama
[TEXT from ('127.0.0.1', 65355)] Pesan kedua
[TEXT from ('127.0.0.1', 65355)] Pesan ketiga
[-] Client ('127.0.0.1', 65355) disconnected.
```

Log terminal client (`TCPClient.py demo3`):
```
Connected to localhost:12000
Sent (no delay): Pesan pertama
Sent (no delay): Pesan kedua
Sent (no delay): Pesan ketiga
Connection closed.
```

Wireshark capture pada `lo0` menunjukkan hanya **2 segmen data** yang
terkirim di kabel, bukan 3:

- Segmen pertama: `[PSH, ACK] Len=21` — persis ukuran frame pesan pertama
  (4 byte length prefix + 4 byte tag `TEXT` + 13 byte teks "Pesan pertama"
  = 21 byte).
- Segmen kedua: `[FIN, PSH, ACK] Len=39` — ukuran ini adalah **gabungan**
  dari frame kedua (4+4+11 = 19 byte, untuk "Pesan kedua") dan frame ketiga
  (4+4+12 = 20 byte, untuk "Pesan ketiga"), 19 + 20 = 39 byte. TCP
  menggabungkan kedua `send()` ini menjadi satu segmen karena keduanya
  dipanggil hampir bersamaan tanpa delay.

Ini adalah bukti nyata dari dampak teknis yang dimaksud soal: OS/TCP stack
menggabungkan pesan kedua dan ketiga menjadi satu segmen di level jaringan.
Jika server hanya melakukan `recv(1024)` polos dan menganggap satu
`recv()` sama dengan satu pesan (seperti pada `server_multithreaded.py` di
Tugas 2), server akan salah memproses gabungan 39 byte tersebut sebagai
satu pesan tunggal yang tercampur, bukan dua pesan terpisah.

#### Rancangan Protokol Aplikasi untuk Menyelesaikan Kendala Ini

`TCPServer.py` dan `TCPClient.py` mengimplementasikan protokol framing
custom berbasis **length-prefix header** (lihat bagian "Protokol Framing
TCP" di atas): setiap frame diawali 4 byte panjang (big-endian) yang
memberitahu penerima persis berapa byte payload yang harus dibaca
selanjutnya. Fungsi `recv_exact()` di server memastikan pembacaan terus
berlanjut sampai jumlah byte yang diminta benar-benar terkumpul, tidak
peduli berapa kali panggilan `recv()` dibutuhkan atau apakah beberapa
frame tergabung dalam satu segmen TCP.

Dengan pendekatan ini, meskipun Wireshark membuktikan bahwa pesan kedua
dan ketiga tergabung menjadi satu segmen 39-byte di level TCP, log server
tetap berhasil memisahkan dan menampilkan ketiganya secara terpisah dan
benar ("Pesan pertama", "Pesan kedua", "Pesan ketiga"), karena pemisahan
dilakukan di level aplikasi berdasarkan length prefix, bukan mengandalkan
batas `recv()`.

### Bagian B.2: Analisis Skalabilitas Socket (Bobot 15%)

#### Jumlah Total Soket yang Dibuka Server TCP untuk N Client

Server TCP membuka **N + 1** soket total ketika melayani N client secara
bersamaan:

- **1 welcoming socket**, dibuat sekali di awal (`serverSocket`), tetap
  terikat ke port 12000, dan tidak pernah bertambah jumlahnya berapa pun
  banyaknya client yang terhubung.
- **N connection socket**, satu untuk setiap client yang sedang aktif
  terhubung, masing-masing dibuat oleh panggilan `accept()` yang berbeda
  (lihat `Kode/TCPServer.py`, dieksekusi di `while True: connectionSocket,
  addr = serverSocket.accept()`).

Tiap connection socket diidentifikasi unik oleh OS lewat 4-tuple
(IP lokal, port lokal, IP remote, port remote). Karena port lokal sama
(12000) untuk semua connection socket, yang membedakan satu socket dari
socket lain adalah kombinasi IP dan port di sisi client, yang berbeda-beda
untuk tiap client meskipun berasal dari IP yang sama sekalipun (karena
port ephemeral client berbeda-beda). Ini terbukti langsung pada demo
multi-client di Bagian A.1: 3 client menghasilkan 3 connection socket
terpisah (port ephemeral 65467, 65468, 65469) plus 1 welcoming socket yang
sama untuk ketiganya, total 4 soket.

#### Mengapa Server UDP Hanya Membutuhkan 1 Soket

Server UDP (`UDPPingerServer.py`) tidak melakukan `listen()` atau
`accept()` sama sekali. UDP adalah protokol connectionless: tidak ada
konsep "sesi" atau "koneksi" yang perlu dijaga statenya di level socket.
Satu soket yang di-`bind()` ke port 12000 sudah cukup untuk menerima
datagram dari **siapa pun**, karena setiap panggilan `recvfrom()`
mengembalikan payload sekaligus alamat pengirim (IP, port) datagram
tersebut, dan server bisa langsung `sendto()` balik ke alamat itu tanpa
perlu socket khusus per client.

Implikasi terhadap konsumsi memori OS dan port binding:

- **Memori OS**: Server UDP menggunakan hanya 1 file descriptor dan 1
  buffer socket (send/receive buffer kernel) berapa pun banyaknya client
  yang mengirim datagram, sedangkan server TCP menggunakan file descriptor
  dan buffer socket yang bertumbuh linear (O(N)) terhadap jumlah client
  aktif. Untuk sistem dengan jumlah client sangat besar, ini adalah alasan
  UDP jauh lebih ringan secara memori dibanding TCP per unit client.
- **Port binding**: Karena hanya perlu 1 `bind()`, server UDP tidak
  pernah kehabisan port lokal untuk melayani banyak client (port lokal
  server tetap satu, 12000, selamanya). Server TCP juga sebenarnya tidak
  kehabisan port lokal untuk *menerima* koneksi (welcoming socket tetap 1
  port), tapi tiap connection socket tetap mengonsumsi entry pada
  tabel koneksi kernel (connection tracking table) sehingga ada batas
  praktis jumlah koneksi simultan yang bisa dilayani (dibatasi oleh
  file descriptor limit, memori, dan ukuran tabel koneksi OS), sedangkan
  UDP tidak memiliki batasan setara ini sama sekali karena tidak ada
  state per client yang disimpan di level socket.

### Bagian B.3: Evolusi Transport & QUIC (Bobot 15%)

#### Mengapa QUIC Berjalan di Atas UDP (SOCK_DGRAM)

QUIC memilih berjalan di atas UDP, bukan membuat transport protocol baru
dari nol atau menumpang di atas TCP, karena beberapa alasan:

1. **Deployability di internet nyata**: Membuat protokol transport baru
   di level IP (nomor protokol baru selain TCP=6 dan UDP=17) hampir mustahil
   di-deploy secara luas, karena middlebox (NAT, firewall, router lama) di
   seluruh internet hanya mengenal dan meloloskan TCP dan UDP. Paket dengan
   nomor protokol IP baru akan banyak di-drop di tengah jalan. UDP sudah
   diloloskan hampir universal, sehingga membangun di atasnya menjamin
   QUIC bisa langsung berjalan di infrastruktur yang sudah ada tanpa perlu
   upgrade middlebox di mana pun.
2. **Menghindari batasan TCP di level kernel OS**: TCP diimplementasikan
   di kernel OS dan sangat kaku untuk diubah atau dieksperimen (perubahan
   butuh update kernel di seluruh dunia, proses yang sangat lambat).
   Dengan berjalan di atas UDP (yang hanya menyediakan pengiriman datagram
   tanpa logic tambahan), QUIC bisa mengimplementasikan seluruh logic
   transport-nya sendiri (reliability, congestion control, flow control,
   enkripsi) di level aplikasi/user-space, sehingga bisa berevolusi cepat
   dan di-deploy lewat update aplikasi/library saja, tanpa perlu menyentuh
   kernel OS pengguna.
3. **UDP memberi kontrol penuh tanpa overhead tambahan**: UDP tidak
   memaksakan model reliability atau ordering apa pun, jadi QUIC bebas
   merancang model deliverynya sendiri yang lebih sesuai kebutuhan modern
   (multiplexing banyak stream independen dalam satu koneksi) tanpa
   terikat asumsi desain TCP yang dibuat untuk kasus penggunaan lama.

#### Bagaimana QUIC Menyelesaikan Head-of-Line (HOL) Blocking

Pada TCP, HOL blocking terjadi karena TCP hanya mengenal satu aliran byte
tunggal per koneksi: jika satu segmen hilang di tengah jalan, seluruh
byte stream setelahnya (termasuk byte milik request/resource lain yang
di-multiplex di atas koneksi yang sama, seperti pada HTTP/2) harus
menunggu segmen yang hilang tersebut di-retransmit dan diterima ulang
secara berurutan, meskipun byte-byte lain itu sebenarnya sudah tiba dengan
selamat di buffer penerima. Semua stream tersandera oleh satu segmen yang
hilang.

QUIC menyelesaikan ini dengan mengimplementasikan **multiplexing di level
stream native**, bukan menumpangkannya di atas satu byte stream tunggal
seperti HTTP/2 di atas TCP. Setiap stream QUIC memiliki nomor urut
(sequence) dan buffer reliability-nya sendiri secara independen. Jika satu
paket QUIC yang membawa data untuk stream A hilang, hanya stream A yang
menunggu retransmisi; stream B, C, dan seterusnya yang datanya sudah tiba
lengkap tetap bisa langsung diserahkan ke aplikasi tanpa menunggu. Karena
QUIC berjalan di atas UDP yang connectionless dan tidak memaksakan
pengurutan byte stream global, hilangnya satu datagram tidak lagi memblokir
datagram-datagram independen lainnya, sehingga HOL blocking di level
transport yang menjadi masalah struktural pada TCP tidak terjadi pada
QUIC.

### Bagian B.4: Skenario Bind Explicit pada Client (Bobot 15%)

#### Apa yang Terjadi Jika UDPClient.py Melakukan `clientSocket.bind(('', 5432))` Sebelum Mengirim

Secara default, ketika client memanggil `sendto()` tanpa `bind()`
eksplisit sebelumnya, OS akan otomatis memilih port lokal sementara
(ephemeral port) begitu socket pertama kali digunakan untuk mengirim data
(implicit bind). Ini terjadi otomatis di balik layar tanpa client perlu
tahu port berapa yang dipakai.

Jika client secara eksplisit memanggil
`clientSocket.bind(('', 5432))` sebelum mengirim, client memaksa socket
tersebut memakai port lokal 5432 secara spesifik, bukan port ephemeral
acak yang biasanya dipilih OS. `bind(('', ...))` mengikat socket ke port
5432 pada semua interface lokal yang tersedia (`''` berarti `INADDR_ANY`),
bukan ke IP tertentu.

#### Apakah Server Masih Bisa Membalas Pesan Tersebut

Ya, server tetap bisa membalas seperti biasa. Ini karena mekanisme balasan
UDP tidak bergantung pada bagaimana client mendapatkan port lokalnya
(implicit atau explicit bind), melainkan murni berdasarkan alamat pengirim
yang tercatat di header paket UDP yang diterima. Ketika server memanggil
`recvfrom()`, ia mendapatkan tuple `(IP_client, port_client)` dari paket
yang masuk, di kasus ini `(IP_client, 5432)`. Server lalu memanggil
`sendto(reply, (IP_client, 5432))`, dan balasan itu akan sampai dengan
benar ke client yang memang sedang mendengarkan (bind) di port 5432
tersebut. Dari perspektif protokol, port 5432 hasil bind eksplisit
berfungsi identik dengan port ephemeral hasil implicit bind, karena
keduanya sama-sama hanya berupa nomor port biasa di header UDP.

#### Potensi Kendala Jika 2 Instansiasi Client Berjalan Bersamaan di Host yang Sama

Di sinilah letak masalahnya. Port yang sudah di-bind secara eksplisit ke
nomor tetap (5432) bersifat eksklusif per host untuk kombinasi
(protokol, IP lokal, port lokal) tersebut: hanya satu proses yang bisa
menguasai port UDP 5432 pada satu waktu di host yang sama (kecuali diatur
memakai opsi khusus seperti `SO_REUSEADDR`/`SO_REUSEPORT`, yang defaultnya
tidak diaktifkan).

Jika instansiasi client kedua dijalankan bersamaan di host yang sama dan
juga mencoba `bind(('', 5432))`, panggilan `bind()` tersebut akan gagal
dan melempar exception (`OSError: [Errno 48] Address already in use` di
macOS/Linux), karena port 5432 sudah dipakai oleh instansiasi client yang
pertama. Client kedua tidak akan bisa berjalan sama sekali sampai
instansiasi pertama ditutup (socket-nya dilepas) atau memakai port bind
yang berbeda.

Ini adalah perbedaan fundamental dibanding client yang membiarkan OS
memilih port ephemeral secara otomatis: dengan implicit bind, setiap
instansiasi client baru otomatis mendapat port ephemeral yang berbeda-beda
(dipilih OS dari pool port yang belum terpakai), sehingga banyak
instansiasi client bisa berjalan bersamaan tanpa konflik apa pun. Memaksa
bind ke port fixed seperti 5432 menghilangkan keuntungan ini dan membuat
aplikasi client rentan terhadap konflik port ketika dijalankan lebih dari
satu kali secara bersamaan di host yang sama.
