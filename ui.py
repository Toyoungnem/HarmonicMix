"""Interface moderne du panneau Serato, séparée du contrôleur app.py.

Style « bento » : tuiles très arrondies teintées, grandes typographies,
palette douce. Toute la logique (callbacks, pochettes, recherche, stats)
est conservée ; seule l'apparence change.

Pour revenir à l'ancienne palette orange/bleu, mets THEME = "legacy".
"""
from __future__ import annotations

import customtkinter as ctk
import math
import tkinter as tk
from collections import Counter
from tkinter import messagebox
from pathlib import Path
import sys
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps

# Les clés gardent les mêmes noms dans les deux thèmes :
#   mint   = accent principal (marque, action principale)
#   violet = accent secondaire (infos, liens)
#   gold   = accent tertiaire (dashboard)
#   red / orange / yellow / blue = paliers de suggestion
THEMES = {
    "dusk": {
        "background": "#0E0D14", "surface": "#171620", "surface_2": "#201F2C",
        "surface_hover": "#2B2938", "border": "#2C2A3A", "border_hover": "#5A5678",
        "text": "#F0EEF7", "muted": "#A9A5BF", "dim": "#726E8A",
        "mint": "#8FE3C0", "mint_dark": "#1B3A32", "violet": "#B9A8FF",
        "violet_dark": "#2B2650", "magenta": "#E9A9EA", "magenta_dark": "#3C2742",
        "gold": "#F4CD8B", "gold_dark": "#3A2F20", "progress_bg": "#2B2938",
        "red": "#FF8F95", "red_dark": "#46262B",
        "orange": "#FFB27E", "orange_dark": "#432C1D",
        "yellow": "#F1DE8C", "yellow_dark": "#3A361B",
        "blue": "#8DCBFF", "blue_dark": "#1E3146",
    },
    "legacy": {
        "background": "#08090D", "surface": "#11141B", "surface_2": "#191D27",
        "surface_hover": "#222936", "border": "#292F3A", "border_hover": "#347EB3",
        "text": "#F3F6FB", "muted": "#9AA7B8", "dim": "#687487",
        "mint": "#FF7A1A", "mint_dark": "#3D210F", "violet": "#39A9FF",
        "violet_dark": "#122A40", "magenta": "#75C5FF", "magenta_dark": "#19334A",
        "gold": "#FFB04A", "gold_dark": "#3A2816", "progress_bg": "#252B36",
        "red": "#FF5263", "red_dark": "#421921",
        "orange": "#FF963D", "orange_dark": "#402514",
        "yellow": "#FFD166", "yellow_dark": "#403516",
        "blue": "#43B8FF", "blue_dark": "#122B3E",
    },
}
THEME = "dusk"
COLORS = THEMES[THEME]

FONT = "Segoe UI"
FONT_BOLD = "Segoe UI Semibold"
FONT_LIGHT = "Segoe UI Light"
APP_VERSION = "2.0.0"
ctk.set_appearance_mode("dark")

