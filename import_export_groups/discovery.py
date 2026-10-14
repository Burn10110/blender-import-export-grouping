"""Discover the entries of File > Import / Export as the user sees them.

Each draw function of the menu is run against a RecordingLayout. Owner filtering of the
real menu (`bl_owner_use_filter`) is not applied: every entry any add-on draws is listed.
Cheap enough to run on every redraw (~1 ms for both menus, 5.2.2).
"""

import bpy

from .menu_patch import MENUS, RecordingLayout, original_draw

_reported = set()  # draw funcs that raised, reported once per session


class _FakeMenu:
    """`self` for a menu draw function: a layout, the menu idname, None for the rest."""

    def __init__(self, idname, layout):
        self.bl_idname = idname
        self.layout = layout

    def __getattr__(self, name):
        return None


def operator_label(idname):
    """`bl_label` of a registered operator, or None if it is not registered."""
    module, _, name = idname.partition(".")
    try:
        return getattr(getattr(bpy.ops, module), name).get_rna_type().name
    except (AttributeError, KeyError):
        return None


def _call_text(call):
    if "text" in call["kwargs"]:
        return call["kwargs"]["text"]
    return call["args"][0] if call["args"] else None


def menu_entries(side, context):
    """Ordered [(idname, label)] of the stock + add-on entries, first occurrence wins."""
    menu_name = MENUS[side]
    menu_cls = getattr(bpy.types, menu_name)
    draw = original_draw(menu_cls)
    calls = []
    for func in getattr(draw, "_draw_funcs", [draw]):
        try:
            func(_FakeMenu(menu_name, RecordingLayout(calls)), context)
        except Exception as ex:  # a broken add-on must not break our UI
            key = (menu_name, getattr(func, "__qualname__", repr(func)))
            if key not in _reported:
                _reported.add(key)
                print(f"Import/Export Groups: {key[1]} raised while listing {menu_name}: {ex!r}")

    entries = []
    seen = set()
    for call in calls:
        idname = call["idname"]
        if idname in seen:
            continue
        seen.add(idname)
        text = _call_text(call)
        entries.append((idname, text or operator_label(idname) or idname))
    return entries
