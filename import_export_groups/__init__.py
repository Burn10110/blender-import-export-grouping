"""Import/Export Groups: organise File > Import / Export entries into submenus."""

from . import config, menu_patch, prefs


def register():
    cfg = config.load()
    prefs.set_config(cfg)
    prefs.register()
    menu_patch.patch(cfg)


def unregister():
    menu_patch.unpatch()
    prefs.unregister()
