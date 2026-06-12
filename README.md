# rename-many

A small Tkinter GUI for renaming many files and folders in a directory at once.

Pick a folder and every item in it appears as a row: the original name on the
left (read-only, but selectable and copyable), and an editable new name on the
right. Edit the names you want to change, then click **Rename** to apply them
all in one pass.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)

## Features

- **Folder picker** — type or paste a path (quotes from Explorer's "Copy as
  path" are stripped automatically) and press Enter or Ctrl+Enter, or click
  **Browse…**. You can also pass a folder on the command line.
- **Spreadsheet-style editing** — a scrollable grid of original → new names,
  with mouse-wheel support. Press Enter in a name to jump to the next row.
  Folders are listed too, marked with 📁 and sorted first.
- **Visual diff** — rows whose new name differs from the original are
  highlighted, and the **Rename (n)** button shows a live count of pending
  changes. **Revert All** resets every edit.
- **Safety checks** — before anything touches the disk, the new names are
  validated: empty names, characters that are illegal in file names, trailing
  dots/spaces on Windows, and duplicate targets (including a new name
  colliding with a file you didn't edit) are all rejected with a clear error.
- **Swap-safe renaming** — renames go through unique temporary names in two
  phases, so `a.txt ↔ b.txt` swaps, rename chains, and case-only renames
  (`readme.md` → `README.md`) all work. If an individual rename fails (e.g.,
  the file is open in another program), that item is restored to its original
  name and the failure is reported; the rest still go through.

## Installation

Requires Python 3.9+ with Tkinter (included in the standard python.org
installers). No third-party dependencies.

```sh
git clone https://github.com/LionKimbro/rename-many.git
cd rename-many
pip install .
```

This installs a `rename-many` command.

## Usage

```sh
rename-many              # start with an empty folder field
rename-many C:\some\dir  # open a folder immediately
```

Or run it without installing:

```sh
python src/renamemany/app.py
```

1. Choose a folder (Browse, or paste a path and press Enter).
2. Edit the names you want to change in the right-hand column.
3. Click **Rename (n)** and confirm.

The list refreshes after renaming and the status line reports the result.

## Caveats

There is no undo — the validation pass and the confirmation dialog are the
guardrails, so read the highlighted rows before you confirm.

## License

See [LICENSE](LICENSE).
