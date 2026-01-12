import os
import glob
import math
import csv
import numpy as np
import pandas as pd
import streamlit as st

# ==========================================
# 定数設定
# ==========================================
FMIN = 1405e6
FMAX = 1420e6
THETA_IS_DEGREE = False
c = 299792458.0
OBS_ENCODING = "utf-8"
TABLE_ENCODING = "shift_jis"
F_REST_FALLBACK = 1420.40575177e6

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

def load_table_data(table_dir):
    """表データを読み込んでリストを返す"""
    try:
        theta_df = pd.read_csv(os.path.join(table_dir, "θ_o表.csv"), encoding=TABLE_ENCODING)
        es_df    = pd.read_csv(os.path.join(table_dir, "E_s表.csv"), encoding=TABLE_ENCODING)
        dist_df  = pd.read_csv(os.path.join(table_dir, "中心距離標.csv"), encoding=TABLE_ENCODING)
        
        theta_list = theta_df.iloc[:, 0].tolist()
        es_list    = es_df.iloc[:, 0].tolist()
        dist_ly    = dist_df.iloc[:, 1].to_numpy()
        return theta_list, es_list, dist_ly
    except FileNotFoundError:
        return None, None, None

# ==========================================
# 0. TRA -> CSV 変換処理 (新規追加)
# ==========================================
def convert_tra_to_csv(target_dir):
    """
    指定フォルダ(およびサブフォルダ)内の .tra ファイルを全て .csv に変換する
    """
    # 再帰的に .tra を探す
    tra_files = glob.glob(os.path.join(target_dir, "**", "*.tra"), recursive=True)
    
    if not tra_files:
        return 0, ["エラー: .tra ファイルが見つかりませんでした。"]

    converted_count = 0
    logs = []

    for tra_path in tra_files:
        # 拡張子を変えて出力パスを作成 (.tra -> .csv)
        base, _ = os.path.splitext(tra_path)
        output_file = base + ".csv"

        try:
            with open(tra_path, "r", encoding="utf-8") as fin, \
                 open(output_file, "w", newline="", encoding="utf-8") as fout:
                
                reader = csv.reader(fin)
                writer = csv.writer(fout)
                
                # ヘッダスキップ (1行目)
                next(reader, None)
                
                # 新しいヘッダを書き込み
                writer.writerow(["Frequency_Hz", "Amplitude_dBm"])

                for row in reader:
                    # データ行のみ処理 (Frequency, Amplitude があるか確認)
                    if len(row) >= 3:
                        try:
                            freq = float(row[1])
                            amp = float(row[2])
                            writer.writerow([freq, amp])
                        except ValueError:
                            continue
            converted_count += 1
        except Exception as e:
            logs.append(f"変換エラー: {os.path.basename(tra_path)} -> {e}")

    return converted_count, logs

# ==========================================
# 1. 平均化処理
# ==========================================
def process_average_once(root_dir, folder_path, max_angle, step_angle):
    avg_dir = os.path.join(folder_path, "avg")
    os.makedirs(avg_dir, exist_ok=True)

    longitudes = list(range(0, max_angle + 1, step_angle))
    log_messages = []
    processed_count = 0

    if not os.path.exists(folder_path):
        return 0, avg_dir, ["エラー: データフォルダが見つかりません。"]

    for lon in longitudes:
        for suffix in ["", "B"]: 
            pattern = os.path.join(folder_path, f"{lon}{suffix}.*.csv")
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
# 2. 回転速度計算 (Velocity ON / BGあり)
# ==========================================
def calculate_velocity_on(folder_path, max_angle, step_angle):
    obs_dir = os.path.join(folder_path, "avg")
    table_dir = "./tables" if os.path.exists("./tables") else "."
    longitudes = list(range(0, max_angle + 1, step_angle))
    peak_list = []
    logs = []

    if not os.path.exists(obs_dir):
        return None, f"エラー: {obs_dir} が見つかりません。「平均化」を実行してください。"

    # 1. ピーク検出
    for lon in longitudes:
        freq_on, amp_on = load_and_average_spectra(lon, "B0", obs_dir)
        freq_bg, amp_bg = load_and_average_spectra(lon, "B5", obs_dir)

        if freq_on is None or freq_bg is None:
            logs.append(f"銀経 {lon}°: データ不足")
            continue
        if not np.allclose(freq_on, freq_bg):
            logs.append(f"銀経 {lon}°: 周波数軸不一致")
            continue

        freq = freq_on
        amp_sub = amp_on - amp_bg 
        mask = (freq >= FMIN) & (freq <= FMAX)
        if not mask.any(): continue

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
        f_rest = F_REST_FALLBACK
        logs.append("WARN: 銀経0°なし -> f_rest暫定値使用")
    else:
        f_rest = sum(f_ref_candidates) / len(f_ref_candidates)

    return _calculate_velocity_common(peak_list, f_rest, table_dir, logs)

# ==========================================
# 3. 回転速度計算 (Velocity OFF / BGなし)
# ==========================================
def calculate_velocity_off(folder_path, max_angle, step_angle):
    obs_dir = os.path.join(folder_path, "avg")
    table_dir = "./tables" if os.path.exists("./tables") else "."
    longitudes = list(range(0, max_angle + 1, step_angle))
    peak_list = []
    logs = []

    if not os.path.exists(obs_dir):
        return None, f"エラー: {obs_dir} が見つかりません。「平均化」を実行してください。"

    for lon in longitudes:
        # ONだけ読む
        freq, amp = load_and_average_spectra(lon, "B0", obs_dir)
        if freq is None:
            continue

        mask = (freq >= FMIN) & (freq <= FMAX)
        if not mask.any(): continue

        freq_win = freq[mask]
        amp_win = amp[mask]
        
        # 簡易ベースライン補正（中央値を引く）
        amp_win2 = amp_win - np.median(amp_win)
        
        idx_peak = int(np.argmax(amp_win2))
        f_peak = float(freq_win[idx_peak])
        peak_list.append({"銀経": lon, "f_peak_Hz": f_peak})

    if not peak_list:
        return None, "ピークが見つかりませんでした"

    # f_rest 決定
    f_ref_candidates = [p["f_peak_Hz"] for p in peak_list if p["銀経"] == 0]
    if not f_ref_candidates:
        f_rest = F_REST_FALLBACK
        logs.append("WARN: 銀経0°なし -> f_rest暫定値使用")
    else:
        f_rest = float(sum(f_ref_candidates) / len(f_ref_candidates))

    return _calculate_velocity_common(peak_list, f_rest, table_dir, logs)

# ==========================================
# 共通計算ロジック
# ==========================================
def _calculate_velocity_common(peak_list, f_rest, table_dir, logs):
    theta_list, es_list, dist_ly = load_table_data(table_dir)
    if theta_list is None:
        return None, "エラー: 表ファイルが見つかりません。tablesフォルダを確認してください。"

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
