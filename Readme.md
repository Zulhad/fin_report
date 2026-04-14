# 💰 Rekap Keuangan AI

App Streamlit untuk mengekstrak, memverifikasi, dan menganalisis laporan keuangan dari gambar menggunakan AI (Gemini).

---

## Fitur

- Upload foto/scan laporan keuangan
- Ekstraksi data otomatis via Gemini Vision AI (gratis)
- Human-in-the-loop: review & edit sebelum disimpan
- Database SQLite lokal sebagai master transaksi
- AI Insight: analisis tren, anomali, dan rekomendasi
- Export data ke CSV

---

## Cara Menjalankan

### 1. Install Python (jika belum)
Download dari https://python.org — pilih versi 3.10 atau lebih baru.

### 2. Install dependencies

Buka terminal/command prompt di folder ini, lalu jalankan:

```bash
pip install -r requirements.txt
```

### 3. Dapatkan Gemini API Key (GRATIS)

1. Buka https://aistudio.google.com/apikey
2. Login dengan akun Google
3. Klik "Create API Key"
4. Copy API Key-nya

### 4. Jalankan app

```bash
streamlit run app.py
```

Browser akan otomatis terbuka ke http://localhost:8501

---

## Cara Pakai

1. **Masukkan API Key** di sidebar kiri
2. **Upload & Ekstrak** — Upload foto laporan keuangan, klik tombol Ekstrak
3. **Review & Simpan** — Cek dan koreksi data, lalu simpan ke database
4. **Database** — Lihat semua transaksi, filter, dan export CSV
5. **AI Insight** — Dapatkan analisis dan rekomendasi dari AI

---

## Catatan

- Database tersimpan lokal di file `keuangan.db` (SQLite)
- Data tidak dikirim ke mana pun selain Gemini API untuk proses OCR
- Gemini API gratis: 1.500 request/hari, cukup untuk penggunaan normal
- Gambar terbaik: foto tegak lurus, pencahayaan cukup, tulisan terbaca jelas

---

## Struktur File

```
finance_ocr_app/
├── app.py              # Aplikasi utama Streamlit
├── requirements.txt    # Library yang dibutuhkan
├── README.md           # Panduan ini
└── keuangan.db         # Database SQLite (dibuat otomatis)
```
