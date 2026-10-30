# Valerie plugins

Plugins and browser extensions people made for [Valerie](https://github.com/cullen-b/valerie), the browser you change
by asking.

**Install one:** type **Plugins** in Valerie's command bar to browse, search and install. Or from Terminal:
`valerie plugins search <words>` and `valerie plugins install <name>`.

**Share yours:** when your AI makes you a plugin or extension, Valerie offers to share it here. Or run **Share Plugin** in the command
bar, or `valerie plugins share <name>`. Valerie opens a pull request from your GitHub account; once it's reviewed and
merged, everyone can install it.

## What's here

Each folder in `plugins/` is one plugin, exactly as it sits in Valerie's `plugins/` folder: a `plugin.yaml` plus
optional `script.js` (runs in matching pages), `style.css` and other files.

Each folder in `extensions/` is one browser extension, exactly as it sits in Valerie's `extensions/` folder: an unpacked
web extension with a `manifest.json` (as for Safari or Chrome "load unpacked"). They need macOS 15.4 or later, and
Valerie asks before loading each one. Plugins work everywhere Valerie does, so prefer a plugin when either would do.

`index.json` is built from both on every merge, with every file pinned to that commit and checksummed, so what you
install is exactly what was reviewed.

## Rules for plugins

- One clear job, said in `description` (`plugin.yaml`, or `manifest.json` with a `name`). Folder names are lowercase
  words with hyphens.
- Readable source only: no minified or obfuscated code, no binaries, text files under 200 KB.
- No tracking, no sending people's data anywhere they didn't ask for.
- Anything that runs programs on someone's computer (`run:` in a command or `on_page_load`) is shown to them before
  they install it, and gets a closer look in review. So do extensions that reach every site or ask for permissions
  like `nativeMessaging`, `cookies` or `webRequest`.
- Check the list first: if a plugin already does it, improve that one instead of adding another.
