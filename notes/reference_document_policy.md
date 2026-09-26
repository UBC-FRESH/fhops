# Reference Document Policy

Date: 2026-09-26
Issue: #25

## Decision

FHOPS keeps full-text reference documents in a **private DataLad-backed GitHub repository** and
links that vault back to the public repository as an **optional git submodule** at
`reference-documents/`.

The public repo keeps bibliographic notes, derived public metadata, and runtime JSON artifacts.
Restricted PDFs, downloaded snapshots, spreadsheets, and extraction working files stay in the
private vault. The parent FHOPS repository tracks only the submodule gitlink/commit; it does not
track the restricted contents.

## Rationale

- The public tree and package artifacts must not redistribute material whose copyright terms may not
  permit republication.
- Rewriting historical Git tags/commits would be disruptive and is not necessary to protect the
  current public tree.
- A private DataLad dataset gives collaborators a reproducible vault with dataset metadata while
  keeping access control at GitHub.
- The optional submodule keeps paths stable for FHOPS notes/scripts without forcing public users to
  fetch private material.

## Implementation

- `reference-documents/` is an optional submodule pointing to the private
  `UBC-FRESH/fhops-reference-docs` repository.
- The private repository is initialized as a DataLad dataset with `--no-annex`; GitHub remains the
  storage/transport layer while DataLad provides dataset metadata and clone workflows.
- `pyproject.toml` excludes `reference-documents/**` from source distributions.
- Public docs direct authorized collaborators to initialize the submodule:

  ```bash
  git submodule update --init reference-documents
  ```

  DataLad users may also use `datalad clone` directly when their GitHub credentials are configured.

## Historical-note decision

Historical reference-document blobs remain in old public commits/tags. We accept that residual
exposure rather than force-pushing rewritten public history. The operational control is
forward-looking: new restricted payloads belong in the private DataLad-backed vault, not in the
public FHOPS tree.

## Collaborator checklist

- Keep restricted documents under `reference-documents/` only.
- Do not copy restricted files into `docs/`, `notes/`, `data/`, or package artifacts.
- Commit vault changes inside the private `reference-documents` repository first, then update the
  FHOPS submodule gitlink deliberately.
- Cite public bibliographic notes in `notes/reference_log.md` and `notes/reference/` instead of
  attaching full text.
