# SPDX-FileCopyrightText: 2026 Igor Burn
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Add-on preferences: one tab per menu, groups and entries shown as a tree in a UIList.

The rows are a working copy (D8): rebuilt from the config + live menu discovery whenever
either changes, so they never need to be saved or trusted. Every edit is written to
groups.json and re-patches the menus at once; there is no Save button.
"""

import fnmatch
import os

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)

from . import config, discovery, edits, menu_patch

_state = {
    "config": config.empty(),
    "revision": 0,      # bumped on every config change
    "signature": {},    # side -> what the rows were last built from
    "building": False,  # rows are being written by us, not edited by the user
    "filter_opened": set(),  # UIList ids whose filter field was opened this session
}


def set_config(cfg):
    """Make `cfg` the config the preferences show."""
    _state["config"] = cfg
    _state["revision"] += 1


def get_config():
    return _state["config"]


def _apply(side, groups):
    """Save `groups` as the new `side`, re-patch the menus, return the clean config.

    Raises OSError if the file cannot be written; nothing is applied then.
    """
    return _apply_config({**_state["config"], side: groups})


def _apply_config(cfg):
    """Save `cfg` as the whole config, re-patch the menus, return the clean config."""
    cfg = config.normalize(cfg)
    config.save(cfg)
    menu_patch.patch(cfg)
    set_config(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Rows

def _on_rename(row, context):
    if _state["building"] or row.kind != "GROUP":
        return
    edit = edits.rename_group(_state["config"][row.side], row.group_index, row.name)
    if edit is not None:
        try:
            _apply(row.side, edit.groups)
            return
        except OSError as ex:
            print(f"Import/Export Groups: cannot save {config.FILENAME}: {ex}")
    # Empty / unchanged / not saved: the next redraw rebuilds the row with the stored
    # name. Not rebuilt here: this row is the one being edited.
    set_config(_state["config"])


class IEG_Row(bpy.types.PropertyGroup):
    kind: EnumProperty(items=(
        ("GROUP", "Group", ""),
        ("ITEM", "Entry", ""),
        ("SEPARATOR", "Separator", ""),
    ))
    # Label; used by the name filter, editable (double-click) on group rows.
    name: StringProperty(update=_on_rename)
    side: StringProperty()
    idname: StringProperty()
    group_index: IntProperty(default=edits.UNGROUPED)  # ungrouped entry / separator
    count: IntProperty()
    missing: BoolProperty()
    expanded: BoolProperty(name="Expand", default=True,
                           description="Show the entries of this group (view only)")


def _build_rows(rows, side, entries, index_map=None, expand=None):
    """Rebuild the rows of `side`. Collapse state is keyed by group index: `index_map`
    (old -> new) carries it along when groups moved, `expand` opens one group."""
    expanded = {r.group_index: r.expanded for r in rows if r.kind == "GROUP"}
    if index_map is not None:
        expanded = {index_map[i]: v for i, v in expanded.items() if i in index_map}
    if expand is not None:
        expanded[expand] = True
    labels = dict(entries)
    groups = _state["config"][side]
    grouped = {idname for group in groups for idname in group["items"]}

    def add(kind, name, **props):
        row = rows.add()
        row.kind = kind
        row.name = name
        row.side = side
        for key, value in props.items():
            setattr(row, key, value)

    _state["building"] = True
    try:
        rows.clear()
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
    finally:
        _state["building"] = False


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


def _find_row(rows, key, fallback):
    if key is not None:
        kind, value = key
        for index, row in enumerate(rows):
            if row.kind == kind and value == (row.group_index if kind == "GROUP" else row.idname):
                return index
    return max(0, min(fallback, len(rows) - 1))


def _commit(prefs, side, edit, context):
    """Apply `edit`, rebuild the rows of `side` and select the row the edit points at."""
    _apply(side, edit.groups)
    rows, _, active_prop = _side_props(prefs, side)
    entries = discovery.menu_entries(side, context)
    _build_rows(rows, side, entries, edit.index_map, edit.expand)
    _state["signature"][side] = (_state["revision"], tuple(entries))
    setattr(prefs, active_prop, _find_row(rows, edit.select, getattr(prefs, active_prop)))


def _active(context):
    """(prefs, side, selected row or None) of the visible tab."""
    addon = context.preferences.addons.get(__package__)
    if addon is None:
        return None, None, None
    prefs = addon.preferences
    side = prefs.tab
    rows, _, active_prop = _side_props(prefs, side)
    index = getattr(prefs, active_prop)
    return prefs, side, (rows[index] if 0 <= index < len(rows) else None)


# ---------------------------------------------------------------------------
# Edit operators

class _EditOperator:
    bl_options = {"INTERNAL"}

    @staticmethod
    def make_edit(groups, row, props):
        """The `edits.Edit` for the selected `row`, or None. `props` is None in poll."""
        raise NotImplementedError

    @classmethod
    def poll(cls, context):
        prefs, side, row = _active(context)
        return prefs is not None and cls.make_edit(get_config()[side], row, None) is not None

    def execute(self, context):
        prefs, side, row = _active(context)
        edit = self.make_edit(get_config()[side], row, self)
        if edit is None:
            return {"CANCELLED"}
        try:
            _commit(prefs, side, edit, context)
        except OSError as ex:
            self.report({"ERROR"}, f"Cannot save {config.FILENAME}: {ex}")
            return {"CANCELLED"}
        return {"FINISHED"}


class IEG_OT_add_group(_EditOperator, bpy.types.Operator):
    bl_idname = "import_export_groups.add_group"
    bl_label = "Add Group"
    bl_description = "Add a new group after the selected one (double-click it to rename)"

    @staticmethod
    def make_edit(groups, row, props):
        at = row.group_index + 1 if row is not None and row.group_index >= 0 else None
        return edits.add_group(groups, at)


class IEG_OT_remove(_EditOperator, bpy.types.Operator):
    bl_idname = "import_export_groups.remove"
    bl_label = "Remove"
    bl_description = ("Remove the selected group (its entries become ungrouped) "
                      "or take the selected entry out of its group")

    @staticmethod
    def make_edit(groups, row, props):
        if row is None:
            return None
        if row.kind == "GROUP":
            return edits.remove_group(groups, row.group_index)
        if row.kind == "ITEM":
            return edits.remove_item(groups, row.group_index, row.idname)
        return None


class _Move(_EditOperator):
    step = 0

    @classmethod
    def make_edit(cls, groups, row, props):
        if row is None:
            return None
        if row.kind == "GROUP":
            return edits.move_group(groups, row.group_index, cls.step)
        if row.kind == "ITEM":
            return edits.move_item(groups, row.group_index, row.idname, cls.step)
        return None


class IEG_OT_move_up(_Move, bpy.types.Operator):
    bl_idname = "import_export_groups.move_up"
    bl_label = "Move Up"
    bl_description = ("Move the selected group or entry up; "
                      "an entry crosses into the group above")
    step = -1


class IEG_OT_move_down(_Move, bpy.types.Operator):
    bl_idname = "import_export_groups.move_down"
    bl_label = "Move Down"
    bl_description = ("Move the selected group or entry down; an entry crosses into "
                      "the group below, out of the last group to ungrouped")
    step = 1


class IEG_OT_send_to(_EditOperator, bpy.types.Operator):
    bl_idname = "import_export_groups.send_to"
    bl_label = "Send to Group"
    bl_description = "Move the selected entry to this group"

    target: IntProperty(default=edits.UNGROUPED, options={"SKIP_SAVE"})

    @staticmethod
    def make_edit(groups, row, props):
        if row is None or row.kind != "ITEM":
            return None
        if props is None:  # poll: any entry can be sent somewhere (a new group)
            return edits.send_item(groups, row.group_index, row.idname, edits.NEW_GROUP)
        return edits.send_item(groups, row.group_index, row.idname, props.target)


class IEG_MT_send_to(bpy.types.Menu):
    bl_label = "Send to Group"

    def draw(self, context):
        layout = self.layout
        _prefs, side, row = _active(context)
        if row is None or row.kind != "ITEM":
            layout.label(text="Select an entry first")
            return
        op_id = IEG_OT_send_to.bl_idname

        def radio(on):
            return "RADIOBUT_ON" if on else "RADIOBUT_OFF"

        for index, group in enumerate(get_config()[side]):
            layout.operator(op_id, text=group["name"], translate=False,
                            icon=radio(row.group_index == index)).target = index
        layout.separator()
        layout.operator(op_id, text="Ungrouped",
                        icon=radio(row.group_index == edits.UNGROUPED)).target = edits.UNGROUPED
        layout.operator(op_id, text="New Group", icon="ADD").target = edits.NEW_GROUP


# ---------------------------------------------------------------------------
# File operators

def _summary(cfg):
    return ", ".join(f"{len(cfg[side])} {side}" for side in config.SIDES) + " groups"


class IEG_OT_export_json(bpy.types.Operator, ExportHelper):
    bl_idname = "import_export_groups.export_json"
    bl_label = "Export Groups"
    bl_description = "Save all import and export groups to a JSON file"
    bl_options = {"INTERNAL"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "import_export_groups.json"
        return super().invoke(context, event)

    def execute(self, context):
        cfg = get_config()
        try:
            config.save(cfg, self.filepath, backup=False)
        except OSError as ex:
            self.report({"ERROR"}, f"Cannot write {self.filepath}: {ex}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {_summary(cfg)} to {self.filepath}")
        return {"FINISHED"}


class IEG_OT_import_json(bpy.types.Operator, ImportHelper):
    bl_idname = "import_export_groups.import_json"
    bl_label = "Import Groups"
    bl_description = "Replace all import and export groups with the ones from a JSON file"
    bl_options = {"INTERNAL"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        # The file browser cannot ask for confirmation itself: hand over to an operator
        # that shows what will be replaced.
        bpy.ops.import_export_groups.import_json_confirm("INVOKE_DEFAULT",
                                                        filepath=self.filepath)
        return {"FINISHED"}


class IEG_OT_import_json_confirm(bpy.types.Operator):
    bl_idname = "import_export_groups.import_json_confirm"
    bl_label = "Replace All Groups"
    bl_description = "Replace all import and export groups with the ones from a JSON file"
    bl_options = {"INTERNAL"}

    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})

    def _read(self):
        try:
            return config.read_file(self.filepath)
        except (OSError, ValueError) as ex:
            self.report({"ERROR"}, f"Cannot import {self.filepath}: {ex}")
            return None

    def invoke(self, context, event):
        cfg = self._read()
        if cfg is None:
            return {"CANCELLED"}
        return context.window_manager.invoke_confirm(
            self, event, title="Replace All Groups",
            message=(f"Replace {_summary(get_config())} with {_summary(cfg)} from the file? "
                     f"The current setup is kept as {config.FILENAME}.bak."),
            confirm_text="Replace", icon="WARNING")

    def execute(self, context):
        cfg = self._read()  # read again: the file may have changed while the dialog was up
        if cfg is None:
            return {"CANCELLED"}
        try:
            cfg = _apply_config(cfg)
        except OSError as ex:
            self.report({"ERROR"}, f"Cannot save {config.FILENAME}: {ex}")
            return {"CANCELLED"}
        addon = context.preferences.addons.get(__package__)
        if addon is not None:
            # A new setup: drop the old collapse state and selection; draw rebuilds rows.
            for side in config.SIDES:
                rows, _, active_prop = _side_props(addon.preferences, side)
                rows.clear()
                setattr(addon.preferences, active_prop, 0)
            _state["signature"].clear()
        self.report({"INFO"}, f"Imported {_summary(cfg)}")
        return {"FINISHED"}


class IEG_OT_open_config_folder(bpy.types.Operator):
    bl_idname = "import_export_groups.open_config_folder"
    bl_label = "Open Config Folder"
    bl_description = (f"Open the folder with {config.FILENAME} "
                      "(and its .bak) in the file manager")
    bl_options = {"INTERNAL"}

    def execute(self, context):
        folder = os.path.dirname(config.config_path())  # created if missing
        return bpy.ops.wm.path_open(filepath=folder)


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
            row.prop(item, "name", text="", icon="FILE_FOLDER", emboss=False)  # double-click
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
        # Filter field open by default. The Python instance is recreated on every redraw
        # (verified 5.2.2), the flag lives in the C list: open it once per list and session,
        # so the user can still fold it away.
        if self.list_id not in _state["filter_opened"]:
            _state["filter_opened"].add(self.list_id)
            self.use_filter_show = True

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

        rows, rows_prop, active_prop = _side_props(self, side)
        split = layout.row()
        split.template_list("IEG_UL_entries", side, self, rows_prop, self, active_prop,
                            rows=12)

        col = split.column(align=True)
        col.operator(IEG_OT_add_group.bl_idname, text="", icon="ADD")
        col.operator(IEG_OT_remove.bl_idname, text="", icon="REMOVE")
        col.separator()
        sub = col.column(align=True)
        index = getattr(self, active_prop)
        sub.enabled = 0 <= index < len(rows) and rows[index].kind == "ITEM"
        sub.menu(IEG_MT_send_to.__name__, text="", icon="FORWARD")
        col.separator()
        col.operator(IEG_OT_move_up.bl_idname, text="", icon="TRIA_UP")
        col.operator(IEG_OT_move_down.bl_idname, text="", icon="TRIA_DOWN")

        row = layout.row()
        row.operator(IEG_OT_export_json.bl_idname, text="Export JSON...", icon="EXPORT")
        row.operator(IEG_OT_import_json.bl_idname, text="Import JSON...", icon="IMPORT")
        row.operator(IEG_OT_open_config_folder.bl_idname, icon="FILE_FOLDER")


classes = (
    IEG_Row,
    IEG_OT_add_group,
    IEG_OT_remove,
    IEG_OT_move_up,
    IEG_OT_move_down,
    IEG_OT_send_to,
    IEG_MT_send_to,
    IEG_OT_export_json,
    IEG_OT_import_json,
    IEG_OT_import_json_confirm,
    IEG_OT_open_config_folder,
    IEG_UL_entries,
    IEG_Preferences,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _state["signature"].clear()
