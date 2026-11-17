//! `--type`: zg 0.3.0's file-type table and how a value picks files.
use crate::error::{Fail, Res};

pub struct Kind {
    name: &'static str,
    exts: &'static [&'static str],
    files: &'static [&'static str],
}

const KINDS: &[Kind] = &[
    Kind { name: "c", exts: &["c"], files: &[] },
    Kind { name: "cpp", exts: &["cc", "cpp", "cxx", "h", "hpp"], files: &[] },
    Kind { name: "go", exts: &["go"], files: &[] },
    Kind { name: "java", exts: &["java"], files: &[] },
    Kind { name: "javascript", exts: &["js", "mjs", "cjs"], files: &[] },
    Kind { name: "jsx", exts: &["jsx"], files: &[] },
    Kind { name: "python", exts: &["py"], files: &[] },
    Kind { name: "rust", exts: &["rs"], files: &[] },
    Kind { name: "tsx", exts: &["tsx"], files: &[] },
    Kind { name: "typescript", exts: &["ts"], files: &[] },
    Kind { name: "svelte", exts: &["svelte"], files: &[] },
    Kind { name: "vue", exts: &["vue"], files: &[] },
    Kind { name: "bash", exts: &["sh", "bash", "zsh"], files: &[] },
    Kind { name: "csharp", exts: &["cs"], files: &[] },
    Kind { name: "css", exts: &["css"], files: &[] },
    Kind { name: "dockerfile", exts: &[], files: &["Dockerfile"] },
    Kind { name: "kotlin", exts: &["kt", "kts"], files: &[] },
    Kind { name: "less", exts: &["less"], files: &[] },
    Kind { name: "makefile", exts: &[], files: &["Makefile"] },
    Kind { name: "php", exts: &["php"], files: &[] },
    Kind { name: "ruby", exts: &["rb"], files: &[] },
    Kind { name: "scala", exts: &["scala"], files: &[] },
    Kind { name: "scss", exts: &["scss"], files: &[] },
    Kind { name: "sql", exts: &["sql"], files: &[] },
    Kind { name: "swift", exts: &["swift"], files: &[] },
    Kind { name: "csv", exts: &["csv"], files: &[] },
    Kind { name: "html", exts: &["html", "htm"], files: &[] },
    Kind { name: "json", exts: &["json", "jsonc"], files: &[] },
    Kind { name: "markdown", exts: &["md", "mdx"], files: &[] },
    Kind { name: "rst", exts: &["rst"], files: &[] },
    Kind { name: "text", exts: &["txt"], files: &[] },
    Kind { name: "toml", exts: &["toml"], files: &[] },
    Kind { name: "xml", exts: &["xml"], files: &[] },
    Kind { name: "yaml", exts: &["yaml", "yml"], files: &[] },
];

pub enum Filter {
    Kind(&'static Kind),
    Ext(String),
}

/// A type name in any case, an extension with or without its dot, or a file name from the table.
pub fn parse(value: &str) -> Res<Filter> {
    let lower = value.to_lowercase();
    let ext = lower.trim_start_matches('.');
    KINDS
        .iter()
        .find(|k| k.name == lower || k.files.contains(&value))
        .map(Filter::Kind)
        .or_else(|| KINDS.iter().any(|k| k.exts.contains(&ext)).then(|| Filter::Ext(ext.to_string())))
        .ok_or_else(|| Fail::new(format!("unknown file type: {value}")))
}

impl Filter {
    fn matches(&self, path: &str) -> bool {
        let name = path.rsplit('/').next().unwrap_or(path);
        let ext = name.rsplit_once('.').map(|(_, e)| e.to_lowercase());
        match self {
            Filter::Kind(k) => k.files.contains(&name) || ext.is_some_and(|e| k.exts.contains(&e.as_str())),
            Filter::Ext(want) => ext.as_deref() == Some(want),
        }
    }
}

/// True when no filter is given, else when any filter matches.
pub fn any_matches(filters: &[Filter], path: &str) -> bool {
    filters.is_empty() || filters.iter().any(|f| f.matches(path))
}
