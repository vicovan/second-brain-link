#!/usr/bin/env python3
"""
pyenv — run under an interpreter that actually has what this script needs.

The trap this exists for: Second Brain Studio is a GUI app, so it inherits launchd's PATH,
not your login shell's. `python3` there resolves to /usr/bin/python3 (the system 3.9), which
has no `reportlab` and no `pypdf` — while the python on your shell's PATH does. The CV
builder then degrades to Markdown-only and exits 0, which an agent reads as success. A
missing PDF that reports success is worse than a failure.

So: if the module is missing, look for an interpreter that has it and re-exec there, once.
If none does, say so loudly and name what to install — never pretend it worked.
"""
import os
import subprocess
import sys

# Ordered by likelihood on a developer machine; sys.executable first so an explicitly
# chosen interpreter always wins.
CANDIDATES = [
    sys.executable,
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python3",
]

_GUARD = "SBL_PYENV_REEXEC"


def _has(interp: str, module: str) -> bool:
    try:
        return subprocess.run(
            [interp, "-c", "import " + module],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def require(module: str, pip_name: str = "") -> bool:
    """True if `module` is importable here (possibly after re-exec). False if nowhere.

    Re-execs at most once (guarded by an env var) so a machine without the module cannot
    loop. Returns False rather than exiting, so the caller decides how to degrade.
    """
    try:
        __import__(module)
        return True
    except ImportError:
        pass
    if os.environ.get(_GUARD):
        return False
    seen = set()
    for interp in CANDIDATES:
        if not interp or interp in seen or not os.path.exists(interp):
            continue
        seen.add(interp)
        if interp == sys.executable:
            continue
        if _has(interp, module):
            env = dict(os.environ, **{_GUARD: "1"})
            print(
                "note: %s is not available under %s — re-running with %s"
                % (module, sys.executable, interp),
                file=sys.stderr,
            )
            os.execve(interp, [interp] + sys.argv, env)  # replaces this process
    sys.stderr.write(
        "\n%s is not installed for any python on this machine.\n"
        "   Install it with:  %s -m pip install %s\n\n"
        % (module, sys.executable, pip_name or module)
    )
    return False
