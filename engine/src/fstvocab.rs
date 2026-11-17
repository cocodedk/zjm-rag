//! A memory-mapped Unigram vocabulary: an FST (token bytes to id), scores, and a skeleton
//! tokenizer that keeps only the normalizer and pre-tokenizer. Encodes as tokenizers does.
use crate::constants::*;
use crate::error::{Fail, Res};
use fst::{raw::Output, Map};
use memmap2::Mmap;
use std::{fs::File, path::Path};
use tokenizers::{NormalizedString, Normalizer, OffsetReferential, OffsetType, PreTokenizedString, PreTokenizer, Tokenizer};

pub struct FstVocab {
    fst: Map<Mmap>,
    scores: Mmap,
    prep: Tokenizer,
    pub unk: u32,
    unk_score: f64,
}

fn map(dir: &Path, name: &str) -> Res<Mmap> {
    let path = dir.join(name);
    let file = File::open(&path).map_err(|e| Fail::io(&path, e))?;
    // SAFETY: the vocabulary files are read-only and are not modified while mapped.
    unsafe { Mmap::map(&file) }.map_err(|e| Fail::io(&path, e))
}

impl FstVocab {
    pub fn open(dir: &Path) -> Res<FstVocab> {
        let fst = Map::new(map(dir, FST_FILE)?).map_err(|e| Fail::new(format!("vocab.fst: {e}")))?;
        let skeleton = dir.join(SKELETON_FILE);
        let meta_path = dir.join(META_FILE);
        let meta: serde_json::Value = serde_json::from_slice(&std::fs::read(&meta_path).map_err(|e| Fail::io(&meta_path, e))?)?;
        let bad = || Fail::new("vocab/meta.json is incomplete");
        Ok(FstVocab {
            fst,
            scores: map(dir, SCORES_FILE)?,
            prep: Tokenizer::from_file(skeleton)?,
            unk: meta["unk_id"].as_u64().ok_or_else(bad)? as u32,
            unk_score: meta["min_score"].as_f64().ok_or_else(bad)? - UNK_PENALTY,
        })
    }

    fn score(&self, id: u64) -> f64 {
        let o = id as usize * 8;
        f64::from_le_bytes(self.scores[o..o + 8].try_into().unwrap())
    }

    pub fn encode(&self, text: &str) -> Res<Vec<u32>> {
        let mut n = NormalizedString::from(text);
        if let Some(nz) = self.prep.get_normalizer() {
            nz.normalize(&mut n)?;
        }
        let mut p = PreTokenizedString::from(n);
        if let Some(pt) = self.prep.get_pre_tokenizer() {
            pt.pre_tokenize(&mut p)?;
        }
        let mut out = Vec::new();
        for (piece, _, _) in p.get_splits(OffsetReferential::Original, OffsetType::Byte) {
            self.viterbi(piece, &mut out);
        }
        Ok(out)
    }

    /// tokenizers' Unigram best path with runs of unknown characters fused into one unknown.
    fn viterbi(&self, s: &str, out: &mut Vec<u32>) {
        if s.is_empty() {
            return;
        }
        let bytes = s.as_bytes();
        let size = bytes.len();
        let mut best: Vec<(u32, f64, Option<usize>)> = vec![(0, 0.0, None); size + 1];
        let raw = self.fst.as_fst();
        let mut start = 0;
        while start < size {
            let till = best[start].1;
            let mblen = s[start..].chars().next().map_or(1, char::len_utf8);
            let mut single = false;
            let mut node = raw.root();
            let mut acc = Output::zero();
            for (i, &b) in bytes[start..].iter().enumerate() {
                let Some(ti) = node.find_input(b) else { break };
                let tr = node.transition(ti);
                acc = acc.cat(tr.out);
                node = raw.node(tr.addr);
                if node.is_final() {
                    let id = acc.cat(node.final_output()).value();
                    let len = i + 1;
                    let cand = self.score(id) + till;
                    let tgt = &mut best[start + len];
                    if tgt.2.is_none() || cand > tgt.1 {
                        *tgt = (id as u32, cand, Some(start));
                    }
                    single |= len == mblen;
                }
            }
            if !single {
                let cand = self.unk_score + till;
                let tgt = &mut best[start + mblen];
                if tgt.2.is_none() || cand > tgt.1 {
                    *tgt = (self.unk, cand, Some(start));
                }
            }
            start += mblen;
        }
        let mut pieces = Vec::new();
        let (mut end, mut in_unk) = (size, false);
        while end > 0 {
            let (id, _, from) = best[end];
            let from = from.unwrap_or(0);
            if id == self.unk {
                if !in_unk {
                    pieces.push(self.unk);
                    in_unk = true;
                }
            } else {
                in_unk = false;
                pieces.push(self.fst.get(&s[from..end]).map_or(self.unk, |v| v as u32));
            }
            end = from;
        }
        pieces.reverse();
        out.extend(pieces);
    }
}
