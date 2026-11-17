//! A model folder opened for use: the mapped table and the tokenizer.
use crate::constants::MODEL_FILE;
use crate::error::{Fail, Res};
use crate::pool::pool;
use crate::table::Table;
use crate::tok::Tok;
use std::path::Path;

pub struct Model {
    pub name: String,
    pub table: Table,
    pub tok: Tok,
}

pub struct Embedded {
    pub vector: Vec<f32>,
    /// All of the text's token ids, the unknown token dropped (the keyword leg's terms).
    pub ids: Vec<u32>,
}

impl Model {
    pub fn open(dir: &Path) -> Res<Model> {
        let canonical = dir.canonicalize().map_err(|e| Fail::io(dir, e))?;
        let name = canonical.file_name().map_or_else(String::new, |n| n.to_string_lossy().into_owned());
        Ok(Model { name, table: Table::open(&canonical.join(MODEL_FILE))?, tok: Tok::open(&canonical)? })
    }

    pub fn embed(&self, text: &str) -> Res<Embedded> {
        let mut ids = self.tok.encode(text)?;
        let vector = pool(&ids, &self.table, self.tok.unk())?;
        ids.retain(|&i| Some(i) != self.tok.unk());
        Ok(Embedded { vector, ids })
    }
}
