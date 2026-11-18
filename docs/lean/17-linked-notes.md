# 17 — a project's notes folder may be a symlink into ~/vaults

Project notes live in a separate private git repo at `~/vaults`, and a project's `memory` folder is a symlink to
`~/vaults/<project>`. `zjm-project reindex` refused it ("is a symlink: index the real path"), because `mirror.inside`
refuses every symlink on a configured path (#37). One locker per project; a project lists `memory` in its own
`zjm-project.json` and searches only its own notes.

## The rule

- `mirror.NOTES_ROOT` is `~/vaults`, resolved.
- A `folders` entry is accepted as a symlink only when it is a single path component (no earlier component is a link)
  and its real target is a strict subfolder of `NOTES_ROOT`. The notes root itself is refused: it holds every
  project's notes. Any other symlink is refused as before, with a message that names `NOTES_ROOT`.
- `files` is unchanged: a symlinked file entry is refused.
- `reindex` mirrors a linked folder from its real target with `mirror.make`, as for any folder (floor, exclude list and
  the target repo's own git rules apply; the project's `.gitignore` does not). The mount is the link's name, so hits read
  `memory/...`. The real path goes into the state `dirs` lines, so `STALE` detection walks the notes.
  `floor_check` runs on the real path; the duplicate-name and `_files` checks use the link's name.

## Tests

Exactly **155** (150 before). Five new in `tests/test_skill.py`:

1. a link into `HOME/vaults/proj` (a git repo with a tracked note and a git-ignored file) reindexes: the stub sees
   `memory/<note>` and not the ignored file, and the config allows `/sources/memory`.
2. a link to a folder outside the notes root: rc 2, "is a symlink".
3. a link to the notes root itself: rc 2.
4. `folders: ["docs/linked"]` with `docs/linked` a link into the notes root: rc 2.
5. after reindex, changing a note makes `find` print `STALE`.

The suite reports exactly 155 tests.
