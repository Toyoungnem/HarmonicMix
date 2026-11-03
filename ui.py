"""Interface du panneau Serato, séparée du contrôleur app.py.

Identité unique : noir profond, nuances d'orange (ambre, sable, or pâle) et
blanc cassé. Toute la logique (callbacks, pochettes, recherche, statistiques)
est conservée ; ce module ne fait que la présenter.
"""
from __future__ import annotations

import customtkinter as ctk
import math
import tkinter as tk
import tkinter.font as tkfont
from collections import Counter
from tkinter import messagebox
from pathlib import Path
import sys
from io import BytesIO
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

# Palette : un seul axe chromatique (orange) sur un noir neutre.
# Les clés gardent les noms historiques pour ne rien casser dans app.py.
COLORS = {
    "background": "#0A0908", "surface": "#131110", "surface_2": "#1C1916",
    "surface_hover": "#282320", "border": "#2C2622", "border_hover": "#B4642A",
    "text": "#F6EFE7", "muted": "#A99B8C", "dim": "#6E6357",
    "mint": "#FF7A18", "mint_dark": "#3A1D08",
    "violet": "#FFA24C", "violet_dark": "#3B2410",
    "magenta": "#FFC078", "magenta_dark": "#3A2A14",
    "gold": "#F2C46B", "gold_dark": "#332711",
    "progress_bg": "#262120",
    "red": "#FF6B2C", "red_dark": "#3D1A0B",
    "orange": "#FF9A3C", "orange_dark": "#3A230F",
    "yellow": "#FFC978", "yellow_dark": "#382B15",
    "blue": "#F2E9DC", "blue_dark": "#2C2620",
}

FONT = "Segoe UI"
FONT_BOLD = "Segoe UI Semibold"
FONT_LIGHT = "Segoe UI Light"
APP_VERSION = "2.0.0"

# Nom court de chaque palier, affiché sur la carte à côté du rang.
TIER_LABELS = {
    "red": "Très jouée",
    "orange": "Habituelle",
    "yellow": "Rare en set",
    "blue": "Nouvelle",
}
ctk.set_appearance_mode("dark")

# Rayons : arrondis francs mais cohérents d'un bloc à l'autre.
RADIUS_TILE = 24
RADIUS_CARD = 20
RADIUS_ROW = 16
RADIUS_THUMB = 12


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _blend(start, end, amount):
    """Mélange deux couleurs hexadécimales (0 = start, 1 = end)."""
    a, b = _hex_to_rgb(start), _hex_to_rgb(end)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def _rounded(canvas, x0, y0, x1, y1, radius, fill):
    """Rectangle arrondi tracé sur un Canvas (coins lissés)."""
    radius = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
    points = []
    for cx, cy, start in ((x1 - radius, y1 - radius, 0), (x0 + radius, y1 - radius, 90),
                          (x0 + radius, y0 + radius, 180), (x1 - radius, y0 + radius, 270)):
        for step in range(9):
            angle = math.radians(start + step * 11.25)
            points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    canvas.create_polygon(points, fill=fill, outline=fill, smooth=True)


def _soft(color, amount=0.85):
    """Version très sombre d'un accent, pour les fonds de pastilles."""
    return _blend(COLORS["background"], color, 1 - amount)


