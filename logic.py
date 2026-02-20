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
    """フォルダ内のファイルから経度リストを自動取得"""
    # avgフォルダの中身と、ルートフォルダの中身両方を確認
    search_paths = [folder_path, os.path.join(folder_path, "avg")]
    lons = []
    for s_path in search_paths:
        files = glob.glob(os.path.join(s_path, "*.csv"))
        for f in files:
            name = os.path.basename(f)
            # 数字を探す (例: 120_avg.csv や 2026.02.19.120.1.csv)
            parts = name.replace("_avg", "").split('.')
            for p in parts:
                p_sub = p.split('_')[0] # 90_avg 対策
                if p_sub.isdigit():
                    lons.append(int(p_sub))
    return sorted(list(set(lons)))

def process_average_all(folder_path):
    avg_dir = os.path.join(folder_path, "avg")
    os.makedirs(avg_dir, exist_ok=True)
    
    # 命名規則に柔軟に対応 (*.数字.1.csv や 数字.1.csv)
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
            
            # 出力名をシンプルに「経度_avg.csv」にする
            lon_label = pre.split('.')[-1]
            out_name = f"{lon_label}_avg.csv"
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
    
    if not os.path.exists(bg_path):
        return None, f"エラー: BGファイルが見つかりません ({bg_file_name})"
    
    try:
        bg_df = pd.read_csv(bg_path)
        amp_bg = bg_df["Amplitude_dBm"].to_numpy()
    except Exception as e:
        return None, f"BGファイル読み込み失敗: {e}"
    
    results = []
    avg_files = glob.glob(os.path.join(avg_dir, "*_avg.csv"))
    
    diag_logs = []
    for f in avg_files:
        fname = os.path.basename(f)
        if fname == bg_file_name: continue
        
        try:
            # ファイル名から数値を抽出 (例: 120_avg.csv -> 120)
            lon_str = fname.split('_')[0]
            if not lon_str.isdigit(): continue
            lon = int(lon_str)
            if not (min_lon <= lon <= max_lon): continue
            
            df = pd.read_csv(f)
            freq = df["Frequency_Hz"].to_numpy()
            amp_target = df["Amplitude_dBm"].to_numpy()

            # データ長チェック
            if len(amp_target) != len(amp_bg):
                diag_logs.append(f"銀経 {lon}: データ数不一致 (Target:{len(amp_target)} / BG:{len(amp_bg)})")
                continue

            amp_sub = amp_target - amp_bg
            
            mask = (freq >= FMIN) & (freq <= FMAX)
            if not mask.any(): continue

            f_win, a_win = freq[mask], amp_sub[mask]
            f_peak = float(f_win[np.argmax(a_win)])
            results.append({"銀経": lon, "f_peak_Hz": f_peak})
        except Exception as e:
            diag_logs.append(f"ファイル {fname} の処理でエラー: {e}")
    
    if not results:
        error_msg = "解析対象のデータが見つかりませんでした。"
        if diag_logs: error_msg += "\n" + "\n".join(diag_logs)
        return None, error_msg
    
    return _calculate_velocity_common(results, F_REST, table_dir)

def _calculate_velocity_common(peak_list, f_rest, table_dir):
    try:
        theta_df = pd.read_csv(os.path.join(table_dir, "θ_o表.csv"), encoding=TABLE_ENCODING)
        es_df    = pd.read_csv(os.path.join(table_dir, "E_s表.csv"), encoding=TABLE_ENCODING)
        dist_df  = pd.read_csv(os.path.join(table_dir, "中心距離標.csv"), encoding=TABLE_ENCODING)
        theta_list = theta_df.iloc[:, 0].tolist()
        es_list    = es_df.iloc[:, 0].tolist()
        dist_ly    = dist_df.iloc[:, 1].to_numpy()
    except Exception as e:
        return None, f"テーブル読み込みエラー: {e}\ntablesフォルダに正しくCSVが入っているか確認してください。"

    rows = []
    for p in peak_list:
        lon = p["銀経"]
        f_obs = p["f_peak_Hz"]
        # 5度刻みのテーブル（0, 5, 10...）に対応
        idx = int(lon / 5)
        if idx >= len(theta_list): continue
        
        theta_rad = math.radians(float(theta_list[idx]))
        sin_theta = math.sin(theta_rad)
        if abs(sin_theta) < 1e-6: continue
        
        # ドップラー速度 Vr
        vr = c * (f_rest - f_obs) / f_rest
        # 回転速度 V(R) = (Vr + Es) / sin(l)
        v_rot = (vr + float(es_list[idx])) / sin_theta
        rows.append({
            "銀経": lon, 
            "中心距離[光年]": dist_ly[idx], 
            "回転速度[km/s]": abs(v_rot)/1000.0,
            "観測周波数[MHz]": f_obs/1e6
        })
        
    return pd.DataFrame(rows).sort_values("銀経"), []
