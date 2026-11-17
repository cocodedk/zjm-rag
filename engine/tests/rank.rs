mod common;
use common::*;
use serde_json::Value;
use std::path::Path;
use zjm_engine::index::Chunk;
use zjm_engine::rank::{bm25_ranking, fuse};

/// Indexes `files` with a model whose words all have the given rows; returns the model folder and index.
fn setup(tmp: &Tmp, words: &[&str], rows: &[&[f32]], files: &[(&str, &str)]) -> (String, String) {
    model(&tmp.path("m"), words, rows, false);
    corpus(&tmp.path("c"), files);
    let (code, _, err) = run(&["index", "--model", s(&tmp.path("m")), s(&tmp.path("c")), s(&tmp.path("i"))]);
    assert_eq!(code, 0, "{err}");
    (s(&tmp.path("m")).into(), s(&tmp.path("i")).into())
}

fn query(model: &str, index: &str, limit: &str, texts: &[&str]) -> Value {
    let args = ["query", "--model", model, "--limit", limit, index];
    let (code, out, err) = run_in(&args, &request(texts[0], &texts[1..]));
    assert_eq!(code, 0, "{err}");
    serde_json::from_str(&out).unwrap()
}

fn paths(group: &Value) -> Vec<&str> {
    group.as_array().unwrap().iter().map(|h| h["path"].as_str().unwrap()).collect()
}

/// Every word has the same row, so the vector leg cannot tell chunks apart.
const FLAT: &[&[f32]] = &[&[0.0, 0.0], &[1.0, 0.0], &[1.0, 0.0], &[1.0, 0.0], &[1.0, 0.0]];
const FLAT_WORDS: &[&str] = &["alpha", "beta", "gamma", "zebra"];
const FLAT_FILES: &[(&str, &str)] = &[("a.txt", "alpha beta"), ("b.txt", "gamma beta"), ("c.txt", "zebra alpha")];

#[test]
fn exact_token_wins_through_the_keyword_leg() {
    let tmp = Tmp::new();
    let (m, i) = setup(&tmp, FLAT_WORDS, FLAT, FLAT_FILES);
    // The vector leg ties and falls back to file order (a, b, c); only c holds "zebra".
    // c: 1/61 + 1/63; a: 1/61; b: 1/62.
    let hits = query(&m, &i, "10", &["zebra"]);
    assert_eq!(paths(&hits["query"]), vec!["c.txt", "a.txt", "b.txt"]);
    assert_eq!(hits["query"][0]["rank"], 1);
    assert_eq!((hits["query"][0]["start"].as_u64(), hits["query"][0]["end"].as_u64()), (Some(1), Some(1)));
}

#[test]
fn paraphrase_wins_through_the_vector_leg() {
    let tmp = Tmp::new();
    let rows: &[&[f32]] = &[&[0.0, 0.0], &[1.0, 0.0], &[0.9, 0.1], &[0.0, 1.0]];
    let (m, i) = setup(&tmp, &["car", "auto", "tree"], rows, &[("a.txt", "tree tree"), ("b.txt", "auto auto")]);
    // "car" is in no chunk, so the keyword leg is empty; "auto" is close to it, "tree" is not.
    let idx = zjm_engine::index::read(Path::new(&i), "m").unwrap();
    let chunks: Vec<&Chunk> = idx.chunks.iter().collect();
    assert!(bm25_ranking(&chunks, &[1]).is_empty());
    assert_eq!(paths(&query(&m, &i, "10", &["car"])["query"]), vec!["b.txt", "a.txt"]);
}

#[test]
fn fusion_order_matches_a_worked_example() {
    // A ranks c2, c0, c1; B ranks c0, c1. Scores: c0 = 1/62 + 1/61, c1 = 1/63 + 1/62, c2 = 1/61.
    let fused = fuse(&[vec![2, 0, 1], vec![0, 1]]);
    let want = [(0, 1.0 / 62.0 + 1.0 / 61.0), (1, 1.0 / 63.0 + 1.0 / 62.0), (2, 1.0 / 61.0)];
    assert_eq!(fused.iter().map(|f| f.0).collect::<Vec<_>>(), vec![0, 1, 2]);
    assert!(fused.iter().zip(want).all(|(f, w)| f.0 == w.0 && (f.1 - w.1).abs() < 1e-12));
    // BM25 worked example: both chunks hold t1 once, c1 is longer, so c0 outranks c1.
    let chunk = |counts: Vec<(u32, u32)>| Chunk { path: "p".into(), start: 1, end: 1, vector: vec![], counts };
    let (c0, c1) = (chunk(vec![(1, 1)]), chunk(vec![(1, 1), (2, 1)]));
    assert_eq!(bm25_ranking(&[&c1, &c0], &[1]), vec![1, 0]);
    // A chunk with no query term is not ranked at all.
    assert_eq!(bm25_ranking(&[&c0, &c1], &[2]), vec![1]);
}

#[test]
fn translations_form_their_own_group() {
    let tmp = Tmp::new();
    let (m, i) = setup(&tmp, FLAT_WORDS, FLAT, FLAT_FILES);
    let hits = query(&m, &i, "1", &["gamma", "zebra", "unknownword"]);
    assert_eq!(paths(&hits["query"]), vec!["b.txt"]);
    // The translations' own rankings fuse: "zebra" puts c first, a second text adds nothing known.
    assert_eq!(paths(&hits["translation"]), vec!["c.txt"]);
    assert!(query(&m, &i, "5", &["gamma"])["translation"].as_array().unwrap().is_empty());
}

#[test]
fn limit_caps_each_group() {
    let tmp = Tmp::new();
    let (m, i) = setup(&tmp, FLAT_WORDS, FLAT, FLAT_FILES);
    for (limit, want) in [("1", 1), ("2", 2), ("9", 3)] {
        let hits = query(&m, &i, limit, &["alpha", "beta"]);
        assert_eq!((hits["query"].as_array().unwrap().len(), hits["translation"].as_array().unwrap().len()), (want, want));
    }
    let ranks: Vec<u64> = query(&m, &i, "9", &["alpha"])["query"].as_array().unwrap().iter().map(|h| h["rank"].as_u64().unwrap()).collect();
    assert_eq!(ranks, vec![1, 2, 3]);
}
