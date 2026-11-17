//! Builds `vocab/` for a Unigram tokenizer: an FST of token to id, a score array, a skeleton.
use crate::constants::*;
use crate::error::{Fail, Res};
use fst::MapBuilder;
use std::{collections::BTreeMap, fs, io::BufWriter, path::Path};

pub fn build(tokenizer_json: &Path, out: &Path) -> Res<()> {
    let raw = fs::read(tokenizer_json).map_err(|e| Fail::io(tokenizer_json, e))?;
    let mut t: serde_json::Value = serde_json::from_slice(&raw)?;
    let bad = || Fail::new("tokenizer.json is not a Unigram tokenizer");
    let vocab = t["model"]["vocab"].as_array().ok_or_else(bad)?.clone();
    let unk = t["model"]["unk_id"].as_u64().ok_or_else(bad)?;
    let mut ids: BTreeMap<Vec<u8>, u64> = BTreeMap::new(); // a later duplicate wins, as in tokenizers
    let mut scores = Vec::with_capacity(vocab.len() * 8);
    let mut min = f64::MAX;
    for (i, e) in vocab.iter().enumerate() {
        let score = e[1].as_f64().ok_or_else(bad)?;
        min = min.min(score);
        scores.extend_from_slice(&score.to_le_bytes());
        ids.insert(e[0].as_str().ok_or_else(bad)?.as_bytes().to_vec(), i as u64);
    }
    fs::create_dir_all(out).map_err(|e| Fail::io(out, e))?;
    let fst_path = out.join(FST_FILE);
    let file = fs::File::create(&fst_path).map_err(|e| Fail::io(&fst_path, e))?;
    let mut builder = MapBuilder::new(BufWriter::new(file)).map_err(|e| Fail::new(e.to_string()))?;
    for (k, v) in &ids {
        builder.insert(k, *v).map_err(|e| Fail::new(e.to_string()))?;
    }
    builder.finish().map_err(|e| Fail::new(e.to_string()))?;
    let keep = (unk as usize + 1).max(2).min(vocab.len());
    t["model"]["vocab"] = serde_json::Value::Array(vocab[..keep].to_vec());
    let put = |name: &str, bytes: Vec<u8>| fs::write(out.join(name), bytes).map_err(|e| Fail::io(&out.join(name), e));
    put(SCORES_FILE, scores)?;
    put(SKELETON_FILE, serde_json::to_vec(&t)?)?;
    put(META_FILE, serde_json::to_vec(&serde_json::json!({"unk_id": unk, "min_score": min}))?)
}
