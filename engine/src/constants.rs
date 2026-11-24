//! Every number and file name that means something, defined once.
pub const MAX_CHUNK_CHARS: usize = 3600;
pub const CHUNK_OVERLAP_CHARS: usize = 540;
/// A cut at a line end is taken only when it falls in the last 30% of the piece.
pub const LINE_CUT_MIN_PERCENT: usize = 70;
pub const MAX_MARKDOWN_HASHES: usize = 6;
pub const MAX_TOKENS: usize = 1024;
pub const MAX_FILE_BYTES: u64 = 16 * 1024 * 1024;
pub const NUL_SCAN_BYTES: usize = 8 * 1024;

pub const BM25_K1: f64 = 1.2;
pub const BM25_B: f64 = 0.75;
pub const RRF_K: f64 = 60.0;

pub const EXIT_OK: i32 = 0;
pub const EXIT_ERROR: i32 = 1;
pub const EXIT_FORMAT: i32 = 3;
pub const FORMAT_VERSION: u64 = 1;

pub const QUESTION_KEY: &str = "question";
pub const TRANSLATIONS_KEY: &str = "translations";
pub const NAMES_KEY: &str = "names";
/// Bytes of a chunk record with an empty path, no vector and no token pairs: three u32 and a count.
pub const CHUNK_FIXED_BYTES: usize = 16;
pub const TOKEN_PAIR_BYTES: usize = 8;
pub const F32_BYTES: usize = 4;

pub const MODEL_FILE: &str = "model.safetensors";
pub const TOKENIZER_FILE: &str = "tokenizer.json";
pub const TENSOR_NAME: &str = "embeddings";
pub const VOCAB_DIR: &str = "vocab";
pub const FST_FILE: &str = "vocab.fst";
pub const SCORES_FILE: &str = "scores.f64";
pub const SKELETON_FILE: &str = "skeleton.json";
pub const META_FILE: &str = "meta.json";
/// tokenizers' own penalty below the lowest score for an unknown character.
pub const UNK_PENALTY: f64 = 10.0;
/// Bytes of a safetensors file's length prefix.
pub const SAFETENSORS_PREFIX: usize = 8;