class SuggestionUI:
    """Présente l'état courant et les suggestions; ne lit aucune donnée Serato."""

    def __init__(self, root: ctk.CTk, on_refresh, on_close, on_search,
                 on_profile_select, on_software_select, on_stats, profile_name="Nel",
                 software="serato", on_cover_request=None):
        self.root = root
        self.on_refresh = on_refresh
        self.on_close = on_close
        self.on_search = on_search
        self.on_profile_select = on_profile_select
        self.on_software_select = on_software_select
        self.on_stats = on_stats
        self.on_cover_request = on_cover_request
        self._cover_cache = {}
        self._cover_targets = {}
        self._ring_cache = {}
        self._logo_cache = {}
        self._chip_font = None
        self.profile_name = profile_name
        self.software = software
        self.topmost = True
        self._selected = None
        self.selected_suggestion = None
        self._cards = []
        self.root.title("Harmonic Mix")
        self.root.configure(fg_color=COLORS["background"])
        self.root.attributes("-topmost", True)
        self.root.geometry("470x850")
        self.root.minsize(420, 600)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Escape>", lambda _event: self.show_home())
        self.root.bind("<F11>", lambda _event: self.toggle_stats_fullscreen())
        self._build()
        self.set_software(self.software)
        self._place_near_serato()

    def _build(self):
        self.page_host = ctk.CTkFrame(self.root, fg_color=COLORS["background"], corner_radius=0)
        self.page_host.pack(fill="both", expand=True)
        self.home_page = ctk.CTkFrame(self.page_host, fg_color=COLORS["background"], corner_radius=0)
        self.dashboard_page = ctk.CTkFrame(self.page_host, fg_color=COLORS["background"], corner_radius=0)
        self.stats_page = ctk.CTkFrame(self.page_host, fg_color=COLORS["background"], corner_radius=0)
        for page in (self.home_page, self.dashboard_page, self.stats_page):
            page.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._build_home()
        self._build_dashboard()
        self._build_stats()
        self.show_home()

    # ------------------------------------------------------------------
    # Utilitaires partagés
    # ------------------------------------------------------------------
    def _scrollbar(self, surface):
        return dict(scrollbar_fg_color=surface, scrollbar_button_color=COLORS["border"],
                    scrollbar_button_hover_color=COLORS["mint"])

    def _font_chip(self):
        if self._chip_font is None:
            self._chip_font = tkfont.Font(family=FONT_BOLD, size=8)
        return self._chip_font

    def _logo(self, size=34):
        """Logo arrondi ; monogramme dessiné en secours si le fichier manque."""
        if size in self._logo_cache:
            return self._logo_cache[size]
        tint = COLORS["mint"]
        image = None
        logo_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "HarmonicMix.png"
        try:
            with Image.open(logo_path) as source:
                logo = source.convert("RGBA")
            scale = size * 3
            logo = ImageOps.fit(logo, (scale, scale), method=Image.Resampling.LANCZOS)
            mask = Image.new("L", (scale, scale), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, scale - 1, scale - 1), fill=255)
            logo.putalpha(mask)
            image = ctk.CTkImage(light_image=logo, dark_image=logo, size=(size, size))
        except (OSError, ValueError):
            image = None
        if image is None:
            scale = size * 4
            canvas = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
            draw = ImageDraw.Draw(canvas)
            draw.ellipse((0, 0, scale - 1, scale - 1), fill=_blend(COLORS["surface_2"], tint, 0.16))
            draw.ellipse((6, 6, scale - 7, scale - 7), outline=tint, width=max(2, scale // 18))
            draw.ellipse((scale * 0.38, scale * 0.38, scale * 0.62, scale * 0.62), fill=tint)
            image = ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(size, size))
        self._logo_cache[size] = image
        return image

    def _waveform(self, parent, width=330, height=20, seed=7):
        """Fine ligne de waveform décorative, façon platine."""
        c = COLORS
        color = _blend(c["surface"], c["mint"], 0.55)
        canvas = tk.Canvas(parent, width=width, height=height, bg=c["surface"],
                           highlightthickness=0, bd=0)
        values = []
        state = seed * 7919
        for _index in range(52):
            state = (state * 1103515245 + 12345) % (2 ** 31)
            values.append(0.22 + 0.78 * ((state >> 16) % 1000) / 1000)
        step = width / len(values)
        middle = height / 2
        for index, value in enumerate(values):
            x = index * step + step / 2
            half = max(1.5, (height / 2 - 1) * value)
            canvas.create_line(x, middle - half, x, middle + half,
                               fill=color, width=max(1, step * 0.4), capstyle="round")
        return canvas

    def _chip(self, icon, text, height=20):
        """Largeur et hauteur d'une pastille (dessinée par _paint_chips)."""
        font = self._font_chip()
        width = font.measure(text) + height + 6
        if icon:
            width += font.measure(icon) + 5
        return width, height

    def _paint_chips(self, canvas, chips, top):
        """Dessine les pastilles sur un Canvas unique : fond arrondi à la taille
        exacte du texte, ce que les labels CustomTkinter ne permettent pas."""
        font = self._font_chip()
        x = 0
        for chip in chips:
            if len(chip) == 4:
                icon, text, background, foreground = chip
                height = 20
            else:
                icon, text, background, foreground, height = chip
            width, _height = self._chip(icon, text, height)
            _rounded(canvas, x, top, x + width - 1, top + height - 1, height / 2,
                     fill=background)
            y = top + height / 2
            if icon:
                icon_width = font.measure(icon)
                canvas.create_text(x + 10 + icon_width / 2, y, text=icon,
                                   fill=foreground, font=font, anchor="center")
                canvas.create_text(x + 15 + icon_width, y, text=text, fill=foreground,
                                   font=font, anchor="w")
            else:
                canvas.create_text(x + width / 2, y, text=text, fill=foreground,
                                   font=font, anchor="center")
            x += width + 5

    # ------------------------------------------------------------------
    # Accueil
    # ------------------------------------------------------------------
    def _build_home(self):
        c = COLORS
        shell = ctk.CTkScrollableFrame(self.home_page, fg_color=c["background"],
                                       corner_radius=0, **self._scrollbar(c["background"]))
        shell.pack(fill="both", expand=True, padx=14, pady=10)

        # Barre du haut : logo, nom, profil
        top = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        top.pack(fill="x", pady=(0, 12))
        mark = ctk.CTkFrame(top, width=38, height=38, fg_color=c["surface"],
                            corner_radius=12, border_width=1, border_color=c["border"])
        mark.pack(side="left")
        mark.pack_propagate(False)
        ctk.CTkLabel(mark, text="", image=self._logo(28)).pack(expand=True)
        brand = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
        brand.pack(side="left", padx=10, fill="y")
        ctk.CTkLabel(brand, text="Harmonic Mix", text_color=c["text"],
                     font=(FONT_BOLD, 15), anchor="w").pack(anchor="w", pady=(2, 0))
        self.home_software_caption = ctk.CTkLabel(
            brand, text="Compagnon de mix", text_color=c["muted"],
            font=(FONT, 10), anchor="w")
        self.home_software_caption.pack(anchor="w")
        self.home_profile_button = ctk.CTkButton(
            top, text=f"{self.profile_name}  ▾", command=self.on_profile_select,
            width=94, height=32, corner_radius=16, fg_color=c["surface"],
            hover_color=c["surface_hover"], text_color=c["text"],
            font=(FONT_BOLD, 11), border_width=1, border_color=c["border"])
        self.home_profile_button.pack(side="right", anchor="n")

        # Salutation : une seule ligne de titre, waveform discrète dessous
        hero = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=RADIUS_TILE,
                            border_width=1, border_color=c["border"], height=96)
        hero.pack(fill="x", pady=(0, 10))
        # Hauteur fixée : sans elle, la waveform (Canvas) fait gonfler la tuile.
        hero.pack_propagate(False)
        accent = ctk.CTkFrame(hero, width=3, fg_color=c["mint"], corner_radius=2)
        accent.pack(side="left", fill="y", padx=(12, 0), pady=13)
        hero_body = ctk.CTkFrame(hero, fg_color="transparent", corner_radius=0)
        hero_body.pack(side="left", fill="both", expand=True, padx=13, pady=(11, 10))
        greeting = ctk.CTkFrame(hero_body, fg_color="transparent", corner_radius=0)
        greeting.pack(fill="x")
        ctk.CTkLabel(greeting, text="BONJOUR", text_color=c["mint"],
                     font=(FONT_BOLD, 10), anchor="w").pack(side="left")
        self.home_username_label = ctk.CTkLabel(
            greeting, text=f" {self.profile_name}", text_color=c["text"],
            font=(FONT_LIGHT, 24), anchor="w")
        self.home_username_label.pack(side="left")
        ctk.CTkLabel(hero_body, text="Le morceau qui s'enchaîne naturellement.",
                     text_color=c["muted"], font=(FONT, 10), anchor="w").pack(
                         anchor="w", pady=(0, 8))
        self._waveform(hero_body, width=290, height=14, seed=3).pack(anchor="w")

        # Choix du logiciel : deux tuiles courtes + Dashboard à droite
        software_row = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        software_row.pack(fill="x", pady=(0, 10))
        self.software_buttons = {}
        for software_id, label in (("serato", "Serato DJ"), ("traktor", "Traktor")):
            button = ctk.CTkButton(
                software_row, text=label,
                command=lambda selected=software_id: self.on_software_select(selected),
                height=46, corner_radius=14, fg_color=c["surface"],
                hover_color=c["surface_hover"], text_color=c["muted"],
                font=(FONT_BOLD, 12), border_width=1, border_color=c["border"])
            button.pack(side="left", fill="x", expand=True,
                        padx=(0 if software_id == "serato" else 4,
                              4 if software_id == "serato" else 0))
            self.software_buttons[software_id] = button
        self.dashboard_choice_button = ctk.CTkButton(
            software_row, text="Dashboard  ›", command=self.on_stats, height=46,
            corner_radius=14, fg_color=c["surface"], hover_color=c["surface_hover"],
            text_color=c["gold"], font=(FONT_BOLD, 12), width=112,
            border_width=1, border_color=c["gold_dark"])
        self.dashboard_choice_button.pack(side="left", padx=(4, 0))
        self._update_software_buttons()

        # Dernière session : compacte
        self.home_status_card = ctk.CTkFrame(shell, fg_color=c["surface_2"],
                                             corner_radius=RADIUS_ROW,
                                             border_width=1, border_color=c["border"])
        self.home_status_card.pack(fill="x", pady=(0, 10))
        self.home_status_label = ctk.CTkLabel(
            self.home_status_card, text="Dernière session", text_color=c["violet"],
            font=(FONT_BOLD, 9), anchor="w")
        self.home_status_label.pack(anchor="w", padx=14, pady=(10, 1))
        self.home_track_label = ctk.CTkLabel(
            self.home_status_card, text="Aucune session détectée", text_color=c["text"],
            font=(FONT_BOLD, 15), anchor="w", justify="left", wraplength=330)
        self.home_track_label.pack(fill="x", padx=14)
        self.home_detail_label = ctk.CTkLabel(
            self.home_status_card, text="Choisis Serato DJ ou Traktor ci-dessus",
            text_color=c["muted"], font=(FONT, 10), anchor="w", justify="left",
            wraplength=330)
        self.home_detail_label.pack(fill="x", padx=14, pady=(1, 10))

        self.home_open_button = ctk.CTkButton(
            shell, text="Découvrir mes suggestions   →", command=self.show_dashboard,
            height=44, corner_radius=22, fg_color=c["mint"],
            hover_color=_blend(c["mint"], "#FFFFFF", 0.16), text_color="#14100C",
            font=(FONT_BOLD, 12), border_width=0)
        self.home_open_button.pack(fill="x", pady=(0, 7))
        ctk.CTkLabel(shell, text="Choisis une piste, puis cherche-la dans ton logiciel DJ.",
                     text_color=c["dim"], font=(FONT, 9), anchor="center").pack(fill="x")

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------
    def _build_dashboard(self):
        c = COLORS
        shell = ctk.CTkFrame(self.dashboard_page, fg_color=c["background"], corner_radius=0)
        shell.pack(fill="both", expand=True, padx=14, pady=12)

        header = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", pady=(0, 10))
        brand = ctk.CTkFrame(header, fg_color="transparent", corner_radius=0)
        brand.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(brand, text="Harmonic Mix", text_color=c["text"],
                     font=(FONT_BOLD, 17), anchor="w").pack(anchor="w")
        ctk.CTkLabel(brand, text="La prochaine piste, en harmonie avec ton set",
                     text_color=c["muted"], font=(FONT, 10), anchor="w").pack(
                         anchor="w", pady=(1, 0))
        self.pin_button = ctk.CTkButton(
            header, text="●  Épinglé", command=self.toggle_topmost, width=100,
            height=34, corner_radius=17, fg_color=c["mint_dark"],
            hover_color=c["surface_hover"], text_color=c["mint"],
            font=(FONT_BOLD, 11), border_width=1, border_color=c["mint_dark"])
        self.pin_button.pack(side="right", anchor="n")

        now = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=RADIUS_TILE,
                           border_width=1, border_color=c["border"], height=86)
        now.pack(fill="x", pady=(0, 10))
        now.pack_propagate(False)
        accent = ctk.CTkFrame(now, width=3, fg_color=c["mint"], corner_radius=2)
        accent.pack(side="left", fill="y", padx=(11, 0), pady=12)
        self.current_cover_label = ctk.CTkLabel(
            now, text="HM", width=56, height=56, fg_color=c["surface_2"],
            text_color=c["violet"], corner_radius=RADIUS_THUMB + 2, font=(FONT_BOLD, 13))
        self.current_cover_label.pack(side="left", padx=(11, 0), pady=14)
        current = ctk.CTkFrame(now, fg_color="transparent", corner_radius=0)
        current.pack(side="left", fill="both", expand=True, padx=12, pady=9)
        current_header = ctk.CTkFrame(current, fg_color="transparent", corner_radius=0)
        current_header.pack(fill="x")
        self.current_section_label = ctk.CTkLabel(
            current_header, text="Dernière piste", text_color=c["muted"],
            font=(FONT_BOLD, 10), anchor="w")
        self.current_section_label.pack(side="left")
        self.status_label = ctk.CTkLabel(current_header, text="", text_color=c["mint"],
                                         font=(FONT_BOLD, 9), anchor="e")
        self.status_label.pack(side="right")
        self.current_label = ctk.CTkLabel(
            current, text="En attente de Serato", text_color=c["text"],
            font=(FONT_BOLD, 16), anchor="w", justify="left", wraplength=250)
        self.current_label.pack(fill="x", pady=(3, 0))
        self.detail_label = ctk.CTkLabel(
            current, text="", text_color=c["muted"], font=(FONT, 10), anchor="w",
            justify="left", wraplength=240)
        self.detail_label.pack(fill="x")

        section = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        section.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(section, text="Meilleures suggestions", text_color=c["text"],
                     font=(FONT_BOLD, 14), anchor="w").pack(side="left", padx=(3, 0))
        self.home_button = ctk.CTkButton(
            section, text="⌂", command=self.show_home, width=34, height=34,
            corner_radius=17, fg_color=c["surface"], hover_color=c["surface_hover"],
            text_color=c["text"], font=(FONT_BOLD, 15), border_width=1,
            border_color=c["border"])
        self.home_button.pack(side="right", padx=(6, 0))
        self.refresh_button = ctk.CTkButton(
            section, text="↻", command=self.on_refresh, width=34, height=34,
            corner_radius=17, fg_color=c["surface"], hover_color=c["surface_hover"],
            text_color=c["text"], font=(FONT_BOLD, 15), border_width=1,
            border_color=c["border"])
        self.refresh_button.pack(side="right")

        self.cards = ctk.CTkScrollableFrame(shell, fg_color="transparent",
                                            corner_radius=0, height=60,
                                            **self._scrollbar(c["background"]))
        self.cards.pack(fill="both", expand=True)

        self.load_bar = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        self.load_hint = ctk.CTkLabel(
            self.load_bar, text="Sélectionne un morceau pour le rechercher dans Serato",
            text_color=c["muted"], font=(FONT, 9), anchor="w")
        self.load_hint.pack(fill="x", padx=3, pady=(0, 3))
        self.search_button = ctk.CTkButton(
            self.load_bar, text="⌕  Chercher dans Serato", state="disabled",
            command=self._search_selected, height=38, corner_radius=19,
            fg_color=c["surface"], hover_color=_blend(c["mint"], "#FFFFFF", 0.16),
            text_color=c["dim"], text_color_disabled=c["dim"],
            font=(FONT_BOLD, 12), border_width=1, border_color=c["border"])
        self.search_button.pack(fill="x")

        # Explication de la piste sélectionnée : un seul bloc, une ligne ou deux.
        self.reason_box = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=12,
                                       border_width=1, border_color=c["border"])
        self.reason_label = ctk.CTkLabel(
            self.reason_box,
            text="Sélectionne une piste pour voir pourquoi elle est proposée",
            text_color=c["muted"], font=(FONT, 9), anchor="w", justify="left",
            wraplength=560)
        self.reason_label.pack(fill="x", padx=12, pady=7)

        self.cards.pack_forget()
        self.reason_box.pack(side="bottom", fill="x", pady=(5, 4))
        self.load_bar.pack(side="bottom", fill="x", pady=(4, 0))
        self.cards.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Dashboard / statistiques
    # ------------------------------------------------------------------
    def _build_stats(self):
        c = COLORS
        shell = ctk.CTkFrame(self.stats_page, fg_color=c["background"], corner_radius=0)
        shell.pack(fill="both", expand=True, padx=34, pady=26)

        header = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", pady=(0, 20))
        heading = ctk.CTkFrame(header, fg_color="transparent", corner_radius=0)
        heading.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(heading, text=f"Harmonic Mix  /  Dashboard  ·  v{APP_VERSION}",
                     text_color=c["text"], font=(FONT_LIGHT, 27), anchor="w").pack(anchor="w")
        ctk.CTkLabel(heading, text="Analyse de tes sets et de l'évolution de tes styles musicaux",
                     text_color=c["muted"], font=(FONT, 12), anchor="w").pack(anchor="w", pady=(4, 0))
        self.stats_software_label = ctk.CTkLabel(
            header, text="SERATO DJ", text_color=c["mint"], fg_color=c["mint_dark"],
            corner_radius=14, height=28, width=104, font=(FONT_BOLD, 11), anchor="center")
        self.stats_software_label.pack(side="right", padx=(10, 16))
        ctk.CTkLabel(header, text="●  Mise à jour auto · 5 s", text_color=c["muted"],
                     font=(FONT_BOLD, 11), anchor="e").pack(side="right", padx=(0, 14))
        ctk.CTkButton(
            header, text="←  Accueil", command=self.show_home, height=40,
            corner_radius=20, fg_color=c["surface"], hover_color=c["surface_hover"],
            text_color=c["text"], font=(FONT_BOLD, 12), border_width=1,
            border_color=c["border"]).pack(side="right")

        body = ctk.CTkScrollableFrame(shell, fg_color="transparent", corner_radius=0,
                                      **self._scrollbar(c["background"]))
        body.pack(fill="both", expand=True)

        kpi_row = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        kpi_row.pack(fill="x", pady=(0, 12))
        self.stats_kpi_values = {}
        accents = (c["mint"], c["orange"], c["gold"], c["violet"])
        for index, (key, title) in enumerate((
            ("sessions", "Sets analysés"),
            ("tracks", "Morceaux joués"),
            ("transition_count", "Transitions rejouées"),
            ("distinct_transitions", "Enchaînements distincts"),
        )):
            accent = accents[index]
            card = ctk.CTkFrame(kpi_row, fg_color=c["surface"], corner_radius=RADIUS_TILE,
                                border_width=1, border_color=c["border"])
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 10, 0))
            kpi_row.grid_columnconfigure(index, weight=1, uniform="kpi")
            ctk.CTkLabel(card, text=title, text_color=c["muted"],
                         font=(FONT_BOLD, 11), anchor="w").pack(anchor="w", padx=18,
                                                                pady=(16, 2))
            icon = tk.Canvas(card, width=32, height=32, bg=c["surface"],
                             highlightthickness=0, bd=0)
            icon.place(relx=1.0, x=-16, y=14, anchor="ne")
            self._draw_kpi_icon(icon, key, accent, c["surface"])
            value = ctk.CTkLabel(card, text="—", text_color=c["text"],
                                 font=(FONT_LIGHT, 36), anchor="w")
            value.pack(anchor="w", padx=18, pady=(0, 4))
            bar = ctk.CTkProgressBar(card, height=3, corner_radius=2,
                                     fg_color=c["progress_bg"], progress_color=accent)
            bar.pack(fill="x", padx=18, pady=(0, 14))
            bar.set(1)
            self.stats_kpi_values[key] = value

        analytics = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        analytics.pack(fill="both", expand=True)
        analytics.grid_columnconfigure(0, weight=7, uniform="analytics")
        analytics.grid_columnconfigure(1, weight=4, uniform="analytics")
        transitions_card = ctk.CTkFrame(analytics, fg_color=c["surface"],
                                        corner_radius=RADIUS_TILE, border_width=1,
                                        border_color=c["border"])
        transitions_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(transitions_card, text="Enchaînements les plus fréquents",
                     text_color=c["text"], font=(FONT_BOLD, 14), anchor="w").pack(
                         anchor="w", padx=20, pady=(16, 8))
        self.stats_transitions_list = ctk.CTkScrollableFrame(
            transitions_card, fg_color="transparent", corner_radius=0,
            **self._scrollbar(c["surface"]))
        self.stats_transitions_list.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        destinations_card = ctk.CTkFrame(analytics, fg_color=c["surface"],
                                         corner_radius=RADIUS_TILE, border_width=1,
                                         border_color=c["border"])
        destinations_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(destinations_card, text="Pistes les plus souvent enchaînées",
                     text_color=c["text"], font=(FONT_BOLD, 14), anchor="w",
                     wraplength=320, justify="left").pack(anchor="w", padx=20, pady=(16, 8))
        self.stats_destinations_list = ctk.CTkScrollableFrame(
            destinations_card, fg_color="transparent", corner_radius=0,
            **self._scrollbar(c["surface"]))
        self.stats_destinations_list.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        trend_card = ctk.CTkFrame(body, fg_color=c["surface"], corner_radius=RADIUS_TILE,
                                  border_width=1, border_color=c["border"])
        trend_card.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(trend_card, text="Styles musicaux au fil des sets",
                     text_color=c["text"], font=(FONT_BOLD, 14), anchor="w").pack(
                         anchor="w", padx=20, pady=(16, 0))
        ctk.CTkLabel(trend_card,
                     text="Évolution des genres par set · titres, transitions et BPM moyen à droite.",
                     text_color=c["muted"], font=(FONT, 11), anchor="w").pack(
                         anchor="w", padx=20, pady=(3, 0))
        self.stats_genre_chart = tk.Canvas(trend_card, height=430, bg=c["surface"],
                                           highlightthickness=0, bd=0)
        self.stats_genre_chart.pack(fill="x", padx=16, pady=(2, 14))

        self.stats_footer = ctk.CTkLabel(
            body, text="Les statistiques sont calculées localement depuis ton historique.",
            text_color=c["dim"], font=(FONT, 11), anchor="w")
        self.stats_footer.pack(fill="x", pady=(14, 0))

    def _render_stats(self, stats):
        c = COLORS
        self.stats_software_label.configure(text=stats["software"].upper())
        for key, label in self.stats_kpi_values.items():
            value = int(stats[key])
            label.configure(
                text=self._format_metric(value),
                font=(FONT_LIGHT, 36 if value < 100_000 else 28 if value < 10_000_000 else 22))
        for widget in self.stats_transitions_list.winfo_children():
            widget.destroy()
        for widget in self.stats_destinations_list.winfo_children():
            widget.destroy()

        top = stats["top_transitions"]
        if not top:
            ctk.CTkLabel(self.stats_transitions_list,
                         text="Aucune transition enregistrée pour le moment.",
                         text_color=c["muted"], font=(FONT, 12), anchor="w").pack(
                             fill="x", padx=10, pady=16)
        for rank, row in enumerate(top, 1):
            line = ctk.CTkFrame(self.stats_transitions_list, fg_color=c["surface_2"],
                                corner_radius=RADIUS_ROW)
            line.pack(fill="x", padx=2, pady=3)
            ctk.CTkLabel(line, text=f"{rank:02}", width=30, height=30, corner_radius=15,
                         fg_color=c["mint_dark"], text_color=c["mint"],
                         font=(FONT_BOLD, 10)).pack(side="left", padx=10, pady=8)
            source_cover = ctk.CTkLabel(line, text="HM", width=36, height=36,
                                        fg_color=c["surface"], text_color=c["violet"],
                                        corner_radius=RADIUS_THUMB - 4,
                                        font=(FONT_BOLD, 9))
            source_cover.pack(side="left", padx=(0, 4), pady=6)
            self._request_cover(row["source_path"], source_cover, 36)
            target_cover = ctk.CTkLabel(line, text="HM", width=36, height=36,
                                        fg_color=c["surface"], text_color=c["mint"],
                                        corner_radius=RADIUS_THUMB - 4,
                                        font=(FONT_BOLD, 9))
            target_cover.pack(side="left", padx=(0, 8), pady=6)
            self._request_cover(row["target_path"], target_cover, 36)
            text_frame = ctk.CTkFrame(line, fg_color="transparent", corner_radius=0)
            text_frame.pack(side="left", fill="x", expand=True, padx=(2, 8), pady=7)
            source = row["source_title"] or Path(row["source_path"]).stem
            target = row["target_title"] or Path(row["target_path"]).stem
            ctk.CTkLabel(text_frame, text=f"{source}  →  {target}", text_color=c["text"],
                         font=(FONT_BOLD, 12), anchor="w", justify="left",
                         wraplength=520).pack(fill="x")
            ctk.CTkLabel(line, text=self._format_compact(row["count"]), width=62,
                         text_color=c["mint"], font=(FONT_BOLD, 14)).pack(side="right",
                                                                         padx=14)

        destinations = stats["destinations"]
        if not destinations:
            ctk.CTkLabel(self.stats_destinations_list, text="Pas encore assez de sets.",
                         text_color=c["muted"], font=(FONT, 12), anchor="w").pack(
                             fill="x", padx=10, pady=16)
        for rank, item in enumerate(destinations, 1):
            row = ctk.CTkFrame(self.stats_destinations_list, fg_color=c["surface_2"],
                               corner_radius=RADIUS_ROW)
            row.pack(fill="x", padx=2, pady=3)
            ctk.CTkLabel(row, text=f"{rank:02}", width=30, height=30, corner_radius=15,
                         fg_color=c["violet_dark"], text_color=c["violet"],
                         font=(FONT_BOLD, 9)).pack(side="left", padx=10, pady=8)
            cover_label = ctk.CTkLabel(row, text="HM", width=38, height=38,
                                       fg_color=c["surface"], text_color=c["violet"],
                                       corner_radius=RADIUS_THUMB - 4,
                                       font=(FONT_BOLD, 9))
            cover_label.pack(side="left", padx=(0, 8), pady=6)
            self._request_cover(item.get("path"), cover_label, 38)
            ctk.CTkLabel(row, text=item["title"], text_color=c["text"],
                         font=(FONT_BOLD, 12), anchor="w", justify="left",
                         wraplength=250).pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=self._format_compact(item["count"]), width=58,
                         text_color=c["violet"], font=(FONT_BOLD, 13)).pack(side="right",
                                                                            padx=12)

        state = "session en cours" if stats["active_session"] else "dernière session archivée"
        self.stats_footer.configure(
            text=f"Source : {stats['software']}  ·  Dernier set : {stats['last_session']}"
                 f"  ·  {state}  ·  Échap pour revenir")
        self._stats_data = stats
        self.root.after_idle(self._draw_stats_charts)

    @staticmethod
    def _format_metric(value):
        if value >= 10_000_000:
            return f"{value / 1_000_000:.1f} M"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f} M"
        return f"{value:,}".replace(",", " ")

    @staticmethod
    def _format_compact(value):
        return f"{SuggestionUI._compact_number(value)}×"

    @staticmethod
    def _compact_number(value):
        value = int(value)
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f} M"
        if value >= 10_000:
            return f"{value / 1_000:.1f} k"
        return str(value)

    # ------------------------------------------------------------------
    # Pochettes
    # ------------------------------------------------------------------
    def _request_cover(self, path, label, size):
        if not path:
            if getattr(label, "_hm_cover_path", None) is not None:
                label.configure(text="HM", image=None)
                label._hm_cover_path = None
            return
        key = str(path).casefold()
        if getattr(label, "_hm_cover_path", None) == key:
            return
        if hasattr(label, "_hm_cover_path"):
            label.configure(text="HM", image=None)
        label._hm_cover_path = key
        cache_key = (key, size)
        image = self._cover_cache.get(cache_key)
        if image is not None:
            label.configure(text="", image=image)
            return
        raw = self._cover_cache.get(key)
        if isinstance(raw, bytes):
            image = self._make_cover_image(key, size, raw)
            if image is not None:
                label.configure(text="", image=image)
            return
        if key in self._cover_cache:
            return
        self._cover_targets.setdefault(key, []).append((label, size))
        if self.on_cover_request:
            self._cover_cache[key] = False  # Requête déjà lancée.
            self.on_cover_request(str(path))

    def set_cover(self, path, image_data):
        """Applique sur le thread UI une pochette extraite en arrière-plan."""
        key = str(path).casefold()
        targets = self._cover_targets.pop(key, [])
        valid_data = None
        if image_data:
            try:
                with Image.open(BytesIO(image_data)) as cover:
                    cover.verify()
                valid_data = image_data
            except (OSError, ValueError):
                valid_data = None
        self._cover_cache[key] = valid_data
        for label, size in targets:
            try:
                image = self._make_cover_image(key, size, valid_data) if valid_data else None
                if image is not None:
                    label.configure(text="", image=image)
            except tk.TclError:
                continue

    def _make_cover_image(self, key, size, image_data):
        """Pochette carrée, coins arrondis, sans bandes : l'image remplit le
        cadre (recadrage centré) puis reçoit un léger assombrissement pour que
        le texte des listes reste lisible à côté."""
        cache_key = (key, size)
        if cache_key in self._cover_cache:
            return self._cover_cache[cache_key]
        try:
            with Image.open(BytesIO(image_data)) as cover:
                art = cover.convert("RGB")
                if art.width < 4 or art.height < 4:
                    return None
                sharpness = abs(art.width - art.height) / max(art.width, art.height)
                full = size * 3
                if sharpness < 0.25:
                    # Pochette à peu près carrée : recadrage centré, aucun vide.
                    art = ImageOps.fit(art, (full, full), method=Image.Resampling.LANCZOS)
                else:
                    # Image très allongée (photo de groupe, scan) : on la garde
                    # entière sur un fond tiré de ses propres couleurs.
                    contained = ImageOps.contain(art, (full, full),
                                                 method=Image.Resampling.LANCZOS)
                    backdrop = ImageOps.fit(art, (full, full),
                                            method=Image.Resampling.BILINEAR)
                    backdrop = backdrop.filter(ImageFilter.GaussianBlur(full / 12))
                    backdrop = ImageEnhance.Brightness(backdrop).enhance(0.55)
                    backdrop.paste(contained, ((full - contained.width) // 2,
                                               (full - contained.height) // 2))
                    art = backdrop
                art = ImageEnhance.Brightness(art).enhance(0.94)
                mask = Image.new("L", (full, full), 0)
                ImageDraw.Draw(mask).rounded_rectangle(
                    (0, 0, full - 1, full - 1), radius=size // 3, fill=255)
                art = art.convert("RGBA")
                art.putalpha(mask)
                image = ctk.CTkImage(light_image=art, dark_image=art, size=(size, size))
            self._cover_cache[cache_key] = image
            return image
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Graphiques
    # ------------------------------------------------------------------
    def _score_ring(self, score, color, size=54, thickness=5):
        """Anneau de score lissé ; `score` peut être flottant (animation)."""
        key = (round(max(0.0, min(100.0, score)), 1), color, size)
        cached = self._ring_cache.get(key)
        if cached is not None:
            return cached
        scale = 4
        full = size * scale
        stroke = thickness * scale
        pad = stroke // 2 + scale
        box = (pad, pad, full - pad, full - pad)
        image = Image.new("RGBA", (full, full), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse(box, outline=_blend(COLORS["surface_2"], color, 0.25), width=stroke)
        percent = key[0]
        if percent > 0:
            end = -90 + 360 * percent / 100
            draw.arc(box, start=-90, end=end, fill=color, width=stroke)
            radius = (full - 2 * pad) / 2
            center = full / 2
            cap = stroke / 2
            for angle in (-90, end):
                x = center + radius * math.cos(math.radians(angle))
                y = center + radius * math.sin(math.radians(angle))
                draw.ellipse((x - cap, y - cap, x + cap, y + cap), fill=color)
        ring = ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
        self._ring_cache[key] = ring
        return ring

    @staticmethod
    def _draw_kpi_icon(canvas, kind, color, background=None):
        background = background or COLORS["surface"]
        if kind == "sessions":
            canvas.create_rectangle(6, 7, 26, 26, outline=color, width=2)
            canvas.create_line(6, 13, 26, 13, fill=color, width=2)
            canvas.create_line(11, 4, 11, 10, fill=color, width=2)
            canvas.create_line(21, 4, 21, 10, fill=color, width=2)
            canvas.create_oval(11, 17, 14, 20, fill=color, outline=color)
            canvas.create_oval(18, 17, 21, 20, fill=color, outline=color)
        elif kind == "tracks":
            canvas.create_oval(4, 4, 28, 28, outline=color, width=2)
            canvas.create_oval(10, 10, 22, 22, outline=color, width=2)
            canvas.create_oval(14, 14, 18, 18, fill=color, outline=color)
        elif kind == "transition_count":
            canvas.create_line(5, 9, 25, 9, fill=color, width=2, arrow="last")
            canvas.create_line(27, 22, 7, 22, fill=color, width=2, arrow="last")
            canvas.create_line(9, 16, 23, 16, fill=color, width=2, arrow="last")
        else:
            canvas.create_line(8, 8, 24, 24, fill=color, width=2)
            canvas.create_line(8, 24, 24, 8, fill=color, width=2)
            for x, y in ((8, 8), (24, 24), (8, 24), (24, 8)):
                canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=background,
                                   outline=color, width=2)

    def _draw_stats_charts(self):
        if not hasattr(self, "_stats_data"):
            return
        self._draw_genre_timeline(self.stats_genre_chart,
                                  self._stats_data.get("session_activity", []))

    def _draw_genre_timeline(self, canvas, sessions):
        c = COLORS
        canvas.delete("all")
        self._stats_animation_generation = getattr(self, "_stats_animation_generation", 0) + 1
        generation = self._stats_animation_generation
        width = max(canvas.winfo_width(), 520)
        data = sessions[-12:]
        if not data:
            canvas.create_text(18, 36, fill=c["muted"], anchor="w", font=(FONT, 11),
                               text="Les styles apparaîtront dès qu'un set avec des tags "
                                    "de genre sera analysé.")
            return
        colors = [c["mint"], c["orange"], c["gold"], c["violet"]]
        totals = Counter()
        for session in data:
            totals.update({name: int(count)
                           for name, count in session.get("genres", {}).items()})
        top_genres = [name for name, _ in totals.most_common(4)]
        categories = top_genres + ["Autres / sans tag"]
        palette = colors[:len(top_genres)] + [c["border"]]
        legend_x, legend_row = 120, 0
        legend_right = width - 14
        for name, color in zip(categories, palette):
            label = name[:14]
            entry_width = min(150, max(88, len(label) * 6 + 30))
            if legend_x + entry_width > legend_right and legend_x > 120:
                legend_row += 1
                legend_x = 120
            legend_y = 10 + legend_row * 19
            canvas.create_rectangle(legend_x, legend_y, legend_x + 10, legend_y + 10,
                                    fill=color, outline="")
            canvas.create_text(legend_x + 16, legend_y + 5, text=label, fill=c["muted"],
                               anchor="w", font=(FONT, 9))
            legend_x += entry_width

        chart_x = 120
        right = width - 190
        chart_width = max(90, right - chart_x)
        row_height = 24
        top_y = 42 + legend_row * 19
        canvas.configure(height=max(300, top_y + len(data) * row_height + 22))
        for step in range(5):
            x = chart_x + chart_width * step / 4
            canvas.create_line(x, top_y - 4, x, top_y + len(data) * row_height,
                               fill=c["border"], dash=(2, 4))
            canvas.create_text(x, top_y - 8, text=f"{step * 25}%", fill=c["dim"],
                               anchor="s", font=(FONT, 8))

        animated_bars = []
        for index, session in enumerate(data):
            y = top_y + index * row_height
            canvas.create_text(4, y + 8, text=session.get("label", f"Set {index + 1}"),
                               fill=c["text"], anchor="w", font=(FONT_BOLD, 9))
            genre_counts = {name: int(count)
                            for name, count in session.get("genres", {}).items()}
            track_count = max(0, int(session.get("tracks", 0)))
            selected = [genre_counts.get(name, 0) for name in top_genres]
            known_total = sum(genre_counts.values())
            other_total = max(0, track_count - min(track_count, known_total))
            other_total += sum(count for name, count in genre_counts.items()
                               if name not in top_genres)
            segments = selected + [other_total]
            segment_total = sum(segments)
            if segment_total:
                x = chart_x
                for segment, color in zip(segments, palette):
                    if segment <= 0:
                        continue
                    segment_width = chart_width * segment / segment_total
                    item = canvas.create_rectangle(x, y, x, y + 16, fill=color,
                                                   outline=c["surface"])
                    animated_bars.append((item, x, x + segment_width, y))
                    x += segment_width
            else:
                canvas.create_text(chart_x + 4, y + 8, text="Genres non renseignés",
                                   fill=c["muted"], anchor="w", font=(FONT, 8))
            avg_bpm = session.get("average_bpm")
            bpm_text = f" · {avg_bpm:g} BPM" if avg_bpm else ""
            track_text = f"{self._compact_number(track_count)} titres"
            transition_text = f"{self._compact_number(session.get('transitions', 0))} trans."
            canvas.create_text(width - 6, y + 8, fill=c["muted"], anchor="e",
                               font=(FONT, 8),
                               text=f"{track_text} · {transition_text}{bpm_text}")

        self._animate_stats_bars(animated_bars, generation, 0)

    def _animate_stats_bars(self, bars, generation, frame):
        if generation != getattr(self, "_stats_animation_generation", None):
            return
        progress = min(1.0, frame / 12)
        eased = 1 - (1 - progress) ** 3
        for item, start_x, end_x, y in bars:
            self.stats_genre_chart.coords(item, start_x, y,
                                          start_x + (end_x - start_x) * eased, y + 16)
        if progress < 1:
            self.root.after(16, self._animate_stats_bars, bars, generation, frame + 1)

    # ------------------------------------------------------------------
    # Fenêtre et navigation
    # ------------------------------------------------------------------
    def _place_near_serato(self):
        self._set_page_geometry(470, 850)

    def _set_page_geometry(self, preferred_width, preferred_height):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(preferred_width, screen_w - 28)
        target_height = min(preferred_height, int(screen_h * 0.61))
        height = min(max(600, target_height), screen_h - 28)
        x = screen_w - width - 14
        y = screen_h - height - 14
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def toggle_topmost(self):
        self.set_topmost(not self.topmost)

    def set_topmost(self, enabled):
        self.topmost = bool(enabled)
        self.root.attributes("-topmost", self.topmost)
        c = COLORS
        self.pin_button.configure(
            text="●  Épinglé" if self.topmost else "○  Libre",
            fg_color=c["mint_dark"] if self.topmost else c["surface"],
            hover_color=c["surface_hover"],
            text_color=c["mint"] if self.topmost else c["muted"],
            border_color=c["mint_dark"] if self.topmost else c["border"])

    def show_home(self):
        self.root.attributes("-fullscreen", False)
        self.active_page = "home"
        self._set_page_geometry(470, 850)
        self.home_page.tkraise()

    def show_dashboard(self):
        self.root.attributes("-fullscreen", False)
        self.active_page = "suggestions"
        self._set_page_geometry(470, 850)
        self.dashboard_page.tkraise()

    def show_stats(self, stats):
        self.active_page = "stats"
        self._render_stats(stats)
        self.root.attributes("-fullscreen", True)
        self.stats_page.tkraise()
        # Le canvas des genres est dimensionné une fois la page affichée.
        self.root.after(60, self._draw_stats_charts)
        self.root.bind("<Configure>", self._on_stats_resize)

    def _on_stats_resize(self, event=None):
        if getattr(self, "active_page", "home") != "stats":
            return
        if event is not None and getattr(event, "widget", None) is not self.root:
            return
        pending = getattr(self, "_stats_resize_job", None)
        if pending:
            try:
                self.root.after_cancel(pending)
            except (ValueError, tk.TclError):
                pass
        self._stats_resize_job = self.root.after(120, self._draw_stats_charts)

    def toggle_stats_fullscreen(self):
        if getattr(self, "active_page", "home") == "stats":
            current = self.root.attributes("-fullscreen") in (True, 1, "1", "true")
            self.root.attributes("-fullscreen", not current)

    def set_profile(self, name):
        self.profile_name = name
        self.home_profile_button.configure(text=f"{name}  ▾")
        self.home_username_label.configure(text=f" {name}")
        self.home_track_label.configure(text=f"En attente de {self._software_name()}")

    def _software_name(self):
        return "Serato DJ" if self.software == "serato" else "Traktor"

    def set_software(self, software):
        self.software = software if software in {"serato", "traktor"} else "serato"
        self._update_software_buttons()
        label = self._software_name()
        self.root.title(f"{label} · Harmonic Mix")
        self.home_software_caption.configure(text=f"{label}  ·  Compagnon de mix")
        self.current_label.configure(text=f"En attente de {label}")
        self.home_track_label.configure(text=f"En attente de {label}")
        self.search_button.configure(text=f"⌕  Chercher dans {label}")
        self.load_hint.configure(text=f"Sélectionne un morceau pour le rechercher dans {label}")
        self.home_open_button.configure(
            text=f"Découvrir mes suggestions {label}   →")

    def _update_software_buttons(self):
        c = COLORS
        for software_id, button in self.software_buttons.items():
            selected = software_id == self.software
            button.configure(
                fg_color=c["mint_dark"] if selected else c["surface"],
                text_color=c["mint"] if selected else c["muted"],
                border_color=c["mint"] if selected else c["border"])

    def show_error(self, message):
        self.status_label.configure(text="● Erreur", text_color=COLORS["gold"])
        self.reason_label.configure(text=message)

    # ------------------------------------------------------------------
    # Recherche dans le logiciel DJ
    # ------------------------------------------------------------------
    def _set_search_state(self, state):
        c = COLORS
        enabled = state == "normal"
        self.search_button.configure(
            state=state,
            fg_color=c["mint"] if enabled else c["surface"],
            hover_color=_blend(c["mint"], "#FFFFFF", 0.16),
            text_color="#14100C" if enabled else c["dim"],
            border_color=c["mint"] if enabled else c["border"])

    def _search_selected(self):
        if self.selected_suggestion is not None:
            self._set_search_state("disabled")
            self.load_hint.configure(
                text=f"Recherche progressive dans {self._software_name()}…",
                text_color=COLORS["violet"])
            self.on_search(self.selected_suggestion)

    def show_search_result(self, message, success=True, busy=False, pause_refresh=False):
        color = COLORS["mint"] if success else COLORS["gold"]
        self.load_hint.configure(text=message, text_color=color)
        self._set_search_state(
            "disabled" if busy else
            ("normal" if self.selected_suggestion is not None else "disabled"))
        self.refresh_button.configure(state="disabled" if busy or pause_refresh else "normal")

    # ------------------------------------------------------------------
    # Rendu principal
    # ------------------------------------------------------------------
    def render(self, title, detail, status, status_color, suggestions,
               session_date="", session_detail="", cover_path=None):
        is_playing = "EN DIRECT" in status or status == "● SERATO"
        self.current_label.configure(text=title)
        self.detail_label.configure(text=detail)
        self.home_track_label.configure(text=session_date or "Aucune session détectée")
        self.home_detail_label.configure(text=session_detail or
                                         "Choisis Serato DJ ou Traktor ci-dessus")
        self.home_status_label.configure(text="Dernière session", text_color=status_color)
        self.current_section_label.configure(
            text="En cours" if is_playing else "Dernière session",
            text_color=COLORS["mint"] if is_playing else COLORS["muted"])
        self.status_label.configure(text=status, text_color=status_color)
        self._request_cover(cover_path, self.current_cover_label, 56)
        self._render_cards(suggestions)

    def _render_cards(self, suggestions):
        c = COLORS
        for child in self.cards.winfo_children():
            child.destroy()
        self._cards = []
        self._selected = None
        self.selected_suggestion = None
        self._set_search_state("disabled")
        self.load_hint.configure(
            text=f"Sélectionne un morceau pour le rechercher dans {self._software_name()}",
            text_color=c["muted"])
        if not suggestions:
            empty_message = (
                "Aucune session Traktor archivée. Ferme Traktor après un set pour importer son historique."
                if self.software == "traktor" else
                "Pas encore de suggestion pour cette piste. Joue quelques morceaux puis actualise l'historique."
            )
            ctk.CTkLabel(self.cards, text=empty_message, text_color=c["muted"],
                         font=(FONT, 12), anchor="w", justify="left",
                         wraplength=400).pack(fill="x", padx=6, pady=16)
            return
        for rank, suggestion in enumerate(suggestions, 1):
            self._build_card(rank, suggestion)

    def _build_card(self, rank, suggestion):
        """Carte de suggestion : pochette, informations, anneau de score animé,
        jauge de compatibilité puis pastilles tempo / tonalité / habitude."""
        c = COLORS
        tier = c[suggestion.category]
        tier_bg = c[f"{suggestion.category}_dark"]
        relation = {
            "même tonalité": "MÊME CLÉ",
            "relative majeure/mineure": "RELATIVE",
            "voisine Camelot (+1/-1)": "±1",
            "voisine élargie (+2/-2)": "±2",
            "sous-dominante (quarte)": "QUARTE",
            "dominante / tonique (quinte)": "QUINTE",
            "tonalité parallèle (même tonique)": "PARALLÈLE",
            "quinte/tonique avec changement de mode": "QUINTE ± MODE",
            "quarte avec changement de mode": "QUARTE ± MODE",
            "tonalité éloignée": "LOINTAINE",
        }.get(suggestion.key_relation, "CAMELOT")

        card = ctk.CTkFrame(self.cards, fg_color=c["surface"], corner_radius=RADIUS_CARD,
                            border_width=1, border_color=c["border"])
        card.pack(fill="x", padx=2, pady=4)
        self._cards.append((card, tier))

        body = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
        body.pack(fill="x", padx=12, pady=(10, 0))

        cover_label = ctk.CTkLabel(body, text="HM", width=54, height=54,
                                   fg_color=c["surface_2"], text_color=tier,
                                   corner_radius=RADIUS_THUMB, font=(FONT_BOLD, 12))
        cover_label.pack(side="left", padx=(0, 11), anchor="n")
        self._request_cover(suggestion.path, cover_label, 54)

        info = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        info.pack(side="left", fill="x", expand=True)

        head = ctk.CTkFrame(info, fg_color="transparent", corner_radius=0)
        head.pack(fill="x")
        rank_label = ctk.CTkLabel(head, text=f"{rank:02}", text_color=tier,
                                  font=(FONT_BOLD, 9), anchor="w", width=16)
        rank_label.pack(side="left")
        tier_label = ctk.CTkLabel(head, text=TIER_LABELS.get(suggestion.category, "").upper(),
                                  text_color=tier, font=(FONT_BOLD, 9), anchor="w")
        tier_label.pack(side="left", padx=(7, 0))

        title_label = ctk.CTkLabel(info, text=suggestion.title, text_color=c["text"],
                                   font=(FONT_BOLD, 13), anchor="w", justify="left",
                                   wraplength=252)
        title_label.pack(fill="x", pady=(4, 0))
        artist_label = ctk.CTkLabel(info, text=suggestion.artist or "Artiste non renseigné",
                                    text_color=c["muted"], font=(FONT, 10), anchor="w",
                                    justify="left", wraplength=252)
        artist_label.pack(fill="x")

        score_label = ctk.CTkLabel(body, text="0", width=54, height=54,
                                   image=self._score_ring(0, tier), compound="center",
                                   fg_color="transparent", text_color=tier,
                                   font=(FONT_BOLD, 13))
        score_label.pack(side="right", anchor="n", padx=(8, 0))

        meter = ctk.CTkProgressBar(card, height=3, corner_radius=2,
                                   fg_color=c["progress_bg"], progress_color=tier)
        meter.pack(fill="x", padx=13, pady=(8, 0))
        meter.set(0)

        chips = []
        if suggestion.bpm:
            tempo = f"{suggestion.bpm:g} BPM"
            if suggestion.bpm_delta_pct is not None:
                tempo += f" · {suggestion.bpm_delta_pct:.1f}%"
            if suggestion.bpm_ratio != 1.0:
                tempo += " ×2" if suggestion.bpm_ratio == 2.0 else " ÷2"
            chips.append(("♪", tempo, c["surface_2"], c["text"]))
        if suggestion.camelot:
            chips.append(("◈", f"{suggestion.camelot} · {relation}",
                          c["surface_2"], c["violet"]))
        elif suggestion.key:
            chips.append(("◈", suggestion.key, c["surface_2"], c["violet"]))
        if suggestion.transition_count:
            chips.append(("↻", f"{suggestion.transition_count}× EN SET", tier_bg, tier))
        else:
            chips.append(("+", "JAMAIS ENCHAÎNÉE", tier_bg, tier))

        chip_canvas = tk.Canvas(card, height=26, bg=c["surface"], highlightthickness=0, bd=0)
        chip_canvas.pack(fill="x", padx=13, pady=(6, 10))

        def paint(_event=None, data=chips):
            try:
                width = chip_canvas.winfo_width()
            except tk.TclError:
                return
            if width <= 1:
                return
            chip_canvas.delete("all")
            self._paint_chips(chip_canvas, data, 2)

        chip_canvas.bind("<Configure>", paint)

        def select(_event=None, item=suggestion, selected=card, selected_tier=tier):
            self.reason_label.configure(text=item.reason, text_color=c["muted"])
            self.selected_suggestion = item
            self._set_search_state("normal")
            self.load_hint.configure(text=f"Prêt à chercher : {item.title}",
                                     text_color=c["text"])
            previous = self._selected
            self._selected = selected
            if previous is not None and previous is not selected:
                self._tween_card(previous, previous._hm_rest)
            self._tween_card(selected, selected_tier)
            self.load_hint.configure(
                text=f"Double-clique pour rechercher dans {self._software_name()}",
                text_color=c["muted"])

        def quick_search(_event=None, item=suggestion):
            answer = messagebox.askyesno(
                "Rechercher ce morceau ?",
                f"Lancer la recherche de « {item.title} » dans {self._software_name()} ?\n\n"
                "La piste ne sera pas chargée automatiquement : tu pourras vérifier le résultat "
                "puis choisir le deck.",
                parent=self.root)
            if answer:
                self.selected_suggestion = item
                self._set_search_state("disabled")
                self.on_search(item)

        card._hm_rest = c["border"]

        def enter(_event=None, frame=card):
            if frame is not self._selected:
                self._tween_card(frame, c["border_hover"])

        def leave(_event=None, frame=card):
            if frame is not self._selected:
                self._tween_card(frame, frame._hm_rest)

        for widget in (card, body, cover_label, info, head, rank_label, tier_label,
                       title_label, artist_label, score_label, chip_canvas):
            widget.bind("<Button-1>", select, add="+")
            widget.bind("<Double-Button-1>", quick_search, add="+")
            widget.bind("<Enter>", enter, add="+")
            widget.bind("<Leave>", leave, add="+")

        # Anneau, chiffre et jauge montent ensemble depuis zéro.
        self._animate_card({"kind": "ring", "label": score_label, "meter": meter,
                            "color": tier, "from": 0.0, "to": float(suggestion.score),
                            "frame": 0, "frames": 18})

    def _tween_card(self, card, target, steps=7):
        """Transition douce du contour de carte (survol et sélection)."""
        try:
            start = card.cget("border_color")
            if not isinstance(start, str) or not start.startswith("#"):
                card.configure(border_color=target)
                return
        except tk.TclError:
            return
        card._hm_tween = getattr(card, "_hm_tween", 0) + 1
        token = card._hm_tween

        def step(index):
            if getattr(card, "_hm_tween", None) != token or not card.winfo_exists():
                return
            eased = 1 - (1 - index / steps) ** 3
            try:
                card.configure(border_color=_blend(start, target, eased))
            except tk.TclError:
                return
            if index < steps:
                self.root.after(18, step, index + 1)
        step(1)

    # ------------------------------------------------------------------
    # Animations
    # ------------------------------------------------------------------
    def _animate_card(self, animation):
        """Programme une animation de carte (abandonnée si la carte disparaît)."""
        self.root.after(16, self._step_card_animation, animation)

    def _step_card_animation(self, animation):
        label = animation["label"]
        if not label.winfo_exists():
            return
        animation["frame"] += 1
        progress = min(1.0, animation["frame"] / animation["frames"])
        eased = 1 - (1 - progress) ** 3
        value = animation["from"] + (animation["to"] - animation["from"]) * eased
        try:
            label.configure(image=self._score_ring(value, animation["color"]),
                            text=f"{value:.0f}")
            animation["meter"].set(min(1.0, value / 100))
        except tk.TclError:
            return
        if progress < 1:
            self.root.after(16, self._step_card_animation, animation)
