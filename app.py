import streamlit as st
import os
import shutil
import zipfile
import pandas as pd
import logic

# ページ設定
st.set_page_config(page_title="電波天文 解析ランチャー", layout="centered")

# GitHubなど削除
hide_streamlit_style = """
            <style>
            /* 右上のデプロイボタンなどを消す */
            .stAppDeployButton {display:none;}
            /* 右上のハンバーガーメニューを消す */
            #MainMenu {visibility: hidden;}
            /* フッター（Made with Streamlit）を消す */
            footer {visibility: hidden;}
            /* ヘッダーの装飾バーを消す */
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# タイトル
st.title("🚀 解析ツール")
st.write("実行したい機能を選択してください。")

# ==========================================
# 0. データのアップロード
# ==========================================
st.sidebar.header("📁 データ準備")
st.sidebar.write("ZIPファイルをアップロードしてください。")

TEMP_DIR = "temp_upload"
uploaded_file = st.sidebar.file_uploader("観測データのZIPファイル", type="zip")

if "target_path" not in st.session_state:
    st.session_state.target_path = None
if "folder_name" not in st.session_state:
    st.session_state.folder_name = ""

if uploaded_file is not None:
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
        zip_ref.extractall(TEMP_DIR)
    
    # フォルダ自動検出ロジック (改良版)
    found_path = None
    found_name = ""
    has_csv = False
    has_tra = False

    for root, dirs, files in os.walk(TEMP_DIR):
        # 余計なフォルダは無視
        if "__MACOSX" in root: continue

        # CSVがあるか？
        if any(f.endswith(".csv") for f in files) and "avg" not in root:
            found_path = root
            has_csv = True
        
        # TRAがあるか？ (CSVが無い場合のみ優先度を下げるためチェック)
        if any(f.endswith(".tra") for f in files):
            if not found_path: # CSVが見つかっていない場合のみ候補にする
                found_path = root
            has_tra = True

        if found_path:
            found_name = os.path.basename(root)
            if found_name == "temp_upload":
                found_name = "ルートフォルダ"
            # CSVが見つかったら即確定
            if has_csv:
                break
    
    if found_path:
        st.session_state.target_path = found_path
        st.session_state.folder_name = found_name
        
        if has_csv:
            st.sidebar.success(f"✅ CSV検出: {found_name}")
        elif has_tra:
            st.sidebar.warning(f"⚠️ TRA検出: {found_name}\n(先に変換を行ってください)")
    else:
        st.session_state.target_path = None
        st.sidebar.error("⚠️ ファイル(.csv または .tra)が見つかりません")
else:
    st.session_state.target_path = None
    st.session_state.folder_name = ""

st.sidebar.markdown("---")
st.sidebar.info("表データ(tables): " + ("OK" if os.path.exists("./tables/θ_o表.csv") else "未検出"))


# ==========================================
# メイン画面：機能選択
# ==========================================

# 選択肢の定義
OPTIONS = {
    "select": "--- 実行するプログラムを選択 ---",
    "tra_csv": "0. データ形式変換 (.tra → .csv)",
    "avg": "1. 平均化処理 (average_once.py)",
    "vel_on": "2. 回転速度解析 [BGあり] (velocity_on.py)",
    "vel_off": "3. 回転速度解析 [BGなし] (velocity_off.py)",
}

selected_key = st.selectbox(
    "メニュー",
    options=list(OPTIONS.keys()),
    format_func=lambda x: OPTIONS[x]
)

st.markdown("---")

# データ未アップロード時の警告
if selected_key != "select" and not st.session_state.target_path:
    st.warning("👈 先にZIPファイルをアップロードしてください。")

# ------------------------------------
# 0. TRA -> CSV 変換
# ------------------------------------
elif selected_key == "tra_csv":
    st.subheader("🔄 .tra → .csv 変換")
    st.write("観測データ(.tra)を解析用(.csv)に変換します。")
    st.text_input("対象フォルダ", value=st.session_state.folder_name, disabled=True)

    if st.button("変換実行", type="primary"):
        with st.spinner("変換中..."):
            count, logs = logic.convert_tra_to_csv(st.session_state.target_path)
        
        if logs:
            with st.expander("エラーログ"):
                for l in logs: st.write(l)
        
        if count > 0:
            st.success(f"完了！ {count} 個のファイルを変換しました。")
            st.info("続いて「1. 平均化処理」を行ってください。")
        else:
            st.error(".tra ファイルが見つかりませんでした。")

# ------------------------------------
# 1. 平均化処理
# ------------------------------------
elif selected_key == "avg":
    st.subheader("📊 平均スペクトルの作成")
    st.write("各銀経のデータを平均化して `avg` フォルダを作成します。")

    with st.form("avg_form"):
        st.text_input("対象フォルダ", value=st.session_state.folder_name, disabled=True)
        c1, c2 = st.columns(2)
        max_angle = c1.number_input("最後の銀経", value=60, step=5)
        step_angle = c2.number_input("刻み幅", value=5, step=1)
        submitted = st.form_submit_button("実行", type="primary")

    if submitted:
        with st.spinner("処理中..."):
            count, out_dir, logs = logic.process_average_once(
                TEMP_DIR, st.session_state.target_path, max_angle, step_angle
            )
        if logs:
            with st.expander("詳細ログ"):
                for l in logs: st.write(l)
        if count > 0:
            st.success(f"完了！ {count} ファイル作成")
        else:
            st.error("作成失敗（CSVファイルはありますか？先に変換が必要かもしれません）")

# ------------------------------------
# 2. 回転速度 (BGあり)
# ------------------------------------
elif selected_key == "vel_on":
    st.subheader("🌌 回転速度解析 (BG引き算あり)")
    
    avg_path = os.path.join(st.session_state.target_path, "avg")
    if not os.path.exists(avg_path):
        st.error("⚠️ `avg` フォルダがありません。「平均化処理」を先に実行してください。")
    else:
        with st.form("vel_on_form"):
            st.text_input("対象フォルダ", value=st.session_state.folder_name, disabled=True)
            c1, c2 = st.columns(2)
            max_angle = c1.number_input("最後の銀経", value=60, step=5)
            step_angle = c2.number_input("刻み幅", value=5, step=1)
            submitted = st.form_submit_button("実行", type="primary")

        if submitted:
            with st.spinner("解析中..."):
                df, msg = logic.calculate_velocity_on(
                    st.session_state.target_path, max_angle, step_angle
                )
            if df is None:
                st.error(msg)
            else:
                st.success("解析完了！")
                st.line_chart(df.set_index("中心距離[光年]")["回転速度[km/s]"])
                csv_data = df.to_csv(index=False, encoding="shift_jis")
                st.download_button("CSVダウンロード", csv_data, f"velocity_ON_{st.session_state.folder_name}.csv", "text/csv")

# ------------------------------------
# 3. 回転速度 (BGなし)
# ------------------------------------
elif selected_key == "vel_off":
    st.subheader("💫 回転速度解析 (ONデータのみ)")
    
    avg_path = os.path.join(st.session_state.target_path, "avg")
    if not os.path.exists(avg_path):
        st.error("⚠️ `avg` フォルダがありません。「平均化処理」を先に実行してください。")
    else:
        with st.form("vel_off_form"):
            st.text_input("対象フォルダ", value=st.session_state.folder_name, disabled=True)
            c1, c2 = st.columns(2)
            max_angle = c1.number_input("最後の銀経", value=60, step=5)
            step_angle = c2.number_input("刻み幅", value=5, step=1)
            submitted = st.form_submit_button("実行", type="primary")

        if submitted:
            with st.spinner("解析中..."):
                df, msg = logic.calculate_velocity_off(
                    st.session_state.target_path, max_angle, step_angle
                )
            if df is None:
                st.error(msg)
            else:
                st.success("解析完了！")
                st.line_chart(df.set_index("中心距離[光年]")["回転速度[km/s]"])
                csv_data = df.to_csv(index=False, encoding="shift_jis")
                st.download_button("CSVダウンロード", csv_data, f"velocity_OFF_{st.session_state.folder_name}.csv", "text/csv")

else:
    st.info("👆 上のボックスから機能を選択してください。")

