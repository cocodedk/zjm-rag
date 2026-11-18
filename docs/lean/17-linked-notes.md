# 17 — a project's notes folder may be a symlink into ~/vaults

Project notes live in a separate private git repo at `~/vaults`, and a project's `memory` folder is a symlink to
`~/vaults/<project>`. `zjm-project reindex` refused it ("is a symlink: index the real path"), because `mirror.inside`
refuses every symlink on a configured path (#37). One locker per project; a project lists `memory` in its own
`zjm-project.json` and searches only its own notes.

## The rule

- `mirror.NOTES_ROOT` is `~/vaults`, resolved.
- A `folders` entry is accepted as a symlink only when it is a single path component and its real target (found with
  `os.path.realpath`, which does not raise on a link loop) is `NOTES_ROOT/<checkout folder name>` or inside it: the vault folder must have the same name as the project's checkout
  folder (deliberate: it stops a typo indexing another project's notes), so a worktree or a clone under another folder
  name is refused, with a message naming the expected folder. A link
  to the notes root, to another project's notes or elsewhere is refused with "is a symlink to <target>: a notes link
  must point into <expected folder>". Every other symlink (a file entry, a deeper component) is refused with the old
  "<path> is a symlink: index the real path".
- `files` is unchanged: a symlinked file entry is refused.
- `reindex` mirrors a linked folder from its real target with `mirror.make`, as for any folder (floor, exclude list and
  the target repo's own git rules apply; the project's `.gitignore` does not). The mount is the link's name, so hits read
  `memory/...`. Each linked entry has its own state line, `L\t<link>\t<real path>` (one per entry, so two links to one folder are two lines): `ident` compares the real path, and `STALE` fires when the link is gone
  or no longer resolves to that real path, else the real path is walked.
  `floor_check` runs on the real path; the duplicate-name and `_files` checks use the link's name.

## Tests

Exactly **160** (150 before). Ten new in `tests/test_skill.py`:

1. a link into `HOME/vaults/project` (the checkout folder is named `project`; a git repo with a tracked note and a git-ignored file) reindexes: the stub sees
   `memory/<note>` and not the ignored file, and the config allows `/sources/memory`.
2. a link to a folder outside the notes root: rc 2, "is a symlink".
3. a link to the notes root itself: rc 2.
4. `folders: ["docs/linked"]` with `docs/linked` a link into the notes root: rc 2.
5. after reindex, changing a note makes `find` print `STALE`.
6. a link to another project's notes folder: rc 2, names the expected folder.
7. a link loop: rc 2, no traceback.
8. removing the link, or repointing it to another folder, makes `find` print `STALE`.
9. a checkout folder named `clone` linking `vaults/project`: rc 2, the message names `vaults/clone`.
10. two entries linking one folder: removing one link gives one `STALE` line naming it; repointing one gives exactly one.

The suite reports exactly 160 tests.
