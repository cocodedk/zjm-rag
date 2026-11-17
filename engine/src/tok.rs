//! Tokenizing: the prebuilt FST vocabulary when the model folder has one, else tokenizer.json.
use crate::constants::{TOKENIZER_FILE, VOCAB_DIR};
use crate::error::{Fail, Res};
use crate::fstvocab::FstVocab;
use std::path::Path;
use tokenizers::Tokenizer;

pub enum Tok {
    Fst(Box<FstVocab>),
    Stock { tokenizer: Box<Tokenizer>, unk: Option<u32> },
}

impl Tok {
    pub fn open(model: &Path) -> Res<Tok> {
        let vocab = model.join(VOCAB_DIR);
        if vocab.is_dir() {
            return Ok(Tok::Fst(Box::new(FstVocab::open(&vocab)?)));
        }
        let path = model.join(TOKENIZER_FILE);
        let raw = std::fs::read(&path).map_err(|e| Fail::io(&path, e))?;
        let json: serde_json::Value = serde_json::from_slice(&raw)?;
        let mut tokenizer = Tokenizer::from_file(&path)?;
        tokenizer.with_truncation(None)?;
        tokenizer.with_padding(None);
        let m = &json["model"];
        let unk = match m["unk_id"].as_u64() {
            Some(id) => Some(id as u32),
            None => m["unk_token"].as_str().and_then(|t| tokenizer.token_to_id(t)),
        };
        Ok(Tok::Stock { tokenizer: Box::new(tokenizer), unk })
    }

    pub fn unk(&self) -> Option<u32> {
        match self {
            Tok::Fst(v) => Some(v.unk),
            Tok::Stock { unk, .. } => *unk,
        }
    }

    pub fn encode(&self, text: &str) -> Res<Vec<u32>> {
        match self {
            Tok::Fst(v) => v.encode(text),
            Tok::Stock { tokenizer, .. } => Ok(tokenizer.encode(text, false)?.get_ids().to_vec()),
        }
    }
}
