"""Add-on preferences: one tab per menu, groups and entries shown as a tree in a UIList.

The rows are a working copy (D8): rebuilt from the config + live menu discovery whenever
either changes, so they never need to be saved or trusted.
"""

import fnmatch

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)

from . import config, discovery

_state = {
    "config": config.empty(),
    "revision": 0,     # bumped on every config change
    "signature": {},   # side -> what the rows were last built from
}


def set_config(cfg):
    """Make `cfg` the config the preferences show."""
    _state["config"] = cfg
    _state["revision"] += 1


def get_config():
    return _state["config"]


# ---------------------------------------------------------------------------
# Rows

class IEG_Row(bpy.types.PropertyGroup):
    kind: EnumProperty(items=(
        ("GROUP", "Group", ""),
        ("ITEM", "Entry", ""),
        ("SEPARATOR", "Separator", ""),
    ))
    # `name` (label) is inherited from PropertyGroup and used by the name filter.
    idname: StringProperty()
    group_index: IntProperty(default=-1)  # -1: ungrouped entry / separator
    count: IntProperty()
    missing: BoolProperty()
    expanded: BoolProperty(name="Expand", default=True,
                           description="Show the entries of this group (view only)")


def _build_rows(rows, side, entries):
    expanded = {r.group_index: r.expanded for r in rows if r.kind == "GROUP"}
    labels = dict(entries)
    groups = _state["config"][side]
    grouped = {idname for group in groups for idname in group["items"]}

    rows.clear()

    def add(kind, name, **props):
        row = rows.add()
        row.kind = kind
        row.name = name
        for key, value in props.items():
            setattr(row, key, value)

    for index, group in enumerate(groups):
        add("GROUP", group["name"], group_index=index, count=len(group["items"]),
            expanded=expanded.get(index, True))
        for idname in group["items"]:
            label = labels.get(idname)
            missing = label is None
            if missing:
                label = discovery.operator_label(idname) or idname
            add("ITEM", label, idname=idname, group_index=index, missing=missing)

    if groups:
        add("SEPARATOR", "Other entries")
    for idname, label in entries:
        if idname not in grouped:
            add("ITEM", label, idname=idname)


def _side_props(prefs, side):
    return getattr(prefs, f"{side}_rows"), f"{side}_rows", f"{side}_active"


def _refresh(prefs, side, entries):
    """Rebuild the rows of `side` if their sources changed.

    Called from `draw`: writing AddonPreferences there is allowed (verified 5.2.2).
    """
    signature = (_state["revision"], tuple(entries))
    if _state["signature"].get(side) != signature:
        _build_rows(_side_props(prefs, side)[0], side, entries)
        _state["signature"][side] = signature


# ---------------------------------------------------------------------------
# UI

class IEG_UL_entries(bpy.types.UIList):
    """Tree-like list: group rows with their entries, then the ungrouped entries."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname,
                  index=0, flt_flag=0):
        row = layout.row(align=True)
        if item.kind == "GROUP":
            tri = "DISCLOSURE_TRI_DOWN" if item.expanded else "DISCLOSURE_TRI_RIGHT"
            row.prop(item, "expanded", text="", icon=tri, emboss=False)
            row.label(text=item.name, icon="FILE_FOLDER")
            count = row.row()
            count.alignment = "RIGHT"
            count.label(text=str(item.count))
        elif item.kind == "SEPARATOR":
            row.enabled = False
            row.label(text=item.name, icon="REMOVE")
        else:
            row.label(text="", icon="BLANK1")  # under the disclosure triangle
            if item.group_index >= 0:
                row.label(text="", icon="BLANK1")  # one level deeper
            if item.missing:
                row.label(text=f"{item.name}  (not available)", icon="ERROR")
            else:
                row.label(text=item.name)

    def draw_filter(self, context, layout):
        # Name filter only: sorting would break the tree.
        layout.row().prop(self, "filter_name", text="", icon="VIEWZOOM")

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        show = self.bitflag_filter_item
        if not self.filter_name:
            collapsed = {r.group_index for r in rows if r.kind == "GROUP" and not r.expanded}
            flags = [0 if r.kind == "ITEM" and r.group_index in collapsed else show
                     for r in rows]
            return flags, []

        # Matching entries, plus the group header / separator they sit under.
        pattern = f"*{self.filter_name.lower()}*"
        matched = [r.kind != "SEPARATOR" and fnmatch.fnmatchcase(r.name.lower(), pattern)
                   for r in rows]
        groups_hit = {r.group_index for r, m in zip(rows, matched) if m}
        flags = []
        for r, m in zip(rows, matched):
            visible = (m
                       or (r.kind == "GROUP" and r.group_index in groups_hit)
                       or (r.kind == "SEPARATOR" and -1 in groups_hit))
            flags.append(show if visible else 0)
        return flags, []


class IEG_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    tab: EnumProperty(name="Menu", items=(
        ("import", "Import", "File > Import"),
        ("export", "Export", "File > Export"),
    ))
    import_rows: CollectionProperty(type=IEG_Row)
    import_active: IntProperty()
    export_rows: CollectionProperty(type=IEG_Row)
    export_active: IntProperty()

    def draw(self, context):
        layout = self.layout
        layout.row().prop(self, "tab", expand=True)

        side = self.tab
        _refresh(self, side, discovery.menu_entries(side, context))

        _rows, rows_prop, active_prop = _side_props(self, side)
        layout.template_list("IEG_UL_entries", side, self, rows_prop, self, active_prop,
                             rows=12)


classes = (IEG_Row, IEG_UL_entries, IEG_Preferences)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _state["signature"].clear()
