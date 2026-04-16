import streamlit as st
import sqlite3
import pandas as pd
import json
import base64
import os
from datetime import datetime
from openai import OpenAI
from PIL import Image
import io

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Rekap Keuangan AI",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header { font-size: 1.6rem; font-weight: 600; margin-bottom: 0.2rem; }
    .sub-header  { font-size: 0.9rem; color: #888; margin-bottom: 1.5rem; }
    .card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
        border: 1px solid #e9ecef;
    }
    .badge-success { background:#d4edda; color:#155724; padding:3px 10px; border-radius:20px; font-size:12px; }
    .badge-warning { background:#fff3cd; color:#856404; padding:3px 10px; border-radius:20px; font-size:12px; }
    .badge-danger  { background:#f8d7da; color:#721c24; padding:3px 10px; border-radius:20px; font-size:12px; }
    .metric-box { text-align:center; padding:0.8rem; background:#fff; border-radius:8px; border:1px solid #e9ecef; }
    .metric-val { font-size:1.4rem; font-weight:600; }
    .metric-lbl { font-size:0.78rem; color:#888; }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Database setup ────────────────────────────────────────────────────────────
# ── Database setup ────────────────────────────────────────────────────────────
DB_PATH = "keuangan.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transaksi (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal     TEXT NOT NULL,
            shift       TEXT,
            keterangan  TEXT,
            kategori    TEXT,
            tipe_pembayaran TEXT,
            debit       REAL DEFAULT 0,
            kredit      REAL DEFAULT 0,
            sumber_file TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_conn():
    return sqlite3.connect(DB_PATH)

def save_transaksi(rows: list[dict], nama_file: str):
    conn = get_conn()
    c = conn.cursor()
    for r in rows:
        c.execute("""
            INSERT INTO transaksi (tanggal, shift, keterangan, kategori, tipe_pembayaran, debit, kredit, sumber_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.get("tanggal", ""),
            r.get("shift", "Pagi"),
            r.get("keterangan", ""),
            r.get("kategori", ""),
            r.get("tipe_pembayaran", "Tunai"),
            float(r.get("debit", 0) or 0),
            float(r.get("kredit", 0) or 0),
            nama_file
        ))
    conn.commit()
    conn.close()

def load_transaksi(limit=None) -> pd.DataFrame:
    conn = get_conn()
    query = "SELECT * FROM transaksi ORDER BY tanggal DESC, id DESC"
    if limit:
        query += f" LIMIT {limit}"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# ── OpenAI OCR ────────────────────────────────────────────────────────────────
EXTRACT_PROMPT = """
Kamu adalah asisten ekstraksi data keuangan hotel. Analisa gambar laporan kasir ini.
Ekstrak SEMUA transaksi dengan format JSON array:
{
  "transaksi": [
    {
      "tanggal": "YYYY-MM-DD",
      "shift": "Pagi atau Malam",
      "keterangan": "deskripsi item",
      "kategori": "Kamar, F&B, Operasional, Selisih, atau Lain-lain",
      "tipe_pembayaran": "Tunai atau Non-Tunai",
      "debit": 0,
      "kredit": 0
    }
  ]
}
Aturan:
- Debit = Pengeluaran / Non-Tunai yang mengurangi kas fisik.
- Kredit = Pemasukan (Kamar, F&B, dll).
"""

def ocr_dengan_openai(api_key: str, image_bytes: bytes) -> list[dict]:
    client = OpenAI(api_key=api_key)
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACT_PROMPT + "\nKembalikan HANYA JSON object dengan key 'transaksi'."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            }
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    
    res_json = json.loads(response.choices[0].message.content)
    return res_json.get("transaksi", [])



INSIGHT_PROMPT = """
Kamu adalah analis keuangan Hotel Royal Inn. Analisis data transaksi HISTORIS berikut secara keseluruhan.
Berikan laporan dalam format markdown yang sangat detail:

1. ANALISIS PENDAPATAN (INFLOW)
   - Buat tabel perbandingan Pendapatan Kamar vs F&B.
   - Bandingkan performa Shift Pagi vs Shift Malam.
   - Identifikasi adanya pelunasan "Kekurangan Setoran".

2. ANALISIS PENGELUARAN (OUTFLOW)
   - Total pengeluaran.
   - Pisahkan antara Pembayaran Non-Tunai (QRIS/Debit) vs Belanja Operasional.

3. REKONSILIASI KAS (LOGIKA SETORAN)
   - Gunakan Rumus: Total Pendapatan - (Total Non-Tunai + Total Belanja) = Total Tunai yang harus disetor.
   - Tampilkan perhitungan saldo tunai akhir.

4. CATATAN & OBSERVASI
   - Efisiensi F&B (hitung rasio F&B vs Pendapatan Kamar).
   - Analisis Piutang/Selisih Setoran.
   - Tren Metode Pembayaran (Persentase Tunai vs Non-Tunai).

5. REKOMENDASI (Saran untuk meningkatkan profit atau efisiensi operasional).

Data Transaksi (Seluruh Sejarah):
{data}
"""


def generate_insight(api_key: str, df: pd.DataFrame) -> str:
    client = OpenAI(api_key=api_key)
    summary = {
        "total_transaksi": len(df),
        "total_debit": df["debit"].sum(),
        "total_kredit": df["kredit"].sum(),
        "saldo_bersih": df["kredit"].sum() - df["debit"].sum(),
        "kategori_terbesar": df.groupby("kategori")["debit"].sum().nlargest(3).to_dict() if "kategori" in df.columns else {},
        "sample_transaksi": df.head(10).to_dict(orient="records")
    }
    prompt = INSIGHT_PROMPT.format(data=json.dumps(summary, ensure_ascii=False, indent=2))
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Sistem")
    # Mengambil API Key dari st.secrets secara otomatis
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
        st.success("🤖 AI Engine: OpenAI Active")
    except:
        api_key = None
        st.error("❌ OpenAI API Key tidak ditemukan")
        st.info("Pastikan OPENAI_API_KEY sudah diatur di .streamlit/secrets.toml.")

    st.divider()


    menu = st.radio("Navigasi", ["Upload & Ekstrak", "Review & Simpan", "Database", "AI Insight"])

# ── State init ────────────────────────────────────────────────────────────────
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = []
if "current_file" not in st.session_state:
    st.session_state.current_file = ""

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: UPLOAD & EKSTRAK
# ══════════════════════════════════════════════════════════════════════════════
if menu == "Upload & Ekstrak":
    st.markdown('<div class="main-header">📤 Upload Laporan Keuangan</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Upload foto atau scan laporan keuangan untuk diekstrak otomatis</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        uploaded = st.file_uploader(
            "Pilih gambar laporan",
            type=["jpg", "jpeg", "png", "webp"],
            help="Format: JPG, PNG, WEBP"
        )
        if uploaded:
            st.image(uploaded, caption=uploaded.name, use_column_width=True)
            st.session_state.current_file = uploaded.name

    with col2:
        if uploaded:
            st.markdown("#### Detail file")
            st.markdown(f"""
            <div class="card">
                <b>Nama file:</b> {uploaded.name}<br>
                <b>Ukuran:</b> {uploaded.size/1024:.1f} KB<br>
                <b>Tipe:</b> {uploaded.type}
            </div>
            """, unsafe_allow_html=True)

            if not api_key:
                st.warning("Masukkan Gemini API Key di sidebar untuk mulai ekstraksi.")
            else:
                if st.button("🔍 Ekstrak Data dengan AI", type="primary", use_container_width=True):
                    with st.spinner("AI sedang membaca laporan keuangan..."):
                        try:
                            img_bytes = uploaded.read()
                            data = ocr_dengan_openai(api_key, img_bytes)
                            st.session_state.extracted_data = data
                            if data:
                                st.success(f"✅ Berhasil mengekstrak {len(data)} transaksi!")
                            else:
                                st.warning("Tidak ditemukan data transaksi. Coba gambar yang lebih jelas.")
                        except json.JSONDecodeError:
                            st.error("Gagal parse JSON dari AI. Coba lagi atau gunakan gambar berbeda.")
                        except Exception as e:
                            st.error(f"Error: {e}")

        if st.session_state.extracted_data:
            st.markdown("#### Hasil ekstraksi (preview)")
            df_preview = pd.DataFrame(st.session_state.extracted_data)
            st.dataframe(df_preview, use_container_width=True, height=280)
            st.info("👉 Buka **Review & Simpan** untuk verifikasi sebelum menyimpan ke database.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: REVIEW & SIMPAN (Human in the Loop)
# ══════════════════════════════════════════════════════════════════════════════
elif menu == "Review & Simpan":
    st.markdown('<div class="main-header">✅ Review & Verifikasi Data</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Periksa dan koreksi data hasil ekstraksi sebelum disimpan ke database</div>', unsafe_allow_html=True)

    if not st.session_state.extracted_data:
        st.info("Belum ada data untuk direview. Silakan upload gambar terlebih dahulu.")
    else:
        st.markdown(f"**File:** `{st.session_state.current_file}` · **{len(st.session_state.extracted_data)} transaksi** ditemukan")

        df_edit = pd.DataFrame(st.session_state.extracted_data)
        # Pastikan kolom lengkap
        for col in ["tanggal", "keterangan", "kategori", "debit", "kredit", "saldo"]:
            if col not in df_edit.columns:
                df_edit[col] = "" if col in ["tanggal","keterangan","kategori"] else 0.0

        st.markdown("#### Edit tabel di bawah jika ada kesalahan:")
        edited_df = st.data_editor(
            df_edit[["tanggal","keterangan","kategori","debit","kredit","saldo"]],
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "tanggal":     st.column_config.TextColumn("Tanggal", width=110),
                "keterangan":  st.column_config.TextColumn("Keterangan", width=220),
                "kategori":    st.column_config.SelectboxColumn("Kategori", width=130,
                               options=["Pemasukan","Pengeluaran","Operasional","Transfer",
                                        "Gaji","Pajak","Investasi","Lain-lain"]),
                "debit":       st.column_config.NumberColumn("Debit (Rp)", format="%.0f"),
                "kredit":      st.column_config.NumberColumn("Kredit (Rp)", format="%.0f"),
                "saldo":       st.column_config.NumberColumn("Saldo (Rp)", format="%.0f"),
            }
        )

        st.divider()
        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            total_debit  = edited_df["debit"].sum()
            total_kredit = edited_df["kredit"].sum()
            st.metric("Total Debit",  f"Rp {total_debit:,.0f}")
        with col_b:
            st.metric("Total Kredit", f"Rp {total_kredit:,.0f}")
        with col_c:
            saldo = total_kredit - total_debit
            st.metric("Saldo Bersih", f"Rp {saldo:,.0f}", delta=f"{saldo:,.0f}")

        st.divider()
        col_save, col_discard = st.columns(2)
        with col_save:
            if st.button("💾 Simpan ke Database", type="primary", use_container_width=True):
                records = edited_df.to_dict(orient="records")
                save_transaksi(records, st.session_state.current_file)
                st.session_state.extracted_data = []
                st.session_state.current_file = ""
                st.success("✅ Data berhasil disimpan ke database lokal!")
                st.balloons()


        with col_discard:
            if st.button("🗑️ Buang Data", use_container_width=True):
                st.session_state.extracted_data = []
                st.session_state.current_file = ""
                st.warning("Data dibuang.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DATABASE
# ══════════════════════════════════════════════════════════════════════════════
elif menu == "Database":
    st.markdown('<div class="main-header">🗄️ Master Transaksi</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Seluruh transaksi yang sudah diverifikasi</div>', unsafe_allow_html=True)

    df = load_transaksi()
    
    if df.empty:
        st.warning("Database masih kosong. Silakan upload laporan terlebih dahulu.")
    else:
        summary = {
            "jumlah": len(df),
            "total_debit": df["debit"].sum(),
            "total_kredit": df["kredit"].sum(),
        }
        summary["saldo_bersih"] = summary["total_kredit"] - summary["total_debit"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Transaksi", f"{summary['jumlah']:,}")
        c2.metric("Total Debit", f"Rp {summary['total_debit']:,.0f}")
        c3.metric("Total Kredit", f"Rp {summary['total_kredit']:,.0f}")
        c4.metric("Saldo Bersih", f"Rp {summary['saldo_bersih']:,.0f}")

        st.divider()
        st.dataframe(df.drop(columns=["id"]), use_container_width=True, height=420)



    st.divider()
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Export CSV", csv, "transaksi_export.csv", "text/csv")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: AI INSIGHT
# ══════════════════════════════════════════════════════════════════════════════
elif menu == "AI Insight":
    st.markdown('<div class="main-header">🤖 AI Insight & Analisis</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Analisis otomatis dan rekomendasi dari data transaksi</div>', unsafe_allow_html=True)

    df = load_transaksi()

    if df.empty:
        st.info("Belum ada data transaksi di database.")
    else:
        # Analisa Total Data
        total_kredit = df["kredit"].sum()
        total_debit = df["debit"].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Pemasukan", f"Rp {total_kredit:,.0f}")
        c2.metric("Total Pengeluaran", f"Rp {total_debit:,.0f}")
        c3.metric("Kas Bersih", f"Rp {total_kredit - total_debit:,.0f}")

        # Bar chart per Shift
        st.markdown("#### Pendapatan per Shift (Kumulatif)")
        shift_df = df.groupby("shift")["kredit"].sum().reset_index()
        st.bar_chart(shift_df.set_index("shift"))

        st.divider()

        if not api_key:
            st.warning("Masukkan Gemini API Key di sidebar untuk menghasilkan AI Insight.")
        else:
            if st.button("✨ Generate AI Insight", type="primary"):
                with st.spinner("AI sedang menganalisis data keuangan..."):
                    try:
                        insight = generate_insight(api_key, df)
                        st.markdown("#### Hasil Analisis AI")
                        st.markdown(f"""
                        <div class="card">
                        {insight.replace(chr(10), '<br>')}
                        </div>
                        """, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Error: {e}")
