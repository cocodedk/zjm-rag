mod common;
use zjm_engine::chunk::chunks;

fn ranges(path: &str, text: &str) -> Vec<(u32, u32)> {
    chunks(path, text).iter().map(|c| (c.start, c.end)).collect()
}

/// Lines of `width` characters including the newline.
fn lines(count: usize, width: usize) -> String {
    (0..count).map(|_| format!("{}\n", "x".repeat(width - 1))).collect()
}

#[test]
fn markdown_splits_at_headings() {
    let text = "# A\ntext\n```\n# not a heading\n```\n## B\nmore\n#nospace\n";
    // The fenced "#" and the "#nospace" line are not headings.
    assert_eq!(ranges("a.md", text), vec![(1, 5), (6, 8)]);
    assert_eq!(chunks("a.md", text)[1].text, "## B\nmore\n#nospace\n");
    assert_eq!(ranges("a.md", "intro\n# A\nx\n"), vec![(1, 1), (2, 3)]);
}

#[test]
fn long_section_splits_with_overlap_at_a_line_end() {
    // 60-char lines: a piece is exactly 60 lines, the next starts 540 chars (9 lines) back.
    assert_eq!(ranges("a.txt", &lines(100, 60)), vec![(1, 60), (52, 100)]);
    // 70-char lines: 3,600 chars end mid-line 52, so the piece is cut at the end of line 51 (3,570
    // chars, past the 70% mark); the next piece starts 540 chars back, inside line 44.
    assert_eq!(ranges("a.txt", &lines(120, 70)), vec![(1, 51), (44, 94), (87, 120)]);
    let text = lines(100, 60);
    assert!(chunks("a.txt", &text).iter().all(|c| c.text.chars().count() <= 3600));
}

#[test]
fn other_files_use_the_same_splitter() {
    let long = lines(100, 60);
    assert_eq!(ranges("a.txt", &long), ranges("b.rs", &long));
    // A "#" line splits only markdown.
    let text = "# one\nx\n# two\ny\n";
    assert_eq!(ranges("a.py", text), vec![(1, 4)]);
    assert_eq!(ranges("a.md", text), vec![(1, 2), (3, 4)]);
    assert!(chunks("a.txt", " \n\t\n").is_empty());
}
