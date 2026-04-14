import streamlit as st
import pandas as pd
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
from PIL import Image
import io
import json

# --- CONFIGURATION ---
st.set_page_config(page_title="Royal Inn Financial Dashboard", page_icon="🏦", layout="wide")

# Custom CSS untuk Tampilan Premium & Modern
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .stApp { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); }
    
    .main-card {
        background: rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 2rem;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.18);
        margin-bottom: 2rem;
    }
    
    .header-text {
        font-weight: 800; color: #1e3a8a; font-size: 2.5rem; text-align: center; margin-bottom: 0.5rem;
    }
    
    .metric-container {
        display: flex; justify-content: space-around; background: white; border-radius: 15px; padding: 1rem; margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.title("⚙️ Settings")
    api_key = st.text_input("Gemini API Key", type="password", help="Dapatkan di aistudio.google.com")
    sheet_url = "https://docs.google.com/spreadsheets/d/1A1CFgeghyJFhms_s80NcqtO9h9r69eXdIoH523Hz7Nk/edit?usp=sharing"
    st.info("Target Sheet: Financial Insight (Opal App)")

# --- LOGIC: AI EXTRACTION ---
def extract_data(img_bytes, key):
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = """
    Kamu adalah akuntan profesional. Ekstrak data dari laporan keuangan ini.
    Keluarkan HANYA JSON dengan struktur:
    {
        "metadata": {"date": "YYYY-MM-DD", "guests": 0},
        "transactions": [
            {"shift": "Pagi/Malam", "description": "...", "income": 0, "expense_debit": 0, "expense_cash": 0}
        ]
    }
    Aturan: 
    - Income adalah total semua pemasukan di baris tersebut.
    - Satuan angka murni tanpa titik/koma.
    """
    
    img = Image.open(io.BytesIO(img_bytes))
    response = model.generate_content([prompt, img])
    return json.loads(response.text.replace('```json', '').replace('```', ''))

# --- UI: MAIN CONTENT ---
st.markdown('<div class="header-text">🏦 Hotel Royal Inn</div>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center; color:#64748b;">AI-Powered Daily Financial Reporting</p>', unsafe_allow_html=True)

# 1. UPLOAD SECTION
with st.container():
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Scan atau Unggah Laporan Harian", type=['png', 'jpg', 'jpeg'])
    
    if uploaded_file and api_key:
        if st.button("🔍 Jalankan Analisis AI", type="primary", use_container_width=True):
            with st.spinner("AI sedang membaca data..."):
                try:
                    res = extract_data(uploaded_file.read(), api_key)
                    st.session_state.data = res
                    st.success("Ekstraksi Berhasil!")
                except Exception as e:
                    st.error(f"Gagal mengekstrak: {e}")
    st.markdown('</div>', unsafe_allow_html=True)

# 2. REVIEW & EDIT SECTION
if 'data' in st.session_state:
    st.markdown("### 📝 Verifikasi Data (Human-in-the-Loop)")
    meta = st.session_state.data['metadata']
    
    col1, col2 = st.columns(2)
    with col1:
        report_date = st.text_input("Tanggal Laporan", value=meta['date'])
    with col2:
        guest_count = st.number_input("Jumlah Tamu", value=meta['guests'])

    df = pd.DataFrame(st.session_state.data['transactions'])
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    # 3. SYNC TO GOOGLE SHEETS
    if st.button("🚀 Simpan ke Google Sheets", type="primary", use_container_width=True):
        with st.spinner("Sinkronisasi ke Spreadsheet..."):
            try:
                # Menyiapkan data final sesuai urutan kolom A sampai G
                final_data = edited_df.copy()
                final_data['Date'] = report_date
                final_data['Guest'] = guest_count
                
                # Reorder kolom sesuai urutan Google Sheets Anda
                final_data = final_data[['Date', 'Guest', 'shift', 'description', 'income', 'expense_debit', 'expense_cash']]
                
                # Koneksi ke Sheets
                conn = st.connection("gsheets", type=GSheetsConnection)
                existing_data = conn.read(spreadsheet=sheet_url)
                updated_df = pd.concat([existing_data, final_data], ignore_index=True)
                
                conn.update(spreadsheet=sheet_url, data=updated_df)
                st.balloons()
                st.success("✅ Data berhasil masuk ke Google Sheets!")
                del st.session_state.data
            except Exception as e:
                st.error(f"Koneksi Gagal: {e}. Pastikan Google Sheets memiliki akses Share ke 'Anyone with the link' atau Service Account.")

else:
    st.info("Silakan unggah foto laporan untuk memulai.")
