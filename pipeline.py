#!/usr/bin/env python3
import os
import sys
import json
import struct
import urllib.request
import re
import shutil
import zipfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
TOOLS_DIR = BASE_DIR / "tools"

CHILLYROOM_URL = "https://chillyroom.com/en"
IL2CPP_DUMPER_RELEASE = "https://github.com/Perfare/Il2CppDumper/releases/download/v6.7.46/Il2CppDumper-net7-v6.7.46.zip"

def scrape_apk_url():
    print("[*] Scraping chillyroom.com/en for Otherworld Legends APK...")
    req = urllib.request.Request(CHILLYROOM_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8")
    
    matches = re.findall(r'https?://[^\s"\'<>]+\.apk', html)
    owl_matches = [m for m in matches if any(k in m.lower() for k in ["otherworld", "zhmr"])]
    target_url = owl_matches[0] if owl_matches else (matches[0] if matches else None)
    
    if not target_url:
        raise RuntimeError("[-] No APK link found on chillyroom.com/en")
    print(f"[+] Found APK URL: {target_url}")
    return target_url

def download_file(url, dest_path):
    print(f"[*] Downloading {url} -> {dest_path.name}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as f:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024 * 2 # 2MB chunks
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                percent = (downloaded / total) * 100
                print(f"\r    {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB ({percent:.1f}%)", end="", flush=True)
    print("\n[+] Download finished.")

def extract_apk_components(apk_path, out_dir):
    print(f"[*] Extracting libil2cpp and global-metadata from {apk_path.name}...")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    bin_path = None
    meta_path = None
    
    with zipfile.ZipFile(apk_path, "r") as zf:
        names = zf.namelist()
        
        # Priority for binary: arm64-v8a > armeabi-v7a > x86_64
        preferred_bins = [
            "lib/arm64-v8a/libil2cpp.so",
            "lib/armeabi-v7a/libil2cpp.so",
            "lib/x86_64/libil2cpp.so"
        ]
        chosen_bin_entry = None
        for pb in preferred_bins:
            if pb in names:
                chosen_bin_entry = pb
                break
        if not chosen_bin_entry:
            for n in names:
                if n.endswith("libil2cpp.so"):
                    chosen_bin_entry = n
                    break
        
        if not chosen_bin_entry:
            raise RuntimeError("[-] libil2cpp.so not found inside APK.")
        
        # Metadata entry
        meta_entry = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
        if meta_entry not in names:
            for n in names:
                if n.endswith("global-metadata.dat"):
                    meta_entry = n
                    break
        
        if not meta_entry:
            raise RuntimeError("[-] global-metadata.dat not found inside APK.")
            
        print(f"[+] Found binary: {chosen_bin_entry}")
        print(f"[+] Found metadata: {meta_entry}")
        
        bin_path = out_dir / Path(chosen_bin_entry).name
        meta_path = out_dir / Path(meta_entry).name
        
        with zf.open(chosen_bin_entry) as src, open(bin_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        with zf.open(meta_entry) as src, open(meta_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
            
    print(f"[+] Extracted: {bin_path.name} ({bin_path.stat().st_size} bytes)")
    print(f"[+] Extracted: {meta_path.name} ({meta_path.stat().st_size} bytes)")
    return bin_path, meta_path

def setup_il2cpp_dumper(tools_dir):
    dumper_dir = tools_dir / "il2cppdumper"
    dumper_dll = dumper_dir / "Il2CppDumper.dll"
    if dumper_dll.exists():
        return dumper_dll
        
    dumper_dir.mkdir(parents=True, exist_ok=True)
    zip_dest = tools_dir / "il2cppdumper.zip"
    download_file(IL2CPP_DUMPER_RELEASE, zip_dest)
    
    with zipfile.ZipFile(zip_dest, "r") as zf:
        zf.extractall(dumper_dir)
        
    # Configure non-interactive execution
    cfg_path = dumper_dir / "config.json"
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["RequireAnyKey"] = False
        cfg["GenerateDummyDll"] = False
        cfg["GenerateStruct"] = True
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            
    return dumper_dll

def run_il2cpp_dumper(dumper_dll, bin_path, meta_path, dump_dir):
    print("[*] Running Il2CppDumper...")
    dump_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = ["dotnet", str(dumper_dll), str(bin_path), str(meta_path), str(dump_dir)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(dumper_dll.parent))
    if res.returncode != 0:
        print("Dumper Stderr:", res.stderr)
        raise RuntimeError(f"Il2CppDumper failed with return code {res.returncode}")
        
    print("[+] Il2CppDumper finished successfully.")

def find_gamelogic_cdn_url(dump_dir):
    print("[*] Extracting GameLogic.dll CDN link from dumped metadata...")
    str_json = dump_dir / "stringliteral.json"
    if str_json.exists():
        with open(str_json, "r", encoding="utf-8") as f:
            for item in json.load(f):
                val = item.get("value", "")
                if "GameLogic.dll.bytes" in val and val.startswith("http"):
                    print(f"[+] Found CDN link in stringliteral.json: {val}")
                    return val

    # Scan global-metadata as fallback
    for p in dump_dir.glob("*.dat"):
        matches = re.findall(rb'https?://[^\x00\r\n\s]+GameLogic\.dll\.bytes', p.read_bytes())
        if matches:
            url = matches[0].decode('utf-8')
            print(f"[+] Found CDN link in metadata: {url}")
            return url
            
    raise RuntimeError("[-] GameLogic.dll.bytes URL not found in dump outputs.")

def dynamic_english_name(code_name):
    if not code_name:
        return ""
    words = []
    for part in code_name.split("_"):
        if not part:
            continue
        tokens = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b|\d)|[0-9]+', part)
        words.extend(tokens if tokens else [part])
    return " ".join(w.capitalize() if w.islower() else w for w in words)

def extract_item_info(category, code_name, item_id):
    info = {
        "id": item_id,
        "name": dynamic_english_name(code_name),
        "code_name": code_name
    }
    if category == "Tape":
        sub = code_name[6:] if code_name.startswith("album_") else code_name
        info["name"] = dynamic_english_name(sub)
        info["track_type"] = "Boss Track" if "boss" in sub.lower() else "Stage Track"
    elif category == "Heroskin":
        parts = code_name.split("_")
        if len(parts) >= 2 and parts[0] == "hero":
            hero = dynamic_english_name(parts[1])
            skin = dynamic_english_name("_".join(parts[2:])) if len(parts) > 2 else "Default"
            info["name"] = f"{hero} - {skin}"
            info["hero"] = hero
            info["skin"] = skin
    elif category == "Characters":
        if code_name.startswith("hero_"):
            info["name"] = dynamic_english_name(code_name[5:])
            info["category"] = "Hero"
        elif code_name.startswith("pet_"):
            info["name"] = dynamic_english_name(code_name[4:])
            info["category"] = "Pet"
        elif code_name.startswith("npc_") or code_name in ["totem", "other_pile"]:
            info["name"] = dynamic_english_name(code_name)
            info["category"] = "NPC / Object"
        else:
            info["name"] = dynamic_english_name(code_name)
            info["category"] = "Boss / Enemy"
    return info

def dump_gamelogic_data(dll_path, out_dir):
    import dnfile
    print(f"[*] Dumping game data from {dll_path.name}...")
    pe = dnfile.dnPE(str(dll_path))

    constant_map = {}
    if hasattr(pe.net.mdtables, "Constant") and pe.net.mdtables.Constant:
        for crow in pe.net.mdtables.Constant:
            parent = crow.Parent
            if parent and parent.row:
                tname = getattr(parent.table, "name", str(parent.table))
                val_bytes = crow.Value.value if hasattr(crow.Value, "value") else b""
                ctype = crow.Type
                val = val_bytes
                if ctype in (0x08, 0x09) and len(val_bytes) >= 4:
                    val = struct.unpack("<i" if ctype == 0x08 else "<I", val_bytes[:4])[0]
                elif ctype in (0x04, 0x05) and len(val_bytes) >= 1:
                    val = val_bytes[0]
                elif ctype in (0x06, 0x07) and len(val_bytes) >= 2:
                    val = struct.unpack("<h" if ctype == 0x06 else "<H", val_bytes[:2])[0]
                elif ctype in (0x0A, 0x0B) and len(val_bytes) >= 8:
                    val = struct.unpack("<q" if ctype == 0x0A else "<Q", val_bytes[:8])[0]
                elif ctype == 0x02 and len(val_bytes) >= 1:
                    val = bool(val_bytes[0])
                elif ctype == 0x0E:
                    val = val_bytes.decode("utf-16le", errors="ignore")
                constant_map[(tname, parent.row_index)] = val

    all_enums = {}
    for row in pe.net.mdtables.TypeDef:
        extends = getattr(row, "Extends", None)
        if extends and hasattr(extends, "row") and extends.row:
            if getattr(extends.row, "TypeName", "") == "Enum":
                ename = str(row.TypeName)
                members = []
                for f_idx in row.FieldList:
                    fname = str(f_idx.row.Name)
                    if fname == "value__":
                        continue
                    tname = getattr(f_idx.table, "name", str(f_idx.table))
                    val = constant_map.get((tname, f_idx.row_index))
                    members.append({
                        "id": val,
                        "name": dynamic_english_name(fname),
                        "code_name": fname
                    })
                if members:
                    all_enums[ename] = members

    out_dir.mkdir(parents=True, exist_ok=True)

    tape_items = [extract_item_info("Tape", i["code_name"], i["id"]) for i in all_enums.get("AlbumName", [])]
    room_items = [extract_item_info("Roomskin", i["code_name"], i["id"]) for i in all_enums.get("MenuSkinType", [])]
    hero_skins = [extract_item_info("Heroskin", i["code_name"], i["id"]) for i in all_enums.get("HeroSkinName", [])]
    npc_skins = [extract_item_info("NPCSkin", i["code_name"], i["id"]) for i in all_enums.get("NPCSkinName", [])]
    powers = [extract_item_info("Power", i["code_name"], i["id"]) for i in all_enums.get("HeroSkinPowerID", [])]
    orb_types = [extract_item_info("Orb", i["code_name"], i["id"]) for i in all_enums.get("SixCycleOrbType", [])]
    orb_affixes = [extract_item_info("Orb", i["code_name"], i["id"]) for i in all_enums.get("SixCycleOrbAffixID", [])]
    characters = [extract_item_info("Characters", i["code_name"], i["id"]) for i in all_enums.get("CharacterName", [])]

    categories = {
        "Tape": {"count": len(tape_items), "description": "Magnetic Cassette Tapes / Music Albums", "data": tape_items},
        "Roomskin": {"count": len(room_items), "description": "Living Room / Lobby Menu Skins", "data": room_items},
        "Heroskin": {
            "hero_skin_count": len(hero_skins),
            "npc_skin_count": len(npc_skins),
            "power_count": len(powers),
            "description": "Hero & NPC Skins and Powers",
            "hero_skins": hero_skins,
            "npc_skins": npc_skins,
            "powers": powers
        },
        "Orb": {
            "types_count": len(orb_types),
            "affixes_count": len(orb_affixes),
            "description": "Six Cycles / Six Realms Orbs and Affixes",
            "types": orb_types,
            "affixes": orb_affixes
        },
        "Characters": {"count": len(characters), "description": "Characters, Heroes, Bosses, and Monsters", "data": characters},
        "Items": {"count": len(all_enums.get("ItemID", [])), "description": "Items and Relics", "data": all_enums.get("ItemID", [])},
        "Skills": {
            "skills_count": len(all_enums.get("SkillName", [])),
            "styles_count": len(all_enums.get("HeroSkillStyleName", [])),
            "description": "Skills and Skill Styles",
            "skills": all_enums.get("SkillName", []),
            "styles": all_enums.get("HeroSkillStyleName", [])
        },
        "Weapons": {"count": len(all_enums.get("WeaponPowerID", [])), "description": "Weapon Powers", "data": all_enums.get("WeaponPowerID", [])},
        "Buffs": {"count": len(all_enums.get("BuffID", [])), "description": "Buffs and Status Effects", "data": all_enums.get("BuffID", [])},
        "Pets": {"count": len(all_enums.get("PetName", [])), "description": "Pets and Companions", "data": all_enums.get("PetName", [])},
        "Achievements": {"count": len(all_enums.get("AchievementID", [])), "description": "Achievements", "data": all_enums.get("AchievementID", [])}
    }

    for cat_name, cat_obj in categories.items():
        with open(out_dir / f"{cat_name.lower()}_data.json", "w", encoding="utf-8") as f:
            json.dump(cat_obj, f, indent=2, ensure_ascii=False)
        print(f"[+] Saved {cat_name.lower()}_data.json")

    with open(out_dir / "all_game_data.json", "w", encoding="utf-8") as f:
        json.dump({"categories": categories, "all_enums": all_enums}, f, indent=2, ensure_ascii=False)
    print(f"[+] Dumped all {len(all_enums)} enums to all_game_data.json")

def main():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Scrape APK URL
    apk_url = scrape_apk_url()

    # 2. Download APK
    apk_name = apk_url.split("/")[-1]
    apk_path = TEMP_DIR / apk_name
    if not apk_path.exists():
        download_file(apk_url, apk_path)
    else:
        print(f"[+] Using cached APK: {apk_path.name}")

    # 3. Extract libil2cpp.so and global-metadata.dat
    bin_path, meta_path = extract_apk_components(apk_path, TEMP_DIR / "extracted_bin")

    # 4. Download and setup Il2CppDumper
    dumper_dll = setup_il2cpp_dumper(TOOLS_DIR)

    # 5. Run Il2CppDumper
    dump_out_dir = TEMP_DIR / "dumper_out"
    run_il2cpp_dumper(dumper_dll, bin_path, meta_path, dump_out_dir)

    # 6. Extract CDN URL from dump
    gamelogic_cdn_url = find_gamelogic_cdn_url(dump_out_dir)

    # 7. Download GameLogic.dll
    dll_path = TEMP_DIR / "GameLogic.dll"
    download_file(gamelogic_cdn_url, dll_path)

    # 8. Dump all game data to data/
    dump_gamelogic_data(dll_path, DATA_DIR)

    print("[+] All tasks completed successfully. Output in 'data/' folder.")

if __name__ == "__main__":
    main()
