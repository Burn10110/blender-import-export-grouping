# Import/Export Groups

*[Русская версия](README.ru.md)*

A Blender extension that organises **File > Import** and **File > Export** into your own named
groups, each shown as a submenu: "Photogrammetry", "Flat formats", "FBX for Unreal", whatever
fits your work.

Every add-on you install adds its entries to these two menus, and after a while they become a
long flat list. This extension only changes how the list is arranged:

- A grouped entry is **moved** into its group's submenu (not duplicated).
- Everything you have not grouped stays where it was, in its original order.
- Clicking an entry runs the original importer/exporter with its usual file browser and options.
  No presets, no wrappers.
- Import and Export have independent group lists.

## Requirements

Blender **4.2 or newer** (extension format). Tested on 4.5 LTS and 5.2 LTS.

## Installation

1. Download `import-export-groups-<version>.zip` from the
   [Releases](https://github.com/Burn10110/blender-import-export-grouping/releases) page.
2. In Blender: **Edit > Preferences > Add-ons**, the **⌄** menu in the top right >
   **Install from Disk...**, pick the zip. Dragging the zip into the Blender window works too.
3. Make sure **Import/Export Groups** is enabled under **Add-ons**.

## Usage

Open **Edit > Preferences > Add-ons > Import/Export Groups** and expand it.

- **Import / Export** tabs switch between the two menus.
- The list shows your groups with their entries, then **Other entries**: everything currently in
  the menu that is not grouped.
- **+** adds a group after the selected one. Double-click a group to rename it.
- **−** removes the selected group (its entries become ungrouped again) or takes the selected
  entry out of its group.
- **→** (Send to Group) moves the selected entry into an existing group, a **New Group**, or back
  to **Ungrouped**.
- **▲ / ▼** move the selected group or entry. An entry moved past the edge of its group crosses
  into the neighbouring group; moving it down out of the last group ungroups it.
- The search field filters the list by name.

Every change is saved and applied at once; there is no Save button and no restart.

In the menus, groups appear at the top in your order, followed by a separator and the rest of
the stock menu.

### When an add-on is disabled

If an entry belongs to an add-on that is currently disabled or uninstalled, it is skipped in the
menu and shown as **(not available)** in the preferences. It stays in your groups and comes
back when the add-on is enabled again. A group with no available entries is not shown.
Entries added by add-ons installed later appear ungrouped in the normal list.

### Moving groups between machines

- **Export JSON...** saves all Import and Export groups to a file.
- **Import JSON...** replaces all groups with the ones from a file (asks for confirmation; the
  previous file is kept as `groups.json.bak`).
- **Open Config Folder** opens the folder with `groups.json`, the file that holds your groups.
  It lives in Blender's per-extension user folder, separate from the extension's own files.

### Disabling

Disabling the extension restores the stock menus immediately. Your groups stay in `groups.json`
and are applied again when you re-enable it.

## Limitations

- One level of groups; no nested submenus.
- Groups only re-arrange entries; they do not store operator settings (use the operators' own
  presets or Blender's Collection Exporters for that).
- Only File > Import and File > Export are handled.
- If another add-on replaces the whole draw function of these menus (instead of appending to
  them, as add-ons normally do), and it loads after this one, the groups may not show up.

## Building from source

```
blender --command extension build --source-dir import_export_groups --output-filepath dist/import-export-groups-1.0.0.zip
```

## License

[GPL-3.0-or-later](LICENSE). © 2026 Igor Burn.
