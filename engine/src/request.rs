//! The query request: one JSON object on stdin, so no question text is on the command line.
use crate::constants::{QUESTION_KEY, TRANSLATIONS_KEY};
use crate::error::{Fail, Res};
use std::io::Read;

/// The question first, then the translations.
pub fn read_texts(mut input: impl Read) -> Res<Vec<String>> {
    let mut raw = Vec::new();
    input.read_to_end(&mut raw).map_err(|e| Fail::new(format!("stdin: {e}")))?;
    let bad = || Fail::new(format!("stdin must be {{\"{QUESTION_KEY}\": text, \"{TRANSLATIONS_KEY}\": [text, ...]}}"));
    let body: serde_json::Value = serde_json::from_slice(&raw).map_err(|_| bad())?;
    let question = body[QUESTION_KEY].as_str().filter(|q| !q.trim().is_empty()).ok_or_else(bad)?;
    let mut texts = vec![question.to_string()];
    match &body[TRANSLATIONS_KEY] {
        serde_json::Value::Null => {}
        serde_json::Value::Array(list) => {
            for t in list {
                texts.push(t.as_str().ok_or_else(bad)?.to_string());
            }
        }
        _ => return Err(bad()),
    }
    Ok(texts)
}
