import logging
import math
import os
import threading
import tkinter as tk
import tkinter.font as tkfont
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from audit import AuditLogger
from config import AppConfig, DIAGNOSIS_ALLERGEN_MAP
from hardware_service import ACUHardware
from vision_service import VisionService
from emergency_service import send_emergency_whatsapp


BG = "#ECECEC"
WHITE = "#F7F7F7"
HEADER = "#2C5E65"
TEAL_TEXT = "#2C5E65"
TEAL_LINE = "#2C5E65"
DARK_TEXT = "#1E1E1E"
BODY_TEXT = "#2E2E2E"
MUTED = "#6B6B6B"
CARD = "#E9E9E9"
CARD_GREEN = "#EFF5EF"
CARD_AMBER = "#EEEAE4"
GREEN = "#049767"
RED = "#C63838"
AMBER = "#C46A00"
SCAN_DARK = "#000000"
SCAN_GREEN = "#049767"

DISPLAY_FAMILY = "Arial Black"
BODY_FAMILY = "Arial"


def f_display(size: int, bold: bool = True):
    return (DISPLAY_FAMILY, size, "bold" if bold else "normal")


def f_body(size: int, bold: bool = False):
    return (BODY_FAMILY, size, "bold" if bold else "normal")


def hud_box_points(x, y, w, h, clip=22):
    return [
        x + clip, y,
        x + w - clip, y,
        x + w, y + clip,
        x + w, y + h - clip,
        x + w - clip, y + h,
        x + clip, y + h,
        x, y + h - clip,
        x, y + clip,
    ]


def header_bottom_shape_points(width, height=120):
    y = height - 1
    cw = int(width * 0.67)
    cw2 = int(width * 0.33)
    return [
        0, 0, width, 0, width, y - 10, width - 12, y,
        cw + 88, y, cw + 80, y - 8, cw - 80, y - 8, cw - 88, y,
        cw2 + 88, y, cw2 + 80, y - 8, cw2 - 80, y - 8, cw2 - 88, y,
        18, y, 0, y - 10,
    ]


def draw_hatch(canvas, x, y, w, h, color, step=18):
    for i in range(-h, w + h, step):
        canvas.create_line(x + i, y + h, x + i + h, y, fill=color, width=3)


def draw_diamond_cluster(canvas, x, y):
    for dx, dy in [(0, 10), (18, 0), (18, 20), (36, 10), (18, 38)]:
        cx, cy = x + dx, y + dy
        canvas.create_polygon(cx, cy - 6, cx + 6, cy, cx, cy + 6, cx - 6, cy, fill=GREEN, outline=HEADER, width=1)


def draw_back_icon(canvas, x, y, color=WHITE):
    canvas.create_line(x + 14, y - 18, x - 8, y, x + 14, y + 18, fill=color, width=4)
    canvas.create_line(x - 4, y, x + 20, y, fill=color, width=4)


def draw_arrow_icon(canvas, x, y, color):
    canvas.create_line(x - 20, y, x + 8, y, fill=color, width=4)
    canvas.create_line(x - 2, y - 16, x + 14, y, x - 2, y + 16, fill=color, width=4)


def draw_x_icon(canvas, x, y, color):
    canvas.create_line(x - 16, y - 16, x + 16, y + 16, fill=color, width=4)
    canvas.create_line(x - 16, y + 16, x + 16, y - 16, fill=color, width=4)


def draw_menu_icon(canvas, x, y, color):
    dr = 2.8
    dx = x - 18
    for off in (-12, 0, 12):
        cy = y + off
        canvas.create_oval(dx - dr, cy - dr, dx + dr, cy + dr, fill=color, outline=color)
        canvas.create_line(x - 4, cy, x + 24, cy, fill=color, width=4)


def draw_camera_icon(canvas, x, y, color):
    canvas.create_rectangle(x - 32, y - 18, x + 6, y + 18, outline=color, width=4)
    canvas.create_polygon(x + 8, y - 8, x + 28, y - 24, x + 28, y + 24, x + 8, y + 8, outline=color, fill="", width=4)
    canvas.create_oval(x - 12, y - 8, x + 0, y + 4, fill=color, outline=color)


def draw_emergency_icon(canvas, x, y, color):
    canvas.create_line(x - 24, y + 18, x - 18, y + 18, fill=color, width=4)
    canvas.create_line(x - 14, y + 18, x - 4, y - 18, fill=color, width=4)
    canvas.create_line(x + 4, y - 18, x + 14, y + 18, fill=color, width=4)
    canvas.create_line(x + 18, y + 18, x + 28, y + 18, fill=color, width=4)
    canvas.create_line(x, y - 10, x, y + 4, fill=color, width=4)
    canvas.create_oval(x - 2, y + 10, x + 2, y + 14, fill=color, outline=color)


def draw_corner_bracket(canvas, x, y, arm, color, corner="tl", width=2):
    if corner == "tl":
        canvas.create_line(x + arm, y, x, y, x, y + arm, fill=color, width=width)
    elif corner == "tr":
        canvas.create_line(x - arm, y, x, y, x, y + arm, fill=color, width=width)
    elif corner == "bl":
        canvas.create_line(x + arm, y, x, y, x, y - arm, fill=color, width=width)
    elif corner == "br":
        canvas.create_line(x - arm, y, x, y, x, y - arm, fill=color, width=width)


class TacticalCanvas(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, bg=BG, highlightthickness=0, bd=0, **kwargs)
        self._keepalive = []

    def keep(self, obj):
        self._keepalive.append(obj)
        return obj


