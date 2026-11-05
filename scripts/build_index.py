#!/usr/bin/env python3
"""Check every plugin, browser extension and layout and write index.json, the list Valerie installs from.

Plugins are folders in plugins/ (a plugin.yaml), extensions are folders in extensions/ (an unpacked web extension's
manifest.json), layouts are folders in layouts/ (a plugin that also has layouts/<folder name>.yaml and the panels it uses). Each file is pinned to the commit it was indexed at (and its sha256), so what Valerie downloads is
exactly what was reviewed. `--check` only validates (for pull requests) and prints what each one can run or reach,
for the reviewer.
"""
import base64, hashlib, json, os, re, subprocess, sys
import yaml

REPO = os.environ.get("GITHUB_REPOSITORY", "cullen-b/valerie-plugins")
SHA = os.environ.get("GITHUB_SHA") or subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
MANIFEST_KEYS = {"description", "author", "enabled", "matches", "commands", "on_page_load", "settings", "run_at", "all_frames",
                 "rerun_when_url_changes", "permissions", "events", "search", "sidebar", "spaces"}
# What a layout may contain: keep these in step with src/window_layout.rs in Valerie.
LAYOUT_KEYS = {"title", "description", "settings", "css", "window", "floating", "replace"}
LOOK_SECTIONS = {"layout", "sidebar", "window", "command_bar", "start_page", "toast_seconds"}
WINDOWS = {"sidebar", "command_bar", "chats", "terminal", "little_window", "answer", "welcome", "plugins"}
PARTS = {"pages", "sidebar", "top_bar", "terminal"}
PREVIEW_LIMIT = 60_000

