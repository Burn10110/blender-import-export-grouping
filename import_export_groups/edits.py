# SPDX-FileCopyrightText: 2026 Igor Burn
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Edits of one menu side's groups, behind the preference buttons.

Pure functions on plain data: each takes `groups` ([{"name", "items"}], never modified) and
returns an `Edit`, or None when the action does nothing there (its button is greyed out).
Ungrouped entries are not stored: they are whatever the menu has and no group holds,
in menu order, so moving an entry out of a group needs no position.
"""

from typing import NamedTuple

from .config import DEFAULT_GROUP_NAME

UNGROUPED = -1
NEW_GROUP = -2


class Edit(NamedTuple):
    groups: list
    select: tuple | None            # ("GROUP", index) / ("ITEM", idname) to select after
    index_map: dict | None = None   # old group index -> new (dropped: deleted); None: same
    expand: int | None = None       # group to expand so the selected entry stays visible


def _copy(groups):
    return [{"name": g["name"], "items": list(g["items"])} for g in groups]


def _position(groups, group, idname):
    if 0 <= group < len(groups):
        items = groups[group]["items"]
        if idname in items:
            return items.index(idname)
    return None


def unique_name(groups, base=DEFAULT_GROUP_NAME):
    """`base`, or Blender-style `base.001`, `base.002`... if taken."""
    names = {g["name"] for g in groups}
    name, n = base, 0
    while name in names:
        n += 1
        name = f"{base}.{n:03d}"
    return name


def add_group(groups, at=None):
    """New empty group at index `at` (default: last)."""
    at = len(groups) if at is None else max(0, min(at, len(groups)))
    new = _copy(groups)
    new.insert(at, {"name": unique_name(groups), "items": []})
    return Edit(new, ("GROUP", at), {i: i + (i >= at) for i in range(len(groups))})


def remove_group(groups, group):
    """Delete a group; its entries become ungrouped again."""
    if not 0 <= group < len(groups):
        return None
    new = _copy(groups)
    del new[group]
    select = ("GROUP", min(group, len(new) - 1)) if new else None
    index_map = {i: i - (i > group) for i in range(len(groups)) if i != group}
    return Edit(new, select, index_map)


def rename_group(groups, group, name):
    name = name.strip()
    if not 0 <= group < len(groups) or not name or name == groups[group]["name"]:
        return None
    new = _copy(groups)
    new[group]["name"] = name
    return Edit(new, ("GROUP", group))


def move_group(groups, group, step):
    other = group + step
    if not (0 <= group < len(groups) and 0 <= other < len(groups)):
        return None
    new = _copy(groups)
    new[group], new[other] = new[other], new[group]
    index_map = {i: i for i in range(len(groups))}
    index_map[group], index_map[other] = other, group
    return Edit(new, ("GROUP", other), index_map)


def remove_item(groups, group, idname):
    """Take an entry out of its group; the selection stays at the same place in the group."""
    pos = _position(groups, group, idname)
    if pos is None:
        return None
    new = _copy(groups)
    items = new[group]["items"]
    del items[pos]
    select = ("ITEM", items[min(pos, len(items) - 1)]) if items else ("GROUP", group)
    return Edit(new, select)


def move_item(groups, group, idname, step):
    """▲ (step -1) / ▼ (step +1) across group borders, see docs/step4-plan.md.

    Inside a group: swap with the neighbour. ▲ on the first entry: end of the previous
    group. ▼ on the last: start of the next group, or ungrouped after the last group.
    Ungrouped ▲: end of the last group. Ungrouped ▼: nothing (menu order is fixed).
    """
    if group == UNGROUPED:
        if step > 0 or not groups:
            return None
        return send_item(groups, UNGROUPED, idname, len(groups) - 1)

    pos = _position(groups, group, idname)
    if pos is None:
        return None
    new = _copy(groups)
    items = new[group]["items"]
    other = pos + step
    if 0 <= other < len(items):
        items[pos], items[other] = items[other], items[pos]
        return Edit(new, ("ITEM", idname))

    if step < 0:
        if group == 0:
            return None
        del items[pos]
        new[group - 1]["items"].append(idname)
        return Edit(new, ("ITEM", idname), expand=group - 1)

    del items[pos]
    if group + 1 < len(new):
        new[group + 1]["items"].insert(0, idname)
        return Edit(new, ("ITEM", idname), expand=group + 1)
    return Edit(new, ("ITEM", idname))  # out to ungrouped


def send_item(groups, group, idname, target):
    """Move an entry to the end of group `target`, to UNGROUPED, or into a NEW_GROUP."""
    if group != UNGROUPED and _position(groups, group, idname) is None:
        return None
    if target == group or not (target in (UNGROUPED, NEW_GROUP) or 0 <= target < len(groups)):
        return None
    new = _copy(groups)
    if group != UNGROUPED:
        new[group]["items"].remove(idname)
    if target == UNGROUPED:
        return Edit(new, ("ITEM", idname))
    if target == NEW_GROUP:
        new.append({"name": unique_name(groups), "items": []})
        target = len(new) - 1
    new[target]["items"].append(idname)
    return Edit(new, ("ITEM", idname), expand=target)
