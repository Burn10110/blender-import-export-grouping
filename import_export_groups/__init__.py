"""Import/Export Groups: organise File > Import / Export entries into submenus."""

from . import menu_patch

# Step 2: hard-coded test groups. Replaced by stored config in step 3.
STATIC_CONFIG = {
    "import": [
        {"name": "Photogrammetry", "items": [
            "import_scene.meshroom_sfm_json",
            "import_scene.colmap_model",
        ]},
    ],
    "export": [
        {"name": "FBX", "items": [
            "export_scene.fbx",
            "better_export.fbx",
        ]},
    ],
}


def register():
    menu_patch.patch(STATIC_CONFIG)


def unregister():
    menu_patch.unpatch()
