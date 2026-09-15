# Tugas 3: Pengembangan dan Analisis Sistem Distribusi Pesan & File Berbasis Hybrid Socket

Mata Kuliah: Jaringan Komputer Lanjut (S2 Ilmu Komputer)

Repo ini memuat source code sekaligus laporan analisis Tugas 3. README ini
adalah laporan analisis lengkap (bukan file PDF terpisah): source code di
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

*(Akan diisi setelah demo dan bukti tangkapan layar diambil.)*

### Bagian B.1: Byte-Stream vs Message Boundary (Bobot 15%)

*(Akan diisi.)*

### Bagian B.2: Analisis Skalabilitas Socket (Bobot 15%)

*(Akan diisi.)*

### Bagian B.3: Evolusi Transport & QUIC (Bobot 15%)

*(Akan diisi.)*

### Bagian B.4: Skenario Bind Explicit pada Client (Bobot 15%)

*(Akan diisi.)*
