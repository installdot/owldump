# Otherworld Legends Automated Data Dumper

Automated CI/CD pipeline that scrapes `https://chillyroom.com/en` for the latest Otherworld Legends APK, extracts `libil2cpp.so` and `global-metadata.dat`, runs `Il2CppDumper`, resolves the hotfix CDN logic DLL, and dynamically extracts all game data (characters, skills, skins, rooms, tapes, orbs, items, achievements, etc.) with IDs and dynamic English names.

## Features
- **Auto-scraping**: Detects new APK releases on `https://chillyroom.com/en`.
- **Il2Cpp Unpacking**: Extracts `libil2cpp.so` (arm64) and `global-metadata.dat` from the APK.
- **Headless Il2CppDumper**: Automatically downloads cross-platform Il2CppDumper and executes non-interactively via .NET.
- **CDN Resolution**: Extracts `GameLogic.dll.bytes` from dumped metadata and downloads the hotfix assembly.
- **Dynamic English Extraction**: Resolves clean English names and IDs without preset dictionaries.
- **Auto-Commit**: Pushes updated datasets in `data/` via GitHub Actions on a weekly schedule or manual trigger.

## Output Datasets in `data/`
- `tape_data.json`: 39 cassette soundtrack albums.
- `roomskin_data.json`: 16 lobby/living room skins.
- `heroskin_data.json`: 107 hero skins, 28 NPC skins, skin powers.
- `orb_data.json`: 7 realms, 51 affixes, creation levels.
- `characters_data.json`: 283 heroes, bosses, monsters, NPCs, pets.
- `items_data.json`: 271 items, relics, qualities, item types.
- `skills_data.json`: 775 skills and 247 skill styles.
- `weapons_data.json`: 105 weapon powers, weapon qualities.
- `buffs_data.json`: 109 buffs and debuffs.
- `pets_data.json`: 25 pets.
- `achievements_data.json`: 205 achievements.
- `all_game_data.json`: Complete dump of all 386 enums.

## Running Locally
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run pipeline
python pipeline.py
```
