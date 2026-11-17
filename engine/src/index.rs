//! The index file: a JSON header line, then each chunk's path, lines, vector and token counts.
use crate::constants::{CHUNK_FIXED_BYTES, F32_BYTES, FORMAT_VERSION, TOKEN_PAIR_BYTES};
use crate::error::{Fail, Res};
use std::{fs, io::Write, path::Path};

fn damaged() -> Fail {
    Fail::new("damaged index: its sizes do not match the file")
}

#[derive(Debug, PartialEq)]
pub struct Chunk {
    pub path: String,
    pub start: u32,
    pub end: u32,
    pub vector: Vec<f32>,
    /// (token id, count), sorted by id.
    pub counts: Vec<(u32, u32)>,
}

#[derive(Debug, PartialEq)]
pub struct Index {
    pub model: String,
    pub dim: usize,
    pub chunks: Vec<Chunk>,
}

pub fn write(path: &Path, index: &Index) -> Res<()> {
    let mut buf = Vec::new();
    let header = serde_json::json!({
        "version": FORMAT_VERSION, "model": index.model, "chunks": index.chunks.len(), "dim": index.dim,
    });
    writeln!(buf, "{header}").unwrap();
    let put = |buf: &mut Vec<u8>, v: u32| buf.extend_from_slice(&v.to_le_bytes());
    for c in &index.chunks {
        put(&mut buf, c.path.len() as u32);
        buf.extend_from_slice(c.path.as_bytes());
        put(&mut buf, c.start);
        put(&mut buf, c.end);
        c.vector.iter().for_each(|x| buf.extend_from_slice(&x.to_le_bytes()));
        put(&mut buf, c.counts.len() as u32);
        for &(id, n) in &c.counts {
            put(&mut buf, id);
            put(&mut buf, n);
        }
    }
    fs::write(path, buf).map_err(|e| Fail::io(path, e))
}

struct Cursor<'a> {
    bytes: &'a [u8],
    at: usize,
}

impl<'a> Cursor<'a> {
    fn take(&mut self, n: usize) -> Res<&'a [u8]> {
        let slice = self.bytes.get(self.at..self.at.saturating_add(n)).ok_or_else(damaged)?;
        self.at += n;
        Ok(slice)
    }
    fn u32(&mut self) -> Res<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
}

/// Reads an index; exit 3 when it has another format version or is for another model, exit 1
/// when its sizes do not add up to the bytes in the file.
pub fn read(path: &Path, model: &str) -> Res<Index> {
    let bytes = fs::read(path).map_err(|e| Fail::io(path, e))?;
    let nl = bytes.iter().position(|&b| b == b'\n').ok_or_else(|| Fail::format("index has no header"))?;
    let header: serde_json::Value = serde_json::from_slice(&bytes[..nl]).map_err(|_| Fail::format("index has an unknown header"))?;
    if header["version"].as_u64() != Some(FORMAT_VERSION) {
        return Err(Fail::format("index has another format version"));
    }
    if header["model"].as_str() != Some(model) {
        return Err(Fail::format("index was built for another model"));
    }
    let size = |key: &str| header[key].as_u64().and_then(|v| usize::try_from(v).ok()).ok_or_else(damaged);
    let (count, dim) = (size("chunks")?, size("dim")?);
    let left = bytes.len() - (nl + 1);
    let min_chunk = dim.checked_mul(F32_BYTES).and_then(|v| v.checked_add(CHUNK_FIXED_BYTES)).ok_or_else(damaged)?;
    if count.checked_mul(min_chunk).is_none_or(|need| need > left) {
        return Err(damaged());
    }
    let mut cur = Cursor { bytes: &bytes, at: nl + 1 };
    let mut chunks = Vec::with_capacity(count);
    for _ in 0..count {
        let len = cur.u32()? as usize;
        let path = String::from_utf8_lossy(cur.take(len)?).into_owned();
        let (start, end) = (cur.u32()?, cur.u32()?);
        let vector = cur.take(dim * F32_BYTES)?.chunks_exact(F32_BYTES).map(|b| f32::from_le_bytes(b.try_into().unwrap())).collect();
        let n = cur.u32()? as usize;
        let pairs = cur.take(n.checked_mul(TOKEN_PAIR_BYTES).ok_or_else(damaged)?)?;
        let counts = pairs.chunks_exact(TOKEN_PAIR_BYTES).map(|p| (u32::from_le_bytes(p[..4].try_into().unwrap()), u32::from_le_bytes(p[4..].try_into().unwrap()))).collect();
        chunks.push(Chunk { path, start, end, vector, counts });
    }
    if cur.at != bytes.len() {
        return Err(damaged());
    }
    Ok(Index { model: model.to_string(), dim, chunks })
}
