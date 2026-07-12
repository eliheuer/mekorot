//! Hebrew × Arabic scale/weight comparison specimen.
//!
//! Renders Mekorot (Hebrew) and Open Gate Naskh (Arabic) together in long
//! text blocks on shared baselines, with metric guides, so scale and weight
//! mismatches are visible at a glance. The merge decisions (scale factor,
//! weight target) are Eli's — this sheet is the evidence.
//!
//! Ported from the virtua-grotesk designbot setup (same palette, same
//! sfnt family-name loader, same text helpers).
//!
//!     designbot --render specimen_hebrew_arabic.rs --output out.png
//! or in a cargo scratchpad: cargo run --release -- [out_dir]

use designbot::prelude::*;

const W: f64 = 2400.0;
const H: f64 = 3200.0;
const MARGIN: f64 = 96.0;

fn bg() -> Color { Color::rgb(16, 16, 16) }
fn ink() -> Color { Color::rgb(235, 235, 235) }
fn green() -> Color { Color::rgb(0x14, 0xd6, 0x7e) }
fn blue() -> Color { Color::rgb(0x5c, 0x86, 0xff) }
fn red() -> Color { Color::rgb(0xff, 0x3a, 0x28) }

// --- minimal sfnt reader (family name for ctx.font()) -----------------------

fn read_u16(d: &[u8], o: usize) -> u16 {
    u16::from_be_bytes([d[o], d[o + 1]])
}

fn find_table(d: &[u8], tag: &[u8; 4]) -> Option<usize> {
    let n = read_u16(d, 4) as usize;
    (0..n).find_map(|i| {
        let rec = 12 + i * 16;
        (&d[rec..rec + 4] == tag)
            .then(|| u32::from_be_bytes([d[rec + 8], d[rec + 9], d[rec + 10], d[rec + 11]]) as usize)
    })
}

fn load_family(renderer: &mut Renderer, path: &str) -> String {
    renderer.load_font(path).expect("load font");
    let data = std::fs::read(path).expect("read font");
    let name = find_table(&data, b"name").expect("no name table");
    let count = read_u16(&data, name + 2) as usize;
    let string_off = name + read_u16(&data, name + 4) as usize;
    for want in [16u16, 1] {
        for i in 0..count {
            let rec = name + 6 + i * 12;
            if read_u16(&data, rec) == 3 && read_u16(&data, rec + 6) == want {
                let len = read_u16(&data, rec + 8) as usize;
                let off = string_off + read_u16(&data, rec + 10) as usize;
                let units: Vec<u16> = data[off..off + len]
                    .chunks_exact(2)
                    .map(|c| u16::from_be_bytes([c[0], c[1]]))
                    .collect();
                return String::from_utf16_lossy(&units);
            }
        }
    }
    panic!("no Windows family name record in {path}");
}

// --- specimen ----------------------------------------------------------------

struct Sheet {
    renderer: Renderer,
    mono: String,
    hebrew: String,
    hebrew_medium: String,
    arabic: String,
}

// UDHR article 1 — long, neutral, standard specimen text in both scripts.
const HEB: &str = "כל בני האדם נולדו בני חורין ושווים בערכם ובזכויותיהם. כולם חוננו בתבונה ובמצפון, לפיכך חובה עליהם לנהוג איש ברעהו ברוח של אחווה.";
const ARA: &str = "يولد جميع الناس أحراراً متساوين في الكرامة والحقوق. وقد وهبوا عقلاً وضميراً وعليهم أن يعامل بعضهم بعضاً بروح الإخاء.";

impl Sheet {
    fn label(&self, ctx: &mut Canvas, txt: &str, x: f64, y: f64, color: Color, align: i8) {
        let w = self.renderer.text_width(txt, Some(&self.mono), 30.0, &[]);
        let x = match align { -1 => x, 0 => x - w / 2.0, _ => x - w };
        ctx.font(&self.mono)
            .clear_font_variations()
            .font_size(30.0)
            .fill(color)
            .text_align(TextAlign::Left)
            .text(txt, x, y);
    }

