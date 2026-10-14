"""Group config: JSON file in the extension's user directory.

Format:
    {"version": 1,
     "import": [{"name": "Photogrammetry", "items": ["import_scene.colmap_model", ...]}, ...],
     "export": [...]}

The file is the source of truth: AddonPreferences are wiped when the add-on is disabled
from the UI (see docs/knowledge), so they can only be a working copy.
"""

import json
import os
import shutil
import time

import bpy

VERSION = 1
SIDES = ("import", "export")
FILENAME = "groups.json"
DEFAULT_GROUP_NAME = "Group"


def empty():
    return {side: [] for side in SIDES}


def config_path():
    return os.path.join(bpy.utils.extension_path_user(__package__, create=True), FILENAME)


def normalize(data):
    """Return a clean config from untrusted data.

    Unknown keys are dropped, wrong types skipped, an idname may belong to only one group
    per side (first wins: an entry is moved into a group, never duplicated).
    """
    result = empty()
    if not isinstance(data, dict):
        return result
    for side in SIDES:
        groups = data.get(side)
        if not isinstance(groups, list):
            continue
        taken = set()
        for group in groups:
            if not isinstance(group, dict):
                continue
            name = group.get("name")
            name = name.strip() if isinstance(name, str) else ""
            items = []
            for idname in group.get("items") or []:
                if isinstance(idname, str) and idname and idname not in taken:
                    taken.add(idname)
                    items.append(idname)
            result[side].append({"name": name or DEFAULT_GROUP_NAME, "items": items})
    return result


def load(path=None):
    """Read config. Missing file -> empty config.

    An unreadable file is renamed aside (never overwritten later) and an empty config is
    returned, with a warning in the console.
    """
    path = path or config_path()
    if not os.path.exists(path):
        return empty()
    try:
        with open(path, encoding="utf-8-sig") as f:  # tolerate a BOM from hand editing
            data = json.load(f)
    except (OSError, ValueError) as ex:
        aside = f"{path}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            os.replace(path, aside)
        except OSError:
            aside = None
        print(f"Import/Export Groups: cannot read {path!r} ({ex}); "
              f"starting empty, old file kept as {aside!r}")
        return empty()
    return normalize(data)


def save(config, path=None):
    """Write config atomically; the previous file is kept as `<name>.bak`."""
    path = path or config_path()
    data = {"version": VERSION, **normalize(config)}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    os.replace(tmp, path)  # the config file itself is never missing
