mod common;
use common::*;

/// A model, a two-file corpus and its index; returns (model, index) paths.
fn ready(tmp: &Tmp) -> (String, String) {
    model(&tmp.path("m"), &["alpha", "beta"], &[&[0.0, 0.0], &[1.0, 0.0], &[0.0, 1.0]], false);
    corpus(&tmp.path("c"), &[("a.txt", "alpha"), ("b.txt", "beta")]);
    let (m, i) = (s(&tmp.path("m")).to_string(), s(&tmp.path("i")).to_string());
    assert_eq!(run(&["index", "--model", &m, s(&tmp.path("c")), &i]).0, 0);
    (m, i)
}

#[test]
fn question_comes_from_stdin_not_the_command_line() {
    let tmp = Tmp::new();
    let (m, i) = ready(&tmp);
    let args = ["query", "--model", &m, "--limit", "5", &i];
    let (code, out, _) = run_in(&args, &request("alpha", &["beta"]));
    let v: serde_json::Value = serde_json::from_str(&out).unwrap();
    assert_eq!(code, 0);
    assert_eq!((v["query"][0]["path"].as_str(), v["translation"][0]["path"].as_str()), (Some("a.txt"), Some("b.txt")));
    // Translations may be absent or empty.
    for body in [r#"{"question":"alpha"}"#, r#"{"question":"alpha","translations":[]}"#] {
        let (code, out, _) = run_in(&args, body);
        assert_eq!((code, out.contains(r#""translation":[]"#)), (0, true), "{body}");
    }
    // Text on the command line is refused, with or without `--`.
    for extra in [vec!["alpha"], vec!["--", "alpha"]] {
        let mut more = args.to_vec();
        more.extend(extra);
        let (code, out, err) = run_in(&more, &request("alpha", &[]));
        assert_eq!((code, out.as_str(), err.lines().count()), (1, "", 1), "{more:?}");
    }
}

#[test]
fn bad_stdin_is_refused() {
    let tmp = Tmp::new();
    let (m, i) = ready(&tmp);
    let args = ["query", "--model", &m, "--limit", "5", &i];
    for body in ["", "alpha", "[]", "{}", r#"{"question":""}"#, r#"{"question":"  "}"#, r#"{"question":7}"#, r#"{"question":"a","translations":"b"}"#, r#"{"question":"a","translations":[1]}"#] {
        let (code, out, err) = run_in(&args, body);
        assert_eq!((code, out.as_str(), err.lines().count()), (1, "", 1), "{body:?}");
    }
}

#[test]
fn damaged_index_is_refused_exactly() {
    let tmp = Tmp::new();
    let (m, i) = ready(&tmp);
    let good = std::fs::read(&i).unwrap();
    let nl = good.iter().position(|&b| b == b'\n').unwrap();
    let header = String::from_utf8(good[..nl].to_vec()).unwrap();
    let with_header = |h: &str| [h.as_bytes(), &good[nl..]].concat();
    let mut path_len = good.clone();
    path_len[nl + 1..nl + 5].copy_from_slice(&u32::MAX.to_le_bytes());
    let cases: Vec<(&str, Vec<u8>)> = vec![
        ("truncated body", good[..good.len() - 3].to_vec()),
        ("chunk count past the body", with_header(&header.replace(r#""chunks":2"#, r#""chunks":3"#))),
        ("huge chunk count", with_header(&header.replace(r#""chunks":2"#, r#""chunks":4000000000000"#))),
        ("huge dim", with_header(&header.replace(r#""dim":2"#, r#""dim":4000000000000"#))),
        ("path length past the end", path_len),
        ("trailing bytes", [good.clone(), vec![0]].concat()),
        ("chunk count short of the body", with_header(&header.replace(r#""chunks":2"#, r#""chunks":1"#))),
        ("no chunk count", with_header(&header.replace(r#""chunks":2,"#, ""))),
        ("empty file", Vec::new()),
        ("header without newline", header.clone().into_bytes()),
        ("header that is not JSON", b"zzz\n".to_vec()),
        ("header with no version", with_header(&header.replace(r#","version":1"#, ""))),
    ];
    let args = ["query", "--model", &m, "--limit", "5", &i];
    for (name, bytes) in cases {
        std::fs::write(&i, bytes).unwrap();
        let (code, out, err) = run_in(&args, &request("alpha", &[]));
        assert_eq!((code, out.as_str()), (1, ""), "{name}");
        assert!(err.contains("damaged index") && err.lines().count() == 1, "{name}: {err}");
    }
    // Another version stays exit 3, and the undamaged file still works.
    std::fs::write(&i, with_header(&header.replace(r#""version":1"#, r#""version":9"#))).unwrap();
    assert_eq!(run_in(&args, &request("alpha", &[])).0, 3);
    std::fs::write(&i, good).unwrap();
    assert_eq!(run_in(&args, &request("alpha", &[])).0, 0);
}
