# SPDX-FileCopyrightText: 2026 Igor Burn
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Patch File > Import / Export: group submenus on top, grouped entries hidden below.

The menus' `draw` is Blender's `draw_ls` (see `_bpy_types._GenericUI._dyn_ui_initialize`),
which iterates `draw._draw_funcs`. We replace `cls.draw` with a wrapper that shares the same
`_draw_funcs` list, so `append()` / `remove()` by other addons keep working while patched.
"""

import traceback

import bpy

MENUS = {
    "import": "TOPBAR_MT_file_import",
    "export": "TOPBAR_MT_file_export",
}

# Layout methods that return a sub-layout which must stay proxied.
_SUBLAYOUTS = {"row", "column", "box", "split", "column_flow", "grid_flow"}


# ---------------------------------------------------------------------------
# Layout proxies

class _PropSink:
    """Stands in for OperatorProperties; stores assignments in a dict."""

    def __init__(self, store):
        object.__setattr__(self, "_store", store)

    def __setattr__(self, name, value):
        self._store[name] = value

    def __getattr__(self, name):
        return self._store.get(name)


class RecordingLayout:
    """Records `operator()` calls instead of drawing; everything else is a no-op."""

    def __init__(self, calls):
        self._calls = calls
        self.operator_context = "INVOKE_REGION_WIN"

    def operator(self, operator, *args, **kwargs):
        props = {}
        self._calls.append({
            "idname": operator,
            "args": args,
            "kwargs": kwargs,
            "props": props,
            "ctx": self.operator_context,
        })
        return _PropSink(props)

    def _sub(self, *args, **kwargs):
        sub = RecordingLayout(self._calls)
        sub.operator_context = self.operator_context
        return sub

    row = column = box = split = column_flow = grid_flow = _sub

    def __getattr__(self, name):
        # Attributes not set in __init__ (enabled, scale_y, ...) and other drawing calls.
        def _noop(*args, **kwargs):
            return None
        return _noop


class FilteringLayout:
    """Forwards to a real UILayout, but skips `operator()` for hidden idnames."""

    def __init__(self, layout, hidden):
        object.__setattr__(self, "_layout", layout)
        object.__setattr__(self, "_hidden", hidden)

    def operator(self, operator, *args, **kwargs):
        if operator in self._hidden:
            return _PropSink({})
        return self._layout.operator(operator, *args, **kwargs)

    def __getattr__(self, name):
        attr = getattr(self._layout, name)
        if name in _SUBLAYOUTS:
            def _wrapped(*args, **kwargs):
                return FilteringLayout(attr(*args, **kwargs), self._hidden)
            return _wrapped
        return attr

    def __setattr__(self, name, value):
        setattr(self._layout, name, value)


class _MenuProxy:
    """Stands in for the Menu instance (`self` in draw funcs) with a substituted layout."""

    def __init__(self, menu, layout):
        object.__setattr__(self, "_menu", menu)
        object.__setattr__(self, "layout", layout)

    def __getattr__(self, name):
        return getattr(self._menu, name)

    def __setattr__(self, name, value):
        setattr(self._menu, name, value)


# ---------------------------------------------------------------------------
# Recording / replay

def record(menu_cls, menu, context):
    """Run the original menu draw against a RecordingLayout, return the operator calls."""
    calls = []
    original = original_draw(menu_cls)
    original(_MenuProxy(menu, RecordingLayout(calls)), context)
    return calls


def replay(layout, call):
    """Draw a recorded operator call on a real layout, as the original code did."""
    layout.operator_context = call["ctx"]
    props = layout.operator(call["idname"], *call["args"], **call["kwargs"])
    for name, value in call["props"].items():
        setattr(props, name, value)


# ---------------------------------------------------------------------------
# Group submenus (one registered Menu class per group)

_group_classes = []  # registered classes, for unregister


def _group_menu_idname(side, index):
    return f"IEG_MT_{side}_group_{index}"


def _make_group_menu(side, index, group):
    menu_cls_name = MENUS[side]
    items = list(group["items"])

    def draw(self, context):
        by_idname = {}
        for call in record(getattr(bpy.types, menu_cls_name), self, context):
            by_idname.setdefault(call["idname"], call)
        for idname in items:
            call = by_idname.get(idname)
            if call is not None:
                replay(self.layout, call)

    idname = _group_menu_idname(side, index)
    return type(idname, (bpy.types.Menu,), {
        "bl_idname": idname,
        "bl_label": group["name"],
        # Like the stock IO menus: workspace "Filter Add-ons" must not drop IO entries.
        # `draw_ls` reads this from `self`, which is the group menu while recording.
        "bl_owner_use_filter": False,
        "draw": draw,
    })


# ---------------------------------------------------------------------------
# Main menu patch

def original_draw(menu_cls):
    draw = menu_cls.draw
    return getattr(draw, "_ieg_original", draw)


def _make_draw(side, original, groups):
    hidden = {idname for group in groups for idname in group["items"]}
    menu_ids = [_group_menu_idname(side, i) for i in range(len(groups))]
    menu_name = MENUS[side]

    def draw(self, context):
        layout = self.layout
        try:
            shown = []
            if groups:
                menu_cls = getattr(bpy.types, menu_name)
                present = {call["idname"] for call in record(menu_cls, self, context)}
                shown = [(group, menu_id) for group, menu_id in zip(groups, menu_ids)
                         if present.intersection(group["items"])]
        except Exception:
            # Our bug must not take File > Import / Export down: draw the stock menu.
            traceback.print_exc()
            original(self, context)
            return
        for group, menu_id in shown:
            layout.menu(menu_id, text=group["name"])
        if shown:
            layout.separator()
        original(_MenuProxy(self, FilteringLayout(layout, hidden)), context)

    draw._draw_funcs = original._draw_funcs  # shared: later append()/remove() land here
    draw._ieg_original = original
    return draw


def _ensure_draw_funcs(menu_cls):
    if not hasattr(menu_cls.draw, "_draw_funcs"):
        menu_cls._dyn_ui_initialize()  # private Blender API; what append() itself calls


def patch(config):
    """Apply `config` ({side: [{"name", "items"}]}). Safe to call again (re-applies)."""
    unpatch()
    for side, menu_name in MENUS.items():
        groups = [g for g in config.get(side, []) if g["items"]]
        for index, group in enumerate(groups):
            cls = _make_group_menu(side, index, group)
            bpy.utils.register_class(cls)
            _group_classes.append(cls)

        menu_cls = getattr(bpy.types, menu_name)
        _ensure_draw_funcs(menu_cls)
        menu_cls.draw = _make_draw(side, original_draw(menu_cls), groups)


def unpatch():
    for menu_name in MENUS.values():
        menu_cls = getattr(bpy.types, menu_name, None)
        if menu_cls is None:
            continue
        original = getattr(menu_cls.draw, "_ieg_original", None)
        if original is not None:
            menu_cls.draw = original

    while _group_classes:
        cls = _group_classes.pop()
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
