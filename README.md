# Tugas 3: Pengembangan dan Analisis Sistem Distribusi Pesan & File Berbasis Hybrid Socket

Mata Kuliah: Jaringan Komputer Lanjut (S2 Ilmu Komputer)

Sistem hybrid socket yang menggabungkan:
- **TCP multi-threaded server** untuk transmisi teks/pesan (dan file) secara konkuren,
  dengan protokol layer aplikasi buatan sendiri (length-prefixed framing) untuk
  mengatasi masalah byte-stream boundary pada TCP.
- **UDP Pinger** untuk mengukur RTT dan packet loss antara client dan server.

## Struktur Repo

```
Kode/
  TCPServer.py          # Multi-threaded TCP server (welcoming + connection socket)
  TCPClient.py          # TCP client: text, file, demo3 (no-delay), multi (concurrency demo)
  UDPPingerServer.py     # UDP ping server (single socket, simulasi packet loss)
  UDPPingerClient.py     # UDP ping client (settimeout 1.0, RTT & loss statistics)
JAWABAN_A1.md            # Jawaban Bagian A.1: TCP multi-client (welcoming vs connection socket)
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