class MedicalKiosk(ctk.CTk):
    HEADER_H = 120

    def __init__(self, config: AppConfig, audit: AuditLogger, hardware: ACUHardware, vision: VisionService):
        super().__init__()
        self.config_obj = config
        self.audit = audit
        self.hardware = hardware
        self.vision = vision
        self.title("Autonomous Care Unit")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self._resolve_font_families()

        if self.config_obj.fullscreen:
            self.window_w = self.winfo_screenwidth()
            self.window_h = self.winfo_screenheight()
            self.attributes("-fullscreen", True)
        else:
            self.window_w = self.config_obj.window_width
            self.window_h = self.config_obj.window_height
            self.geometry(f"{self.window_w}x{self.window_h}")
            self._center_window()

        self.bind("<Escape>", self._escape_handler)
        self.bind("<F11>", self._toggle_fullscreen)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._spin_job = None
        self._spin_frame = 0
        self._scan_cancelled = False
        self._countdown = 0
        self.current: Optional[TacticalCanvas] = None
        self._hotspots = []
        self._termination_canvas = None

        # Stock tracking — in-memory only, resets every program start.
        self._stock: dict = dict(self._DEFAULT_STOCK)

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.root = tk.Frame(self, bg=BG)
        self.root.pack(fill="both", expand=True)

        self.logo_source = self._load_logo()
        self.scan_preview = self._load_scan_preview()

        self.viewport_w = self.window_w
        self.viewport_h = self.window_h
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.scale = 1.0
        self._refresh_viewport_metrics()

        self.after(50, self.show_home)

    def _resolve_font_families(self):
        global DISPLAY_FAMILY
        self.update_idletasks()
        available = set(tkfont.families(self))
        if "Nippo" in available:
            DISPLAY_FAMILY = "Nippo"
            return

        font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.config_obj.font_dir)
        if os.path.isdir(font_dir):
            found = any(name.lower().startswith("nippo") for name in os.listdir(font_dir))
            if found:
                print("[font] Nippo files were found, but the Nippo family is not installed for Tk. Using Arial Black fallback.")

    def _center_window(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, (sw - self.window_w) // 2)
        y = max(0, (sh - self.window_h) // 2)
        self.geometry(f"{self.window_w}x{self.window_h}+{x}+{y}")

    def _refresh_viewport_metrics(self):
        self.update_idletasks()

        w = self.root.winfo_width()
        h = self.root.winfo_height()

        if w <= 1:
            w = self.winfo_width()
        if h <= 1:
            h = self.winfo_height()

        if w <= 1:
            w = self.window_w
        if h <= 1:
            h = self.window_h

        self.viewport_w = max(1, int(w))
        self.viewport_h = max(1, int(h))
        self.scale_x = self.viewport_w / self.config_obj.design_width
        self.scale_y = self.viewport_h / self.config_obj.design_height
        self.scale = min(self.scale_x, self.scale_y)

    def _escape_handler(self, _=None):
        if self.attributes("-fullscreen"):
            self.attributes("-fullscreen", False)
        else:
            self.destroy()

    def _toggle_fullscreen(self, _=None):
        self.attributes("-fullscreen", not bool(self.attributes("-fullscreen")))
        self.after(10, self._refresh_viewport_metrics)

    def _on_close(self):
        try:
            self.vision.cleanup()
            self.hardware.cleanup()
        finally:
            self.destroy()

    def X(self, v):
        return int(round(v * self.scale_x))

    def Y(self, v):
        return int(round(v * self.scale_y))

    def S(self, v):
        return max(1, int(round(v * self.scale)))

    def _abs_asset(self, rel_path: str) -> str:
        return os.path.join(self.script_dir, rel_path)

    def _load_logo(self):
        path = self._abs_asset(self.config_obj.logo_path)
        if not os.path.exists(path):
            return None
        try:
            return Image.open(path).convert("RGBA")
        except Exception as exc:
            logging.warning("Logo load failed: %s", exc)
            return None

    def _load_scan_preview(self):
        for rel_path in self.config_obj.scan_preview_candidates:
            path = self._abs_asset(rel_path)
            if os.path.exists(path):
                try:
                    return Image.open(path).convert("RGBA")
                except Exception:
                    pass
        return None

    def _photo(self, img, thumb=None, exact=None):
        work = img.copy()
        if thumb:
            work.thumbnail((max(1, self.X(thumb[0])), max(1, self.Y(thumb[1]))), Image.LANCZOS)
        elif exact:
            work = work.resize((max(1, self.X(exact[0])), max(1, self.Y(exact[1]))), Image.LANCZOS)
        return ImageTk.PhotoImage(work)

    def _clear(self):
        if self._spin_job:
            self.after_cancel(self._spin_job)
            self._spin_job = None
        self._hotspots = []
        for child in self.root.winfo_children():
            child.destroy()
        self.current = None

    def _bind_events(self, cv):
        cv.bind("<Button-1>", self._click)
        cv.bind("<Motion>", self._motion)
        cv.bind("<Leave>", lambda e: cv.configure(cursor=""))

    def _add_hotspot(self, x0, y0, x1, y1, cmd):
        self._hotspots.append(((x0, y0, x1, y1), cmd))

    def _scale_hotspots(self):
        self._hotspots = [((self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)), cmd) for (x0, y0, x1, y1), cmd in self._hotspots]

    def _scale_canvas(self, cv):
        if abs(self.scale_x - 1) < 1e-6 and abs(self.scale_y - 1) < 1e-6:
            return

        for item in cv.find_all():
            kind = cv.type(item)
            if kind == "image":
                coords = cv.coords(item)
                if coords:
                    cv.coords(item, coords[0] * self.scale_x, coords[1] * self.scale_y)
            else:
                cv.scale(item, 0, 0, self.scale_x, self.scale_y)

            if kind != "text":
                try:
                    width = cv.itemcget(item, "width")
                    if width not in ("", "0", 0, None):
                        cv.itemconfigure(item, width=max(1, int(round(float(width) * self.scale))))
                except Exception:
                    pass

            if kind == "text":
                try:
                    font_obj = tkfont.Font(font=cv.itemcget(item, "font"))
                    size = max(6, int(round(abs(int(font_obj.cget("size"))) * self.scale)))
                    cv.itemconfigure(item, font=(font_obj.cget("family"), size, font_obj.cget("weight")))
                except Exception:
                    pass

    def _finalize(self, cv):
        self._scale_canvas(cv)
        self._scale_hotspots()

    def _motion(self, event):
        x, y = event.x, event.y
        for (x0, y0, x1, y1), _ in self._hotspots:
            if x0 <= x <= x1 and y0 <= y <= y1:
                event.widget.configure(cursor="hand2")
                return
        event.widget.configure(cursor="")

    def _click(self, event):
        x, y = event.x, event.y
        for (x0, y0, x1, y1), cmd in reversed(self._hotspots):
            if x0 <= x <= x1 and y0 <= y <= y1:
                cmd()
                return

    def _new_canvas(self):
        self._refresh_viewport_metrics()

        if self._spin_job:
            self.after_cancel(self._spin_job)
            self._spin_job = None

        if self.current is not None:
            self.current.destroy()

        cv = TacticalCanvas(self.root, width=self.viewport_w, height=self.viewport_h)
        self._bind_events(cv)
        self._hotspots = []
        cv.place(x=0, y=0, width=self.viewport_w, height=self.viewport_h)
        self.current = cv
        return cv

    def _header(self, cv, title, back_cmd=None):
        cv.create_polygon(header_bottom_shape_points(self.config_obj.design_width, self.HEADER_H), fill=HEADER, outline=HEADER)
        draw_hatch(cv, 22, self.HEADER_H - 26, 80, 14, "#B8D0D3", step=16)
        draw_hatch(cv, self.config_obj.design_width // 3 - 80, self.HEADER_H - 26, 160, 14, "#B8D0D3", step=16)
        draw_hatch(cv, self.config_obj.design_width * 2 // 3 - 80, self.HEADER_H - 26, 160, 14, "#B8D0D3", step=16)
        draw_hatch(cv, self.config_obj.design_width - 100, self.HEADER_H - 26, 80, 14, "#B8D0D3", step=16)
        size = 34 if len(title) <= 12 else 26
        cv.create_text(self.config_obj.design_width // 2, 52, text=title, fill=WHITE, font=f_display(size), anchor="center")
        if back_cmd:
            draw_back_icon(cv, 54, 56, WHITE)
            self._add_hotspot(12, 16, 100, 96, back_cmd)

    def _footer(self, cv):
        y = self.config_obj.design_height - 46
        draw_diamond_cluster(cv, 20, y - 12)
        cv.create_text(76, y + 1, text="ALL SYSTEMS OPERATIONAL", fill=MUTED, font=f_body(10), anchor="w")

    def _hud_button(self, cv, x, y, w, h, text, command, outline=TEAL_LINE, fill="", text_color=TEAL_TEXT, icon=None, filled=False, font_size=30):
        self._add_hotspot(x, y - 14, x + w, y + h + 14, command)
        pts = hud_box_points(x, y, w, h, clip=22)

        if filled:
            cv.create_polygon(pts, fill=fill, outline=fill, width=3)
            mx = x + w // 2
            cv.create_polygon(mx - 92, y, mx - 70, y - 14, mx + 70, y - 14, mx + 92, y, fill=fill, outline=fill)
            cv.create_polygon(mx - 24, y + h, mx - 12, y + h + 14, mx, y + h, mx + 12, y + h + 14, mx + 24, y + h, fill=fill, outline=fill)
            for off in (0, 10, 20):
                cv.create_polygon(x + w - 10, y + h - 6 - off, x + w, y + h - 6 - off, x + w - 5, y + h - 1 - off, fill=WHITE, outline=WHITE)
            txt_col = WHITE
        else:
            cv.create_polygon(pts, fill=WHITE, outline=outline, width=3)
            mx = x + w // 2
            cv.create_polygon(mx - 90, y, mx - 76, y - 12, mx + 76, y - 12, mx + 90, y, fill=outline, outline=outline)
            cv.create_line(x, y + h - 16, x + 16, y + h, fill=outline, width=3)
            txt_col = text_color

        tx = x + w / 2 - (34 if icon else 0)
        cv.create_text(tx, y + h / 2 + 1, text=text, fill=txt_col, font=f_display(font_size, bold=False), anchor="center")

        ix = x + w - (60 if icon == "menu" else 88)
        iy = y + h / 2
        if icon == "arrow":
            draw_arrow_icon(cv, ix, iy, txt_col)
        elif icon == "x":
            draw_x_icon(cv, ix, iy, txt_col)
        elif icon == "menu":
            draw_menu_icon(cv, ix, iy, txt_col)
        elif icon == "camera":
            draw_camera_icon(cv, ix, iy, txt_col)
        elif icon == "emergency":
            draw_emergency_icon(cv, ix, iy, txt_col)

    def _card_bracket(self, cv, x, y, w, h, color, arm=18):
        lw = 2
        cv.create_line(x, y + arm, x, y, x + arm, y, fill=color, width=lw)
        cv.create_line(x + w - arm, y, x + w, y, x + w, y + arm, fill=color, width=lw)
        cv.create_line(x, y + h - arm, x, y + h, x + arm, y + h, fill=color, width=lw)
        cv.create_line(x + w - arm, y + h, x + w, y + h, x + w, y + h - arm, fill=color, width=lw)

    def _card(self, cv, x, y, w, h, title, icon, fill, title_color, divider_color, left_bar=False, left_bar_color=None):
        cv.create_rectangle(x, y, x + w, y + h, fill=fill, outline="")
        cv.create_line(x + 4, y + 10, x, y + 10, x, y + h - 10, x + 4, y + h - 10, fill=title_color, width=2)
        if left_bar:
            cv.create_line(x, y + 12, x, y + h - 12, fill=left_bar_color or title_color, width=5)
        cv.create_text(x + 22, y + 26, text=title, fill=title_color, font=f_display(13), anchor="w")
        cv.create_line(x + 22, y + 44, x + w - 12, y + 44, fill=divider_color, width=1)
        icon_x = x + 22
        icon_y = y + 72
        if icon == "check":
            cv.create_text(icon_x, icon_y, text="\u2713", fill=title_color, font=f_body(16, True), anchor="w")
        elif icon == "warn":
            cv.create_text(icon_x, icon_y, text="\u26a0", fill=title_color, font=f_body(15, True), anchor="w")
        else:
            cv.create_text(icon_x, icon_y, text="\u2699", fill=MUTED, font=f_body(14, True), anchor="w")
        return y + 58

    def _card_inline_text(self, cv, x, y, parts):
        cx = x
        for text, font, color in parts:
            font_obj = tkfont.Font(font=font)
            width = font_obj.measure(text)
            cv.create_text(cx, y, text=text, fill=color, font=font, anchor="w")
            cx += width
        return cx

    def _get_allergen_for_diagnosis(self, diagnosis: str) -> str:
        config_map = getattr(self.config_obj, "diagnosis_allergen_map", None)
        if isinstance(config_map, dict):
            value = config_map.get(diagnosis)
            if value:
                return value

        value = DIAGNOSIS_ALLERGEN_MAP.get(diagnosis)
        if value:
            return value

        try:
            value = self.vision.get_allergen(diagnosis)
            if value:
                return value
        except Exception:
            pass

        return "Unknown Ingredient"

    def _draw_home_frame(self, cv):
        gc = GREEN
        cv.create_line(20, 14, 20, 320, fill=gc, width=2)
        for yy in (34, 70, 126, 148, 170, 262, 280, 298):
            cv.create_line(14, yy, 20, yy, fill=gc, width=3)
        cv.create_oval(14, 434, 26, 446, outline=gc, width=1)
        cv.create_line(38, 12, 210, 12, fill=gc, width=2)
        cv.create_line(206, 12, 218, 22, fill=gc, width=2)
        draw_hatch(cv, 274, 0, 80, 12, gc, step=22)
        cv.create_polygon(356, 12, 516, 12, 532, 28, 523, 36, 440, 36, 430, 28, 368, 28, fill=gc, outline=gc)
        cv.create_line(self.config_obj.design_width - 60, 18, self.config_obj.design_width - 1, 18, fill=gc, width=2)
        cv.create_line(self.config_obj.design_width - 22, 18, self.config_obj.design_width - 1, 36, fill=gc, width=2)
        cv.create_line(self.config_obj.design_width - 22, 36, self.config_obj.design_width - 22, 420, fill=gc, width=2)
        cv.create_line(self.config_obj.design_width - 22, 198, self.config_obj.design_width - 6, 216, fill=gc, width=2)
        cv.create_line(self.config_obj.design_width - 22, 296, self.config_obj.design_width - 6, 280, fill=gc, width=2)
        cv.create_line(self.config_obj.design_width - 22, 432, self.config_obj.design_width - 22, 594, fill=gc, width=2)
        draw_hatch(cv, self.config_obj.design_width - 32, 804, 24, 100, gc, step=20)
        cv.create_line(62, 604, 176, 604, fill=gc, width=5)
        cv.create_polygon(176, 604, 253, 604, 242, 612, 62, 612, fill=gc, outline=gc)
        cv.create_line(430, 690, 590, 690, fill=gc, width=4)
        cv.create_line(590, 690, self.config_obj.design_width - 1, 648, fill=gc, width=4)

    def _draw_logo_fallback(self, cv, cx, cy):
        pf, cf = HEADER, GREEN
        petals = [
            [(cx - 36, cy - 82), (cx - 106, cy - 138), (cx - 178, cy - 66), (cx - 106, cy + 6)],
            [(cx + 36, cy - 82), (cx + 106, cy - 138), (cx + 178, cy - 66), (cx + 106, cy + 6)],
            [(cx - 36, cy + 82), (cx - 106, cy + 138), (cx - 178, cy + 66), (cx - 106, cy - 6)],
            [(cx + 36, cy + 82), (cx + 106, cy + 138), (cx + 178, cy + 66), (cx + 106, cy - 6)],
        ]
        for pts in petals:
            cv.create_polygon(*sum(pts, []), fill=pf, outline=pf)
        cv.create_polygon(cx, cy - 78, cx + 78, cy, cx, cy + 78, cx - 78, cy, fill=WHITE, outline=WHITE)
        for sx, sy in [(-120, -80), (118, -82), (-122, 84), (118, 84)]:
            cv.create_line(cx + sx, cy + sy, cx + sx + 42, cy + sy + 36, fill=cf, width=5)
            cv.create_oval(cx + sx + 35, cy + sy + 29, cx + sx + 49, cy + sy + 43, fill=cf, outline=cf)

    def _draw_brand_label(self, cv, y):
        cv.create_line(48, y, 178, y, fill=GREEN, width=4)
        cv.create_polygon(48, y, 28, y + 36, 34, y + 36, 52, y + 8, 176, y + 8, 186, y, fill=GREEN, outline=GREEN)
        tid = cv.create_text(self.config_obj.design_width // 2, y + 46, text="AUTONOMOUS CARE UNIT", fill=GREEN, font=f_display(18), anchor="center")
        bb = cv.bbox(tid)
        if bb:
            rx0 = bb[2] + 18
            cv.create_line(rx0, y + 72, self.config_obj.design_width - 56, y + 72, fill=GREEN, width=4)
            cv.create_line(self.config_obj.design_width - 56, y + 72, self.config_obj.design_width - 28, y + 30, fill=GREEN, width=4)

    def _draw_scan_background(self, cv, x, y, w, h):
        if self.scan_preview is not None:
            photo = self._photo(self.scan_preview, exact=(w, h))
            cv.keep(photo)
            cv.create_image(x, y, image=photo, anchor="nw")
            return
        cv.create_rectangle(x, y, x + w, y + h, fill=SCAN_DARK, outline="")

    def show_home(self):
        cv = self._new_canvas()
        self._draw_home_frame(cv)
        if self.logo_source is not None:
            photo = self._photo(self.logo_source, thumb=(340, 340))
            cv.keep(photo)
            cv.create_image(self.config_obj.design_width // 2, 256, image=photo, anchor="center")
        else:
            self._draw_logo_fallback(cv, self.config_obj.design_width // 2, 290)
        self._draw_brand_label(cv, 606)
        self._hud_button(cv, 42, 826, 516, 106, "START", self.show_method, fill=HEADER, text_color=WHITE, icon="arrow", filled=True, font_size=28)
        self._footer(cv)
        self._finalize(cv)

    def show_method(self):
        cv = self._new_canvas()
        self._header(cv, "SELECT SERVICE", back_cmd=self.show_home)
        self._hud_button(cv, 42, 158, 516, 124, "SCAN INJURY", self.show_scan, icon="camera", font_size=30)
        self._hud_button(cv, 42, 312, 516, 124, "SELECT SYMPTOMS", self.show_symptoms, icon="menu", font_size=30)
        self._hud_button(cv, 42, 536, 516, 124, "EMERGENCY", self._emergency_stop, outline=RED, text_color=RED, icon="emergency", font_size=30)
        self._footer(cv)
        self._finalize(cv)

    def show_symptoms(self):
        cv = self._new_canvas()
        self._header(cv, "SELECT SYMPTOMS", back_cmd=self.show_method)

        headache_allergen = self._get_allergen_for_diagnosis("Headache")
        stomach_allergen = self._get_allergen_for_diagnosis("Stomach Upset")
        burn_allergen = self._get_allergen_for_diagnosis("Burn")

        self._hud_button(
            cv,
            42,
            158,
            516,
            124,
            "HEADACHE",
            lambda: self.show_safety("Headache", headache_allergen, 1.0),
            font_size=30,
        )

        self._hud_button(
            cv,
            42,
            312,
            516,
            124,
            "STOMACH UPSET",
            lambda: self.show_safety("Stomach Upset", stomach_allergen, 1.0),
            font_size=30,
        )

        self._hud_button(
            cv,
            42,
            466,
            516,
            124,
            "BURN",
            lambda: self.show_safety("Burn", burn_allergen, 1.0),
            font_size=30,
        )

        self._footer(cv)
        self._finalize(cv)

    def show_scan(self):
        cv = self._new_canvas()
        self._scan_cancelled = False
        self._header(cv, "SCAN INJURY", back_cmd=self._cancel_scan)
        self._draw_scan_background(cv, 0, self.HEADER_H, self.config_obj.design_width, self.config_obj.design_height - self.HEADER_H)

        px2, py, pw, ph2 = 36, 153, 528, 106
        cv.create_rectangle(px2, py, px2 + pw, py + ph2, fill="#176B76", outline="")
        cv.create_line(px2 + 8, py + 10, px2 + 8, py + ph2 - 10, fill="#7AE2EB", width=4)
        cv.create_text(px2 + 22, py + 28, text="INFORMATION", fill="#E7FFFF", font=f_display(14), anchor="w")
        cv.create_line(px2 + 22, py + 44, px2 + pw - 14, py + 44, fill="#7AE2EB", width=1)
        cv.create_text(px2 + 22, py + 66, text="\u29d7", fill="#DDFEFF", font=f_body(15, True), anchor="w")
        cv.create_text(px2 + 56, py + 66, text="Align the injury inside the box...", fill="#F8FFFF", font=f_body(11), anchor="w", tags="scan_status")
        self._card_bracket(cv, px2, py, pw, ph2, color="#7AE2EB", arm=16)

        fx0, fy0, fx1, fy1 = 64, 326, 536, 806
        cv.create_line(64, 292, 264, 292, fill=SCAN_GREEN, width=6)
        cv.create_line(278, 292, 292, 306, fill=SCAN_GREEN, width=2)
        cv.create_line(292, 306, 558, 306, fill=SCAN_GREEN, width=2)
        cv.create_line(fx0, fy0, fx0, fy1, fill=SCAN_GREEN, width=2)
        cv.create_line(fx1, fy0 + 40, fx1, fy1, fill=SCAN_GREEN, width=2)
        cv.create_line(64, 847, 328, 847, fill=SCAN_GREEN, width=2)
        cv.create_polygon(328, 847, 342, 860, 558, 860, 558, 847, fill=SCAN_GREEN, outline=SCAN_GREEN)

        by = 910
        cv.create_line(115, by, 150, by, fill=SCAN_GREEN, width=6)
        cv.create_rectangle(115, by + 22, 127, by + 28, outline=SCAN_GREEN, width=1)
        cv.create_rectangle(135, by + 22, 145, by + 28, outline=SCAN_GREEN, width=1)
        cv.create_rectangle(121, by + 41, 395, by + 86, fill=SCAN_GREEN, outline="")
        for xx in range(401, 521, 16):
            cv.create_line(xx, by + 88, xx + 20, by + 41, fill="#7ED2C4", width=4)
        cv.create_line(530, by + 40, 530, by + 86, fill=SCAN_GREEN, width=1)
        cv.create_line(538, by + 58, 548, by + 58, fill=SCAN_GREEN, width=1)
        cv.create_line(72, by + 54, 106, by + 54, fill=SCAN_GREEN, width=1)
        cv.create_line(81, by + 22, 81, by + 90, fill=SCAN_GREEN, width=2)
        cv.create_line(104, by + 16, 508, by + 16, fill=SCAN_GREEN, width=1)

        self._footer(cv)
        self._finalize(cv)
        self.after(300, self._start_scan_thread)

    def _cancel_scan(self):
        self._scan_cancelled = True
        self.show_method()

    def _start_scan_thread(self):
        if self._scan_cancelled:
            return
        threading.Thread(target=self._vision_worker, daemon=True).start()

    def _scan_preview_callback(self, frame, status_text: str, status_color: str):
        if self._scan_cancelled or self.current is None:
            return
        self.after(0, lambda: self._update_scan_preview(frame, status_text, status_color))

    def _update_scan_preview(self, frame, status_text: str, status_color: str):
        if self.current is None or self._scan_cancelled:
            return

        cv = self.current

        x0, y0, x1, y1 = 64, 326, 536, 806
        w = max(1, self.X(x1 - x0))
        h = max(1, self.Y(y1 - y0))

        pil_img = self.vision.frame_to_preview(frame, (w, h))
        if pil_img is not None:
            photo = ImageTk.PhotoImage(pil_img)
            cv._preview_photo = photo
            cv.delete("scan_preview")
            cv.create_image(self.X(x0), self.Y(y0), image=photo, anchor="nw", tags="scan_preview")

        cv.delete("scan_status")
        cv.create_text(
            self.X(56),
            self.Y(219),
            text=status_text,
            fill=status_color,
            font=(BODY_FAMILY, max(10, self.S(11))),
            anchor="w",
            tags="scan_status",
        )

    def _on_scan_decision(self, diagnosis: str, confidence: float) -> None:
        if self._scan_cancelled:
            return

        if not diagnosis or diagnosis == "Unknown" or confidence <= 0.0:
            self.show_method()
            return

        allergen = self._get_allergen_for_diagnosis(diagnosis)
        self.show_safety(diagnosis, allergen, confidence)

    def _vision_worker(self):
        try:
            decision = self.vision.scan_until_stable(
                preview_callback=self._scan_preview_callback,
                should_cancel=lambda: self._scan_cancelled,
            )
            diagnosis = decision.diagnosis
            confidence = float(decision.confidence)
        except Exception as exc:
            logging.error("Vision failure: %s", exc)
            diagnosis = "Unknown"
            confidence = 0.0

        if not self._scan_cancelled:
            self.after(0, lambda: self._on_scan_decision(diagnosis, confidence))

    def show_safety(self, diagnosis="Unknown", allergen="Unknown Ingredient", confidence=0.0):
        # Remember which diagnosis was confirmed so _do_dispense can branch on it.
        self._pending_diagnosis = diagnosis
        cv = self._new_canvas()
        self._header(cv, "SAFETY CHECK", back_cmd=self.show_method)

        dx, dy, dw, dh = 42, 152, 516, 126
        body_y = self._card(
            cv,
            dx,
            dy,
            dw,
            dh,
            title="DIAGNOSIS",
            icon="gear",
            fill=CARD,
            title_color=DARK_TEXT,
            divider_color=DARK_TEXT,
        )
        self._card_bracket(cv, dx, dy, dw, dh, color=MUTED, arm=16)
        self._card_inline_text(
            cv,
            dx + 56,
            body_y,
            [
                ("Analysis shows  ", f_body(12), BODY_TEXT),
                (f"{diagnosis}.", f_body(12, True), DARK_TEXT),
            ],
        )

        ax, ay, aw, ah = 42, 307, 516, 138
        body_y2 = self._card(
            cv,
            ax,
            ay,
            aw,
            ah,
            title="ALLERGY WARNING",
            icon="warn",
            fill=CARD_AMBER,
            title_color=AMBER,
            divider_color=AMBER,
            left_bar=True,
            left_bar_color=AMBER,
        )
        self._card_bracket(cv, ax, ay, aw, ah, color=AMBER, arm=16)
        cv.create_text(
            ax + 56,
            body_y2,
            text="Please check if the patient is allergic to",
            fill=BODY_TEXT,
            font=f_body(11),
            anchor="w",
        )
        cv.create_text(
            ax + 56,
            body_y2 + 20,
            text=f"{allergen}.",
            fill=DARK_TEXT,
            font=f_body(11, True),
            anchor="w",
        )

        self._hud_button(
            cv,
            42,
            620,
            516,
            124,
            "PROCEED",
            self.show_dispensing,
            outline=TEAL_LINE,
            text_color=TEAL_TEXT,
            icon="arrow",
            font_size=30,
        )
        self._hud_button(
            cv,
            42,
            828,
            516,
            124,
            "CANCEL",
            self.show_method,
            outline=RED,
            text_color=RED,
            icon="x",
            font_size=30,
        )

        self._footer(cv)
        self._finalize(cv)

        self.audit.log("safety_check", diagnosis, f"{confidence:.3f}", f"allergen={allergen}")

    def _emergency_stop(self):
        self.audit.log("emergency_stop", details="service_page_button")
        threading.Thread(target=self._send_emergency_message_async, daemon=True).start()

    def _send_emergency_message_async(self):
        try:
            message_sid = send_emergency_whatsapp()
            logging.info("Emergency WhatsApp sent successfully. SID=%s", message_sid)
            self.audit.log("emergency_message_sent", details=message_sid)
        except Exception as exc:
            logging.error("Failed to send emergency WhatsApp: %s", exc)
            self.audit.log("emergency_message_failed", details=str(exc))

        self.after(0, self.show_home)


    # ── Stock helpers ──────────────────────────────────────────────────────────

    # Shared pill tray (Headache + Stomach Upset): 14 total
    # Burn gel: 15 total
    # Laceration: no stock tracking (manual bandage / external supply)
    _DEFAULT_STOCK = {
        "pills": 14,   # shared by Headache and Stomach Upset
        "Burn":  15,
    }

    # Map each diagnosis to its stock key (None = no stock)
    _STOCK_KEY = {
        "Headache":      "pills",
        "Stomach Upset": "pills",
        "Burn":          "Burn",
        "Laceration":    None,
    }

    def _decrement_stock(self, diagnosis: str) -> None:
        key = self._STOCK_KEY.get(diagnosis)
        if key and key in self._stock:
            self._stock[key] = max(0, self._stock[key] - 1)

    def _draw_stock_card(self, cv, diagnosis: str, y: int = 430) -> None:
        """Draw a compact remaining-stock indicator. No-op for diagnoses with no stock."""
        key = self._STOCK_KEY.get(diagnosis)
        if not key:
            return
        count = self._stock.get(key, 0)
        if count > 5:
            bar_color = "#049767"   # green
            label_color = "#049767"
        elif count > 2:
            bar_color = "#C46A00"   # amber
            label_color = "#C46A00"
        else:
            bar_color = "#C63838"   # red
            label_color = "#C63838"

        # Card background
        bx, by, bw, bh = 42, y, 516, 100
        cv.create_rectangle(
            self.X(bx), self.Y(by),
            self.X(bx + bw), self.Y(by + bh),
            fill=WHITE, outline=bar_color, width=2
        )

        # Left colour strip
        cv.create_rectangle(
            self.X(bx), self.Y(by),
            self.X(bx + 8), self.Y(by + bh),
            fill=bar_color, outline=""
        )

        # Title
        cx = self.X(bx + bw // 2)
        cv.create_text(
            cx, self.Y(by + 22),
            text="REMAINING STOCK",
            fill=MUTED, font=f_body(10, bold=True), anchor="center"
        )

        # Count
        cv.create_text(
            cx, self.Y(by + 56),
            text=str(count),
            fill=label_color, font=f_display(28), anchor="center"
        )

        # Treatment label
        treatment = self.config_obj.diagnosis_treatment_map.get(diagnosis, diagnosis)
        cv.create_text(
            cx, self.Y(by + 82),
            text=treatment,
            fill=MUTED, font=f_body(10), anchor="center"
        )
    def show_dispensing(self):
        cv = self._new_canvas()
        self._header(cv, "DISPENSING")
        bx, by, bw, bh = 42, 308, 516, 76
        draw_corner_bracket(cv, bx, by, 20, TEAL_LINE, "tl", 3)
        draw_corner_bracket(cv, bx + bw, by, 20, TEAL_LINE, "tr", 3)
        draw_corner_bracket(cv, bx, by + bh, 20, TEAL_LINE, "bl", 3)
        draw_corner_bracket(cv, bx + bw, by + bh, 20, TEAL_LINE, "br", 3)
        cv.create_text(self.config_obj.design_width // 2, by + bh // 2 + 1, text="Applying treatment...", fill=TEAL_TEXT, font=f_display(28, False), anchor="center")
        self._footer(cv)
        self._finalize(cv)
        self._spin_frame = 0
        self._spin_spinner(cv, self.X(self.config_obj.design_width // 2), self.Y(580), self.S(96))
        threading.Thread(target=self._do_dispense, daemon=True).start()

    def _spin_spinner(self, cv, cx, cy, radius):
        cv.delete("spinner")
        n = 8
        base = (self._spin_frame // 2) % n
        bar_width = max(self.S(12), int(radius * 0.16))
        inner = radius * 0.34
        outer = radius * 0.70
        colors = {0: HEADER, 1: "#44767D", 2: "#6F959B", 3: "#A4B9BD"}
        default_color = "#D6DEDF"
        for i in range(n):
            lag = (base - i) % n
            color = colors.get(lag, default_color)
            grow = 1.0 + max(0, (3 - lag)) * 0.06
            angle = math.radians((360 / n) * i - 90)
            x0 = cx + inner * math.cos(angle)
            y0 = cy + inner * math.sin(angle)
            x1 = cx + outer * grow * math.cos(angle)
            y1 = cy + outer * grow * math.sin(angle)
            cv.create_line(x0, y0, x1, y1, fill=color, width=bar_width, capstyle="butt", tags="spinner")
        self._spin_frame += 1
        self._spin_job = self.after(70, lambda: self._spin_spinner(cv, cx, cy, radius))

    def _do_dispense(self):
        diagnosis = getattr(self, "_pending_diagnosis", "")
        try:
            if diagnosis in ("Headache", "Stomach Upset"):
                # Pill / tablet diagnoses: servo channel 0 (command '1').
                self.hardware.trigger_servo_for_pill()
            elif diagnosis == "Burn":
                # Gel diagnoses: servo channel 2 (command '2').
                self.hardware.trigger_servo_for_gel()
            else:
                # Physical-treatment diagnoses (Laceration, …): use the
                # thermal-sensor-gated solenoid dispenser as before.
                self.hardware.dispense_item()
        except Exception:
            pass
        # Schedule _end_dispense on the main thread now that hardware is truly done.
        self.after(0, self._end_dispense)

    def _end_dispense(self):
        if self._spin_job:
            self.after_cancel(self._spin_job)
            self._spin_job = None
        self.audit.log("dispense_complete")
        self._decrement_stock(getattr(self, "_pending_diagnosis", ""))
        self.show_discharged()

    def show_discharged(self):
        cv = self._new_canvas()
        self._header(cv, "DISCHARGED")
        cx2, cy2, cw, ch = 36, 153, 528, 107
        body_y = self._card(cv, cx2, cy2, cw, ch, title="PROCESS COMPLETED", icon="check", fill=CARD_GREEN, title_color="#1E8C4A", divider_color="#1E8C4A", left_bar=True, left_bar_color="#1E8C4A")
        self._card_bracket(cv, cx2, cy2, cw, ch, color="#1E8C4A", arm=14)
        cv.create_text(cx2 + 56, body_y, text="We wish you a speedy recovery.", fill=BODY_TEXT, font=f_body(11), anchor="w")
        self._footer(cv)
        self._finalize(cv)
        self._draw_stock_card(cv, getattr(self, "_pending_diagnosis", ""), y=430)
        self._countdown = 5
        self._termination_canvas = cv
        self._draw_termination_card()
        self._tick_countdown()

    def _corner_line(self, x, y, arm, corner):
        if corner == "tl":
            return [x + arm, y, x, y, x, y + arm]
        if corner == "tr":
            return [x - arm, y, x, y, x, y + arm]
        if corner == "bl":
            return [x + arm, y, x, y, x, y - arm]
        return [x - arm, y, x, y, x, y - arm]

    def _draw_termination_card(self):
        cv = self._termination_canvas
        if cv is None:
            return
        cv.delete("termination")
        tx, ty, tw, th = self.X(36), self.Y(291), self.X(528), self.Y(107)
        arm = self.S(16)
        lw = self.S(2)
        cv.create_rectangle(tx, ty, tx + tw, ty + th, fill=CARD, outline="", tags="termination")
        for px, py, corner in [(tx, ty, "tl"), (tx + tw, ty, "tr"), (tx, ty + th, "bl"), (tx + tw, ty + th, "br")]:
            cv.create_line(*self._corner_line(px, py, arm, corner), fill=MUTED, width=lw, tags="termination")
        cv.create_line(tx + self.S(4), ty + self.S(10), tx, ty + self.S(10), tx, ty + th - self.S(10), tx + self.S(4), ty + th - self.S(10), fill=DARK_TEXT, width=lw, tags="termination")
        cv.create_text(tx + self.S(22), ty + self.S(26), text="PROCESS TERMINATION", fill=DARK_TEXT, font=(DISPLAY_FAMILY, max(10, self.S(13)), "bold"), anchor="w", tags="termination")
        cv.create_line(tx + self.S(22), ty + self.S(44), tx + tw - self.S(12), ty + self.S(44), fill=DARK_TEXT, width=max(1, self.S(1)), tags="termination")
        cv.create_text(tx + self.S(22), ty + self.S(76), text="\u2699", fill=MUTED, font=(BODY_FAMILY, max(10, self.S(14)), "bold"), anchor="w", tags="termination")
        pre = "Returning to home screen in "
        num = str(self._countdown)
        post = "..."
        fbase = (BODY_FAMILY, max(9, self.S(11)))
        fbold = (BODY_FAMILY, max(9, self.S(11)), "bold")
        pre_w = tkfont.Font(font=fbase).measure(pre)
        num_w = tkfont.Font(font=fbold).measure(num)
        bx2 = tx + self.S(58)
        tbase = ty + self.S(76)
        cv.create_text(bx2, tbase, text=pre, fill=MUTED, font=fbase, anchor="w", tags="termination")
        cv.create_text(bx2 + pre_w, tbase, text=num, fill=DARK_TEXT, font=fbold, anchor="w", tags="termination")
        cv.create_text(bx2 + pre_w + num_w, tbase, text=post, fill=MUTED, font=fbase, anchor="w", tags="termination")

    def _tick_countdown(self):
        self._draw_termination_card()
        if self._countdown <= 0:
            self.show_home()
            return
        self._countdown -= 1
        self.after(1000, self._tick_countdown)

    def _send_emergency_message_background(self):
        try:
            sid = send_emergency_whatsapp()
            logging.info("Emergency WhatsApp sent successfully. SID=%s", sid)
            self.audit.log("emergency_whatsapp_sent", details=f"sid={sid}")
            self.after(0, lambda: self.show_emergency_status("Emergency alert sent successfully."))
        except Exception as exc:
            logging.error("Emergency WhatsApp failed: %s", exc)
            self.audit.log("emergency_whatsapp_failed", details=str(exc))
            self.after(0, lambda: self.show_emergency_status("Failed to send emergency alert."))

    def show_emergency_status(self, message_text):
        cv = self._new_canvas()
        self._header(cv, "EMERGENCY", back_cmd=self.show_method)

        x, y, w, h = 42, 240, 516, 180
        cv.create_rectangle(x, y, x + w, y + h, fill=CARD_AMBER, outline="")
        self._card_bracket(cv, x, y, w, h, color=RED, arm=16)

        cv.create_text(
            self.config_obj.design_width // 2,
            y + 55,
            text="EMERGENCY ALERT",
            fill=RED,
            font=f_display(20),
            anchor="center",
        )

        cv.create_text(
            self.config_obj.design_width // 2,
            y + 110,
            text=message_text,
            fill=DARK_TEXT,
            font=f_body(14, True),
            anchor="center",
            width=420,
        )

        self._hud_button(
            cv,
            42,
            828,
            516,
            124,
            "BACK",
            self.show_method,
            outline=TEAL_LINE,
            text_color=TEAL_TEXT,
            icon="arrow",
            font_size=30,
        )

        self._footer(cv)
        self._finalize(cv)