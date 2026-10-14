"""Import/Export Groups: organise File > Import / Export entries into submenus."""

from . import config, menu_patch


def register():
    menu_patch.patch(config.load())


def unregister():
    menu_patch.unpatch()
