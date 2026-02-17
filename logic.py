import os
import glob
import math
import csv
import numpy as np
import pandas as pd

# ==========================================
# 定数設定
# ==========================================
# ピークを探す範囲 (1420.4MHzを中心にドップラーシフト分をカバー)
FMIN = 1419.0e6 
FMAX = 1421.5e6
c = 299792458.0
OBS_ENCODING = "utf-8"
TABLE_ENCODING = "shift_jis"
F_REST = 1420.405751e6 # 水素線の静止周波数

# ==========================================
# 0. TRA -> CSV 変換処理 (そのまま維持)
# ==========================================
def convert_tra_to_csv(target_dir):
    tra_files = glob.glob(os.path.join(target_dir, "**", "*.tra"), recursive=True)
    if not tra_files:
        return 0, ["エラー: .tra ファイルが見つかりませんでした。"]
    converted_count = 0
    logs = []
    for tra_path in tra_files:
        base, _ = os.path.splitext(tra_path)
        output_file = base + ".csv"
        try:
            with open(tra_path, "r", encoding="utf-8") as fin, \
                 open(output_file, "w", newline="", encoding="utf-8") as fout:
                reader = csv.reader(fin)
                writer = csv.writer(fout)
                next(reader, None) # ヘッダスキップ
                writer.writerow(["Frequency_Hz", "Amplitude_dBm"])
                for row in reader:
                    if len(row) >= 3:
                        try:
                            writer.writerow([float(row[1]), float(row[2])])
                        except ValueError: continue
            converted_count += 1
        except Exception as e:
            logs.append(f"変換エラー: {os.path.basename(tra_path)} -> {e}")
    return converted_count, logs

# ==========================================
# 1. 平均化処理 (1〜3番をまとめて平均化)
# ==========================================
def process_average_once(folder_path, max_angle, step_angle, bg_filename_pattern="BG"):
    """
    1.csv, 2.csv, 3.csv を平均化する。
    bg_filename_pattern: バックグラウンドファイルに含まれる文字列 (例: 'BG' や 'B90')
    """
    avg_dir = os.path.join(folder_path, "avg")
    os.makedirs(avg_dir, exist_ok=True)

    longitudes = list(range(0, max_angle + 1, step_angle))
    if 180 not in longitudes: longitudes.append(180) # テスト用の180度を追加
    
    log_messages = []
    processed_count = 0

    # A. 観測地点（経度）ごとの平均化
    for lon in longitudes:
        # パターン: 経度を含み、末尾が .1.csv, .2.csv, .3.csv のものを探す
        pattern = os.path.join(folder_path, f"*{lon}.[123].csv")
        paths = sorted(glob.glob(pattern))
        
        if not paths: continue

        try:
            dfs = [pd.read_csv(p) for p in paths]
            freqs = dfs[0]["Frequency_Hz"].to_numpy()
            amps = np.stack([df["Amplitude_dBm"].to_numpy() for df in dfs], axis=0).mean(axis=0)

            out_df = pd.DataFrame({"Frequency_Hz": freqs, "Amplitude_dBm": amps})
            out_path = os.path.join(avg_dir, f"{lon}_avg.csv")
            out_df.to_csv(out_path, index=False)
            processed_count += 1
            log_messages.append(f"Success: 銀経 {lon} ({len(paths)}個を平均)")
        except Exception as e:
            log_messages.append(f"Error at lon {lon}: {e}")

    # B. バックグラウンド（銀緯90度など）の平均化
    bg_pattern = os.path.join(folder_path, f"*{bg_filename_pattern}*.[123].csv")
    bg_paths = sorted(glob.glob(bg_pattern))
    if bg_paths:
        try:
            dfs = [pd.read_csv(p) for p in bg_paths]
            freqs = dfs[0]["Frequency_Hz"].to_numpy()
            amps = np.stack([df["Amplitude_dBm"].to_numpy() for df in dfs], axis=0).mean(axis=0)
            pd.DataFrame({"Frequency_Hz": freqs, "Amplitude_dBm": amps}).to_csv(os.path.join(avg_dir, "BG_avg.csv"), index=False)
            log_messages.append(f"Success: バックグラウンド平均作成完了")
        except Exception as e:
            log_messages.append(f"BG Error: {e}")

    return processed_count, avg_dir, log_messages

