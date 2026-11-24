//! The query request: one JSON object on stdin, so no question text or file name is on the command line.
use crate::constants::{NAMES_KEY, QUESTION_KEY, TRANSLATIONS_KEY};
use crate::error::{Fail, Res};
use serde_json::Value;
use std::io::Read;

/// The question first, then the translations; and the file names to search, `None` for every file.
pub fn read(mut input: impl Read) -> Res<(Vec<String>, Option<Vec<String>>)> {
    let mut raw = Vec::new();
    input.read_to_end(&mut raw).map_err(|e| Fail::new(format!("stdin: {e}")))?;
    let bad = || {
        Fail::new(format!(
            "stdin must be {{\"{QUESTION_KEY}\": text, \"{TRANSLATIONS_KEY}\": [text, ...], \"{NAMES_KEY}\": [name, ...]}}"
        ))
    };
    let body: Value = serde_json::from_slice(&raw).map_err(|_| bad())?;
    let question = body[QUESTION_KEY].as_str().filter(|q| !q.trim().is_empty()).ok_or_else(bad)?;
    let strings = |list: &[Value]| list.iter().map(|t| t.as_str().map(str::to_string).ok_or_else(bad)).collect::<Res<Vec<_>>>();
    let mut texts = vec![question.to_string()];
    match &body[TRANSLATIONS_KEY] {
        Value::Null => {}
        Value::Array(list) => texts.extend(strings(list)?),
        _ => return Err(bad()),
    }
    // An empty selection is refused, never read as every file.
    let names = match &body[NAMES_KEY] {
        Value::Null => None,
        Value::Array(list) if !list.is_empty() => Some(strings(list)?),
        _ => return Err(bad()),
    };
    Ok((texts, names))
}