# Échelle de rayons commune : tout est très arrondi, avec la même logique.
RADIUS_TILE = 30      # grandes tuiles
RADIUS_CARD = 26      # cartes de suggestion
RADIUS_ROW = 20       # lignes de liste
RADIUS_THUMB = 16     # pochettes


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _blend(start, end, amount):
    """Mélange deux couleurs hexadécimales (0 = start, 1 = end)."""
    a, b = _hex_to_rgb(start), _hex_to_rgb(end)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


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
        self.profile_name = profile_name
        self.software = software
        self.topmost = True
        self._selected = None
        self.selected_suggestion = None
        self._cards = []
        self.root.title("Harmonic Mix")
        self.root.configure(fg_color=COLORS["background"])
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)
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
    # Accueil
    # ------------------------------------------------------------------
    def _build_home(self):
        c = COLORS
        shell = ctk.CTkScrollableFrame(
            self.home_page, fg_color=c["background"], corner_radius=0,
            scrollbar_fg_color=c["background"], scrollbar_button_color=c["border"],
            scrollbar_button_hover_color=c["violet"])
        shell.pack(fill="both", expand=True, padx=18, pady=14)

        # Barre du haut : logo rond, nom, profil
        top = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        top.pack(fill="x", pady=(2, 18))
        mark = ctk.CTkFrame(top, width=46, height=46, fg_color=c["surface_2"],
                            corner_radius=23)
        mark.pack(side="left")
        mark.pack_propagate(False)
        logo_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "HarmonicMix.png"
        try:
            logo = Image.open(logo_path).convert("RGBA")
            self.logo_image = ctk.CTkImage(light_image=logo, dark_image=logo, size=(36, 36))
            ctk.CTkLabel(mark, text="", image=self.logo_image).pack(expand=True)
        except OSError:
            ctk.CTkLabel(mark, text="HM", text_color=c["mint"],
                         font=(FONT_BOLD, 14)).pack(expand=True)
        brand = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
        brand.pack(side="left", padx=12, fill="y")
        ctk.CTkLabel(brand, text="Harmonic Mix", text_color=c["text"],
                     font=(FONT_BOLD, 16), anchor="w").pack(anchor="w", pady=(3, 0))
        self.home_software_caption = ctk.CTkLabel(
            brand, text="Compagnon de mix", text_color=c["muted"],
            font=(FONT, 11), anchor="w")
        self.home_software_caption.pack(anchor="w")
        self.home_profile_button = ctk.CTkButton(
            top, text=f"{self.profile_name}  ▾",
            command=self.on_profile_select, width=104, height=38,
            corner_radius=19, fg_color=c["surface_2"],
            hover_color=c["surface_hover"], text_color=c["text"],
            font=(FONT_BOLD, 12), border_width=0)
        self.home_profile_button.pack(side="right", anchor="n")

        # Grande tuile de salutation
        hero = ctk.CTkFrame(shell, fg_color=c["mint_dark"], corner_radius=RADIUS_TILE)
        hero.pack(fill="x", pady=(0, 16))
        hero_body = ctk.CTkFrame(hero, fg_color="transparent", corner_radius=0)
        hero_body.pack(fill="both", expand=True, padx=26, pady=(24, 26))
        username = self.profile_name
        ctk.CTkLabel(hero_body, text="Bonjour,", text_color=c["mint"],
                     font=(FONT_BOLD, 15), anchor="w").pack(anchor="w")
        self.home_username_label = ctk.CTkLabel(
            hero_body, text=username, text_color=c["text"],
            font=(FONT_LIGHT, 46), anchor="w")
        self.home_username_label.pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            hero_body, text="Ton compagnon de mix pour trouver le morceau qui s'enchaîne naturellement.",
            text_color=_blend(c["text"], c["mint_dark"], 0.35), font=(FONT, 12),
            justify="left", anchor="w", wraplength=320).pack(fill="x", pady=(6, 0))

        # Étape 1 : choix du logiciel, en deux grandes tuiles
        ctk.CTkLabel(shell, text="1  ·  Choisis ton espace",
                     text_color=c["muted"], font=(FONT_BOLD, 12), anchor="w").pack(
                         anchor="w", padx=6, pady=(0, 8))
        software_row = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        software_row.pack(fill="x", pady=(0, 10))
        self.software_buttons = {}
        for software_id, label, accent_color in (
            ("serato", "Serato DJ", c["mint"]),
            ("traktor", "Traktor", c["violet"]),
        ):
            button = ctk.CTkButton(
                software_row, text=label,
                command=lambda selected=software_id: self.on_software_select(selected),
                height=88, corner_radius=RADIUS_CARD, fg_color=c["surface_2"],
                hover_color=c["surface_hover"], text_color=accent_color,
                font=(FONT_BOLD, 16), border_width=2, border_color=c["surface_2"])
            button.pack(side="left", fill="x", expand=True, padx=(0 if software_id == "serato" else 5,
                                                                   5 if software_id == "serato" else 0))
            self.software_buttons[software_id] = button
        self.dashboard_choice_button = ctk.CTkButton(
            shell, text="Dashboard   ›", command=self.on_stats,
            height=60, corner_radius=RADIUS_CARD, fg_color=c["gold_dark"],
            hover_color=_blend(c["gold_dark"], c["gold"], 0.2), text_color=c["gold"],
            font=(FONT_BOLD, 15), border_width=0)
        self.dashboard_choice_button.pack(fill="x", pady=(0, 16))
        self._update_software_buttons()

        # Dernière session
        self.home_status_card = ctk.CTkFrame(
            shell, fg_color=c["surface"], corner_radius=RADIUS_TILE)
        self.home_status_card.pack(fill="x", pady=(0, 18))
        self.home_status_label = ctk.CTkLabel(
            self.home_status_card, text="Dernière session",
            text_color=c["violet"], font=(FONT_BOLD, 12), anchor="w")
        self.home_status_label.pack(anchor="w", padx=24, pady=(20, 6))
        self.home_track_label = ctk.CTkLabel(
            self.home_status_card, text="Aucune session détectée", text_color=c["text"],
            font=(FONT_BOLD, 21), anchor="w", justify="left", wraplength=330)
        self.home_track_label.pack(fill="x", padx=24)
        self.home_detail_label = ctk.CTkLabel(
            self.home_status_card, text="Choisis Serato DJ ou Traktor ci-dessus",
            text_color=c["muted"], font=(FONT, 12), anchor="w", justify="left",
            wraplength=330)
        self.home_detail_label.pack(fill="x", padx=24, pady=(4, 20))

        # Étape 2 : action principale
        self.home_open_button = ctk.CTkButton(
            shell, text="2  ·  Découvrir mes suggestions   →", command=self.show_dashboard,
            height=64, corner_radius=32, fg_color=c["mint"],
            hover_color=_blend(c["mint"], "#FFFFFF", 0.18),
            text_color=c["background"], font=(FONT_BOLD, 15), border_width=0)
        self.home_open_button.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            shell, text="Choisis une piste, puis cherche-la dans ton logiciel DJ.",
            text_color=c["dim"], font=(FONT, 11), anchor="center").pack(fill="x")

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------
    def _build_dashboard(self):
        c = COLORS
        shell = ctk.CTkFrame(self.dashboard_page, fg_color=c["background"], corner_radius=0)
        shell.pack(fill="both", expand=True, padx=18, pady=14)

        header = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", pady=(0, 10))
        brand = ctk.CTkFrame(header, fg_color="transparent", corner_radius=0)
        brand.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(brand, text="Harmonic Mix", text_color=c["text"],
                     font=(FONT_BOLD, 18), anchor="w").pack(anchor="w")
        ctk.CTkLabel(brand, text="La prochaine piste, en harmonie avec ton set",
                     text_color=c["muted"], font=(FONT, 11), anchor="w").pack(
                         anchor="w", pady=(1, 0))
        self.pin_button = ctk.CTkButton(
            header, text="●  Épinglé", command=self.toggle_topmost, width=104,
            height=36, corner_radius=18, fg_color=c["mint_dark"],
            hover_color=c["surface_hover"], text_color=c["mint"], font=(FONT_BOLD, 11),
            border_width=0)
        self.pin_button.pack(side="right", anchor="n")

        # Morceau en cours : tuile mise en avant
        now = ctk.CTkFrame(shell, fg_color=c["surface_2"], corner_radius=RADIUS_TILE,
                           height=100)
        now.pack(fill="x", pady=(0, 10))
        now.pack_propagate(False)
        self.current_cover_label = ctk.CTkLabel(
            now, text="HM", width=68, height=68, fg_color=c["surface"],
            text_color=c["violet"], corner_radius=RADIUS_THUMB + 2, font=(FONT_BOLD, 15))
        self.current_cover_label.pack(side="left", padx=(16, 0), pady=16)
        current = ctk.CTkFrame(now, fg_color="transparent", corner_radius=0)
        current.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        current_header = ctk.CTkFrame(current, fg_color="transparent", corner_radius=0)
        current_header.pack(fill="x")
        self.current_section_label = ctk.CTkLabel(
            current_header, text="Dernière piste", text_color=c["muted"],
            font=(FONT_BOLD, 11), anchor="w")
        self.current_section_label.pack(side="left")
        self.status_label = ctk.CTkLabel(current_header, text="", text_color=c["mint"],
                                         font=(FONT_BOLD, 10), anchor="e")
        self.status_label.pack(side="right")
        self.current_label = ctk.CTkLabel(
            current, text="En attente de Serato", text_color=c["text"],
            font=(FONT_BOLD, 18), anchor="w", justify="left", wraplength=250)
        self.current_label.pack(fill="x", pady=(4, 1))
        self.detail_label = ctk.CTkLabel(
            current, text="", text_color=c["muted"], font=(FONT, 11),
            anchor="w", justify="left", wraplength=250)
        self.detail_label.pack(fill="x")

        section = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        section.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(section, text="Meilleures suggestions", text_color=c["text"],
                     font=(FONT_BOLD, 15), anchor="w").pack(side="left", padx=(4, 0))
        self.home_button = ctk.CTkButton(
            section, text="⌂", command=self.show_home, width=38, height=38,
            corner_radius=19, fg_color=c["surface_2"], hover_color=c["surface_hover"],
            text_color=c["text"], font=(FONT_BOLD, 16), border_width=0)
        self.home_button.pack(side="right", padx=(6, 0))
        self.refresh_button = ctk.CTkButton(
            section, text="↻", command=self.on_refresh, width=38, height=38,
            corner_radius=19, fg_color=c["surface_2"], hover_color=c["surface_hover"],
            text_color=c["text"], font=(FONT_BOLD, 16), border_width=0)
        self.refresh_button.pack(side="right")

        self.cards = ctk.CTkScrollableFrame(
            shell, fg_color="transparent", corner_radius=0, height=60,
            scrollbar_fg_color=c["background"], scrollbar_button_color=c["border"],
            scrollbar_button_hover_color=c["violet"])
        self.cards.pack(fill="both", expand=True)

        # Action de recherche
        self.load_bar = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        self.load_hint = ctk.CTkLabel(
            self.load_bar, text="Sélectionne un morceau pour le rechercher dans Serato",
            text_color=c["muted"], font=(FONT, 11), anchor="w")
        self.load_hint.pack(fill="x", padx=4, pady=(0, 4))
        self.search_button = ctk.CTkButton(
            self.load_bar, text="⌕  Chercher dans Serato", state="disabled",
            command=self._search_selected, height=44, corner_radius=22,
            fg_color=c["surface_2"], hover_color=_blend(c["mint"], "#FFFFFF", 0.18),
            text_color=c["dim"], text_color_disabled=c["dim"],
            font=(FONT_BOLD, 13), border_width=0)
        self.search_button.pack(fill="x")

        # Explication de la suggestion choisie
        self.reason_box = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=RADIUS_ROW)
        ctk.CTkLabel(self.reason_box, text="Pourquoi cette piste", text_color=c["violet"],
                     font=(FONT_BOLD, 10), anchor="w").pack(fill="x", padx=18, pady=(10, 0))
        self.reason_label = ctk.CTkLabel(
            self.reason_box, text="Sélectionne une suggestion pour voir pourquoi elle est proposée",
            text_color=c["muted"], font=(FONT, 11), anchor="w", justify="left",
            wraplength=340)
        self.reason_label.pack(fill="x", padx=18, pady=(1, 10))

        # Légende des couleurs
        footer = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        legend = (("Rouge", "très jouées", c["red"]),
                  ("Orange", "répétées", c["orange"]),
                  ("Jaune", "rares", c["yellow"]),
                  ("Bleu", "jamais · théorie", c["blue"]))
        for index, (name, meaning, color) in enumerate(legend):
            cell = ctk.CTkFrame(footer, fg_color="transparent", corner_radius=0)
            cell.grid(row=0, column=index, sticky="ew", padx=(4 if index == 0 else 4, 4), pady=2)
            ctk.CTkLabel(cell, text=f"●  {name}", text_color=color,
                         font=(FONT_BOLD, 11), anchor="w").pack(anchor="w")
            ctk.CTkLabel(cell, text=meaning, text_color=c["muted"],
                         font=(FONT, 10), anchor="w").pack(anchor="w")
            footer.grid_columnconfigure(index, weight=1)

        # Les blocs du bas restent toujours visibles : la liste de cartes
        # prend uniquement la place restante (et défile si besoin).
        self.cards.pack_forget()
        footer.pack(side="bottom", fill="x", pady=(4, 0))
        self.reason_box.pack(side="bottom", fill="x", pady=(6, 6))
        self.load_bar.pack(side="bottom", fill="x", pady=(6, 0))
        self.cards.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Dashboard / statistiques
    # ------------------------------------------------------------------
    def _build_stats(self):
        c = COLORS
        shell = ctk.CTkFrame(self.stats_page, fg_color=c["background"], corner_radius=0)
        shell.pack(fill="both", expand=True, padx=40, pady=30)

        header = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", pady=(0, 24))
        heading = ctk.CTkFrame(header, fg_color="transparent", corner_radius=0)
        heading.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(heading, text=f"Harmonic Mix  /  Dashboard  ·  v{APP_VERSION}",
                     text_color=c["text"], font=(FONT_LIGHT, 28), anchor="w").pack(anchor="w")
        ctk.CTkLabel(heading, text="Analyse de tes sets et de l'évolution de tes styles musicaux",
                     text_color=c["muted"], font=(FONT, 13), anchor="w").pack(anchor="w", pady=(4, 0))
        self.stats_software_label = ctk.CTkLabel(
            header, text="SERATO DJ", text_color=c["mint"], fg_color=c["mint_dark"],
            corner_radius=15, height=30, width=104, font=(FONT_BOLD, 11), anchor="center")
        self.stats_software_label.pack(side="right", padx=(10, 16))
        ctk.CTkLabel(
            header, text="●  Mise à jour auto · 5 s", text_color=c["muted"],
            font=(FONT_BOLD, 11), anchor="e").pack(side="right", padx=(0, 14))
        ctk.CTkButton(
            header, text="←  Accueil", command=self.show_home, height=44,
            corner_radius=22, fg_color=c["surface_2"], hover_color=c["surface_hover"],
            text_color=c["text"], font=(FONT_BOLD, 12), border_width=0).pack(side="right")

        body = ctk.CTkScrollableFrame(
            shell, fg_color="transparent", corner_radius=0,
            scrollbar_fg_color=c["background"], scrollbar_button_color=c["border"],
            scrollbar_button_hover_color=c["violet"])
        body.pack(fill="both", expand=True)

        # Quatre tuiles chiffrées, chacune teintée à la couleur de son accent
        kpi_row = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        kpi_row.pack(fill="x", pady=(0, 14))
        self.stats_kpi_values = {}
        for index, (key, title, accent, tile) in enumerate((
            ("sessions", "Sets analysés", c["violet"], c["violet_dark"]),
            ("tracks", "Morceaux joués", c["mint"], c["mint_dark"]),
            ("transition_count", "Transitions rejouées", c["gold"], c["gold_dark"]),
            ("distinct_transitions", "Enchaînements distincts", c["blue"], c["blue_dark"]),
        )):
            card = ctk.CTkFrame(kpi_row, fg_color=tile, corner_radius=RADIUS_TILE)
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 10, 0))
            kpi_row.grid_columnconfigure(index, weight=1, uniform="kpi")
            ctk.CTkLabel(card, text=title, text_color=_blend(accent, tile, 0.25),
                         font=(FONT_BOLD, 11), anchor="w").pack(anchor="w", padx=20, pady=(18, 2))
            icon = tk.Canvas(card, width=34, height=34, bg=tile,
                             highlightthickness=0, bd=0)
            icon.place(relx=1.0, x=-18, y=16, anchor="ne")
            self._draw_kpi_icon(icon, key, accent, tile)
            value = ctk.CTkLabel(card, text="—", text_color=accent,
                                 font=(FONT_LIGHT, 38), anchor="w")
            value.pack(anchor="w", padx=20, pady=(0, 18))
            self.stats_kpi_values[key] = value

        analytics = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        analytics.pack(fill="both", expand=True)
        analytics.grid_columnconfigure(0, weight=7, uniform="analytics")
        analytics.grid_columnconfigure(1, weight=4, uniform="analytics")
        transitions_card = ctk.CTkFrame(
            analytics, fg_color=c["surface"], corner_radius=RADIUS_TILE)
        transitions_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(transitions_card, text="Enchaînements les plus fréquents",
                     text_color=c["text"], font=(FONT_BOLD, 15), anchor="w").pack(
                         anchor="w", padx=24, pady=(20, 8))
        self.stats_transitions_list = ctk.CTkScrollableFrame(
            transitions_card, fg_color="transparent", corner_radius=0,
            scrollbar_fg_color=c["surface"], scrollbar_button_color=c["border"],
            scrollbar_button_hover_color=c["violet"])
        self.stats_transitions_list.pack(fill="both", expand=True, padx=12, pady=(0, 14))

        destinations_card = ctk.CTkFrame(
            analytics, fg_color=c["surface"], corner_radius=RADIUS_TILE)
        destinations_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(destinations_card, text="Pistes les plus souvent enchaînées",
                     text_color=c["text"], font=(FONT_BOLD, 15), anchor="w",
                     wraplength=340, justify="left").pack(anchor="w", padx=24, pady=(20, 8))
        self.stats_destinations_list = ctk.CTkScrollableFrame(
            destinations_card, fg_color="transparent", corner_radius=0,
            scrollbar_fg_color=c["surface"], scrollbar_button_color=c["border"],
            scrollbar_button_hover_color=c["violet"])
        self.stats_destinations_list.pack(fill="both", expand=True, padx=12, pady=(0, 14))

        trend_card = ctk.CTkFrame(body, fg_color=c["surface"], corner_radius=RADIUS_TILE)
        trend_card.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(trend_card, text="Styles musicaux au fil des sets",
                     text_color=c["text"], font=(FONT_BOLD, 15), anchor="w").pack(
                         anchor="w", padx=24, pady=(20, 0))
        ctk.CTkLabel(trend_card,
                     text="Évolution des genres par set · titres, transitions et BPM moyen à droite.",
                     text_color=c["muted"], font=(FONT, 11), anchor="w").pack(
                         anchor="w", padx=24, pady=(3, 0))
        self.stats_genre_chart = tk.Canvas(
            trend_card, height=430, bg=c["surface"], highlightthickness=0, bd=0)
        self.stats_genre_chart.pack(fill="x", padx=20, pady=(2, 16))

        self.stats_footer = ctk.CTkLabel(
            body, text="Les statistiques sont calculées localement depuis ton historique.",
            text_color=c["dim"], font=(FONT, 11), anchor="w")
        self.stats_footer.pack(fill="x", pady=(16, 0))

    def _render_stats(self, stats):
        c = COLORS
        self.stats_software_label.configure(text=stats["software"].upper())
        for key, label in self.stats_kpi_values.items():
            value = int(stats[key])
            label.configure(text=self._format_metric(value),
                            font=(FONT_LIGHT, 38 if value < 100_000 else 30 if value < 10_000_000 else 24))
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
            line = ctk.CTkFrame(self.stats_transitions_list,
                                fg_color=c["surface_2"], corner_radius=RADIUS_ROW)
            line.pack(fill="x", padx=3, pady=4)
            ctk.CTkLabel(line, text=f"{rank:02}", width=32, height=32,
                         corner_radius=16, fg_color=c["violet_dark"],
                         text_color=c["violet"], font=(FONT_BOLD, 10)).pack(
                             side="left", padx=12, pady=9)
            source_cover = ctk.CTkLabel(
                line, text="HM", width=38, height=38, fg_color=c["surface"],
                text_color=c["violet"], corner_radius=RADIUS_THUMB - 5, font=(FONT_BOLD, 9))
            source_cover.pack(side="left", padx=(0, 4), pady=7)
            self._request_cover(row["source_path"], source_cover, 38)
            target_cover = ctk.CTkLabel(
                line, text="HM", width=38, height=38, fg_color=c["surface"],
                text_color=c["mint"], corner_radius=RADIUS_THUMB - 5, font=(FONT_BOLD, 9))
            target_cover.pack(side="left", padx=(0, 8), pady=7)
            self._request_cover(row["target_path"], target_cover, 38)
            text_frame = ctk.CTkFrame(line, fg_color="transparent", corner_radius=0)
            text_frame.pack(side="left", fill="x", expand=True, padx=(2, 8), pady=8)
            source = row["source_title"] or Path(row["source_path"]).stem
            target = row["target_title"] or Path(row["target_path"]).stem
            ctk.CTkLabel(text_frame, text=f"{source}  →  {target}",
                         text_color=c["text"], font=(FONT_BOLD, 12), anchor="w",
                         justify="left", wraplength=520).pack(fill="x")
            ctk.CTkLabel(line, text=self._format_compact(row["count"]), width=62,
                         text_color=c["mint"], font=(FONT_BOLD, 14)).pack(side="right", padx=16)

        destinations = stats["destinations"]
        if not destinations:
            ctk.CTkLabel(self.stats_destinations_list, text="Pas encore assez de sets.",
                         text_color=c["muted"], font=(FONT, 12), anchor="w").pack(
                             fill="x", padx=10, pady=16)
        for rank, item in enumerate(destinations, 1):
            row = ctk.CTkFrame(self.stats_destinations_list,
                               fg_color=c["surface_2"], corner_radius=RADIUS_ROW)
            row.pack(fill="x", padx=3, pady=4)
            ctk.CTkLabel(row, text=f"{rank:02}", width=32, height=32,
                         corner_radius=16, fg_color=c["mint_dark"],
                         text_color=c["mint"], font=(FONT_BOLD, 9)).pack(
                             side="left", padx=12, pady=9)
            cover_label = ctk.CTkLabel(
                row, text="HM", width=40, height=40, fg_color=c["surface"],
                text_color=c["violet"], corner_radius=RADIUS_THUMB - 5, font=(FONT_BOLD, 9))
            cover_label.pack(side="left", padx=(0, 8), pady=7)
            self._request_cover(item.get("path"), cover_label, 40)
            ctk.CTkLabel(row, text=item["title"], text_color=c["text"],
                         font=(FONT_BOLD, 12), anchor="w", justify="left",
                         wraplength=260).pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=self._format_compact(item["count"]), width=58,
                         text_color=c["mint"], font=(FONT_BOLD, 13)).pack(side="right", padx=14)

        state = "session en cours" if stats["active_session"] else "dernière session archivée"
        self.stats_footer.configure(
            text=f"Source : {stats['software']}  ·  Dernier set : {stats['last_session']}  ·  {state}  ·  Échap pour revenir")
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
        cache_key = (key, size)
        if cache_key in self._cover_cache:
            return self._cover_cache[cache_key]
        try:
            with Image.open(BytesIO(image_data)) as cover:
                contained = ImageOps.contain(
                    cover.convert("RGBA"), (size * 2, size * 2),
                    method=Image.Resampling.LANCZOS)
            fitted = Image.new("RGBA", (size * 2, size * 2), COLORS["surface_2"])
            fitted.alpha_composite(contained, (
                (fitted.width - contained.width) // 2,
                (fitted.height - contained.height) // 2))
            mask = Image.new("L", fitted.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, fitted.width - 1, fitted.height - 1),
                radius=max(8, size // 3), fill=255)
            fitted.putalpha(mask)
            image = ctk.CTkImage(light_image=fitted, dark_image=fitted, size=(size, size))
            self._cover_cache[cache_key] = image
            return image
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Graphiques
    # ------------------------------------------------------------------
    def _score_ring(self, score, color, size=56, thickness=5):
        """Anneau de score lissé (dessiné en haute résolution puis réduit)."""
        key = (round(max(0, min(100, score))), color, size)
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
        draw.ellipse(box, outline=_blend(COLORS["background"], color, 0.18), width=stroke)
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
            canvas.create_rectangle(6, 7, 28, 28, outline=color, width=2)
            canvas.create_line(6, 13, 28, 13, fill=color, width=2)
            canvas.create_line(12, 4, 12, 10, fill=color, width=2)
            canvas.create_line(22, 4, 22, 10, fill=color, width=2)
            canvas.create_oval(12, 18, 15, 21, fill=color, outline=color)
            canvas.create_oval(20, 18, 23, 21, fill=color, outline=color)
        elif kind == "tracks":
            canvas.create_oval(4, 4, 30, 30, outline=color, width=2)
            canvas.create_oval(10, 10, 24, 24, outline=color, width=2)
            canvas.create_oval(15, 15, 19, 19, fill=color, outline=color)
        elif kind == "transition_count":
            canvas.create_line(5, 10, 26, 10, fill=color, width=2, arrow="last")
            canvas.create_line(28, 23, 7, 23, fill=color, width=2, arrow="last")
            canvas.create_line(9, 16, 24, 16, fill=color, width=2, arrow="last")
        else:
            canvas.create_line(8, 8, 25, 25, fill=color, width=2)
            canvas.create_line(8, 25, 25, 8, fill=color, width=2)
            for x, y in ((8, 8), (25, 25), (8, 25), (25, 8)):
                canvas.create_oval(x - 3, y - 3, x + 3, y + 3,
                                   fill=background, outline=color, width=2)

    def _draw_stats_charts(self):
        if not hasattr(self, "_stats_data"):
            return
        stats = self._stats_data
        self._draw_genre_timeline(self.stats_genre_chart, stats.get("session_activity", []))

    def _draw_genre_timeline(self, canvas, sessions):
        c = COLORS
        canvas.delete("all")
        self._stats_animation_generation = getattr(self, "_stats_animation_generation", 0) + 1
        generation = self._stats_animation_generation
        width = max(canvas.winfo_width(), 520)
        data = sessions[-12:]
        if not data:
            canvas.create_text(18, 36, text="Les styles apparaîtront dès qu'un set avec des tags de genre sera analysé.",
                               fill=c["muted"], anchor="w", font=(FONT, 11))
            return
        colors = [c["mint"], c["violet"], c["gold"], c["blue"], c["red"]]
        totals = Counter()
        for session in data:
            totals.update({name: int(count) for name, count in session.get("genres", {}).items()})
        top_genres = [name for name, _ in totals.most_common(4)]
        categories = top_genres + ["Autres / sans tag"]
        palette = colors[:len(top_genres)] + [c["border_hover"]]
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
            genre_counts = {name: int(count) for name, count in session.get("genres", {}).items()}
            track_count = max(0, int(session.get("tracks", 0)))
            selected = [genre_counts.get(name, 0) for name in top_genres]
            known_total = sum(genre_counts.values())
            other_total = max(0, track_count - min(track_count, known_total))
            other_total += sum(count for name, count in genre_counts.items() if name not in top_genres)
            segments = selected + [other_total]
            segment_total = sum(segments)
            if segment_total:
                x = chart_x
                for segment, color in zip(segments, palette):
                    if segment <= 0:
                        continue
                    segment_width = chart_width * segment / segment_total
                    item = canvas.create_rectangle(x, y, x, y + 16,
                                                   fill=color, outline=c["surface"])
                    animated_bars.append((item, x, x + segment_width, y))
                    x += segment_width
            else:
                canvas.create_text(chart_x + 4, y + 8, text="Genres non renseignés",
                                   fill=c["muted"], anchor="w", font=(FONT, 8))
            avg_bpm = session.get("average_bpm")
            bpm_text = f" · {avg_bpm:g} BPM" if avg_bpm else ""
            track_text = f"{self._compact_number(track_count)} titres"
            transition_text = f"{self._compact_number(session.get('transitions', 0))} trans."
            canvas.create_text(width - 6, y + 8,
                               text=f"{track_text} · {transition_text}{bpm_text}",
                               fill=c["muted"], anchor="e", font=(FONT, 8))

        # Anime les segments sans effacer/redessiner le canvas à chaque image.
        self._animate_stats_bars(animated_bars, generation, 0)

    def _animate_stats_bars(self, bars, generation, frame):
        if generation != getattr(self, "_stats_animation_generation", None):
            return
        progress = min(1.0, frame / 12)
        # Courbe ease-out : arrivée rapide puis ralentissement en douceur.
        eased = 1 - (1 - progress) ** 3
        for item, start_x, end_x, y in bars:
            self.stats_genre_chart.coords(item, start_x, y, start_x + (end_x - start_x) * eased, y + 16)
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
        # S'aligne sur la zone bibliothèque en bas à droite de Serato :
        # on laisse les decks et les waveforms visibles au-dessus.
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
        for button in (self.pin_button,):
            button.configure(
                text="●  Épinglé" if self.topmost else "○  Libre",
                fg_color=c["mint_dark"] if self.topmost else c["surface_2"],
                hover_color=c["surface_hover"],
                text_color=c["mint"] if self.topmost else c["muted"])

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

    def toggle_stats_fullscreen(self):
        if getattr(self, "active_page", "home") == "stats":
            current = self.root.attributes("-fullscreen") in (True, 1, "1", "true")
            self.root.attributes("-fullscreen", not current)

    def set_profile(self, name):
        self.profile_name = name
        self.home_profile_button.configure(text=f"{name}  ▾")
        self.home_username_label.configure(text=name)
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
            text=f"2  ·  Découvrir mes suggestions {label}   →")

    def _update_software_buttons(self):
        c = COLORS
        for software_id, button in self.software_buttons.items():
            selected = software_id == self.software
            accent = c["mint"] if software_id == "serato" else c["violet"]
            accent_bg = c["mint_dark"] if software_id == "serato" else c["violet_dark"]
            button.configure(
                fg_color=accent_bg if selected else c["surface_2"],
                text_color=accent if selected else c["muted"],
                border_color=accent if selected else c["surface_2"])

    def show_error(self, message):
        self.status_label.configure(text="● Erreur", text_color=COLORS["gold"])
        self.reason_label.configure(text=message)

    # ------------------------------------------------------------------
    # Recherche dans le logiciel DJ
    # ------------------------------------------------------------------
    def _set_search_state(self, state):
        """Active/désactive le bouton de recherche et adapte son apparence."""
        c = COLORS
        enabled = state == "normal"
        self.search_button.configure(
            state=state,
            fg_color=c["mint"] if enabled else c["surface_2"],
            text_color=c["background"] if enabled else c["dim"])

    def _search_selected(self):
        if self.selected_suggestion is not None:
            self._set_search_state("disabled")
            self.load_hint.configure(text=f"Recherche progressive dans {self._software_name()}…",
                                     text_color=COLORS["violet"])
            self.on_search(self.selected_suggestion)

    def show_search_result(self, message, success=True, busy=False, pause_refresh=False):
        color = COLORS["mint"] if success else COLORS["gold"]
        self.load_hint.configure(text=message, text_color=color)
        self._set_search_state(
            "disabled" if busy else
            ("normal" if self.selected_suggestion is not None else "disabled"))
        self.refresh_button.configure(
            state="disabled" if busy or pause_refresh else "normal")

    # ------------------------------------------------------------------
    # Rendu principal
    # ------------------------------------------------------------------
    def render(self, title, detail, status, status_color, suggestions,
               session_date="", session_detail="", cover_path=None):
        is_playing = "EN DIRECT" in status or status == "● SERATO"
        self.current_label.configure(text=title)
        self.detail_label.configure(text=detail)
        self.home_track_label.configure(text=session_date or "Aucune session détectée")
        self.home_detail_label.configure(text=session_detail or "Choisis Serato DJ ou Traktor ci-dessus")
        self.home_status_label.configure(text="Dernière session", text_color=status_color)
        self.current_section_label.configure(
            text="En cours" if is_playing else "Dernière session",
            text_color=COLORS["mint"] if is_playing else COLORS["muted"])
        self.status_label.configure(text=status, text_color=status_color)
        self._request_cover(cover_path, self.current_cover_label, 68)
        self._render_cards(suggestions)

    def _set_border(self, frame, color):
        """Change le contour tout de suite (et annule une transition en cours)."""
        frame._hm_tween = getattr(frame, "_hm_tween", 0) + 1
        try:
            frame.configure(border_color=color)
        except tk.TclError:
            pass

    def _tween_border(self, frame, target, steps=6):
        """Transition douce de la couleur du contour (survol des cartes)."""
        try:
            start = frame.cget("border_color")
            if not isinstance(start, str) or not start.startswith("#"):
                self._set_border(frame, target)
                return
        except tk.TclError:
            return
        frame._hm_tween = getattr(frame, "_hm_tween", 0) + 1
        token = frame._hm_tween

        def step(index):
            if getattr(frame, "_hm_tween", None) != token:
                return
            try:
                frame.configure(border_color=_blend(start, target, index / steps))
            except tk.TclError:
                return
            if index < steps:
                self.root.after(14, step, index + 1)
        step(1)

    def _render_cards(self, suggestions):
        c = COLORS
        for child in self.cards.winfo_children():
            child.destroy()
        self._cards = []
        self._selected = None
        self.selected_suggestion = None
        self._set_search_state("disabled")
        self.load_hint.configure(text=f"Sélectionne un morceau pour le rechercher dans {self._software_name()}",
                                 text_color=c["muted"])
        if not suggestions:
            empty_message = (
                "Aucune session Traktor archivée. Ferme Traktor après un set pour importer son historique."
                if self.software == "traktor" else
                "Pas encore de suggestion pour cette piste. Joue quelques morceaux puis actualise l'historique."
            )
            ctk.CTkLabel(self.cards, text=empty_message,
                         text_color=c["muted"], font=(FONT, 12), anchor="w",
                         justify="left", wraplength=410).pack(
                             fill="x", padx=6, pady=16)
            return

        for rank, suggestion in enumerate(suggestions, 1):
            tier = c[suggestion.category]
            tier_bg = c[f"{suggestion.category}_dark"]
            # Chaque carte est teintée de la couleur de son palier : on lit
            # la fréquence d'un coup d'œil, sans légende.
            tint = _blend(c["surface"], tier_bg, 0.55)
            chip_bg = _blend(tint, c["background"], 0.45)

            card = ctk.CTkFrame(self.cards, fg_color=tint, corner_radius=RADIUS_CARD,
                                border_width=2, border_color=tint)
            card.pack(fill="x", padx=2, pady=5)
            self._cards.append((card, tier))
            top = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
            top.pack(fill="x", padx=16, pady=(16, 0))

            rank_label = ctk.CTkLabel(top, text=f"{rank:02}", width=22, height=22,
                                      corner_radius=8, fg_color="transparent",
                                      text_color=_blend(tint, tier, 0.55), font=(FONT_BOLD, 11))
            rank_label.pack(side="left", anchor="n", padx=(0, 6), pady=(2, 0))
            cover_label = ctk.CTkLabel(
                top, text="HM", width=58, height=58, fg_color=chip_bg,
                text_color=c["violet"], corner_radius=RADIUS_THUMB, font=(FONT_BOLD, 12))
            cover_label.pack(side="left", padx=(0, 12), anchor="n")
            self._request_cover(suggestion.path, cover_label, 58)
            score_label = ctk.CTkLabel(
                top, text=f"{suggestion.score:.0f}", width=56, height=56,
                image=self._score_ring(suggestion.score, tier), compound="center",
                fg_color="transparent", text_color=tier, font=(FONT_BOLD, 13))
            score_label.pack(side="right", anchor="n", padx=(8, 0))
            names = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
            names.pack(side="left", fill="x", expand=True)
            title_label = ctk.CTkLabel(
                names, text=suggestion.title, text_color=c["text"],
                font=(FONT_BOLD, 14), anchor="w", justify="left", wraplength=185)
            title_label.pack(fill="x", pady=(3, 0))
            artist_label = ctk.CTkLabel(
                names, text=suggestion.artist or "Artiste non renseigné",
                text_color=_blend(c["muted"], tint, 0.15), font=(FONT, 11), anchor="w",
                justify="left", wraplength=185)
            artist_label.pack(fill="x", pady=(1, 0))

            chips = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
            chips.pack(fill="x", padx=16, pady=(12, 16))
            if suggestion.bpm:
                tempo = f"{suggestion.bpm:g} BPM"
                if suggestion.bpm_delta_pct is not None:
                    tempo += f"  ·  Δ{suggestion.bpm_delta_pct:.1f}%"
                if suggestion.bpm_ratio != 1.0:
                    tempo += "  ×2" if suggestion.bpm_ratio == 2.0 else "  ÷2"
                self._chip(chips, tempo, chip_bg, c["mint"])
            if suggestion.camelot:
                relation = {
                    "même tonalité": "même clé",
                    "relative majeure/mineure": "relative",
                    "voisine Camelot": "voisine",
                    "voisine avec changement de mode": "voisine ± mode",
                    "mouvement de deux cases": "± 2 cases",
                    "tonalité éloignée": "lointaine",
                }.get(suggestion.key_relation, "Camelot")
                self._chip(chips, f"{suggestion.camelot}  ·  {relation}",
                           chip_bg, c["violet"])
            elif suggestion.key:
                self._chip(chips, suggestion.key, chip_bg, c["violet"])
            if suggestion.transition_count:
                self._chip(chips, f"{suggestion.transition_count}× en set",
                           _blend(tier_bg, tier, 0.22), tier)
            else:
                self._chip(chips, "jamais enchaînée · harmonie",
                           _blend(tier_bg, tier, 0.22), tier)

            def select(_event=None, item=suggestion, selected=card, selected_tier=tier,
                       rest=tint):
                self.reason_label.configure(text=item.reason)
                self.selected_suggestion = item
                self._set_search_state("normal")
                self.load_hint.configure(text=f"Prêt à chercher : {item.title}",
                                         text_color=c["text"])
                previous = self._selected
                self._selected = selected
                if previous is not None and previous is not selected:
                    self._set_border(previous, previous._hm_rest)
                self._set_border(selected, selected_tier)
                self.load_hint.configure(text=f"Double-clique pour rechercher dans {self._software_name()}",
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

            card._hm_rest = tint

            def enter(_event=None, frame=card):
                if frame is not self._selected:
                    self._tween_border(frame, c["border_hover"])

            def leave(_event=None, frame=card):
                if frame is not self._selected:
                    self._tween_border(frame, frame._hm_rest)

            for widget in (card, top, rank_label, cover_label, names, title_label,
                           artist_label, score_label, chips):
                widget.bind("<Button-1>", select, add="+")
                widget.bind("<Double-Button-1>", quick_search, add="+")
                widget.bind("<Enter>", enter, add="+")
                widget.bind("<Leave>", leave, add="+")

    @staticmethod
    def _chip(parent, text, background, foreground):
        ctk.CTkLabel(parent, text=text, height=26, corner_radius=13,
                     fg_color=background, text_color=foreground,
                     font=(FONT_BOLD, 9), padx=8).pack(side="left", padx=(0, 6))