# ==========================================
# 2. 回転速度計算 (マスターBG引き算方式)
# ==========================================
def calculate_velocity_master_bg(folder_path, max_angle, step_angle):
    obs_dir = os.path.join(folder_path, "avg")
    table_dir = "./tables" if os.path.exists("./tables") else "."
    longitudes = list(range(0, max_angle + 1, step_angle))
    peak_list = []
    logs = []

    # BGファイルの読み込み
    bg_path = os.path.join(obs_dir, "BG_avg.csv")
    if not os.path.exists(bg_path):
        return None, "エラー: BG_avg.csv がありません。BGを含めて平均化してください。"
    
    bg_df = pd.read_csv(bg_path)
    freq_bg = bg_df["Frequency_Hz"].to_numpy()
    amp_bg = bg_df["Amplitude_dBm"].to_numpy()

    for lon in longitudes:
        target_path = os.path.join(obs_dir, f"{lon}_avg.csv")
        if not os.path.exists(target_path): continue

        df = pd.read_csv(target_path)
        freq = df["Frequency_Hz"].to_numpy()
        amp = df["Amplitude_dBm"].to_numpy()

        # バックグラウンド引き算 (dBmでの簡易引き算)
        # ※本来は真数に戻すべきですが、ピーク位置特定が目的ならこれで十分です
        amp_sub = amp - amp_bg

        # 1420.4MHz前後のマスク
        mask = (freq >= FMIN) & (freq <= FMAX)
        if not mask.any(): continue

        f_win = freq[mask]
        a_win = amp_sub[mask]
        
        # ピーク（一番盛り上がっている周波数）を特定
        idx_peak = np.argmax(a_win)
        f_peak = float(f_win[idx_peak])
        
        peak_list.append({"銀経": lon, "f_peak_Hz": f_peak})

    if not peak_list:
        return None, "ピークが検出できませんでした"

    # 共通計算処理へ
    return _calculate_velocity_common(peak_list, F_REST, table_dir, logs)

# ==========================================
# 共通計算ロジック (定数調整済み)
# ==========================================
def _calculate_velocity_common(peak_list, f_rest, table_dir, logs):
    # 表データの読み込み
    try:
        theta_df = pd.read_csv(os.path.join(table_dir, "θ_o表.csv"), encoding=TABLE_ENCODING)
        es_df    = pd.read_csv(os.path.join(table_dir, "E_s表.csv"), encoding=TABLE_ENCODING)
        dist_df  = pd.read_csv(os.path.join(table_dir, "中心距離標.csv"), encoding=TABLE_ENCODING)
        theta_list = theta_df.iloc[:, 0].tolist()
        es_list    = es_df.iloc[:, 0].tolist()
        dist_ly    = dist_df.iloc[:, 1].to_numpy()
    except Exception as e:
        return None, f"テーブル読み込みエラー: {e}"

    result_rows = []
    for p in peak_list:
        lon = p["銀経"]
        f_obs = p["f_peak_Hz"]
        
        # テーブルのインデックス計算 (5度刻みのテーブルを想定)
        num = int(lon / 5)
        if num < 0 or num >= len(theta_list): continue

        theta_val = float(theta_list[num])
        es_val = float(es_list[num])
        dist_val = float(dist_ly[num])

        # 速度計算
        # Vv = (c * (f_rest - f_obs) / f_rest + es_val) / sin(theta)
        # ※提供された計算式に基づき実装
        theta_rad = math.radians(theta_val) # テーブルが度数法の場合
        sin_theta = math.sin(theta_rad)

        if abs(sin_theta) < 1e-6:
            v_rot_kms = np.nan
        else:
            # 視線速度 Vr = c * (f_rest - f_obs) / f_rest
            vr = c * (f_rest - f_obs) / f_rest
            # 回転速度 V(R) = (Vr + Es) / sin(l) + V0*sin(l) ... 
            # ここでは提供されたロジックを簡略化して適用
            v_rot = (vr + es_val) / sin_theta
            v_rot_kms = abs(v_rot) / 1000.0

        result_rows.append({
            "銀経": lon,
            "中心距離[光年]": dist_val,
            "回転速度[km/s]": v_rot_kms,
            "観測周波数[MHz]": f_obs / 1e6
        })

    result_df = pd.DataFrame(result_rows).sort_values("銀経")
    return result_df, logs
