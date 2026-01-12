import streamlit as st
import os
import shutil
import zipfile
import pandas as pd
import logic

# ページ設定
st.set_page_config(page_title="電波天文 解析アプリ", layout="wide")

st.title("🌌 電波天文 解析ツール (班員用)")
st.write("自分の観測データ(フォルダごとZIPしたもの)をアップロードして解析できます。")

# ==========================================
# データのアップロードとフォルダ検出処理
# ==========================================
TEMP_DIR = "temp_upload"
st.sidebar.header("1. データのアップロード")
uploaded_file = st.sidebar.file_uploader("観測データのZIPファイル", type="zip")

# セッション状態にパスを保存（ページ切り替えで消えないように）
if "target_path" not in st.session_state:
    st.session_state.target_path = None
if "folder_name" not in st.session_state:
    st.session_state.folder_name = ""

if uploaded_file is not None:
    # 新しいファイルが来たらリセット
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # 解凍
    with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
        zip_ref.extractall(TEMP_DIR)
    
    st.sidebar.success("アップロード＆解凍完了！")
    
    # ---------------------------------------------------------
    # ★改良点: フォルダ名が何であれ、CSVが入っている場所を自動で探す
    # ---------------------------------------------------------
    found_path = None
    found_name = ""

    # temp_upload の中を全部探す
    for root, dirs, files in os.walk(TEMP_DIR):
        # CSVファイルが含まれているかチェック (ただし avg フォルダや MACOSX は除外)
        csv_files = [f for f in files if f.endswith(".csv")]
        if csv_files and "avg" not in root and "__MACOSX" not in root:
            found_path = root
            found_name = os.path.basename(root)
            # もしZIP直下にCSVがある場合、フォルダ名はZIPファイル名などにする手もあるが
            # ここでは root (temp_upload) そのものになる
            if found_name == "temp_upload":
                found_name = "ルートフォルダ(ZIP直下)"
            break
    
    if found_path:
        st.session_state.target_path = found_path
        st.session_state.folder_name = found_name
        st.sidebar.info(f"📁 検出されたデータ: **{found_name}**")
    else:
        st.session_state.target_path = None
        st.session_state.folder_name = ""
        st.sidebar.warning("⚠️ ZIP内にCSVファイルが見つかりませんでした。")
else:
    # ファイルが削除されたらクリア
    st.session_state.target_path = None
    st.session_state.folder_name = ""


st.sidebar.markdown("---")
mode = st.sidebar.radio("機能を選択", ["ホーム", "2. 平均化 (Average)", "3. 回転速度解析 (Velocity ON)"])

# ==========================================
# ホーム画面
# ==========================================
if mode == "ホーム":
    st.markdown("""
    ### 使い方
    1. 観測データのフォルダ（日付の名前など）をZIP圧縮します。
    2. 左のサイドバーにアップロードします。
       - **フォルダ名は自動で認識されます。** (例: `11月19日`, `12月05日` など何でもOK)
    3. 解析メニューを実行してください。
    """)
    
    st.write("---")
    if os.path.exists("./tables/θ_o表.csv"):
        st.success("✅ 共通データ（表ファイル）は準備OKです。")
    else:
        st.error("❌ 共通データ（tablesフォルダ）が見つかりません。")

# ==========================================
# 2. 平均化
# ==========================================
elif mode == "2. 平均化 (Average)":
    st.header("平均スペクトルの作成")
    
    target_path = st.session_state.target_path
    folder_name_display = st.session_state.folder_name

    if not target_path:
        st.error("先にZIPファイルをアップロードしてください。")
    else:
        with st.form("avg_form"):
            st.text_input("解析対象のフォルダ名 (自動検出)", value=folder_name_display, disabled=True)
            col1, col2 = st.columns(2)
            max_angle = col1.number_input("最後の銀経", value=60, step=5)
            step_angle = col2.number_input("刻み幅", value=5, step=1)
            
            submitted = st.form_submit_button("実行")

        if submitted:
            with st.spinner("計算中..."):
                # パスを直接渡す
                count, out_dir, logs = logic.process_average_once(TEMP_DIR, target_path, max_angle, step_angle)
            
            if logs:
                with st.expander("ログ詳細"):
                    for l in logs:
                        st.write(l)
            
            if count > 0:
                st.success(f"完了！ {count} ファイルを作成しました。")
            else:
                st.error("ファイルが作成されませんでした。")

# ==========================================
# 3. 回転速度解析
# ==========================================
elif mode == "3. 回転速度解析 (Velocity ON)":
    st.header("銀河回転速度の計算")
    
    target_path = st.session_state.target_path
    folder_name_display = st.session_state.folder_name

    if not target_path:
        st.error("先にZIPファイルをアップロードしてください。")
    else:
        # avgフォルダがあるか簡易チェック
        if not os.path.exists(os.path.join(target_path, "avg")):
            st.warning("⚠️ 平均データ(avg)が見当たりません。先に「2. 平均化」を実行してください。")

        with st.form("vel_form"):
            st.text_input("解析対象のフォルダ名 (自動検出)", value=folder_name_display, disabled=True)
            col1, col2 = st.columns(2)
            max_angle = col1.number_input("最後の銀経", value=60, step=5)
            step_angle = col2.number_input("刻み幅", value=5, step=1)
            
            submitted = st.form_submit_button("計算実行")

        if submitted:
            with st.spinner("解析中..."):
                # パスを直接渡す
                df_result, msg = logic.calculate_velocity_on(target_path, max_angle, step_angle)
            
            if df_result is None:
                st.error(msg)
            else:
                st.success("計算完了！")
                st.dataframe(df_result)
                
                st.line_chart(df_result.set_index("中心距離[光年]")["回転速度[km/s]"])
                
                # 出力ファイル名は検出したフォルダ名を使う
                safe_name = folder_name_display.replace(" ", "_")
                csv = df_result.to_csv(index=False, encoding="shift_jis")
                st.download_button(
                    label="CSVをダウンロード (Shift-JIS)",
                    data=csv,
                    file_name=f"velocity_{safe_name}.csv",
                    mime="text/csv"
                )
