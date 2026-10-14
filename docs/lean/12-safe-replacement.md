# Safe plain-locker replacement

Prepare all file-add sources and their metadata before modifying a locker's corpus.
Excluded or gitignored sources leave existing content and manifest entries unchanged.
Support replacement between files and directories; restore old paths if installing a
prepared replacement raises an OS error. As before, an indexing error on a plain locker
retains the new corpus and marks the manifest indexed=False; encrypted writes remain atomic.
Staging needs temporary space for incoming content and the replaced paths until indexing ends.
This protects ordinary copy/install errors, not abrupt process or machine failure.

After integration with the translation and help features on main, acceptance: exactly **97 tests**, including batch preparation failure, type changes, ignored
replacement, and rollback after an installation error.
