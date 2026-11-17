//! The two legs (cosine, BM25) and reciprocal-rank fusion. A ranking is chunk positions, best first.
use crate::constants::*;
use crate::index::Chunk;

fn order(scores: &[f64], keep: impl Fn(f64) -> bool) -> Vec<usize> {
    let mut pos: Vec<usize> = (0..scores.len()).filter(|&i| keep(scores[i])).collect();
    pos.sort_by(|&a, &b| scores[b].total_cmp(&scores[a]).then(a.cmp(&b)));
    pos
}

/// Cosine of each chunk's vector with the query's; empty when the query vector is zero.
pub fn vector_ranking(chunks: &[&Chunk], query: &[f32]) -> Vec<usize> {
    if query.iter().all(|&x| x == 0.0) {
        return Vec::new();
    }
    let scores: Vec<f64> = chunks.iter().map(|c| c.vector.iter().zip(query).map(|(a, b)| *a as f64 * *b as f64).sum()).collect();
    order(&scores, |_| true)
}

/// BM25 over token ids; chunks sharing no term with the query are left out.
pub fn bm25_ranking(chunks: &[&Chunk], terms: &[u32]) -> Vec<usize> {
    let mut terms = terms.to_vec();
    terms.sort_unstable();
    terms.dedup();
    let len = |c: &Chunk| c.counts.iter().map(|&(_, n)| n as f64).sum::<f64>();
    let total = chunks.len() as f64;
    let avg = chunks.iter().map(|c| len(c)).sum::<f64>() / total.max(1.0);
    let tf = |c: &Chunk, t: u32| c.counts.binary_search_by_key(&t, |&(id, _)| id).map_or(0.0, |i| c.counts[i].1 as f64);
    let scores: Vec<f64> = {
        let idf: Vec<f64> = terms
            .iter()
            .map(|&t| {
                let df = chunks.iter().filter(|c| tf(c, t) > 0.0).count() as f64;
                (1.0 + (total - df + 0.5) / (df + 0.5)).ln()
            })
            .collect();
        chunks
            .iter()
            .map(|c| {
                let norm = BM25_K1 * (1.0 - BM25_B + BM25_B * len(c) / avg);
                terms.iter().zip(&idf).map(|(&t, w)| w * tf(c, t) * (BM25_K1 + 1.0) / (tf(c, t) + norm)).sum()
            })
            .collect()
    };
    order(&scores, |s| s > 0.0)
}

/// Reciprocal-rank fusion: sum of 1 / (k + rank) over the rankings; best first, ties by position.
pub fn fuse(rankings: &[Vec<usize>]) -> Vec<(usize, f64)> {
    let size = rankings.iter().flatten().max().map_or(0, |m| m + 1);
    let mut score = vec![0f64; size];
    let mut seen = vec![false; size];
    for ranking in rankings {
        for (r, &p) in ranking.iter().enumerate() {
            score[p] += 1.0 / (RRF_K + (r + 1) as f64);
            seen[p] = true;
        }
    }
    let mut out: Vec<(usize, f64)> = (0..size).filter(|&p| seen[p]).map(|p| (p, score[p])).collect();
    out.sort_by(|a, b| b.1.total_cmp(&a.1).then(a.0.cmp(&b.0)));
    out
}
