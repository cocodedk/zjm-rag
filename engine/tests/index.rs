mod common;
use common::*;
use zjm_engine::index::{self, Chunk, Index};

const ROWS: &[&[f32]] = &[&[0.0, 0.0], &[1.0, 0.0], &[0.0, 1.0]];

#[test]
fn skipped_files_make_no_chunk_and_empty_index_is_valid() {
    let tmp = Tmp::new();
    model(&tmp.path("m"), &["alpha", "beta"], ROWS, false);
    let big = vec![b'a'; 16 * 1024 * 1024 + 1];
    corpus(&tmp.path("c"), &[("empty.txt", ""), ("blank.txt", " \n\t\n"), ("ok.txt", "alpha")]);
    std::fs::write(tmp.path("c/nul.bin"), b"alpha\0beta").unwrap();
    std::fs::write(tmp.path("c/big.txt"), big).unwrap();
    std::fs::write(tmp.path("c/latin.txt"), b"alpha \xff beta").unwrap();
    let (code, out, _) = run(&["index", "--model", s(&tmp.path("m")), s(&tmp.path("c")), s(&tmp.path("i1"))]);
    assert_eq!((code, out.trim()), (0, r#"{"chunks":2}"#)); // ok.txt and latin.txt only
    let only_skipped = tmp.path("c2");
    corpus(&only_skipped, &[("empty.txt", ""), ("blank.txt", "\n")]);
    let (code, out, _) = run(&["index", "--model", s(&tmp.path("m")), s(&only_skipped), s(&tmp.path("i2"))]);
    assert_eq!((code, out.trim()), (0, r#"{"chunks":0}"#));
    let args = ["query", "--model", s(&tmp.path("m")), "--limit", "5", s(&tmp.path("i2"))];
    let (code, out, _) = run_in(&args, &request("alpha", &["beta"]));
    assert_eq!((code, out.trim()), (0, r#"{"query":[],"translation":[]}"#));
}

#[test]
fn index_round_trip() {
    let tmp = Tmp::new();
    let idx = Index {
        model: "m".into(),
        dim: 2,
        chunks: vec![
            Chunk { path: "a/ü.md".into(), start: 1, end: 7, vector: vec![0.5, -0.25], counts: vec![(1, 2), (9, 1)] },
            Chunk { path: "b".into(), start: 3, end: 3, vector: vec![0.0, 0.0], counts: vec![] },
        ],
    };
    index::write(&tmp.path("i"), &idx).unwrap();
    assert_eq!(index::read(&tmp.path("i"), "m").unwrap(), idx);
    // Through the binary: one chunk per file, with the model's own vector for its text.
    model(&tmp.path("m"), &["alpha", "beta"], ROWS, false);
    corpus(&tmp.path("c"), &[("a.txt", "alpha"), ("b.txt", "beta")]);
    run(&["index", "--model", s(&tmp.path("m")), s(&tmp.path("c")), s(&tmp.path("i2"))]);
    let read = index::read(&tmp.path("i2"), "m").unwrap();
    let got: Vec<_> = read.chunks.iter().map(|c| (c.path.as_str(), c.vector.clone(), c.counts.clone())).collect();
    assert_eq!(got, vec![("a.txt", vec![1.0, 0.0], vec![(1, 1)]), ("b.txt", vec![0.0, 1.0], vec![(2, 1)])]);
}

#[test]
fn other_version_or_model_exits_3() {
    let tmp = Tmp::new();
    model(&tmp.path("m"), &["alpha", "beta"], ROWS, false);
    model(&tmp.path("other"), &["alpha", "beta"], ROWS, false);
    corpus(&tmp.path("c"), &[("a.txt", "alpha")]);
    let idx = tmp.path("i");
    run(&["index", "--model", s(&tmp.path("m")), s(&tmp.path("c")), s(&idx)]);
    let ask = |model: &str, index: &str| run_in(&["query", "--model", model, "--limit", "3", index], &request("alpha", &[])).0;
    assert_eq!(ask(s(&tmp.path("m")), s(&idx)), 0);
    assert_eq!(ask(s(&tmp.path("other")), s(&idx)), 3);
    let text = std::fs::read(&idx).unwrap();
    let changed = String::from_utf8_lossy(&text).replacen(r#""version":1"#, r#""version":2"#, 1);
    std::fs::write(tmp.path("v2"), changed.as_bytes()).unwrap();
    let args = ["query", "--model", s(&tmp.path("m")), "--limit", "3", s(&tmp.path("v2"))];
    let (code, _, err) = run_in(&args, &request("alpha", &[]));
    assert_eq!((code, err.lines().count()), (3, 1));
    // A missing index is an ordinary error, exit 1.
    assert_eq!(ask(s(&tmp.path("m")), s(&tmp.path("nope"))), 1);
}
