"""
PDFService — fully Unicode PDF using NotoSans for ALL text.
No built-in fonts used anywhere — eliminates all character encoding crashes.
"""

import os
import urllib.request
from fpdf import FPDF
from app.schemas.project import VideoProject

COLOR_MAP = {
    "Green":  (34,  197, 94),
    "Yellow": (234, 179, 8),
    "Red":    (239, 68,  68),
}

FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "fonts")

FONT_REGISTRY = {
    "NotoSans": {
        "filename": "NotoSans-Regular.ttf",
        "url": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    },
    "NotoSansBold": {
        "filename": "NotoSans-Bold.ttf",
        "url": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
    },
    "NotoSansDevanagari": {
        "filename": "NotoSansDevanagari-Regular.ttf",
        "url": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf",
    },
    "NotoSansJP": {
        "filename": "NotoSansJP-Regular.ttf",
        "url": "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
    },
    "NotoSansKR": {
        "filename": "NotoSansKR-Regular.ttf",
        "url": "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf",
    },
}

LANGUAGE_FONT_MAP = {
    "english":    "NotoSans",
    "hindi":      "NotoSansDevanagari",   # ← Devanagari-specific font
    "spanish":    "NotoSans",
    "french":     "NotoSans",
    "german":     "NotoSans",
    "portuguese": "NotoSans",
    "italian":    "NotoSans",
    "japanese":   "NotoSansJP",
    "korean":     "NotoSansKR",
}


def _font_path(font_name: str) -> str:
    return os.path.join(FONTS_DIR, FONT_REGISTRY[font_name]["filename"])


def ensure_font(font_name: str) -> bool:
    os.makedirs(FONTS_DIR, exist_ok=True)
    path = _font_path(font_name)
    if os.path.exists(path):
        return True
    url = FONT_REGISTRY[font_name]["url"]
    print(f"📥  Downloading font: {font_name} → {path}")
    try:
        urllib.request.urlretrieve(url, path)
        print(f"✅  {font_name} downloaded.")
        return True
    except Exception as e:
        print(f"⚠️  Failed to download {font_name}: {e}")
        return False


def clean(text: str) -> str:
    """Universal text cleaner — safe for any Unicode font."""
    if not text:
        return ""
    # Normalise common unicode punctuation to ASCII equivalents
    table = str.maketrans({
        "\u2014": "-", "\u2013": "-", "\u2012": "-",
        "\u201c": '"', "\u201d": '"',
        "\u2018": "'", "\u2019": "'",
        "\u2026": "...",
        "\u00a0": " ",
        "\u2022": "-",
        "\u00b7": ".",
        "\u00ab": '"', "\u00bb": '"',
    })
    text = text.translate(table)
    # Strip control chars only
    return "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\t")


class ScriptPDF(FPDF):
    def __init__(self, base_font: str, bold_font: str):
        super().__init__()
        self.base_font = base_font
        self.bold_font = bold_font

    def footer(self):
        self.set_y(-15)
        self.set_font(self.base_font, size=8)
        self.set_text_color(128)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")


