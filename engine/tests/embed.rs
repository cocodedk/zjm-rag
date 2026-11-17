mod common;
use common::*;
use zjm_engine::constants::MAX_TOKENS;
use zjm_engine::model::Model;
use zjm_engine::vocabbuild;

const ROWS: &[&[f32]] = &[&[0.0, 1.0], &[3.0, 0.0], &[1.0, 4.0]];

#[test]
fn pooling_matches_a_hand_computed_mean() {
    // Mean of (3, 0) and (1, 4) is (2, 2); normalized, (1/sqrt 2, 1/sqrt 2).
    let want = (0.5f64).sqrt() as f32;
    for half in [false, true] {
        let tmp = Tmp::new();
        model(&tmp.path("m"), &["a", "b"], ROWS, half);
        let m = Model::open(&tmp.path("m")).unwrap();
        let v = m.embed("a B").unwrap().vector;
        assert_eq!(v, vec![want, want], "half={half}");
    }
}

#[test]
fn unknown_tokens_dropped_and_1024_cap() {
    let tmp = Tmp::new();
    model(&tmp.path("m"), &["a", "b"], ROWS, false);
    let m = Model::open(&tmp.path("m")).unwrap();
    // The unknown word "zzz" (id 0, row (0, 1)) is dropped, not averaged in.
    assert_eq!(m.embed("a zzz b").unwrap().vector, m.embed("a b").unwrap().vector);
    // Nothing known: the zero vector.
    assert_eq!(m.embed("zzz").unwrap().vector, vec![0.0, 0.0]);
    // Only the first 1,024 tokens count: 1,024 a's, then b's, is just a.
    let text = format!("{} {}", vec!["a"; MAX_TOKENS].join(" "), ["b"; 6].join(" "));
    assert_eq!(m.embed(&text).unwrap().vector, vec![1.0, 0.0]);
    // The keyword leg's ids are not capped, and the unknown token is not in them.
    assert_eq!(m.embed(&text).unwrap().ids.len(), MAX_TOKENS + 6);
    assert_eq!(m.embed("zzz a").unwrap().ids, vec![1]);
}

fn unigram_json() -> String {
    let pieces = [("<unk>", 0.0), ("▁", -2.0), ("▁a", -1.0), ("▁ab", -1.5), ("b", -2.5), ("a", -2.0), ("▁cat", -1.0), ("c", -3.0), ("at", -2.2), ("ñ", -3.0)];
    let vocab: Vec<String> = pieces.iter().map(|(t, s)| format!("[\"{t}\",{s}]")).collect();
    format!(
        r#"{{"version":"1.0","truncation":null,"padding":null,"added_tokens":[],"normalizer":{{"type":"NFKC"}},
"pre_tokenizer":{{"type":"Metaspace","replacement":"▁","prepend_scheme":"always","split":true}},
"post_processor":null,"decoder":null,"model":{{"type":"Unigram","unk_id":0,"byte_fallback":false,"vocab":[{}]}}}}"#,
        vocab.join(",")
    )
}

#[test]
fn prebuilt_vocab_matches_the_stock_tokenizer() {
    let tmp = Tmp::new();
    let plain = tmp.path("plain");
    let rows: Vec<Vec<f32>> = (0..10).map(|i| vec![i as f32, 1.0]).collect();
    let refs: Vec<&[f32]> = rows.iter().map(|r| r.as_slice()).collect();
    let names = ["a"; 9];
    model(&plain, &names, &refs, false);
    std::fs::write(plain.join("tokenizer.json"), unigram_json()).unwrap();
    let fast = tmp.path("fast");
    std::fs::create_dir_all(&fast).unwrap();
    std::fs::copy(plain.join("model.safetensors"), fast.join("model.safetensors")).unwrap();
    vocabbuild::build(&plain.join("tokenizer.json"), &fast.join("vocab")).unwrap();
    let (stock, prebuilt) = (Model::open(&plain).unwrap(), Model::open(&fast).unwrap());
    for text in ["a ab cat", "ab  ab", "ＡＢ cat", "xyz", "a ñ q ñ", "cats at b", "", "  ", "ab\nat"] {
        assert_eq!(stock.tok.encode(text).unwrap(), prebuilt.tok.encode(text).unwrap(), "text {text:?}");
    }
    assert_eq!(stock.tok.unk(), prebuilt.tok.unk());
    assert_eq!(prebuilt.tok.encode("cat").unwrap(), vec![6]);
}
