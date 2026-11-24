//! A search: each text ranks the chunks by both legs; a group fuses its texts' rankings.
use crate::error::{Fail, Res};
use crate::index::{Chunk, Index};
use crate::model::Model;
use crate::rank::{bm25_ranking, fuse, vector_ranking};
use crate::types::Filter;

#[derive(Debug, PartialEq)]
pub struct Hit {
    pub path: String,
    pub start: u32,
    pub end: u32,
    pub rank: usize,
}

pub fn group(model: &Model, chunks: &[&Chunk], texts: &[String], limit: usize) -> Res<Vec<Hit>> {
    let mut rankings = Vec::new();
    for text in texts {
        let e = model.embed(text)?;
        rankings.push(vector_ranking(chunks, &e.vector));
        rankings.push(bm25_ranking(chunks, &e.ids));
    }
    Ok(fuse(&rankings)
        .into_iter()
        .take(limit)
        .enumerate()
        .map(|(i, (p, _))| Hit { path: chunks[p].path.clone(), start: chunks[p].start, end: chunks[p].end, rank: i + 1 })
        .collect())
}

/// A path is named when it equals a name or lies under it as a folder; `None` names every path.
fn named(names: Option<&[String]>, path: &str) -> bool {
    names.map_or(true, |list| list.iter().any(|n| path.strip_prefix(n.as_str()).is_some_and(|rest| rest.is_empty() || rest.starts_with('/'))))
}

/// Hits for the question and for its translations, over the chunks whose file passes `filters` and `names`.
pub fn search(model: &Model, index: &Index, filters: &[Filter], names: Option<&[String]>, texts: &[String], limit: usize) -> Res<(Vec<Hit>, Vec<Hit>)> {
    if index.dim != model.table.dim {
        return Err(Fail::format("index has another vector size than the model"));
    }
    let chunks: Vec<&Chunk> = index.chunks.iter().filter(|c| crate::types::any_matches(filters, &c.path) && named(names, &c.path)).collect();
    let (question, translations) = texts.split_at(1.min(texts.len()));
    let translated = if translations.is_empty() { Vec::new() } else { group(model, &chunks, translations, limit)? };
    Ok((group(model, &chunks, question, limit)?, translated))
}
