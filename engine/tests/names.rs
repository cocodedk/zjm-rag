mod common;
use common::*;
use serde_json::{json, Value};

/// Indexes `files` with a one-word model; returns a query runner: (stdin body, types) -> (exit code, stdout).
fn ready(tmp: &Tmp, files: &[(&str, &str)]) -> impl Fn(&Value, &[&str]) -> (i32, String) {
    model(&tmp.path("m"), &["alpha", "beta"], &[&[0.0, 0.0], &[1.0, 0.0], &[0.0, 1.0]], false);
    corpus(&tmp.path("c"), files);
    let (m, i) = (s(&tmp.path("m")), s(&tmp.path("i")));
    assert_eq!(run(&["index", "--model", m, s(&tmp.path("c")), i]).0, 0);
    move |body, types| {
        let mut args = vec!["query", "--model", m, "--limit", "9"];
        types.iter().for_each(|t| args.extend(["--type", t]));
        args.push(i);
        let (code, out, _) = run_in(&args, &body.to_string());
        (code, out)
    }
}

fn paths(out: &str, key: &str) -> Vec<String> {
    let v: Value = serde_json::from_str(out).unwrap();
    let mut list: Vec<String> = v[key].as_array().unwrap().iter().map(|h| h["path"].as_str().unwrap().to_string()).collect();
    list.sort();
    list
}

const SPLIT: &[(&str, &str)] = &[("a/x.md", "alpha"), ("ab/y.md", "alpha"), ("b/z.md", "alpha")];

#[test]
fn names_pick_files_and_folders_by_prefix() {
    let tmp = Tmp::new();
    let query = ready(&tmp, SPLIT);
    let found = |names: Value| paths(&query(&json!({"question": "alpha", "names": names}), &[]).1, "query");
    assert_eq!(found(json!(["a"])), vec!["a/x.md"]);
    assert_eq!(found(json!(["b/z.md"])), vec!["b/z.md"]);
    assert_eq!(found(json!(["nope"])), Vec::<String>::new());
    assert_eq!(found(Value::Null), vec!["a/x.md", "ab/y.md", "b/z.md"]);
    assert_eq!(paths(&query(&json!({"question": "alpha"}), &[]).1, "query"), vec!["a/x.md", "ab/y.md", "b/z.md"]);
}

#[test]
fn names_and_types_combine_with_and() {
    let tmp = Tmp::new();
    let query = ready(&tmp, &[("a/x.md", "alpha"), ("a/x.txt", "alpha"), ("b/z.md", "alpha")]);
    let (code, out) = query(&json!({"question": "alpha", "names": ["a", "b"]}), &["md"]);
    assert_eq!((code, paths(&out, "query")), (0, vec!["a/x.md".to_string(), "b/z.md".to_string()]));
}

#[test]
fn bad_names_are_refused() {
    let tmp = Tmp::new();
    model(&tmp.path("m"), &["alpha"], &[&[0.0, 0.0], &[1.0, 0.0]], false);
    corpus(&tmp.path("c"), &[("a/x.md", "alpha")]);
    let (m, i) = (s(&tmp.path("m")), s(&tmp.path("i")));
    assert_eq!(run(&["index", "--model", m, s(&tmp.path("c")), i]).0, 0);
    for names in [json!("a"), json!([1]), json!([])] {
        let body = json!({"question": "alpha", "names": names}).to_string();
        let (code, out, err) = run_in(&["query", "--model", m, "--limit", "9", i], &body);
        assert_eq!((code, out.as_str(), err.lines().count()), (1, "", 1), "{names}");
        assert!(err.contains("stdin must be") && err.contains("\"names\""), "{err}");
    }
}

#[test]
fn translation_hits_are_filtered_by_names_too() {
    let tmp = Tmp::new();
    let query = ready(&tmp, &[("a/x.md", "beta"), ("ab/y.md", "beta"), ("b/z.md", "alpha")]);
    let (code, out) = query(&json!({"question": "alpha", "translations": ["beta"], "names": ["a"]}), &[]);
    assert_eq!((code, paths(&out, "query"), paths(&out, "translation")), (0, vec!["a/x.md".to_string()], vec!["a/x.md".to_string()]));
    let (_, all) = query(&json!({"question": "alpha", "translations": ["beta"]}), &[]);
    assert_eq!(paths(&all, "translation"), vec!["a/x.md", "ab/y.md", "b/z.md"]);
}
