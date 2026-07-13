# build_itch.py
# =============
# King's Trial — Distribution Builder for itch.io and Steam.
#
# This Python script bundles the compiled standalone game executable with all
# necessary external folders and configurations (assets, themes, maps, sounds, 
# config.json, and the Stockfish AI engine) into a ready-to-distribute 
# 'itch' folder, and creates a zipped package for instant upload.
#

import os
import shutil
import json
from datetime import datetime

def build():
    print("==================================================")
    print("     KING'S TRIAL — ITCH/STEAM DISTRIBUTOR")
    print("==================================================")
    
    root_dir = os.path.abspath(os.path.dirname(__file__))
    
    # Generate dynamic target directory using today's date
    date_str = datetime.now().strftime("%Y_%m_%d")
    build_dir = os.path.abspath(os.path.join(root_dir, "..", "KingsTrialBuild"))
    itch_dir = os.path.join(build_dir, f"Itch_{date_str}")
    dist_exe = os.path.join(root_dir, "dist", "KingsTrial.exe")
    
    # 1. Verify executable exists
    if not os.path.exists(dist_exe):
        print(f"[-] Compiled KingsTrial.exe not found at {dist_exe}!")
        print("[*] Please run `python build.ps1` or PyInstaller manually.")
        return
        
    print(f"[+] Found compiled KingsTrial.exe at {dist_exe}")
    
    # 2. Clean old itch folder and zip
    if os.path.exists(itch_dir):
        print("[*] Cleaning old itch folder...")
        shutil.rmtree(itch_dir)
        
    zip_path = os.path.join(build_dir, f"KingsTrial_Itch_{date_str}.zip")
    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except Exception:
            pass
        
    # 3. Create itch folder and subfolders
    print("[*] Creating itch/ distribution folder...")
    os.makedirs(os.path.join(itch_dir, "saves"), exist_ok=True)
    
    # 4. Copy KingsTrial.exe
    print("[*] Copying KingsTrial.exe...")
    shutil.copy2(dist_exe, os.path.join(itch_dir, "KingsTrial.exe"))
    
    # 5. Copy assets
    src_assets = os.path.join(root_dir, "assets")
    if os.path.exists(src_assets):
        print("[*] Copying assets folder...")
        shutil.copytree(src_assets, os.path.join(itch_dir, "assets"))
    else:
        print("[!] Warning: assets folder not found!")
        
    # 6. Copy stockfish
    src_stockfish = os.path.join(root_dir, "stockfish")
    if os.path.exists(src_stockfish):
        print("[*] Copying stockfish folder...")
        shutil.copytree(src_stockfish, os.path.join(itch_dir, "stockfish"))
    else:
        print("[!] Warning: stockfish folder not found!")
        
    # 7. Copy config.json
    src_config = os.path.join(root_dir, "config.json")
    if os.path.exists(src_config):
        print("[*] Copying config.json...")
        shutil.copy2(src_config, os.path.join(itch_dir, "config.json"))
    else:
        print("[*] Generating default config.json...")
        default_config = {
            "single_player": False,
            "human_colour": "white",
            "neutral_ai": "random",
            "opponent_ai": "random",
            "time_control": "5+10",
            "theme": "default",
            "sfx_volume": 2,
            "music_volume": 2,
            "layout_file": "TEST_CSV.csv",
            "relay_server_url": "ws://localhost:8765"
        }
        with open(os.path.join(itch_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)

    # Copy README.md
    src_readme = os.path.join(root_dir, "README.md")
    if os.path.exists(src_readme):
        print("[*] Copying README.md...")
        shutil.copy2(src_readme, os.path.join(itch_dir, "README.md"))
            
    # 8. Create compressed zip
    print(f"[*] Compressing itch folder into KingsTrial_Itch_{date_str}.zip...")
    try:
        shutil.make_archive(os.path.join(build_dir, f"KingsTrial_Itch_{date_str}"), 'zip', itch_dir)
        print("[+] Created KingsTrial_itch.zip successfully!")
    except Exception as e:
        print(f"[!] Error compressing itch folder: {e}")
        
    print("\n==================================================")
    print("  DISTRIBUTION PACKAGING COMPLETED SUCCESSFULLY!  ")
    print("==================================================")
    print(f"  Standalone package  : {itch_dir}")
    print(f"  Zipped package      : {zip_path}")
    print("==================================================")

if __name__ == "__main__":
    build()
