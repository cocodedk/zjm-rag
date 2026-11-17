//! Chunks: markdown splits at headings, then any text splits into overlapping pieces.
use crate::constants::*;

#[derive(Debug, PartialEq)]
pub struct Span {
    pub start: u32,
    pub end: u32,
    pub text: String,
}

fn is_markdown(path: &str) -> bool {
    let lower = path.to_lowercase();
    lower.ends_with(".md") || lower.ends_with(".mdx")
}

fn is_heading(line: &str) -> bool {
    let hashes = line.chars().take_while(|&c| c == '#').count();
    (1..=MAX_MARKDOWN_HASHES).contains(&hashes)
        && line[hashes..].chars().next().is_none_or(char::is_whitespace)
}

/// Sections as (1-based first line, text), cut at headings outside code fences.
fn sections(text: &str) -> Vec<(usize, &str)> {
    let mut starts = vec![(0usize, 1usize)];
    let (mut offset, mut fenced) = (0, false);
    for (i, line) in text.split_inclusive('\n').enumerate() {
        let t = line.trim_start();
        if t.starts_with("```") || t.starts_with("~~~") {
            fenced = !fenced;
        } else if !fenced && is_heading(line) && offset > 0 {
            starts.push((offset, i + 1));
        }
        offset += line.len();
    }
    let ends = starts.iter().skip(1).map(|s| s.0).chain([text.len()]);
    starts.iter().zip(ends).map(|(&(from, line), to)| (line, &text[from..to])).collect()
}

/// Byte end of the piece that starts at the front of `rest`.
fn piece_end(rest: &str) -> usize {
    let Some((end, _)) = rest.char_indices().nth(MAX_CHUNK_CHARS) else { return rest.len() };
    if let Some(nl) = rest[..end].rfind('\n') {
        if rest[..=nl].chars().count() >= MAX_CHUNK_CHARS * LINE_CUT_MIN_PERCENT / 100 {
            return nl + 1;
        }
    }
    end
}

fn newlines(s: &str) -> usize {
    s.bytes().filter(|&b| b == b'\n').count()
}

fn split(text: &str, base_line: usize, out: &mut Vec<Span>) {
    let (mut start, mut line) = (0, base_line);
    loop {
        let end = start + piece_end(&text[start..]);
        let piece = &text[start..end];
        if !piece.trim().is_empty() {
            let lead = &piece[..piece.len() - piece.trim_start().len()];
            let first = line + newlines(lead);
            let last = first + newlines(piece.trim());
            out.push(Span { start: first as u32, end: last as u32, text: piece.to_string() });
        }
        if end == text.len() {
            return;
        }
        let keep = piece.chars().count().saturating_sub(CHUNK_OVERLAP_CHARS).max(1);
        let step = piece.char_indices().nth(keep).map_or(piece.len(), |(b, _)| b);
        line += newlines(&piece[..step]);
        start += step;
    }
}

pub fn chunks(path: &str, text: &str) -> Vec<Span> {
    let mut out = Vec::new();
    if is_markdown(path) {
        for (line, section) in sections(text) {
            split(section, line, &mut out);
        }
    } else {
        split(text, 1, &mut out);
    }
    out
}
