//! The embedding table: model.safetensors memory-mapped, f32 or f16 as stored.
use crate::constants::{SAFETENSORS_PREFIX, TENSOR_NAME};
use crate::error::{Fail, Res};
use memmap2::Mmap;
use std::{fs::File, path::Path};

pub struct Table {
    map: Mmap,
    start: usize,
    pub dim: usize,
    pub rows: usize,
    half: bool,
}

fn f16_to_f32(h: u16) -> f32 {
    let sign = ((h >> 15) as u32) << 31;
    let (exp, man) = (((h >> 10) & 0x1f) as u32, (h & 0x3ff) as u32);
    match exp {
        0 => {
            let v = man as f32 * 2f32.powi(-24);
            if sign == 0 { v } else { -v }
        }
        0x1f => f32::from_bits(sign | 0x7f80_0000 | (man << 13)),
        _ => f32::from_bits(sign | ((exp + 112) << 23) | (man << 13)),
    }
}

impl Table {
    pub fn open(path: &Path) -> Res<Table> {
        let file = File::open(path).map_err(|e| Fail::io(path, e))?;
        // SAFETY: the model files are read-only and are not modified while mapped.
        let map = unsafe { Mmap::map(&file) }.map_err(|e| Fail::io(path, e))?;
        let bad = || Fail::new(format!("{}: not a safetensors table", path.display()));
        let prefix = map.get(..SAFETENSORS_PREFIX).ok_or_else(bad)?;
        let n = u64::from_le_bytes(prefix.try_into().unwrap()) as usize;
        let head = map.get(SAFETENSORS_PREFIX..SAFETENSORS_PREFIX.saturating_add(n)).ok_or_else(bad)?;
        let header: serde_json::Value = serde_json::from_slice(head)?;
        let e = &header[TENSOR_NAME];
        let half = match e["dtype"].as_str() {
            Some("F32") => false,
            Some("F16") => true,
            _ => return Err(Fail::new(format!("{}: tensor must be F32 or F16", path.display()))),
        };
        let num = |v: &serde_json::Value| v.as_u64().map(|x| x as usize).ok_or_else(bad);
        let (rows, dim) = (num(&e["shape"][0])?, num(&e["shape"][1])?);
        let (from, to) = (num(&e["data_offsets"][0])?, num(&e["data_offsets"][1])?);
        let start = SAFETENSORS_PREFIX + n + from;
        let width = if half { 2 } else { 4 };
        if to < from || to - from != rows * dim * width || SAFETENSORS_PREFIX + n + to > map.len() {
            return Err(bad());
        }
        Ok(Table { map, start, dim, rows, half })
    }

    /// Adds row `id` into `acc` (in f64).
    pub fn add_row(&self, id: usize, acc: &mut [f64]) {
        for (c, x) in acc.iter_mut().enumerate() {
            let i = id * self.dim + c;
            *x += if self.half {
                let o = self.start + i * 2;
                f16_to_f32(u16::from_le_bytes([self.map[o], self.map[o + 1]])) as f64
            } else {
                let o = self.start + i * 4;
                f32::from_le_bytes(self.map[o..o + 4].try_into().unwrap()) as f64
            };
        }
    }
}
