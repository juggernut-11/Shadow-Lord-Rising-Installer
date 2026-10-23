# Shadow Lord Rising installer — Nexus security review

Installer application source for juggernut's Shadow Lord Rising 0.1.0-test, uploaded to https://www.nexusmods.com/kotor2/mods/1414 on 19 October 2026.

This snapshot corresponds to the installer supplied in both uploaded editions. A mod-content update is in progress; this snapshot remains available so the submitted version can be reviewed independently.

## Contents

- `installer.py`: complete custom installer application, including the game-script source it generates.
- `dependency-sources.zip`: corresponding Python dependency sources in `vendor/` and software notices in `Licenses/`. Extract this archive into the repository folder before building.
- The dependency archive preserves the bundled software license notices.

Game resources are external inputs in each release's `payload/` folder. This repository covers the installer application; it does not contain the mod's models, textures, or proprietary game data.

## Build on Windows x64

Original toolchain: CPython 3.12.11 x64 and PyInstaller 6.22.3. Install Python from python.org. Open PowerShell in this repository folder and run:

```powershell
Expand-Archive -LiteralPath .\dependency-sources.zip -DestinationPath . -Force
py -3.12 -m venv .build-env
.\.build-env\Scripts\python.exe -m pip install PyInstaller==6.22.3
.\.build-env\Scripts\python.exe -m PyInstaller --clean --noconfirm --onefile --name ShadowLordRising-Setup --paths vendor --hidden-import pykotor.resource.formats.ncs.compiler.parsetab installer.py
```

Output: `dist/ShadowLordRising-Setup.exe`. Keep the release's `payload/` folder and `payload-manifest.json` next to the executable. A fresh rebuild may differ in binary hash from the uploaded executable due to build environment differences. Updating a release's executable also requires regenerating its integrity manifest before installation.

The vendor directory is used directly as the dependency source; no game files are compiled into the executable. Python and PyInstaller are build prerequisites, not downloaded by the installer.

## Runtime behavior

The installer checks the selected local game and package, computes recipient-specific table and campaign patches, backs up affected files, and writes those patches. Uninstall checks installed file hashes before restoring backups. Compilation of game scripts is performed locally with the bundled library.

Offline installation and exact-restore checks were performed in isolated fixture folders. These are not an in-game playthrough certification.

