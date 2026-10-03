"""google_drive — a company's documents kept in Google Drive (company brain).

Point the link at a Google Drive for desktop folder (`My Drive` / a shared
drive) or at an unpacked Google Takeout (`Takeout/Drive/` is stripped). The
folder is LINKED, never copied, and read-only. Native Docs/Sheets/Slides
appear on disk as small pointer files (.gdoc/.gsheet/.gslides): only their
`url` and document id are read — never the account e-mail they also carry.
Files that are cloud-only placeholders are NEVER opened (opening one would
make Drive download it); they become metadata-only stubs until the folder is
marked "Available offline".

Each file is tiered by the deterministic scanner (docscan.py): clean documents
come in with their content; anything carrying credentials, secrets or dense
personal data becomes a metadata-only stub. Output: the `docs` layer
(65-documents/). Pulling straight from the Drive API is the separate,
network-declaring docs-connector plugin — this adapter stays offline.
"""
from sources import _docs

NAME = "google_drive"
SUBJECT = "company"


def detect(file_index):
    return _docs.detect_store(NAME, file_index)


def extract(root, file_index, all_paths, col):
    return _docs.extract_store(NAME, root, file_index, all_paths, col,
                               getattr(col, "mapping_dirs", None))