def author_of(path):
    """The GitHub login of whoever first added the plugin (from a noreply address), else their name."""
    out = subprocess.run(["git", "log", "--reverse", "--format=%ae%x09%an", "--", path], capture_output=True, text=True).stdout.splitlines()
    if not out:
        return ""
    email, name = out[0].split("\t", 1)
    m = re.match(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", email)
    return m.group(1) if m else name

def files_of(top, name, folder, problems):
    """Every file in the folder, pinned and checksummed; problems for anything too big, binary or too many."""
    files = []
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for n in sorted(names):
            if n.startswith("."):
                continue
            p = os.path.join(root, n)
            rel = os.path.relpath(p, folder).replace(os.sep, "/")
            data = open(p, "rb").read()
            if len(data) > 200_000:
                problems.append(f"{rel} is over 200 KB")
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                problems.append(f"{rel} isn't text")
            files.append({"path": rel, "url": f"https://raw.githubusercontent.com/{REPO}/{SHA}/{top}/{name}/{rel}",
                          "sha256": hashlib.sha256(data).hexdigest()})
    if len(files) > 30:
        problems.append("more than 30 files")
    return files

def updated(folder):
    return subprocess.run(["git", "log", "-1", "--format=%cs", "--", folder], capture_output=True, text=True).stdout.strip()

# Extension permissions a reviewer should look at closely: they reach outside the page or the browser.
RISKY_PERMISSIONS = {"nativeMessaging", "debugger", "proxy", "webRequest", "webRequestBlocking", "cookies", "history",
                     "downloads", "management", "privacy", "<all_urls>"}

def check_extension(name, folder):
    problems = []
    if not NAME.match(name):
        problems.append("folder name must be lowercase letters, digits and hyphens")
    path = os.path.join(folder, "manifest.json")
    if not os.path.exists(path):
        return None, ["no manifest.json"]
    try:
        m = json.loads(open(path, encoding="utf-8-sig").read())
    except Exception as e:
        return None, [f"manifest.json doesn't parse: {e}"]
    if not isinstance(m, dict):
        return None, ["manifest.json must be an object"]
    if not isinstance(m.get("manifest_version"), int):
        problems.append("manifest.json needs a manifest_version")
    if not str(m.get("name", "")).strip() or not str(m.get("description", "")).strip():
        problems.append("manifest.json needs a name and a one-line description")
    files = files_of("extensions", name, folder, problems)
    sites = [str(x) for k in ("host_permissions",) for x in m.get(k) or []]
    sites += [str(x) for cs in m.get("content_scripts") or [] if isinstance(cs, dict) for x in cs.get("matches") or []]
    permissions = [str(x) for x in m.get("permissions") or [] if isinstance(x, str)]
    author = m.get("author")
    author = author.get("email", "") if isinstance(author, dict) else author
    entry = {
        "name": name, "description": str(m.get("description", "")).strip(), "author": str(author or author_of(folder)),
        "matches": sorted(set(s for s in sites if s not in ("<all_urls>", "*://*/*", "http://*/*", "https://*/*"))),
        "commands": [], "programs": [], "permissions": permissions, "files": files, "updated": updated(folder),
    }
    # Sites like <all_urls> mean every site: matches stays empty, as for a plugin without `matches`.
    return entry, problems

def check(name, folder):
    problems = []
    if not NAME.match(name):
        problems.append("folder name must be lowercase letters, digits and hyphens")
    manifest_path = os.path.join(folder, "plugin.yaml")
    if not os.path.exists(manifest_path):
        return None, ["no plugin.yaml"]
    try:
        m = yaml.safe_load(open(manifest_path)) or {}
    except Exception as e:
        return None, [f"plugin.yaml doesn't parse: {e}"]
    if not isinstance(m, dict):
        return None, ["plugin.yaml must be a mapping"]
    unknown = set(m) - MANIFEST_KEYS
    if unknown:
        problems.append(f"unknown keys in plugin.yaml: {', '.join(sorted(unknown))}")
    if not str(m.get("description", "")).strip():
        problems.append("plugin.yaml needs a one-line description")
    files = files_of("plugins", name, folder, problems)
    programs = [c["run"] for c in m.get("commands") or [] if isinstance(c, dict) and c.get("run")]
    programs += [h["run"] for h in m.get("on_page_load") or [] if isinstance(h, dict) and h.get("run")]
    programs += [h["run"] for h in m.get("events") or [] if isinstance(h, dict) and h.get("run")]
    programs += [h["run"] for h in m.get("search") or [] if isinstance(h, dict) and h.get("run")]
    programs += [h["text_from"] for h in m.get("sidebar") or [] if isinstance(h, dict) and h.get("text_from")]
    entry = {
        "name": name, "description": str(m.get("description", "")).strip(), "author": str(m.get("author") or author_of(folder)),
        "matches": [str(x) for x in m.get("matches") or []],
        "commands": [str(c.get("title", "")) for c in m.get("commands") or [] if isinstance(c, dict)],
        "programs": programs, "permissions": [str(x) for x in m.get("permissions") or []], "files": files, "updated": updated(folder),
        # Its panels: the HTML files a layout can place (start.html is the start page).
        "panels": sorted(f["path"][:-5] for f in files if "/" not in f["path"] and f["path"].endswith(".html") and f["path"] != "start.html"),
    }
    return entry, problems

def walk_tree(node, found, problems):
    """Every part and panel in a layout's tree."""
    if not isinstance(node, dict):
        problems.append("window: each block must be a mapping")
        return
    what = [k for k in ("row", "column", "part", "panel") if k in node]
    if len(what) != 1:
        problems.append(f"window: each block needs exactly one of row, column, part or panel, not {what}")
        return
    if what[0] in ("row", "column"):
        for child in node[what[0]] or []:
            walk_tree(child, found, problems)
    else:
        found[what[0]].append(str(node[what[0]]))

def check_layout(name, folder):
    entry, problems = check(name, folder)
    if not entry:
        return entry, problems
    path = os.path.join(folder, "layouts", name + ".yaml")
    if not os.path.exists(path):
        return entry, problems + [f"no layouts/{name}.yaml"]
    try:
        l = yaml.safe_load(open(path)) or {}
    except Exception as e:
        return entry, problems + [f"layouts/{name}.yaml doesn't parse: {e}"]
    if not isinstance(l, dict):
        return entry, problems + [f"layouts/{name}.yaml must be a mapping"]
    unknown = set(l) - LAYOUT_KEYS
    if unknown:
        problems.append(f"unknown keys in the layout: {', '.join(sorted(unknown))}")
    extra = set(l.get("settings") or {}) - LOOK_SECTIONS
    if extra:
        problems.append(f"a layout can only change how the window looks, not {', '.join(sorted(extra))}")
    found = {"part": [], "panel": []}
    if l.get("window") is not None:
        walk_tree(l["window"], found, problems)
        if found["part"].count("pages") != 1:
            problems.append("window: it needs exactly one `part: pages` block")
        problems += [f"window: part {p!r} isn't one of {sorted(PARTS)}" for p in found["part"] if p not in PARTS]
    replaces = l.get("replace") or {}
    problems += [f"replace: {w!r} isn't one of {sorted(WINDOWS)}" for w in replaces if w not in WINDOWS]
    used = found["panel"] + [str(f.get("panel")) for f in l.get("floating") or [] if isinstance(f, dict)] + [str(v) for v in replaces.values()]
    # A layout stands on its own: its panels are its own files, or Valerie's window-panels, which everyone has.
    for panel in used:
        plugin, _, file = panel.partition("/")
        file = file or "panel"
        if plugin == "window-panels":
            continue
        if plugin != name:
            problems.append(f"panel {panel}: bring it in this folder ({name}/{file})")
        elif not os.path.exists(os.path.join(folder, file + ".html")):
            problems.append(f"panel {panel}: no {file}.html")
    if replaces:
        print(f"::warning::layout {name} replaces Valerie's own windows ({', '.join(sorted(replaces))}), with all they can do; review it closely")
    preview = os.path.join(folder, "preview.svg")
    if os.path.exists(preview):
        data = open(preview, "rb").read()
        if len(data) > PREVIEW_LIMIT:
            problems.append(f"preview.svg is over {PREVIEW_LIMIT // 1000} KB")
        entry["preview"] = "data:image/svg+xml;base64," + base64.b64encode(data).decode()
    entry["tree"], entry["floating"], entry["replaces"] = l.get("window"), l.get("floating") or [], sorted(replaces)
    return entry, problems

def main():
    only_check = "--check" in sys.argv
    out, failed = {"plugins": [], "extensions": [], "layouts": []}, False
    # Layouts install into the same folder as plugins, so they can't share a name.
    both = set(os.listdir("plugins") if os.path.isdir("plugins") else []) & set(os.listdir("layouts") if os.path.isdir("layouts") else [])
    for name in sorted(both):
        print(f"::error::{name} is both a plugin and a layout; rename one")
        failed = True
    for top, checker in (("plugins", check), ("extensions", check_extension), ("layouts", check_layout)):
        for name in sorted(os.listdir(top)) if os.path.isdir(top) else []:
            folder = os.path.join(top, name)
            if not os.path.isdir(folder) or name.startswith("."):
                continue
            entry, problems = checker(name, folder)
            for p in problems:
                print(f"::error::{top}/{name}: {p}")
                failed = True
            if not entry:
                continue
            if entry["programs"]:
                print(f"::warning::{name} runs programs on the user's computer; review them:")
                for prog in entry["programs"]:
                    print("    " + prog.replace("\n", "\n    "))
            risky = sorted(set(entry.get("permissions", [])) & RISKY_PERMISSIONS)
            if top == "extensions" and (risky or not entry["matches"]):
                print(f"::warning::extension {name} asks for {', '.join(risky) or 'every site'}; review it closely")
            out[top].append(entry)
    if failed:
        sys.exit(1)
    if not only_check:
        json.dump(out, open("index.json", "w"), indent=2)
        print(f"index.json: {len(out['plugins'])} plugins, {len(out['extensions'])} extensions, {len(out['layouts'])} layouts")

main()
