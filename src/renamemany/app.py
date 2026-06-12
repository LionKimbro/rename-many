"""Rename Many — a Tkinter tool for renaming many files and folders at once.

Pick a folder; every item in it appears as a row with the original name on
the left (read-only, but selectable) and an editable new name on the right.
Edit the names you want to change, then click Rename.

Renaming is done in two phases through temporary names, so swaps like
a.txt <-> b.txt and case-only renames work correctly.
"""

import os
import sys
import uuid
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox

CHANGED_BG = "#fff2a8"      # highlight for rows whose name was edited
READONLY_BG = "#f0f0f0"     # background of the left (original name) column

ALGO_HELP = (
    "The code below runs once for every listed item.  Before each run, OLD is "
    "set to the original\nname (a str); afterwards NEW is read back as the new "
    "name.  Full Python is available (import re,\netc.).  While you edit, the "
    "New-name column previews the result every 2 seconds — click Rename\n"
    "when it looks right, or Revert All to discard."
)

_MISSING = object()         # sentinel: user code did not set NEW

# Characters that may not appear in a file name on this platform.
BAD_CHARS = '<>:"/\\|?*' if sys.platform == "win32" else "/"


class RenameManyApp:
    def __init__(self, root):
        self.root = root
        root.title("Rename Many")
        root.geometry("900x650")

        self.folder = None          # Path of the currently listed folder
        self.rows = []              # one dict per listed item
        self.entry_bg = None        # default Entry background, captured lazily

        self.algo_visible = False
        self._algo_after_id = None  # pending after() callback for the preview
        self._algo_last_code = None # code as of the last preview run

        self._build_path_bar()
        self._build_header()
        self._build_main_area()
        self._build_bottom_bar()
        self._build_algo_panel()

    # ------------------------------------------------------------------ UI

    def _build_path_bar(self):
        bar = tk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(bar, text="Folder:").pack(side="left")
        self.path_var = tk.StringVar()
        self.path_entry = tk.Entry(bar, textvariable=self.path_var)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.path_entry.bind("<Return>", lambda e: self.populate())
        self.path_entry.bind("<Control-Return>", lambda e: self.populate())
        tk.Button(bar, text="Browse…", command=self.browse).pack(side="left")

    def _build_header(self):
        hdr = tk.Frame(self.root)
        hdr.pack(fill="x", padx=(8, 28))
        hdr.columnconfigure(1, weight=1, uniform="cols")
        hdr.columnconfigure(2, weight=1, uniform="cols")
        tk.Label(hdr, width=2).grid(row=0, column=0, padx=(2, 0))
        tk.Label(hdr, text="Original name", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=2)
        tk.Label(hdr, text="New name", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=(2, 4))

    def _build_main_area(self):
        wrap = tk.Frame(self.root, bd=1, relief="sunken")
        wrap.pack(fill="both", expand=True, padx=8, pady=4)

        self.canvas = tk.Canvas(wrap, highlightthickness=0)
        vsb = tk.Scrollbar(wrap, orient="vertical", width=20,
                           command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")
        self.inner.columnconfigure(1, weight=1, uniform="cols")
        self.inner.columnconfigure(2, weight=1, uniform="cols")

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self.inner_id, width=e.width))

        # Mouse-wheel scrolling anywhere in the window (Windows/macOS deltas
        # plus the X11 button events).
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all(
            "<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all(
            "<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))

    def _build_bottom_bar(self):
        bar = self.bottom_bar = tk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=(4, 8))
        self.rename_btn = tk.Button(bar, text="Rename (0)", state="disabled",
                                    command=self.do_rename)
        self.rename_btn.pack(side="right")
        self.revert_btn = tk.Button(bar, text="Revert All",
                                    command=self.revert_all)
        self.revert_btn.pack(side="right", padx=4)
        self.algo_btn = tk.Button(bar, text="Algorithmically Rename…",
                                  command=self.toggle_algo_panel)
        self.algo_btn.pack(side="right")
        self.status = tk.Label(bar, text="Pick a folder to begin.", anchor="w")
        self.status.pack(side="left", fill="x", expand=True)

    def _build_algo_panel(self):
        # Built once, packed/unpacked by toggle_algo_panel().
        self.algo_frame = tk.Frame(self.root, bd=1, relief="groove")
        tk.Label(self.algo_frame, text=ALGO_HELP, justify="left",
                 anchor="w").pack(fill="x", padx=6, pady=(6, 2))

        body = tk.Frame(self.algo_frame)
        body.pack(fill="x", padx=6)
        self.algo_text = tk.Text(body, height=8, undo=True,
                                 font="TkFixedFont")
        sb = tk.Scrollbar(body, orient="vertical",
                          command=self.algo_text.yview)
        self.algo_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.algo_text.pack(side="left", fill="both", expand=True)
        self.algo_text.insert(
            "1.0", '# Example: NEW = OLD.replace(" ", "_")\nNEW = OLD\n')

        btns = tk.Frame(self.algo_frame)
        btns.pack(fill="x", padx=6, pady=(2, 6))
        self.algo_status = tk.Label(btns, text="", anchor="w")
        self.algo_status.pack(side="left", fill="x", expand=True)
        tk.Button(btns, text="Close",
                  command=self.toggle_algo_panel).pack(side="right")
        tk.Button(btns, text="Run Now",
                  command=self._run_algorithm).pack(side="right", padx=4)

    # ------------------------------------------------------------- actions

    def browse(self):
        current = self.path_var.get().strip().strip('"')
        kwargs = {}
        if current and Path(current).expanduser().is_dir():
            kwargs["initialdir"] = current
        chosen = filedialog.askdirectory(title="Choose folder", **kwargs)
        if chosen:
            self.path_var.set(os.path.normpath(chosen))
            self.populate()

    def populate(self):
        raw = self.path_var.get().strip().strip('"')
        if not raw:
            self._set_status("Enter a folder path first.")
            return
        folder = Path(raw).expanduser()
        if not folder.is_dir():
            messagebox.showerror("Rename Many", f"Not a folder:\n{folder}")
            return
        try:
            entries = list(folder.iterdir())
        except OSError as exc:
            messagebox.showerror("Rename Many", f"Cannot read folder:\n{exc}")
            return

        self.folder = folder
        for child in self.inner.winfo_children():
            child.destroy()
        self.rows = []

        entries.sort(key=lambda p: (not p.is_dir(), p.name.casefold()))
        for i, p in enumerate(entries):
            self._add_row(i, p.name, p.is_dir())

        self.canvas.yview_moveto(0)
        self._set_status(f"{len(self.rows)} item(s) in {folder}")
        self._update_rename_button()

    def _add_row(self, index, name, is_dir):
        marker = tk.Label(self.inner, text="\U0001f4c1" if is_dir else "",
                          width=2)
        marker.grid(row=index, column=0, padx=(2, 0))

        orig = tk.Entry(self.inner, readonlybackground=READONLY_BG)
        orig.insert(0, name)
        orig.configure(state="readonly")
        orig.grid(row=index, column=1, sticky="ew", padx=2, pady=1)

        var = tk.StringVar(value=name)
        new = tk.Entry(self.inner, textvariable=var)
        new.grid(row=index, column=2, sticky="ew", padx=(2, 4), pady=1)
        if self.entry_bg is None:
            self.entry_bg = new.cget("background")

        row = {"name": name, "is_dir": is_dir, "var": var, "entry": new}
        var.trace_add("write", lambda *_, r=row: self._on_row_edited(r))
        new.bind("<Return>", lambda e, i=index: self._focus_row(i + 1))
        self.rows.append(row)

    def revert_all(self):
        for row in self.rows:
            row["var"].set(row["name"])

    # -------------------------------------------------- algorithmic rename

    def toggle_algo_panel(self):
        if self.algo_visible:
            self.algo_visible = False
            self.algo_frame.pack_forget()
            if self._algo_after_id is not None:
                self.root.after_cancel(self._algo_after_id)
                self._algo_after_id = None
        else:
            self.algo_visible = True
            self.algo_frame.pack(fill="x", padx=8, pady=(0, 4),
                                 before=self.bottom_bar)
            self.algo_text.focus_set()
            # Don't run until the user actually edits the code.
            self._algo_last_code = self.algo_text.get("1.0", "end-1c")
            self._algo_after_id = self.root.after(2000, self._algo_tick)

    def _algo_tick(self):
        self._algo_after_id = None
        if not self.algo_visible:
            return
        code = self.algo_text.get("1.0", "end-1c")
        if code != self._algo_last_code:
            self._run_algorithm()
        self._algo_after_id = self.root.after(2000, self._algo_tick)

    def _run_algorithm(self):
        code = self.algo_text.get("1.0", "end-1c")
        self._algo_last_code = code
        if not code.strip():
            self.algo_status.configure(text="")
            return
        try:
            compiled = compile(code, "<algorithm>", "exec")
        except SyntaxError as exc:
            self.algo_status.configure(text=f"Syntax error: {exc}")
            return
        if not self.rows:
            self.algo_status.configure(
                text="No folder loaded — nothing to preview.")
            return

        updated = errors = 0
        first_error = None
        for row in self.rows:
            globs = {"OLD": row["name"]}
            try:
                exec(compiled, globs)
                new = globs.get("NEW", _MISSING)
                if new is _MISSING:
                    raise NameError("code did not set NEW")
                if not isinstance(new, str):
                    raise TypeError(
                        f"NEW is {type(new).__name__}, expected str")
            except Exception as exc:  # user code can raise anything
                errors += 1
                if first_error is None:
                    first_error = (f'{row["name"]}: '
                                   f"{type(exc).__name__}: {exc}")
                continue
            if row["var"].get() != new:
                row["var"].set(new)
                updated += 1

        text = f"Preview: {updated} name(s) updated"
        if errors:
            text += f"; {errors} error(s) — first: {first_error}"
        self.algo_status.configure(text=text)

    def do_rename(self):
        if self.folder is None:
            return
        changes = [(r["name"], r["var"].get())
                   for r in self.rows if r["var"].get() != r["name"]]
        if not changes:
            return

        errors = self._validate(changes)
        if errors:
            messagebox.showerror("Cannot rename", "\n".join(errors))
            return

        if not messagebox.askokcancel(
                "Rename Many", f"Rename {len(changes)} item(s)?"):
            return

        # Phase 1: move every changed item to a unique temporary name, so
        # swaps and case-only renames cannot collide with each other.
        problems = []
        staged = []
        for old, new in changes:
            src = self.folder / old
            tmp = self.folder / f"~renametmp-{uuid.uuid4().hex}"
            try:
                src.rename(tmp)
                staged.append((old, new, tmp))
            except OSError as exc:
                problems.append(f"{old}: {exc}")

        # Phase 2: move the temporaries to their final names.
        renamed = 0
        for old, new, tmp in staged:
            target = self.folder / new
            try:
                if target.exists() or target.is_symlink():
                    raise OSError("target already exists")
                tmp.rename(target)
                renamed += 1
            except OSError as exc:
                problems.append(f"{old} → {new}: {exc}")
                try:
                    tmp.rename(self.folder / old)
                except OSError:
                    problems.append(
                        f"could not restore {old}; it is now named {tmp.name}")

        self.populate()
        if problems:
            messagebox.showerror("Rename finished with errors",
                                 "\n".join(problems))
        self._set_status(f"Renamed {renamed} of {len(changes)} item(s).")

    # ----------------------------------------------------------- validation

    def _validate(self, changes):
        errors = []
        for old, new in changes:
            if not new.strip():
                errors.append(f'"{old}": new name is empty')
                continue
            if any(c in BAD_CHARS for c in new):
                errors.append(
                    f'"{new}": contains a character not allowed '
                    f'in file names ({BAD_CHARS})')
            if new in (".", ".."):
                errors.append(f'"{new}": not a valid file name')
            if sys.platform == "win32" and new[-1] in ". ":
                errors.append(
                    f'"{new}": Windows does not allow names ending '
                    'with a dot or space')

        # Detect collisions in the final state (unchanged rows keep their
        # name, so this also catches a new name hitting an existing file).
        seen = {}
        for row in self.rows:
            target = row["var"].get()
            seen.setdefault(os.path.normcase(target), []).append(target)
        for names in seen.values():
            if len(names) > 1:
                errors.append("duplicate target name: " + ", ".join(names))
        return errors

    # -------------------------------------------------------------- helpers

    def _on_row_edited(self, row):
        changed = row["var"].get() != row["name"]
        row["entry"].configure(
            background=CHANGED_BG if changed else self.entry_bg)
        self._update_rename_button()

    def _update_rename_button(self):
        count = sum(1 for r in self.rows if r["var"].get() != r["name"])
        self.rename_btn.configure(
            text=f"Rename ({count})",
            state="normal" if count else "disabled")

    def _focus_row(self, index):
        if not 0 <= index < len(self.rows):
            return
        entry = self.rows[index]["entry"]
        entry.focus_set()
        entry.icursor("end")
        entry.select_range(0, "end")
        self._scroll_into_view(entry)

    def _scroll_into_view(self, widget):
        self.canvas.update_idletasks()
        total = self.inner.winfo_height()
        if total <= 0:
            return
        top = self.canvas.canvasy(0)
        view_height = self.canvas.winfo_height()
        y, h = widget.winfo_y(), widget.winfo_height()
        if y < top:
            self.canvas.yview_moveto(y / total)
        elif y + h > top + view_height:
            self.canvas.yview_moveto((y + h - view_height) / total)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) or
                                 (-1 if event.delta > 0 else 1), "units")

    def _set_status(self, text):
        self.status.configure(text=text)


def main():
    root = tk.Tk()
    app = RenameManyApp(root)
    if len(sys.argv) > 1:
        app.path_var.set(sys.argv[1])
        app.populate()
    root.mainloop()


if __name__ == "__main__":
    main()
