"""Generate the Windows version resource PyInstaller embeds in the exe.

Generated rather than checked in, so the version in file Properties can never disagree
with `agent/version.py` — which is the number the server records on every heartbeat and
what an admin reads when deciding whether a machine needs updating.

    python installer/make_version_info.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.version import __version__  # noqa: E402

COMPANY = "Office Management"
PRODUCT = "Office Tracker Agent"
DESCRIPTION = "Reports PC activity and liveness to the Office Management server."

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{company}'),
         StringStruct('FileDescription', '{description}'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'OfficeTrackerAgent'),
         StringStruct('OriginalFilename', 'OfficeTrackerAgent.exe'),
         StringStruct('ProductName', '{product}'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    parts = (__version__.split("+")[0].split("-")[0].split(".") + ["0", "0", "0"])[:3]
    major, minor, patch = (int(part) if part.isdigit() else 0 for part in parts)

    target = Path(__file__).resolve().parent / "version_info.txt"
    target.write_text(
        TEMPLATE.format(
            major=major,
            minor=minor,
            patch=patch,
            version=__version__,
            company=COMPANY,
            product=PRODUCT,
            description=DESCRIPTION,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {target} for version {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
