#!/bin/sh
# Second Brain Link — installer for macOS and Linux (Windows: install.ps1).
#
# Installs the brain builder skill and the agents (Jobs, Fundraising, Travel) for the AI
# tools on this computer: Claude Code → ~/.claude/skills/<name>, Codex → ~/.agents/skills/<name>.
# Needs no git and no Python to install. Every file is checked against dist/manifest.json.
#
#   curl -fsSL https://secondbrainlink.com/install.sh | sh
#   curl -fsSL https://secondbrainlink.com/install.sh | sh -s -- --claude --no-agents
#
# Options:
#   --claude / --codex    install for that tool only (default: every tool found; Claude if none)
#   --no-agents           the brain builder only
#   --from-dir <dist>     install from a local dist/ folder instead of downloading
#   --base-url <url>      download from another dist/ URL
#
# Safe by design: it only writes ~/.claude/skills/<our names> and ~/.agents/skills/<our names>,
# never touches a symlink there (a developer install), and swaps a folder in only after the new
# copy unpacked cleanly.
set -eu

BASE_URL="https://github.com/vicovan/second-brain-link/raw/main/dist/"
FROM_DIR=""
WANT_CLAUDE=""
WANT_CODEX=""
AGENTS=1

while [ $# -gt 0 ]; do
  case "$1" in
    --claude) WANT_CLAUDE=1 ;;
    --codex) WANT_CODEX=1 ;;
    --no-agents) AGENTS=0 ;;
    --from-dir) FROM_DIR="$2"; shift ;;
    --base-url) BASE_URL="$2"; shift ;;
    -h|--help) sed -n '2,22p' "$0" 2>/dev/null || true; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '%s\n' "$*"; }
ok() { printf '  \342\234\223 %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*"; }
die() { printf '\n\342\234\227 %s\n' "$*" >&2; exit 1; }

say "Second Brain Link installer"

# --- which AI tools? ---------------------------------------------------------
if [ -z "$WANT_CLAUDE$WANT_CODEX" ]; then
  if command -v claude >/dev/null 2>&1 || [ -d "$HOME/.claude" ]; then WANT_CLAUDE=1; fi
  if command -v codex >/dev/null 2>&1 || [ -d "$HOME/.codex" ]; then WANT_CODEX=1; fi
  [ -z "$WANT_CLAUDE$WANT_CODEX" ] && WANT_CLAUDE=1
fi

# --- tools this script needs --------------------------------------------------
fetch() { # url dest
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then wget -q "$1" -O "$2"
  else die "Needs curl or wget to download."; fi
}
sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else echo ""; fi
}
unpack() { # zip dest
  if command -v unzip >/dev/null 2>&1; then unzip -q -o "$1" -d "$2"
  elif command -v bsdtar >/dev/null 2>&1; then bsdtar -xf "$1" -C "$2"
  elif [ "$(uname)" = "Darwin" ]; then tar -xf "$1" -C "$2"
  elif command -v python3 >/dev/null 2>&1; then python3 -m zipfile -e "$1" "$2"
  else die "Needs unzip to unpack (e.g. sudo apt install unzip)."; fi
}

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t sbl)"
trap 'rm -rf "$TMP"' EXIT INT TERM

get() { # relative-file dest
  if [ -n "$FROM_DIR" ]; then cp "$FROM_DIR/$1" "$2"; else fetch "$BASE_URL$1" "$2"; fi
}

get manifest.json "$TMP/manifest.json" || die "Could not get the manifest from ${FROM_DIR:-$BASE_URL}"

# manifest.json is written one field per line (packaging/build_all.py) — read it without jq
awk -F'"' '
  /"name":/        { n=$4 }
  /"kind":/        { k=$4 }
  /"provider":/    { p=$4 }
  /"version":/     { if (n != "") v=$4 }
  /"rev":/         { r=$4 }
  /"file":/        { f=$4 }
  /"sha256":/      { s=$4 }
  /"installs_to":/ { print p "|" k "|" n "|" v "|" f "|" s "|" $4 "|" r; n="" }
' "$TMP/manifest.json" > "$TMP/list"
[ -s "$TMP/list" ] || die "The manifest lists nothing to install."

installed=0
while IFS='|' read -r prov kind name ver file sum target rev; do
  [ "$prov" = "claude" ] && [ -z "$WANT_CLAUDE" ] && continue
  [ "$prov" = "codex" ] && [ -z "$WANT_CODEX" ] && continue
  [ "$kind" = "agent" ] && [ "$AGENTS" = "0" ] && continue
  label="$name $ver for $( [ "$prov" = claude ] && echo 'Claude Code' || echo Codex )"
  dest="$HOME/$target"
  if [ -L "$dest" ]; then warn "$label: $dest is a developer link — left as is"; continue; fi
  arc="$TMP/$prov-$name.zip"
  get "$file" "$arc" || { warn "$label: download failed"; continue; }
  got="$(sha256 "$arc")"
  if [ -n "$got" ] && [ "$got" != "$sum" ]; then warn "$label: checksum mismatch — skipped"; continue; fi
  ex="$TMP/ex-$prov-$name"; mkdir -p "$ex"
  unpack "$arc" "$ex"
  [ -d "$ex/$name" ] || { warn "$label: unexpected archive layout — skipped"; continue; }
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ]; then
    rm -rf "$dest.old"; mv "$dest" "$dest.old"
    if mv "$ex/$name" "$dest"; then rm -rf "$dest.old"; else mv "$dest.old" "$dest"; warn "$label: could not replace"; continue; fi
  else
    mv "$ex/$name" "$dest"
  fi
  # the same stamp Second Brain Studio writes, so its "Update agents" check knows this copy
  printf '{"name": "%s", "provider": "%s", "version": "%s", "rev": "%s", "installedBy": "install.sh"}\n' \
    "$name" "$prov" "$ver" "$rev" > "$dest/.sbl-install.json"
  ok "$label → ~/$target"
  installed=$((installed + 1))
done < "$TMP/list"

[ "$installed" -gt 0 ] || die "Nothing was installed."

say ""
say "Next steps"
if ! command -v python3 >/dev/null 2>&1; then
  say "  • Python 3 is needed to build a brain from the terminal:"
  if [ "$(uname)" = "Darwin" ]; then say "      xcode-select --install     (or https://www.python.org/downloads/)"
  else say "      sudo apt install python3   (Fedora: sudo dnf install python3)"; fi
  say "    The desktop app (secondbrainlink.com/download) has Python built in."
fi
if [ -n "$WANT_CLAUDE" ] && ! command -v claude >/dev/null 2>&1; then
  say "  • Install Claude Code: curl -fsSL https://claude.ai/install.sh | bash   then: claude auth login"
fi
if [ -n "$WANT_CODEX" ] && ! command -v codex >/dev/null 2>&1; then
  say "  • Install Codex: curl -fsSL https://chatgpt.com/codex/install.sh | sh   then: codex login"
fi
say "  • Open Claude Code (or Codex) and say: \"Build my second brain from my data exports.\""
say "  • Agents: \"/job-search:onboard\", \"/fundraising:fund-onboard\", \"/travel-planner:onboard\" (Claude Code)."
say "  • Or use the desktop app, which does all of this for you: https://secondbrainlink.com/download"
