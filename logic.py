import os
import glob
import math
import numpy as np
import pandas as pd
import streamlit as st

# 定数
FMIN = 1405e6
FMAX = 1420e6
THETA_IS_DEGREE = False
c = 299792458.0
OBS_ENCODING = "utf-8"
TABLE_ENCODING = "shift_jis"

# ==========================================
# 共通関数
# ==========================================
def load_and_average_spectra(lon, band_str, obs_dir):
    """CSVを読んで周波数と強度を返す"""
    if band_str == "B0":
        fname = f"{lon}_avg.csv"
    elif band_str == "B5":
        fname = f"{lon}B_avg.csv"
    else:
        return None, None

    path = os.path.join(obs_dir, fname)
    if not os.path.exists(path):
        return None, None

    try:
        df = pd.read_csv(path, encoding=OBS_ENCODING)
        freq = df["Frequency_Hz"].to_numpy()
        amp_mean = df["Amplitude_dBm"].to_numpy()
        return freq, amp_mean
    except Exception:
        return None, None

# ==========================================
# 1. 平均化処理
# ==========================================
def process_average_once(data_dir, folder_name, max_angle, step_angle):
    """
    data_dir: 観測データフォルダが入っている親フォルダ (例: ./temp_data)
    folder_name: その中の具体的な日付フォルダ名 (例: 11月19日)
    """
    target_dir = os.path.join(data_dir, folder_name)
    avg_dir = os.path.join(target_dir, "avg")
    os.makedirs(avg_dir, exist_ok=True)

    longitudes = list(range(0, max_angle + 1, step_angle))
    log_messages = []
    processed_count = 0

    if not os.path.exists(target_dir):
        return 0, avg_dir, [f"エラー: {target_dir} が見つかりません。ZIPの中身を確認してください。"]

    for lon in longitudes:
        for suffix in ["", "B"]: 
            pattern = os.path.join(target_dir, f"{lon}{suffix}.*.csv")
            paths = glob.glob(pattern)
            
            if not paths:
                continue

            try:
                dfs = [pd.read_csv(p) for p in paths]
                freqs0 = dfs[0]["Frequency_Hz"].to_numpy()
                amps_stack = np.stack([df["Amplitude_dBm"].to_numpy() for df in dfs], axis=0)
                amps_mean = amps_stack.mean(axis=0)

                out_df = pd.DataFrame({
                    "Frequency_Hz": freqs0,
                    "Amplitude_dBm": amps_mean,
                })
                
                out_name = f"{lon}{suffix}_avg.csv"
                out_path = os.path.join(avg_dir, out_name)
                out_df.to_csv(out_path, index=False)
                processed_count += 1
            except Exception as e:
                log_messages.append(f"Error at lon {lon}{suffix}: {e}")

    return processed_count, avg_dir, log_messages

# ==========================================
# 2. 回転速度計算
# ==========================================
def calculate_velocity_on(data_dir, folder_name, max_angle, step_angle):
    # 観測データはアップロードされた一時フォルダを見る
    obs_dir = os.path.join(data_dir, folder_name, "avg")
    
    # ★重要: 表データはサーバー上の固定フォルダ(tables)を見る
    # もし無ければカレントディレクトリを見る
    table_dir = "./tables" if os.path.exists("./tables") else "."

    longitudes = list(range(0, max_angle + 1, step_angle))
    peak_list = []
    logs = []

    if not os.path.exists(obs_dir):
        return None, f"エラー: {obs_dir} が見つかりません。先に「平均化」を行ってください。"

    # 1. ピーク検出
    for lon in longitudes:
        freq_on, amp_on = load_and_average_spectra(lon, "B0", obs_dir)
        freq_bg, amp_bg = load_and_average_spectra(lon, "B5", obs_dir)

        if freq_on is None or freq_bg is None:
            logs.append(f"銀経 {lon}°: データ不足スキップ")
            continue

        if not np.allclose(freq_on, freq_bg):
            logs.append(f"銀経 {lon}°: 周波数軸不一致")
            continue

        freq = freq_on
        amp_sub = amp_on - amp_bg 

        mask = (freq >= FMIN) & (freq <= FMAX)
        if not mask.any():
            continue

        freq_win = freq[mask]
        amp_win = amp_sub[mask]
        
        idx_peak = np.argmax(amp_win)
        f_peak = float(freq_win[idx_peak])
        peak_list.append({"銀経": lon, "f_peak_Hz": f_peak})

    if not peak_list:
        return None, "ピークが検出できませんでした"

    # 2. f_rest
    f_ref_candidates = [p["f_peak_Hz"] for p in peak_list if p["銀経"] == 0]
    if not f_ref_candidates:
        f_rest = 14204058.0
        logs.append("WARN: 銀経0°なし -> f_rest暫定値使用")
    else:
        f_rest = sum(f_ref_candidates) / len(f_ref_candidates)

    # 3. 表データ読み込み
    try:
        theta_df = pd.read_csv(os.path.join(table_dir, "θ_o表.csv"), encoding=TABLE_ENCODING)
        es_df    = pd.read_csv(os.path.join(table_dir, "E_s表.csv"), encoding=TABLE_ENCODING)
        dist_df  = pd.read_csv(os.path.join(table_dir, "中心距離標.csv"), encoding=TABLE_ENCODING)
    except FileNotFoundError:
        return None, f"エラー: 表ファイルが見つかりません。GitHubの 'tables' フォルダを確認してください。"

    theta_list = theta_df.iloc[:, 0].tolist()
    es_list    = es_df.iloc[:, 0].tolist()
    dist_ly    = dist_df.iloc[:, 1].to_numpy()

    # 4. 速度計算
    result_rows = []
    for p in peak_list:
        lon = p["銀経"]
        f_obs = p["f_peak_Hz"]
        num = int(lon / 5)

        if num < 0 or num >= len(theta_list):
            continue

        theta_val = theta_list[num]
        es_val = es_list[num]
        dist_val = float(dist_ly[num])

        theta_rad = math.radians(theta_val) if THETA_IS_DEGREE else float(theta_val)
        sin_theta = math.sin(theta_rad)

        if abs(sin_theta) < 1e-6:
            Vv_abs_kms = np.nan
        else:
            abs_Es = abs(float(es_val))
            Vv = (c - (c - abs_Es) * (f_rest / f_obs)) / sin_theta
            Vv_abs_kms = abs(Vv) / 1000.0

        result_rows.append({
            "銀経": lon,
            "中心距離[光年]": dist_val,
            "回転速度[km/s]": Vv_abs_kms,
        })

    result_df = pd.DataFrame(result_rows).sort_values("銀経")
    return result_df, logs