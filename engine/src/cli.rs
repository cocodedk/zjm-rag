//! Argument parsing and the three subcommands.
use crate::error::{Fail, Res};
use crate::{indexer, index, model::Model, search, types, vocabbuild};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

const USAGE: &str = "usage: zjm-engine vocab TOKENIZER_JSON OUT_DIR | index --model DIR CORPUS INDEX | \
query --model DIR --limit N [--type T]... INDEX -- QUESTION [TRANSLATION]...";

#[derive(Default)]
struct Args {
    model: Option<PathBuf>,
    limit: Option<usize>,
    types: Vec<String>,
    positional: Vec<String>,
    texts: Vec<String>,
}

fn parse(args: &[String]) -> Res<Args> {
    let mut a = Args::default();
    let mut it = args.iter();
    while let Some(arg) = it.next() {
        let mut value = |flag: &str| it.next().cloned().ok_or_else(|| Fail::new(format!("{flag} needs a value")));
        match arg.as_str() {
            "--model" => a.model = Some(value("--model")?.into()),
            "--limit" => a.limit = Some(value("--limit")?.parse().map_err(|_| Fail::new("--limit must be a number"))?),
            "--type" => a.types.push(value("--type")?),
            "--" => {
                a.texts = it.cloned().collect();
                break;
            }
            other if other.starts_with("--") => return Err(Fail::new(format!("unknown option {other}"))),
            other => a.positional.push(other.to_string()),
        }
    }
    Ok(a)
}

fn hits(list: &[search::Hit]) -> Value {
    list.iter().map(|h| json!({"path": h.path, "start": h.start, "end": h.end, "rank": h.rank})).collect()
}

/// Runs one command; returns what to print on stdout.
pub fn run(args: &[String]) -> Res<String> {
    let usage = || Fail::new(USAGE);
    let (cmd, rest) = args.split_first().ok_or_else(usage)?;
    let a = parse(rest)?;
    let pos = |n: usize| (a.positional.len() == n).then_some(()).ok_or_else(usage);
    match cmd.as_str() {
        "vocab" => {
            pos(2)?;
            vocabbuild::build(Path::new(&a.positional[0]), Path::new(&a.positional[1]))?;
            Ok(String::new())
        }
        "index" => {
            pos(2)?;
            let model = Model::open(a.model.as_deref().ok_or_else(usage)?)?;
            let n = indexer::build(&model, Path::new(&a.positional[0]), Path::new(&a.positional[1]))?;
            Ok(json!({"chunks": n}).to_string())
        }
        "query" => {
            pos(1)?;
            let (model_dir, limit) = (a.model.as_deref().ok_or_else(usage)?, a.limit.ok_or_else(usage)?);
            if a.texts.is_empty() {
                return Err(usage());
            }
            let filters = a.types.iter().map(|t| types::parse(t)).collect::<Res<Vec<_>>>()?;
            let model = Model::open(model_dir)?;
            let idx = index::read(Path::new(&a.positional[0]), &model.name)?;
            let (query, translation) = search::search(&model, &idx, &filters, &a.texts, limit)?;
            Ok(json!({"query": hits(&query), "translation": hits(&translation)}).to_string())
        }
        _ => Err(usage()),
    }
}
