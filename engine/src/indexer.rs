//! Builds an index from a corpus folder.
use crate::chunk::chunks;
use crate::corpus;
use crate::error::Res;
use crate::index::{self, Chunk, Index};
use crate::model::Model;
use std::{collections::BTreeMap, path::Path};

pub fn build(model: &Model, corpus_dir: &Path, out: &Path) -> Res<usize> {
    let mut all = Vec::new();
    for rel in corpus::files(corpus_dir)? {
        let Some(text) = corpus::read_text(&corpus_dir.join(&rel))? else { continue };
        let path = rel.components().map(|c| c.as_os_str().to_string_lossy()).collect::<Vec<_>>().join("/");
        for span in chunks(&path, &text) {
            let e = model.embed(&span.text)?;
            let mut counts: BTreeMap<u32, u32> = BTreeMap::new();
            e.ids.iter().for_each(|&i| *counts.entry(i).or_default() += 1);
            all.push(Chunk { path: path.clone(), start: span.start, end: span.end, vector: e.vector, counts: counts.into_iter().collect() });
        }
    }
    let n = all.len();
    index::write(out, &Index { model: model.name.clone(), dim: model.table.dim, chunks: all })?;
    Ok(n)
}
