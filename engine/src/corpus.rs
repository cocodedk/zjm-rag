//! The corpus: every regular file under a folder, minus the files the skip rule drops.
use crate::constants::{MAX_FILE_BYTES, NUL_SCAN_BYTES};
use crate::error::{Fail, Res};
use std::fs;
use std::path::{Path, PathBuf};

fn walk(dir: &Path, out: &mut Vec<PathBuf>) -> Res<()> {
    let mut entries: Vec<_> = fs::read_dir(dir).map_err(|e| Fail::io(dir, e))?.collect::<Result<_, _>>().map_err(|e| Fail::io(dir, e))?;
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        let kind = entry.file_type().map_err(|e| Fail::io(dir, e))?;
        if kind.is_dir() {
            walk(&entry.path(), out)?;
        } else if kind.is_file() {
            out.push(entry.path());
        }
    }
    Ok(())
}

/// Files under `root`, sorted, as paths relative to it.
pub fn files(root: &Path) -> Res<Vec<PathBuf>> {
    let mut all = Vec::new();
    walk(root, &mut all)?;
    Ok(all.into_iter().filter_map(|p| p.strip_prefix(root).ok().map(Path::to_path_buf)).collect())
}

/// The file's text, or None when it is skipped: empty, whitespace only, binary or too big.
pub fn read_text(path: &Path) -> Res<Option<String>> {
    let size = fs::metadata(path).map_err(|e| Fail::io(path, e))?.len();
    if size > MAX_FILE_BYTES {
        return Ok(None);
    }
    let bytes = fs::read(path).map_err(|e| Fail::io(path, e))?;
    if bytes[..bytes.len().min(NUL_SCAN_BYTES)].contains(&0) {
        return Ok(None);
    }
    let text = String::from_utf8_lossy(&bytes).into_owned();
    Ok((!text.trim().is_empty()).then_some(text))
}
