import streamlit as st
import os, shutil, zipfile, glob
import logic

st.set_page_config(page_title="銀河解析", layout="centered")

if "target_path" not in st.session_state: st.session_state.target_path = None

st.title("🌌 銀河回転曲線 解析")

# 1. アップロード
with st.expander("📁 Step 1: データアップロード", expanded=(st.session_state.target_path is None)):
    uploaded_file = st.file_uploader("ZIPを選択", type="zip")
    if uploaded_file:
        TEMP_DIR = "temp_upload"
        if os.path.exists(TEMP_DIR): shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR)
        with zipfile.ZipFile(uploaded_file, 'r') as z: z.extractall(TEMP_DIR)
        
        # フォルダ検索（"avg"フォルダ内でも見つけるように修正）
        found = None
        for root, dirs, files in os.walk(TEMP_DIR):
            if any(f.endswith(".csv") for f in files):
                found = root
                break
        if found:
            st.session_state.target_path = found
            st.success(f"検出: {os.path.basename(found)}")
        else:
            st.error("CSVが見つかりません")

if not st.session_state.target_path: st.stop()

# 2. 平均化
st.subheader("🛠️ Step 2: 平均化処理")
if st.button("全データを平均化する（1~3番を統合）", use_container_width=True):
    count, out_dir, logs = logic.process_average_all(st.session_state.target_path)
    st.success(f"{count}地点の平均化完了")

# 3. 解析
st.subheader("📈 Step 3: 回転速度解析")
avg_dir = os.path.join(st.session_state.target_path, "avg")
if os.path.exists(avg_dir):
    avg_files = [os.path.basename(f) for f in glob.glob(os.path.join(avg_dir, "*.csv"))]
    
    with st.form("analysis_form"):
        # BGファイルの選択
        bg_file = st.selectbox("バックグラウンド(BG)ファイルを選択", options=avg_files)
        
        # 経度の自動範囲設定
        available_lons = logic.get_available_longitudes(st.session_state.target_path)
        min_val = min(available_lons) if available_lons else 0
        max_val = max(available_lons) if available_lons else 180
        
        c1, c2 = st.columns(2)
        sel_min = c1.number_input("最小銀経", value=min_val)
        sel_max = c2.number_input("最大銀経", value=max_val)
        
        if st.form_submit_button("解析実行", type="primary", use_container_width=True):
            df, logs = logic.calculate_velocity_with_selected_bg(st.session_state.target_path, bg_file, sel_min, sel_max)
            if df is not None:
                st.line_chart(df.set_index("中心距離[光年]")["回転速度[km/s]"])
                st.dataframe(df)
                st.download_button("結果保存", df.to_csv(index=False), "result.csv", use_container_width=True)
            else: st.error("解析失敗")
else:
    st.info("平均化を先に実行してください")
