mod common;
use common::*;
use zjm_engine::types::{any_matches, parse};

fn picks(value: &str, path: &str) -> bool {
    any_matches(&[parse(value).unwrap()], path)
}

#[test]
fn type_matches_name_in_any_case_extension_and_file_name() {
    for value in ["python", "Python", "PYTHON", "py", ".py", "PY"] {
        assert!(picks(value, "src/a.py"), "{value}");
        assert!(!picks(value, "src/a.rs"), "{value}");
    }
    assert!(picks("markdown", "a.MD") && picks("markdown", "a.mdx") && !picks("markdown", "a.txt"));
    assert!(picks("md", "a.md") && !picks("md", "a.mdx"));
    assert!(picks("Dockerfile", "x/Dockerfile") && picks("dockerfile", "Dockerfile") && !picks("Dockerfile", "x/a.txt"));
    assert!(picks("Makefile", "Makefile") && !picks("yml", "a.yaml") && picks("yaml", "a.yml"));
    assert!(any_matches(&[], "anything"));
    // Through the binary: only the python file is searched.
    let tmp = Tmp::new();
    model(&tmp.path("m"), &["alpha"], &[&[0.0, 0.0], &[1.0, 0.0]], false);
    corpus(&tmp.path("c"), &[("a.py", "alpha"), ("b.md", "alpha"), ("Dockerfile", "alpha")]);
    run(&["index", "--model", s(&tmp.path("m")), s(&tmp.path("c")), s(&tmp.path("i"))]);
    let (model_dir, index) = (tmp.path("m"), tmp.path("i"));
    let paths = |t: &[&str]| {
        let mut args = vec!["query", "--model", s(&model_dir), "--limit", "9"];
        t.iter().for_each(|v| args.extend(["--type", v]));
        args.push(s(&index));
        let out: serde_json::Value = serde_json::from_str(&run_in(&args, &request("alpha", &[])).1).unwrap();
        out["query"].as_array().unwrap().iter().map(|h| h["path"].as_str().unwrap().to_string()).collect::<Vec<_>>()
    };
    assert_eq!(paths(&["Python"]), vec!["a.py"]);
    assert_eq!(paths(&["py", "dockerfile"]), vec!["Dockerfile", "a.py"]);
    assert_eq!(paths(&[]).len(), 3);
}

#[test]
fn unknown_type_is_refused() {
    assert!(parse("klingon").is_err());
    assert!(parse("").is_err());
    let tmp = Tmp::new();
    model(&tmp.path("m"), &["alpha"], &[&[0.0, 0.0], &[1.0, 0.0]], false);
    corpus(&tmp.path("c"), &[("a.py", "alpha")]);
    run(&["index", "--model", s(&tmp.path("m")), s(&tmp.path("c")), s(&tmp.path("i"))]);
    let args = ["query", "--model", s(&tmp.path("m")), "--limit", "3", "--type", "klingon", s(&tmp.path("i"))];
    let (code, out, err) = run_in(&args, &request("alpha", &[]));
    assert_eq!((code, out.as_str()), (1, ""));
    assert!(err.contains("klingon"), "{err}");
}
