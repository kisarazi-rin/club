import streamlit as st
import os
import shutil
import zipfile
import pandas as pd
import logic

# ページ設定
st.set_page_config(page_title="銀河回転曲線 解析ツール", layout="centered")

# スタイル調整（スマホ向けに余白を削り、ヘッダーを隠す）
hide_style = """
            <style>
            .stAppDeployButton {display:none;}
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            /* スマホでファイルアップローダーを見やすくする */
            .stFileUploader {padding-top: 1rem;}
            </style>
            """
st.markdown(hide_style, unsafe_allow_html=True)

st.title("🌌 銀河解析システム")

# セッション状態の初期化
if "target_path" not in st.session_state:
    st.session_state.target_path = None
if "folder_name" not in st.session_state:
    st.session_state.folder_name = ""

# ==========================================
# 1. データ準備セクション (メイン画面に配置)
# ==========================================
# ファイルが未アップロードなら開いた状態、アップロード済みなら閉じた状態にする
with st.expander("📁 Step 1: データのアップロード", expanded=(st.session_state.target_path is None)):
    st.write("観測データ（.csv または .tra）が入ったZIPファイルを上げてください。")
    
    TEMP_DIR = "temp_upload"
    uploaded_file = st.file_uploader("ZIPファイルを選択", type="zip")

    if uploaded_file is not None:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)
        
        with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
            zip_ref.extractall(TEMP_DIR)
        
        # フォルダ自動検出
        found_path = None
        has_csv = False
        has_tra = False

        for root, dirs, files in os.walk(TEMP_DIR):
            if "__MACOSX" in root: continue
            if any(f.endswith(".csv") for f in files) and "avg" not in root:
                found_path = root
                has_csv = True
                break
            if any(f.endswith(".tra") for f in files):
                found_path = root
                has_tra = True

        if found_path:
            st.session_state.target_path = found_path
            st.session_state.folder_name = os.path.basename(found_path)
            if has_csv:
                st.success(f"✅ CSV検出: {st.session_state.folder_name}")
            else:
                st.warning(f"⚠️ TRA検出: {st.session_state.folder_name} (変換が必要です)")
        else:
            st.error("⚠️ 有効なファイルが見つかりません。")

    # システム状態の表示
    table_status = "✅ OK" if os.path.exists("./tables/θ_o表.csv") else "❌ 未検出"
    st.info(f"表データ(tables): {table_status}")

# ==========================================
# 2. 機能選択セクション
# ==========================================
st.markdown("---")
if not st.session_state.target_path:
    st.info("👆 まずは上のボタンからデータをアップロードしてください。")
    st.stop()

st.subheader("🛠️ 解析メニュー")
OPTIONS = {
    "select": "--- 実行するプログラムを選択 ---",
    "tra_csv": "0. データ形式変換 (.tra → .csv)",
    "avg": "1. 3回平均化処理 (1〜3番を統合)",
    "vel_master": "2. 回転速度解析 [マスターBG方式]",
}

selected_key = st.selectbox("メニューを選択", options=list(OPTIONS.keys()), format_func=lambda x: OPTIONS[x])

st.markdown("---")

# ------------------------------------
# 0. TRA -> CSV 変換
# ------------------------------------
if selected_key == "tra_csv":
    st.write("📁 対象: ", st.session_state.folder_name)
    if st.button("変換実行", type="primary", use_container_width=True):
        with st.spinner("変換中..."):
            count, logs = logic.convert_tra_to_csv(st.session_state.target_path)
        if count > 0:
            st.success(f"完了！ {count} 個を変換しました。")
        else:
            st.error("変換対象が見つかりませんでした。")

# ------------------------------------
# 1. 平均化処理 (1〜3番を統合)
# ------------------------------------
elif selected_key == "avg":
    st.write("各地点の1.csv, 2.csv, 3.csvを平均化し、`avg`フォルダに保存します。")
    with st.form("avg_form"):
        c1, c2 = st.columns(2)
        max_angle = c1.number_input("最大銀経", value=180, step=10)
        step_angle = c2.number_input("刻み幅", value=10, step=1)
        bg_pattern = st.text_input("BG用キーワード", value="BG")
        submitted = st.form_submit_button("平均化を実行", type="primary", use_container_width=True)

    if submitted:
        with st.spinner("計算中..."):
            # 新しいlogic.pyの引数に合わせて呼び出し
            count, out_dir, logs = logic.process_average_once(
                st.session_state.target_path, max_angle, step_angle, bg_filename_pattern=bg_pattern
            )
        if count > 0:
            st.success(f"成功！ {count}地点の平均を作成しました。")
        with st.expander("ログを表示"):
            for l in logs: st.write(l)

# ------------------------------------
# 2. 回転速度解析 (マスターBG方式)
# ------------------------------------
elif selected_key == "vel_master":
    avg_path = os.path.join(st.session_state.target_path, "avg")
    if not os.path.exists(avg_path):
        st.error("⚠️ `avg` フォルダがありません。先に「1. 平均化」を行ってください。")
    else:
        with st.form("vel_form"):
            c1, c2 = st.columns(2)
            max_angle = c1.number_input("最大銀経", value=180, step=10)
            step_angle = c2.number_input("刻み幅", value=10, step=1)
            submitted = st.form_submit_button("解析実行", type="primary", use_container_width=True)

        if submitted:
            with st.spinner("銀河の回転を計算中..."):
                df, logs = logic.calculate_velocity_master_bg(
                    st.session_state.target_path, max_angle, step_angle
                )
            if df is not None:
                st.success("解析完了！")
                st.line_chart(df.set_index("中心距離[光年]")["回転速度[km/s]"])
                st.dataframe(df)
                csv_data = df.to_csv(index=False, encoding="shift_jis")
                st.download_button("結果CSVを保存", csv_data, "galaxy_velocity.csv", "text/csv", use_container_width=True)
            else:
                st.error("解析に失敗しました。データを確認してください。")
