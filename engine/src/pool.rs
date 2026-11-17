//! A text's vector: the f64 mean of its token rows, normalized, stored as f32.
use crate::constants::MAX_TOKENS;
use crate::error::{Fail, Res};
use crate::table::Table;

/// First `MAX_TOKENS` tokens, unknown token dropped; zero vector when none is left.
pub fn pool(ids: &[u32], table: &Table, unk: Option<u32>) -> Res<Vec<f32>> {
    let kept: Vec<u32> = ids.iter().take(MAX_TOKENS).copied().filter(|&i| Some(i) != unk).collect();
    let mut acc = vec![0f64; table.dim];
    for &id in &kept {
        if id as usize >= table.rows {
            return Err(Fail::new(format!("token id {id} is outside the model's table")));
        }
        table.add_row(id as usize, &mut acc);
    }
    if kept.is_empty() {
        return Ok(vec![0.0; table.dim]);
    }
    let n = kept.len() as f64;
    acc.iter_mut().for_each(|x| *x /= n);
    let norm = acc.iter().map(|x| x * x).sum::<f64>().sqrt();
    let scale = if norm > 0.0 { norm.recip() } else { 1.0 };
    Ok(acc.into_iter().map(|x| (x * scale) as f32).collect())
}
