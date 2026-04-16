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
    page_title="Hotel Royal Inn Dashboard",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Custom CSS for Premium Dashboard ──────────────────────────────────────────
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    * { font-family: 'Inter', sans-serif; }
    .main { background-color: #fcfcfc; }
    
    /* Header Styling */
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 0;
        border-bottom: 2px solid #f1f5f9;
        margin-bottom: 2rem;
    }
    .logo-text {
        font-size: 24px;
        font-weight: 700;
        color: #1e293b;
    }
    .logo-text span { color: #d97706; }
    .status-live {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #94a3b8;
        font-weight: 500;
        font-size: 14px;
    }
    .dot { height: 8px; width: 8px; background-color: #22c55e; border-radius: 50%; display: inline-block; }

    /* Title & Badge */
    .view-title { font-size: 28px; font-weight: 700; color: #1e293b; display: flex; align-items: center; gap: 15px; }
    .badge-pending {
        background: #fef3c7;
        color: #d97706;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 14px;
        font-weight: 600;
    }
    .view-desc { color: #64748b; font-size: 16px; margin-bottom: 2rem; }

    /* Stats Cards */
    .stats-container { display: flex; gap: 20px; margin-bottom: 2rem; }
    .stats-card {
        background: white;
        padding: 15px 25px;
        border-radius: 12px;
        border: 1px solid #f1f5f9;
        flex: 1;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    .stats-label { color: #94a3b8; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
    .stats-val { color: #1e293b; font-size: 20px; font-weight: 700; margin-top: 5px; }

    /* Buttons */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 1rem;
        transition: all 0.2s;
    }
    .btn-approve { background-color: #1e293b !important; color: white !important; width: 100%; border: none; }
</style>

<div class="header-container">
    <div class="logo-text">🏨 Hotel <span>Royal Inn</span> Financial Dashboard</div>
    <div class="status-live"><span class="dot"></span> SYSTEM LIVE</div>
</div>
""", unsafe_allow_html=True)

# ── Database setup ────────────────────────────────────────────────────────────
DB_PATH = "keuangan.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Untuk update skema otomatis di prototype, kita drop jika kolom beda
    try:
        c.execute("SELECT guest FROM transaksi LIMIT 1")
    except:
        c.execute("DROP TABLE IF EXISTS transaksi")
        c.execute("""
            CREATE TABLE transaksi (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT,
                guest         INTEGER,
                shift         TEXT,
                description   TEXT,
                income        REAL DEFAULT 0,
                expense_debit REAL DEFAULT 0,
                expense_cash  REAL DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
    conn.commit()
    conn.close()

init_db()

def get_conn():
    return sqlite3.connect(DB_PATH)

def save_transaksi(rows: list[dict], guest_count: int):
    conn = get_conn()
    c = conn.cursor()
    for r in rows:
        c.execute("""
            INSERT INTO transaksi (date, guest, shift, description, income, expense_debit, expense_cash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            r.get("date", ""),
            guest_count,
            r.get("shift", ""),
            r.get("description", ""),
            float(r.get("income", 0) or 0),
            float(r.get("expense_debit", 0) or 0),
            float(r.get("expense_cash", 0) or 0)
        ))
    conn.commit()
    conn.close()
def load_transaksi(limit=None) -> pd.DataFrame:
    conn = get_conn()
    query = "SELECT * FROM transaksi ORDER BY date DESC, id DESC"
    if limit:
        query += f" LIMIT {limit}"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# ── OpenAI OCR ────────────────────────────────────────────────────────────────
EXTRACT_PROMPT = """
Anda adalah akuntan ahli. Analisis gambar laporan keuangan HOTEL ROYAL INN ini.
Ekstrak data per baris transaksi dengan sangat teliti ke format JSON.

ATURAN PENAMAAN KHUSUS:
- Jika menemukan baris 'SHIFT PAGI' yang memiliki angka Pendapatan, ubah deskripsinya menjadi: "Pendapatan Shift Pagi".
- Jika menemukan baris 'SHIFT MALAM' yang memiliki angka Pendapatan, ubah deskripsinya menjadi: "Pendapatan Shift Malam".
- Baris lainnya seperti 'FNB', 'DEBIT', atau 'BELANJA' tetap menggunakan nama aslinya.

PANDUAN PEMETAAN KOLOM:
1. Shift: Tentukan 'Pagi' atau 'Malam' berdasarkan letak transaksi tersebut di dokumen.
2. Description: Gunakan aturan penamaan khusus di atas atau teks dari kolom 'KETERANGAN'.
3. Income: Jika ada angka di kolom 'PENDAPATAN'.
4. Expense_debit: Jika ada angka di kolom 'DEBIT/QRIS/TF' di bawah 'PENGELUARAN'.
5. Expense_cash: Jika ada angka di kolom 'BELANJA/DLL' di bawah 'PENGELUARAN'.
6. Date & Guest: Cari di bagian atas dokumen.

Format JSON:
{
  "report_date": "...",
  "guest_count": 0,
  "transaksi": [
    {
      "date": "...",
      "shift": "Pagi/Malam",
      "description": "...",
      "income": 0,
      "expense_debit": 0,
      "expense_cash": 0
    }
  ]
}
"""


def ocr_dengan_openai(api_key: str, image_bytes: bytes) -> dict:
    client = OpenAI(api_key=api_key)
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    response = client.chat.completions.create(
        model="gpt-4o",  # Upgrade to FLAGSHIP model for high accuracy
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACT_PROMPT},
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
    return json.loads(response.choices[0].message.content)



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
        "total_income": df["income"].sum(),
        "total_expense_debit": df["expense_debit"].sum(),
        "total_expense_cash": df["expense_cash"].sum(),
        "net_cash": df["income"].sum() - (df["expense_debit"].sum() + df["expense_cash"].sum()),
        "data_summary_per_shift": df.groupby("shift")[["income", "expense_debit", "expense_cash"]].sum().to_dict(),
        "sample_data": df.tail(15).to_dict(orient="records")
    }
    prompt = INSIGHT_PROMPT.format(data=json.dumps(summary, ensure_ascii=False, indent=2))
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# ── Sidebar ───────────────────────────────────────────────────────────────────
# ── Auth & API Check ──────────────────────────────────────────────────────────
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except:
    api_key = None
    st.error("❌ OpenAI API Key tidak ditemukan. Selesaikan pengaturan di secrets.toml.")

# ── Main Tabs ────────────────────────────────────────────────────────────────
tab_upload, tab_history, tab_insight = st.tabs(["📤 Upload & Verify", "🗄️ Database", "🤖 AI Analytics"])

# ── State init ────────────────────────────────────────────────────────────────
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = []
if "current_file" not in st.session_state:
    st.session_state.current_file = ""

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: UPLOAD & EKSTRAK
# ══════════════════════════════════════════════════════════════════════════════
# ── Main Content Area ────────────────────────────────────────────────────────
with tab_upload:
    uploaded = st.file_uploader("Upload Laporan Keuangan (Scan/Foto)", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed")
    
    if uploaded:
        col_img, col_proc = st.columns([1, 1], gap="medium")
        with col_img:
            st.image(uploaded, use_container_width=True)
            if st.button("🔍 Run AI Extraction", type="primary", use_container_width=True):
                with st.spinner("AI is analyzing the scan..."):
                    try:
                        res = ocr_dengan_openai(api_key, uploaded.read())
                        st.session_state.extracted_data = res.get("transaksi", [])
                        st.session_state.metadata = {
                            "date": res.get("report_date", "Unknown"),
                            "guests": res.get("guest_count", 0)
                        }
                    except Exception as e:
                        st.error(f"Error: {e}")

        with col_proc:
            if st.session_state.extracted_data:
                # Premium Header for Verification
                st.markdown(f"""
                <div class="view-title">Data Verification <span class="badge-pending">Pending Review</span></div>
                <div class="view-desc">Review and correct the data extracted from the scan before final submission.</div>
                
                <div class="stats-container">
                    <div class="stats-card">
                        <div class="stats-label">Report Date</div>
                        <div class="stats-val">{st.session_state.metadata.get('date')}</div>
                    </div>
                    <div class="stats-card">
                        <div class="stats-label">Guest Count</div>
                        <div class="stats-val">{st.session_state.metadata.get('guests')} Guests</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Editable Table
                df_verify = pd.DataFrame(st.session_state.extracted_data)
                # Ensure all required columns exist
                for c in ["income", "expense_debit", "expense_cash"]:
                    if c not in df_verify.columns: df_verify[c] = 0.0

                edited_df = st.data_editor(
                    df_verify[["date", "shift", "description", "income", "expense_debit", "expense_cash"]],
                    use_container_width=True,
                    num_rows="dynamic",
                    column_config={
                        "date": st.column_config.TextColumn("Date"),
                        "shift": st.column_config.SelectboxColumn("Shift", options=["Pagi", "Malam"]),
                        "description": st.column_config.TextColumn("Description"),
                        "income": st.column_config.NumberColumn("Income"),
                        "expense_debit": st.column_config.NumberColumn("Expense (Debit)"),
                        "expense_cash": st.column_config.NumberColumn("Expense (Cash)"),
                    },
                    hide_index=True
                )

                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Approve & Sync Data", use_container_width=True, type="primary"):
                    save_transaksi(edited_df.to_dict(orient="records"), st.session_state.metadata.get('guests', 0))
                    st.success("Successfully approved and saved to database!")
                    st.balloons()
                    st.session_state.extracted_data = []

with tab_history:
    st.markdown("### 🗄️ Master Database")
    df_history = load_transaksi()
    if not df_history.empty:
        total_inc = df_history["income"].sum()
        total_exp = df_history["expense_debit"].sum() + df_history["expense_cash"].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Items", len(df_history))
        c2.metric("Total Income", f"Rp {total_inc:,.0f}")
        c3.metric("Total Expense", f"Rp {total_exp:,.0f}")
        c4.metric("Net Cash", f"Rp {total_inc - total_exp:,.0f}")
        
        st.divider()
        st.dataframe(df_history.drop(columns=["id"]), use_container_width=True, height=500)
    else:
        st.info("Database is empty.")

with tab_insight:
    st.markdown("### 🤖 AI Insight Analysis")
    df_ai = load_transaksi()
    if df_ai.empty:
        st.info("Upload and save some data first to generate insights.")
    else:
        if st.button("✨ Generate Full Analysis", type="primary"):
            with st.spinner("Analyzing all historical data..."):
                insight_res = generate_insight(api_key, df_ai)
                st.markdown(insight_res)

# ── Footer ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; color:#94a3b8; font-size:12px; margin-top:50px; padding-bottom:20px;">
    &copy; 2026 Hotel Royal Inn Financial System | Powered by Advanced AI
</div>
""", unsafe_allow_html=True)
