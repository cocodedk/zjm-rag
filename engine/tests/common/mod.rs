#![allow(dead_code)]
//! Tiny synthetic models, temp folders and a runner for the binary.
use std::path::{Path, PathBuf};
use std::io::Write;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};

static COUNTER: AtomicUsize = AtomicUsize::new(0);

pub struct Tmp(pub PathBuf);

impl Tmp {
    pub fn new() -> Tmp {
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let dir = std::env::temp_dir().join(format!("zjm-engine-test-{}-{n}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        Tmp(dir)
    }
    pub fn path(&self, rel: &str) -> PathBuf {
        self.0.join(rel)
    }
}

impl Drop for Tmp {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// F16 bits of the few values the tests store.
fn half_bits(v: f32) -> u16 {
    match v as i32 {
        0 => 0x0000,
        1 => 0x3C00,
        3 => 0x4200,
        4 => 0x4400,
        _ => panic!("no f16 bits for {v}"),
    }
}

/// A model folder: row 0 is the unknown token, row i+1 is `words[i]`.
pub fn model(dir: &Path, words: &[&str], rows: &[&[f32]], half: bool) {
    assert_eq!(words.len() + 1, rows.len());
    std::fs::create_dir_all(dir).unwrap();
    let dim = rows[0].len();
    let data: Vec<u8> = rows.iter().flat_map(|r| r.iter()).flat_map(|&v| if half { half_bits(v).to_le_bytes().to_vec() } else { v.to_le_bytes().to_vec() }).collect();
    let header = format!(
        r#"{{"embeddings":{{"dtype":"{}","shape":[{},{dim}],"data_offsets":[0,{}]}}}}"#,
        if half { "F16" } else { "F32" },
        rows.len(),
        data.len()
    );
    let mut file = (header.len() as u64).to_le_bytes().to_vec();
    file.extend(header.as_bytes());
    file.extend(data);
    std::fs::write(dir.join("model.safetensors"), file).unwrap();
    let vocab: Vec<String> = std::iter::once("[UNK]").chain(words.iter().copied()).enumerate().map(|(i, w)| format!("\"{w}\":{i}")).collect();
    let tokenizer = format!(
        r###"{{"version":"1.0","truncation":null,"padding":null,"added_tokens":[],"normalizer":{{"type":"Lowercase"}},
"pre_tokenizer":{{"type":"Whitespace"}},"post_processor":null,"decoder":null,
"model":{{"type":"WordPiece","unk_token":"[UNK]","continuing_subword_prefix":"##","max_input_chars_per_word":100,"vocab":{{{}}}}}}}"###,
        vocab.join(",")
    );
    std::fs::write(dir.join("tokenizer.json"), tokenizer).unwrap();
}

/// A corpus folder from (relative path, text) pairs.
pub fn corpus(dir: &Path, files: &[(&str, &str)]) {
    for (rel, text) in files {
        let path = dir.join(rel);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, text).unwrap();
    }
}

/// Runs the binary with nothing on stdin: (exit code, stdout, stderr).
pub fn run(args: &[&str]) -> (i32, String, String) {
    run_in(args, "")
}

/// Runs the binary with `stdin` as its standard input.
pub fn run_in(args: &[&str], stdin: &str) -> (i32, String, String) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_zjm-engine"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(stdin.as_bytes()).unwrap();
    let out = child.wait_with_output().unwrap();
    (out.status.code().unwrap(), String::from_utf8_lossy(&out.stdout).into(), String::from_utf8_lossy(&out.stderr).into())
}

/// A query request body for stdin.
pub fn request(question: &str, translations: &[&str]) -> String {
    serde_json::json!({"question": question, "translations": translations}).to_string()
}

/// The path as a string that lives as long as the test process (leaked on purpose).
pub fn s(p: &Path) -> &'static str {
    Box::leak(p.to_str().unwrap().to_string().into_boxed_str())
}
