#!/usr/bin/env python3
"""Check every plugin and browser extension and write index.json, the list Valerie installs from.

Plugins are folders in plugins/ (a plugin.yaml), extensions are folders in extensions/ (an unpacked web extension's
manifest.json). Each file is pinned to the commit it was indexed at (and its sha256), so what Valerie downloads is
exactly what was reviewed. `--check` only validates (for pull requests) and prints what each one can run or reach,
for the reviewer.
"""
import hashlib, json, os, re, subprocess, sys
import yaml

REPO = os.environ.get("GITHUB_REPOSITORY", "cullen-b/valerie-plugins")
SHA = os.environ.get("GITHUB_SHA") or subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
MANIFEST_KEYS = {"description", "enabled", "matches", "commands", "on_page_load", "settings", "author"}

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
    entry = {
        "name": name, "description": str(m.get("description", "")).strip(), "author": str(m.get("author") or author_of(folder)),
        "matches": [str(x) for x in m.get("matches") or []],
        "commands": [str(c.get("title", "")) for c in m.get("commands") or [] if isinstance(c, dict)],
        "programs": programs, "files": files, "updated": updated(folder),
    }
    return entry, problems

def main():
    only_check = "--check" in sys.argv
    out, failed = {"plugins": [], "extensions": []}, False
    for top, checker in (("plugins", check), ("extensions", check_extension)):
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
        print(f"index.json: {len(out['plugins'])} plugins, {len(out['extensions'])} extensions")

main()
