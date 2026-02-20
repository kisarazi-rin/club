import os
import glob
import math
import numpy as np
import pandas as pd

# 定数
FMIN, FMAX = 1419.0e6, 1421.5e6
c = 299792458.0
F_REST = 1420.405751e6
TABLE_ENCODING = "shift_jis"

def get_available_longitudes(folder_path):
    files = glob.glob(os.path.join(folder_path, "*.csv"))
    lons = []
    for f in files:
        parts = os.path.basename(f).split('.')
        if len(parts) >= 3:
            try:
                lon = int(parts[-2])
                lons.append(lon)
            except ValueError: continue
    return sorted(list(set(lons)))

def process_average_all(folder_path):
    avg_dir = os.path.join(folder_path, "avg")
    os.makedirs(avg_dir, exist_ok=True)
    patterns = glob.glob(os.path.join(folder_path, "*.[123].csv"))
    prefixes = set([".".join(os.path.basename(p).split('.')[:-2]) for p in patterns])
    logs = []
    count = 0
    for pre in sorted(list(prefixes)):
        paths = [os.path.join(folder_path, f"{pre}.{i}.csv") for i in [1, 2, 3]]
        valid_paths = [p for p in paths if os.path.exists(p)]
        if not valid_paths: continue
        try:
            dfs = [pd.read_csv(p) for p in valid_paths]
            freqs = dfs[0]["Frequency_Hz"].to_numpy()
            amps = np.stack([df["Amplitude_dBm"].to_numpy() for df in dfs], axis=0).mean(axis=0)
            out_name = f"{pre.split('.')[-1]}_avg.csv"
            pd.DataFrame({"Frequency_Hz": freqs, "Amplitude_dBm": amps}).to_csv(os.path.join(avg_dir, out_name), index=False)
            count += 1
            logs.append(f"平均化完了: {out_name}")
        except Exception as e:
            logs.append(f"エラー {pre}: {e}")
    return count, avg_dir, logs

def calculate_velocity_with_selected_bg(folder_path, bg_file_name, min_lon, max_lon):
    avg_dir = os.path.join(folder_path, "avg")
    bg_path = os.path.join(avg_dir, bg_file_name)
    table_dir = "./tables"
    if not os.path.exists(bg_path): return None, "BGファイルが見つかりません"
    bg_df = pd.read_csv(bg_path)
    amp_bg = bg_df["Amplitude_dBm"].to_numpy()
    results = []
    avg_files = glob.glob(os.path.join(avg_dir, "*_avg.csv"))
    for f in avg_files:
        fname = os.path.basename(f)
        if fname == bg_file_name: continue
        try:
            lon_str = fname.replace("_avg.csv", "")
            lon = int(lon_str)
            if not (min_lon <= lon <= max_lon): continue
        except: continue
        df = pd.read_csv(f)
        freq = df["Frequency_Hz"].to_numpy()
        amp_sub = df["Amplitude_dBm"].to_numpy() - amp_bg
        mask = (freq >= FMIN) & (freq <= FMAX)
        f_win, a_win = freq[mask], amp_sub[mask]
        f_peak = float(f_win[np.argmax(a_win)])
        results.append({"銀経": lon, "f_peak_Hz": f_peak})
    if not results: return None, "解析対象のデータがありません"
    return _calculate_velocity_common(results, F_REST, table_dir)

def _calculate_velocity_common(peak_list, f_rest, table_dir):
    try:
        theta_df = pd.read_csv(os.path.join(table_dir, "θ_o表.csv"), encoding=TABLE_ENCODING)
        es_df    = pd.read_csv(os.path.join(table_dir, "E_s表.csv"), encoding=TABLE_ENCODING)
        dist_df  = pd.read_csv(os.path.join(table_dir, "中心距離標.csv"), encoding=TABLE_ENCODING)
        theta_list = theta_df.iloc[:, 0].tolist()
        es_list    = es_df.iloc[:, 0].tolist()
        dist_ly    = dist_df.iloc[:, 1].to_numpy()
    except Exception as e: return None, f"テーブル読み込みエラー: {e}"
    rows = []
    for p in peak_list:
        lon = p["銀経"]
        f_obs = p["f_peak_Hz"]
        num = int(lon / 5)
        if num >= len(theta_list): continue
        theta_rad = math.radians(float(theta_list[num]))
        sin_theta = math.sin(theta_rad)
        if abs(sin_theta) < 1e-6: continue
        vr = c * (f_rest - f_obs) / f_rest
        v_rot = (vr + float(es_list[num])) / sin_theta
        rows.append({"銀経": lon, "中心距離[光年]": dist_ly[num], "回転速度[km/s]": abs(v_rot)/1000.0})
    return pd.DataFrame(rows).sort_values("銀経"), []

def convert_tra_to_csv(target_dir):
    tra_files = glob.glob(os.path.join(target_dir, "**", "*.tra"), recursive=True)
    if not tra_files: return 0, ["エラー: .tra ファイルが見つかりませんでした。"]
    converted_count = 0
    logs = []
    for tra_path in tra_files:
        base, _ = os.path.splitext(tra_path)
        output_file = base + ".csv"
        try:
            with open(tra_path, "r", encoding="utf-8") as fin, open(output_file, "w", newline="", encoding="utf-8") as fout:
                reader = csv.reader(fin)
                writer = csv.writer(fout)
                next(reader, None)
                writer.writerow(["Frequency_Hz", "Amplitude_dBm"])
                for row in reader:
                    if len(row) >= 3: writer.writerow([float(row[1]), float(row[2])])
            converted_count += 1
        except Exception as e: logs.append(f"変換エラー: {os.path.basename(tra_path)} -> {e}")
    return converted_count, logs
