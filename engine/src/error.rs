//! One error type: a message for stderr and the exit code it maps to.
use crate::constants::{EXIT_ERROR, EXIT_FORMAT};
use std::path::Path;

#[derive(Debug)]
pub struct Fail {
    pub code: i32,
    pub msg: String,
}

pub type Res<T> = Result<T, Fail>;

impl Fail {
    pub fn new(msg: impl Into<String>) -> Fail {
        Fail { code: EXIT_ERROR, msg: msg.into() }
    }
    /// The index was written by another format version or for another model.
    pub fn format(msg: impl Into<String>) -> Fail {
        Fail { code: EXIT_FORMAT, msg: msg.into() }
    }
    pub fn io(path: &Path, e: std::io::Error) -> Fail {
        Fail::new(format!("{}: {e}", path.display()))
    }
}

impl From<serde_json::Error> for Fail {
    fn from(e: serde_json::Error) -> Fail {
        Fail::new(format!("bad JSON: {e}"))
    }
}

impl From<Box<dyn std::error::Error + Send + Sync>> for Fail {
    fn from(e: Box<dyn std::error::Error + Send + Sync>) -> Fail {
        Fail::new(format!("tokenizer: {e}"))
    }
}
