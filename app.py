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
# データのアップロード処理
# ==========================================
# 一時保存用ディレクトリ
TEMP_DIR = "temp_upload"

# サイドバーでZIPアップロード
st.sidebar.header("1. データのアップロード")
uploaded_file = st.sidebar.file_uploader("観測データのZIPファイル", type="zip")

# データフォルダ名の特定
target_folder_name = ""

if uploaded_file is not None:
    # 毎回リセット（古いデータを消す）
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # ZIP解凍
    with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
        zip_ref.extractall(TEMP_DIR)
    
    st.sidebar.success("アップロード＆解凍完了！")
    
    # 解凍した中身からフォルダ名を探す（例: "11月19日"）
    subdirs = [d for d in os.listdir(TEMP_DIR) if os.path.isdir(os.path.join(TEMP_DIR, d))]
    
    # __MACOSX などのゴミフォルダを除外
    subdirs = [d for d in subdirs if not d.startswith("__")]
    
    if len(subdirs) > 0:
        target_folder_name = subdirs[0]
        st.sidebar.info(f"検出されたフォルダ: {target_folder_name}")
    else:
        st.sidebar.warning("ZIPの中にフォルダが見つかりませんでした。")
else:
    st.sidebar.warning("ZIPファイルをアップロードしてください。")


st.sidebar.markdown("---")
mode = st.sidebar.radio("機能を選択", ["ホーム", "2. 平均化 (Average)", "3. 回転速度解析 (Velocity ON)"])

# ==========================================
# ホーム画面
# ==========================================
if mode == "ホーム":
    st.markdown("""
    ### 使い方
    1. 自分のパソコンで、観測データのフォルダ（例: `11月19日`）を**右クリックして「ZIPファイルに圧縮」**します。
       - 中身は `0.1.csv`, `0B.1.csv` ... などが入っている状態にしてください。
    2. 左のサイドバーにあるアップローダーにドラッグ＆ドロップします。
    3. 解析メニューを選んで実行します。
    """)
    
    # サーバー上の表データの確認
    st.write("---")
    st.write("サーバー状態確認:")
    if os.path.exists("./tables/θ_o表.csv"):
        st.success("✅ 共通データ（表ファイル）は正常に読み込まれています。")
    else:
        st.error("❌ 共通データ（tablesフォルダ）が見つかりません。管理者に連絡してください。")

# ==========================================
# 2. 平均化
# ==========================================
elif mode == "2. 平均化 (Average)":
    st.header("平均スペクトルの作成")
    
    if not target_folder_name:
        st.error("先に左のサイドバーからZIPファイルをアップロードしてください。")
    else:
        with st.form("avg_form"):
            st.text_input("対象フォルダ (自動検出)", value=target_folder_name, disabled=True)
            col1, col2 = st.columns(2)
            max_angle = col1.number_input("最後の銀経", value=60, step=5)
            step_angle = col2.number_input("刻み幅", value=5, step=1)
            
            submitted = st.form_submit_button("実行")

        if submitted:
            with st.spinner("計算中..."):
                count, out_dir, logs = logic.process_average_once(TEMP_DIR, target_folder_name, max_angle, step_angle)
            
            if logs:
                with st.expander("ログ詳細"):
                    for l in logs:
                        st.write(l)
            
            if count > 0:
                st.success(f"完了！ {count} ファイルを作成しました。")
                # ZIPでダウンロードさせる機能をつけると親切かも（今回は省略）
            else:
                st.error("ファイルが作成されませんでした。")

# ==========================================
# 3. 回転速度解析
# ==========================================
elif mode == "3. 回転速度解析 (Velocity ON)":
    st.header("銀河回転速度の計算")
    
    if not target_folder_name:
        st.error("先に左のサイドバーからZIPファイルをアップロードしてください。")
    else:
        # 平均データがあるかチェック
        avg_check_path = os.path.join(TEMP_DIR, target_folder_name, "avg")
        if not os.path.exists(avg_check_path) or not os.listdir(avg_check_path):
            st.warning("⚠️ 平均データ(avg)が見当たりません。「2. 平均化」を先に実行したほうが良いかもしれません。")

        with st.form("vel_form"):
            st.text_input("対象フォルダ (自動検出)", value=target_folder_name, disabled=True)
            col1, col2 = st.columns(2)
            max_angle = col1.number_input("最後の銀経", value=60, step=5)
            step_angle = col2.number_input("刻み幅", value=5, step=1)
            
            submitted = st.form_submit_button("計算実行")

        if submitted:
            with st.spinner("解析中..."):
                df_result, msg = logic.calculate_velocity_on(TEMP_DIR, target_folder_name, max_angle, step_angle)
            
            if df_result is None:
                st.error(msg)
            else:
                st.success("計算完了！")
                st.dataframe(df_result)
                
                # グラフ
                st.line_chart(df_result.set_index("中心距離[光年]")["回転速度[km/s]"])
                
                # ダウンロード
                csv = df_result.to_csv(index=False, encoding="shift_jis")
                st.download_button(
                    label="CSVをダウンロード (Shift-JIS)",
                    data=csv,
                    file_name=f"velocity_{target_folder_name}.csv",
                    mime="text/csv"
                )