    /// Right-aligned RTL line; returns the drawn width.
    fn rtl_line(&self, ctx: &mut Canvas, family: &str, txt: &str, right: f64, y: f64,
                size: f64, color: Color) -> f64 {
        let w = self.renderer.text_width(txt, Some(family), size, &[]);
        ctx.font(family)
            .clear_font_variations()
            .font_size(size)
            .fill(color)
            .text_align(TextAlign::Left)
            .text(txt, right - w, y);
        w
    }

    /// Greedy word wrap for RTL text at `size` into lines of at most `max_w`.
    fn wrap(&self, family: &str, txt: &str, size: f64, max_w: f64) -> Vec<String> {
        let mut lines = vec![String::new()];
        for word in txt.split_whitespace() {
            let cand = if lines.last().unwrap().is_empty() {
                word.to_string()
            } else {
                format!("{} {}", lines.last().unwrap(), word)
            };
            if self.renderer.text_width(&cand, Some(family), size, &[]) <= max_w {
                *lines.last_mut().unwrap() = cand;
            } else {
                lines.push(word.to_string());
            }
        }
        lines
    }
}

fn main() {
    let home = std::env::var("HOME").unwrap();
    let out_dir = std::env::args().nth(1).unwrap_or_else(|| {
        format!("{home}/GH/repos/mekorot/documentation/images/merge")
    });
    std::fs::create_dir_all(&out_dir).expect("create output dir");

    let mut renderer = Renderer::new(W as u32, H as u32);
    let mono = load_family(&mut renderer,
        &format!("{home}/GH/repos/google-fonts/ofl/geistmono/GeistMono[wght].ttf"));
    let hebrew = load_family(&mut renderer,
        &format!("{home}/GH/repos/mekorot/fonts/ttf/Mekorot-Regular.ttf"));
    let hebrew_medium = load_family(&mut renderer,
        &format!("{home}/GH/repos/mekorot/fonts/ttf/Mekorot-Medium.ttf"));
    let arabic = load_family(&mut renderer,
        &format!("{home}/GH/repos/open-gate-naskh/fonts/ttf/OpenGateNaskh-Regular.ttf"));
    let sheet = Sheet { renderer, mono, hebrew, hebrew_medium, arabic };

    let mut ctx = Canvas::new(W, H);
    ctx.background(bg());

    // header / footer rules and labels
    let header_y = H - MARGIN;
    ctx.stroke(green()).stroke_width(3.5).no_fill();
    ctx.line(MARGIN, header_y, W - MARGIN, header_y);
    ctx.line(MARGIN, MARGIN, W - MARGIN, MARGIN);
    sheet.label(&mut ctx, "MEKOROT * OPEN GATE NASKH", MARGIN, header_y + 22.0, green(), -1);
    sheet.label(&mut ctx, "SCALE / WEIGHT MERGE SHEET", W - MARGIN, header_y + 22.0, green(), 1);
    sheet.label(&mut ctx, "HEBREW: MEKOROT REGULAR", MARGIN, MARGIN - 40.0, blue(), -1);
    sheet.label(&mut ctx, "ARABIC: OPEN GATE NASKH REGULAR", W - MARGIN, MARGIN - 40.0, red(), 1);

    let right = W - MARGIN;
    let col_w = W - 2.0 * MARGIN;

    // ── 1 · giant control pair on one shared baseline, with guides ──
    let base = H - 560.0;
    let size = 360.0;
    ctx.stroke(green()).stroke_width(2.5).no_fill();
    ctx.line(MARGIN, base, W - MARGIN, base); // shared baseline
    sheet.label(&mut ctx, "BASELINE", MARGIN, base - 36.0, green(), -1);
    let mut x = right;
    for (family, txt, color) in [
        (&sheet.hebrew, "אבגהם", blue()),
        (&sheet.arabic, "ابجهم", red()),
    ] {
        let w = sheet.rtl_line(&mut ctx, family, txt, x, base, size, color);
        x -= w + 120.0;
    }

    // ── 2 · alternating long text lines, same size, shared leading ──
    let text_size = 56.0;
    let leading = 96.0;
    let mut y = base - 420.0;
    sheet.label(&mut ctx, "ALTERNATING 56PX / 96PX LEADING", MARGIN, y + 60.0, green(), -1);
    let heb_lines = sheet.wrap(&sheet.hebrew, HEB, text_size, col_w);
    let ara_lines = sheet.wrap(&sheet.arabic, ARA, text_size, col_w);
    let mut hi = heb_lines.iter();
    let mut ai = ara_lines.iter();
    loop {
        let mut drew = false;
        if let Some(l) = hi.next() {
            ctx.stroke(Color::rgb(0x32, 0x32, 0x32)).stroke_width(1.5).no_fill();
            ctx.line(MARGIN, y, right, y);
            sheet.rtl_line(&mut ctx, &sheet.hebrew.clone(), l, right, y, text_size, ink());
            y -= leading;
            drew = true;
        }
        if let Some(l) = ai.next() {
            ctx.stroke(Color::rgb(0x32, 0x32, 0x32)).stroke_width(1.5).no_fill();
            ctx.line(MARGIN, y, right, y);
            sheet.rtl_line(&mut ctx, &sheet.arabic.clone(), l, right, y, text_size, ink());
            y -= leading;
            drew = true;
        }
        if !drew { break; }
    }

    // ── 3 · waterfall: one line of each at descending sizes ──
    sheet.label(&mut ctx, "WATERFALL 96 / 72 / 56 / 40", MARGIN, y + 40.0, green(), -1);
    y -= 60.0;
    for s in [96.0, 72.0, 56.0, 40.0] {
        sheet.rtl_line(&mut ctx, &sheet.hebrew.clone(),
            "כל בני האדם נולדו בני חורין", right, y, s, ink());
        y -= s * 1.35;
        sheet.rtl_line(&mut ctx, &sheet.arabic.clone(),
            "يولد جميع الناس أحراراً متساوين", right, y, s, ink());
        y -= s * 1.55;
    }

    // ── 4 · scale trials: fixed Hebrew, Arabic at rising factors ──
    sheet.label(&mut ctx, "SCALE TRIALS: ARABIC x 1.00 / 1.15 / 1.25 / 1.35", MARGIN, y + 40.0, green(), -1);
    y -= 70.0;
    let heb_probe = "כל בני האדם נולדו בני חורין";
    let ara_probe = "يولد جميع الناس أحرارا متساوين";
    for f in [1.00_f64, 1.15, 1.25, 1.35] {
        ctx.stroke(Color::rgb(0x32, 0x32, 0x32)).stroke_width(1.5).no_fill();
        ctx.line(MARGIN, y, right, y);
        let w = sheet.rtl_line(&mut ctx, &sheet.hebrew.clone(), heb_probe, right, y, 56.0, ink());
        sheet.rtl_line(&mut ctx, &sheet.arabic.clone(), ara_probe, right - w - 80.0, y, 56.0 * f, ink());
        sheet.label(&mut ctx, &format!("x{f:.2}"), MARGIN, y, green(), -1);
        y -= 120.0;
    }

    // ── 5 · weight trial: Naskh against Mekorot Regular vs Medium ──
    sheet.label(&mut ctx, "WEIGHT TRIAL: NASKH VS MEKOROT REGULAR / MEDIUM", MARGIN, y + 20.0, green(), -1);
    y -= 60.0;
    for (heb_fam, tag) in [(&sheet.hebrew, "REGULAR"), (&sheet.hebrew_medium, "MEDIUM")] {
        ctx.stroke(Color::rgb(0x32, 0x32, 0x32)).stroke_width(1.5).no_fill();
        ctx.line(MARGIN, y, right, y);
        let w = sheet.rtl_line(&mut ctx, &heb_fam.clone(), heb_probe, right, y, 56.0, ink());
        sheet.rtl_line(&mut ctx, &sheet.arabic.clone(), ara_probe, right - w - 80.0, y, 56.0 * 1.25, ink());
        sheet.label(&mut ctx, tag, MARGIN, y, green(), -1);
        y -= 120.0;
    }

    let out = format!("{out_dir}/hebrew-arabic-merge-sheet.png");
    sheet.renderer.render_to_png(&ctx, &out).expect("png");
    println!("wrote {out}");
}