class PDFService:

    def _est_lines(self, pdf, text, width, font, size=9):
        if not text:
            return 0
        pdf.set_font(font, size=size)
        safe_w = width - 2
        lines, cur_w = 1, 0
        for word in text.split(" "):
            ww = pdf.get_string_width(word + " ")
            if cur_w + ww > safe_w:
                lines += 1
                cur_w = ww
            else:
                cur_w += ww
        return lines

    def create_shooting_script(self, project: VideoProject, filename="shooting_script.pdf") -> str:
        # ── Resolve fonts ─────────────────────────────────────────────────────
        lang_key   = project.target_language.lower().strip()
        dlg_font   = LANGUAGE_FONT_MAP.get(lang_key, "NotoSans")

        # Always ensure base NotoSans (used for all UI text) + Bold + language font
        fonts_needed = {"NotoSans", "NotoSansBold", dlg_font}
        font_ok      = {f: ensure_font(f) for f in fonts_needed}

        base_font = "NotoSans"     if font_ok.get("NotoSans")     else None
        bold_font = "NotoSansBold" if font_ok.get("NotoSansBold") else base_font
        dlg_font  = dlg_font       if font_ok.get(dlg_font)       else base_font

        if not base_font:
            raise RuntimeError("NotoSans font could not be loaded. Check your internet connection.")

        pdf = ScriptPDF(base_font=base_font, bold_font=bold_font)
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()

        # Register all needed fonts
        registered = set()
        for fname in fonts_needed:
            if font_ok.get(fname) and fname not in registered:
                pdf.add_font(fname, "", _font_path(fname))
                registered.add(fname)

        print(f"✅  PDF fonts loaded: base={base_font}, dialogue={dlg_font} ({project.target_language})")

        # ── Title ─────────────────────────────────────────────────────────────
        pdf.set_font(bold_font, size=18)
        pdf.multi_cell(0, 10, clean(f"PROJECT: {project.topic}"), align="C")
        pdf.ln(3)

        pdf.set_font(base_font, size=10)
        pdf.cell(
            0, 8,
            clean(
                f"Language: {project.target_language}  |  "
                f"Duration: {project.duration_seconds}s  |  "
                f"Budget: ${project.budget_limit}  |  Niche: {project.niche}"
            ),
            ln=True, align="C",
        )
        pdf.ln(5)

        # ── Budget breakdown ──────────────────────────────────────────────────
        if project.budget_plan:
            pdf.set_font(bold_font, size=11)
            pdf.cell(0, 8, "Budget Breakdown:", ln=True)
            pdf.set_font(base_font, size=9)
            for item in project.budget_plan.breakdown:
                pdf.cell(0, 5, clean(f"  - {item.item}: ${item.estimated_cost}"), ln=True)
            pdf.ln(6)

        # ── Stats ─────────────────────────────────────────────────────────────
        if project.axigrade_scenes:
            total_words = sum(len(s.script_dialogue.split()) for s in project.axigrade_scenes)
            max_words   = int(project.duration_seconds * 2.5)
            pdf.set_font(base_font, size=9)
            pdf.cell(
                0, 6,
                clean(f"Total word count: {total_words} / {max_words} max  |  Scenes: {len(project.axigrade_scenes)}"),
                ln=True,
            )
            pdf.ln(4)

        # ── Color legend ──────────────────────────────────────────────────────
        legend_items = [
            ("Green",  (34,  197, 94),  "Fast-paced, high-energy, hook — keep viewer hooked, no room for drop-off"),
            ("Yellow", (234, 179, 8),   "Moderate pace, exposition — deliver value clearly, watch for retention dip"),
            ("Red",    (239, 68,  68),  "Slow / retention-risk — cut aggressively or re-energise with a visual"),
        ]
        pdf.set_font(bold_font, size=9)
        pdf.cell(0, 6, "Color Code Guide:", ln=True)
        for label, rgb, meaning in legend_items:
            pdf.set_text_color(*rgb)
            pdf.set_font(bold_font, size=9)
            pdf.cell(22, 6, f"[{label}]", ln=False)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(base_font, size=9)
            pdf.cell(0, 6, clean(meaning), ln=True)
        pdf.ln(4)

        # ── Table header ──────────────────────────────────────────────────────
        w_sc  = 12
        w_tm  = 18
        w_cc  = 18
        w_dlg = 80
        w_veo = 62

        def draw_header():
            pdf.set_font(bold_font, size=9)
            pdf.set_fill_color(220, 220, 220)
            for label, w in [("#", w_sc), ("Secs", w_tm), ("Code", w_cc),
                              ("Dialogue", w_dlg), ("Veo / Shoot", w_veo)]:
                pdf.cell(w, 7, label, 1, 0, "C", 1)
            pdf.ln()

        draw_header()

        # ── Scene rows ────────────────────────────────────────────────────────
        page_height = 265

        for scene in project.axigrade_scenes:
            rgb = COLOR_MAP.get(scene.color_code, (100, 100, 100))

            dlg_text = clean(scene.script_dialogue)
            veo_text = clean(f"VEO: {scene.veo_prompt}\n\nSHOOT: {scene.shoot_instructions}")

            lines_dlg = self._est_lines(pdf, dlg_text, w_dlg, dlg_font, 9)
            lines_veo = self._est_lines(pdf, veo_text, w_veo, base_font, 7)
            row_h     = max((lines_dlg * 5) + 6, (lines_veo * 5) + 6, 14)

            if pdf.get_y() + row_h > page_height:
                pdf.add_page()
                draw_header()

            x0 = pdf.get_x()
            y0 = pdf.get_y()

            # Scene #
            pdf.rect(x0, y0, w_sc, row_h)
            pdf.set_font(bold_font, size=9)
            pdf.set_xy(x0, y0 + row_h / 2 - 3)
            pdf.cell(w_sc, 6, str(scene.scene_number), 0, 0, "C")

            # Secs
            pdf.rect(x0 + w_sc, y0, w_tm, row_h)
            pdf.set_font(base_font, size=9)
            pdf.set_xy(x0 + w_sc, y0 + row_h / 2 - 3)
            pdf.cell(w_tm, 6, f"{scene.estimated_time_seconds}s", 0, 0, "C")

            # Color code
            pdf.rect(x0 + w_sc + w_tm, y0, w_cc, row_h)
            pdf.set_text_color(*rgb)
            pdf.set_font(bold_font, size=8)
            pdf.set_xy(x0 + w_sc + w_tm, y0 + row_h / 2 - 3)
            pdf.cell(w_cc, 6, scene.color_code, 0, 0, "C")
            pdf.set_text_color(0, 0, 0)

            # Dialogue
            pdf.rect(x0 + w_sc + w_tm + w_cc, y0, w_dlg, row_h)
            pdf.set_font(dlg_font, size=9)
            pdf.set_xy(x0 + w_sc + w_tm + w_cc, y0 + 2)
            pdf.multi_cell(w_dlg, 5, dlg_text, border=0, align="L")

            # Veo + Shoot
            pdf.rect(x0 + w_sc + w_tm + w_cc + w_dlg, y0, w_veo, row_h)
            pdf.set_font(base_font, size=7)
            pdf.set_text_color(60, 60, 60)
            pdf.set_xy(x0 + w_sc + w_tm + w_cc + w_dlg, y0 + 2)
            pdf.multi_cell(w_veo, 4, veo_text, border=0, align="L")
            pdf.set_text_color(0, 0, 0)

            pdf.set_xy(x0, y0 + row_h)

        pdf.output(filename)
        return filename
