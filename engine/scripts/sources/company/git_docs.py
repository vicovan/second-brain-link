"""git_docs — a company's documents kept in a Git repository (company brain).

The repository is LINKED, never copied: `data/company/<entity>/git_docs/` holds a
`_SOURCE_LINK.json` (written by Studio's "Link folder…" or `doclink.py init`)
pointing at a local clone. Everything is read-only and local — the clone, its
`.git/` folder and every file in it are left byte-identical. The repository
history (author NAMES only, never e-mail addresses) dates each document and links
it to its authors.

Each file is tiered by the deterministic scanner (docscan.py): clean documents
come in with their content; anything carrying credentials, secrets or dense
personal data becomes a metadata-only stub whose content never enters the brain.
Output: the `docs` layer (65-documents/). Shared pipeline: sources/_docs.py.

Inline mode (no link file — the repository's files dropped straight into
`git_docs/`) also works, but then sibling adapters can see the files too; the
link file is the recommended way.
"""
from sources import _docs

NAME = "git_docs"
SUBJECT = "company"


def detect(file_index):
    return _docs.detect_store(NAME, file_index)


def extract(root, file_index, all_paths, col):
    return _docs.extract_store(NAME, root, file_index, all_paths, col,
                               getattr(col, "mapping_dirs", None))
