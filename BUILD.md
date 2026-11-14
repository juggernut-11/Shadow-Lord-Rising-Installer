# Shadow Lord Rising installer 0.1.1-test � matching review source

This snapshot corresponds to the installer in the 0.1.1-test Full and Maul-Progression packages. This is the current release source.

The 14 November 2026 release refresh changes only three light-side eye textures. It reuses the existing 0.1.1-test installer executable without recompiling or modifying it. Game art and recipient-specific campaign resources are external inputs, not compiled into this executable.

## Exact Windows build steps

Original toolchain: CPython 3.12.11 x64 and PyInstaller 6.22.3. Open PowerShell in the repository folder and run:

```powershell
Expand-Archive -LiteralPath .\dependency-sources.zip -DestinationPath . -Force
py -3.12 -m venv .build-env
.\.build-env\Scripts\python.exe -m pip install PyInstaller==6.22.3
.\.build-env\Scripts\python.exe -m PyInstaller --clean --noconfirm --onefile --noupx --name ShadowLordRising-Setup --paths vendor --hidden-import pykotor.resource.formats.ncs.compiler.parsetab installer.py
```

Output: `dist/ShadowLordRising-Setup.exe`. The dependency archive contains the corresponding vendored Python source and licenses. Keep a release package's `payload/` and integrity manifest beside the executable for installation. A fresh build may have a different binary hash because of build-environment differences; replacing an executable also requires regenerating the release integrity manifest.

## Supplied executable and source checksums

- Setup EXE: `c4fa8d58f4f5713d21c7246f931f41c3955509a2757fa248ab65d5a169a01d11`
- Installer source: `587f1a1819399cc30cbd14f412906bdbeadc41a5cd4b75ac92a72c1f40eee67c`

`REVIEW-MANIFEST.json` records dependency-source and release-archive hashes. The raw installer source is kept byte-identical to the source shipped with those packages.

## Behavior and verification

The installer reads a user-selected local game, prepares table and campaign patches locally, confirms installation in the interactive flow, and backs up replaced files. Uninstall checks hashes before restoring backups. Game scripts are compiled locally from source embedded in installer.py. There is no game launcher, online downloader, updater, antivirus exclusion or security bypass in the installer.

Both editions passed offline dry-run checks in the standalone EXE and transparent Python-launcher variants, with identical patch plans and unchanged fixture files. This is not an in-game playthrough or a Nexus/antivirus approval claim. No request to Nexus support has been sent by this update.
