"""Interface moderne du panneau Serato, séparée du contrôleur app.py."""
from __future__ import annotations

import customtkinter as ctk

COLORS = {
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
}
FONT = "Segoe UI"
FONT_BOLD = "Segoe UI Semibold"
ctk.set_appearance_mode("dark")


class SuggestionUI:
    """Présente l'état courant et les suggestions; ne lit aucune donnée Serato."""

    def __init__(self, root: ctk.CTk, on_refresh, on_close, on_search,
                 on_profile_select, on_software_select, profile_name="Nel",
                 software="serato"):
        self.root = root
        self.on_refresh = on_refresh
        self.on_close = on_close
        self.on_search = on_search
        self.on_profile_select = on_profile_select
        self.on_software_select = on_software_select
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
        self._build()
        self.set_software(self.software)
        self._place_near_serato()

    def _build(self):
        self.page_host = ctk.CTkFrame(self.root, fg_color=COLORS["background"], corner_radius=0)
        self.page_host.pack(fill="both", expand=True)
        self.home_page = ctk.CTkFrame(self.page_host, fg_color=COLORS["background"], corner_radius=0)
        self.dashboard_page = ctk.CTkFrame(self.page_host, fg_color=COLORS["background"], corner_radius=0)
        for page in (self.home_page, self.dashboard_page):
            page.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._build_home()
        self._build_dashboard()
        self.show_home()

    def _build_home(self):
        c = COLORS
        shell = ctk.CTkFrame(self.home_page, fg_color=c["background"], corner_radius=0)
        shell.pack(fill="both", expand=True, padx=20, pady=18)

        top = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        top.pack(fill="x", pady=(2, 25))
        mark = ctk.CTkFrame(top, width=42, height=42, fg_color=c["surface_2"],
                            corner_radius=13, border_width=1, border_color=c["mint"])
        mark.pack(side="left")
        mark.pack_propagate(False)
        ctk.CTkLabel(mark, text="HM", text_color=c["mint"],
                     font=(FONT_BOLD, 14)).pack(expand=True)
        brand = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
        brand.pack(side="left", padx=11, fill="y")
        ctk.CTkLabel(brand, text="HARMONIC MIX", text_color=c["text"],
                     font=(FONT_BOLD, 13), anchor="w").pack(anchor="w", pady=(3, 0))
        self.home_software_caption = ctk.CTkLabel(
            brand, text="COMPAGNON DE MIX", text_color=c["muted"],
            font=(FONT, 8), anchor="w")
        self.home_software_caption.pack(anchor="w")
        self.home_profile_button = ctk.CTkButton(
            top, text=f"PROFIL · {self.profile_name.upper()}",
            command=self.on_profile_select, width=112, height=32,
            corner_radius=16, fg_color=c["surface_2"],
            hover_color=c["surface_hover"], text_color=c["violet"],
            font=(FONT_BOLD, 9), border_width=1, border_color=c["border"])
        self.home_profile_button.pack(side="right", anchor="n")

        hero = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=22,
                            border_width=1, border_color=c["border"])
        hero.pack(fill="x", pady=(0, 14))
        accent = ctk.CTkFrame(hero, width=5, fg_color=c["mint"], corner_radius=3)
        accent.pack(side="left", fill="y", padx=(14, 0), pady=18)
        hero_body = ctk.CTkFrame(hero, fg_color="transparent", corner_radius=0)
        hero_body.pack(side="left", fill="both", expand=True, padx=17, pady=19)
        username = self.profile_name
        ctk.CTkLabel(hero_body, text="BONJOUR", text_color=c["mint"],
                     font=(FONT_BOLD, 10), anchor="w").pack(anchor="w", pady=(3, 5))
        self.home_username_label = ctk.CTkLabel(hero_body, text=username, text_color=c["text"],
                     font=(FONT_BOLD, 27), anchor="w")
        self.home_username_label.pack(anchor="w")
        ctk.CTkLabel(hero_body, text="HARMONIC MIX", text_color=c["violet"],
                     font=(FONT_BOLD, 12), anchor="w").pack(anchor="w", pady=(9, 0))
        ctk.CTkLabel(
            hero_body, text="Ton compagnon de mix pour trouver le morceau qui s'enchaîne naturellement.",
            text_color=c["muted"], font=(FONT, 11), justify="left", anchor="w",
            wraplength=345).pack(fill="x", pady=(7, 6))

        software_card = ctk.CTkFrame(
            shell, fg_color=c["surface"], corner_radius=15,
            border_width=1, border_color=c["border"])
        software_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(software_card, text="CHOISIS TON LOGICIEL DJ",
                     text_color=c["muted"], font=(FONT_BOLD, 9), anchor="w").pack(
                         anchor="w", padx=13, pady=(10, 6))
        software_row = ctk.CTkFrame(software_card, fg_color="transparent", corner_radius=0)
        software_row.pack(fill="x", padx=9, pady=(0, 9))
        self.software_buttons = {}
        for software_id, label, accent_color in (
            ("serato", "SERATO DJ", c["mint"]),
            ("traktor", "TRAKTOR", c["violet"]),
        ):
            button = ctk.CTkButton(
                software_row, text=label,
                command=lambda selected=software_id: self.on_software_select(selected),
                height=36, corner_radius=11, fg_color=c["surface_2"],
                hover_color=c["surface_hover"], text_color=accent_color,
                font=(FONT_BOLD, 10), border_width=1, border_color=c["border"])
            button.pack(side="left", fill="x", expand=True, padx=4)
            self.software_buttons[software_id] = button
        self._update_software_buttons()

        self.home_status_card = ctk.CTkFrame(
            shell, fg_color=c["surface_2"], corner_radius=17,
            border_width=1, border_color=c["border"])
        self.home_status_card.pack(fill="x", pady=(0, 15))
        self.home_status_label = ctk.CTkLabel(
            self.home_status_card, text="DERNIÈRE SESSION",
            text_color=c["violet"], font=(FONT_BOLD, 10), anchor="w")
        self.home_status_label.pack(anchor="w", padx=16, pady=(15, 6))
        self.home_track_label = ctk.CTkLabel(
            self.home_status_card, text="Aucune session détectée", text_color=c["text"],
            font=(FONT_BOLD, 16), anchor="w", justify="left", wraplength=370)
        self.home_track_label.pack(fill="x", padx=16)
        self.home_detail_label = ctk.CTkLabel(
            self.home_status_card, text="Choisis Serato DJ ou Traktor ci-dessus",
            text_color=c["muted"], font=(FONT, 10), anchor="w", justify="left",
            wraplength=370)
        self.home_detail_label.pack(fill="x", padx=16, pady=(4, 15))

        self.home_open_button = ctk.CTkButton(
            shell, text="DÉCOUVRIR MES SUGGESTIONS   →", command=self.show_dashboard,
            height=48, corner_radius=14, fg_color=c["mint"], hover_color="#E86B13",
            text_color="#111117", font=(FONT_BOLD, 11), border_width=0)
        self.home_open_button.pack(fill="x", pady=(0, 19))

        guide = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=17,
                             border_width=1, border_color=c["border"])
        guide.pack(fill="x", pady=(0, 13))
        ctk.CTkLabel(guide, text="COMMENT ÇA MARCHE",
                     text_color=c["text"], font=(FONT_BOLD, 9), anchor="w").pack(
                         anchor="w", padx=14, pady=(12, 6))
        for number, heading, explanation, color in (
            ("01", "Joue ton set", "Serato suit ton historique.", c["mint"]),
            ("02", "Trouve un match", "Transitions, BPM et tonalité.", c["violet"]),
            ("03", "Enchaîne", "Cherche puis charge sur un deck.", c["yellow"]),
        ):
            step = ctk.CTkFrame(guide, fg_color="transparent", corner_radius=0)
            step.pack(fill="x", padx=13, pady=5)
            bubble = ctk.CTkLabel(step, text=number, width=34, height=34,
                                  corner_radius=11, fg_color=c["surface_2"],
                                  text_color=color, font=(FONT_BOLD, 9))
            bubble.pack(side="left", anchor="n", padx=(0, 10))
            copy = ctk.CTkFrame(step, fg_color="transparent", corner_radius=0)
            copy.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(copy, text=heading, text_color=c["text"],
                         font=(FONT_BOLD, 11), anchor="w").pack(anchor="w")
            ctk.CTkLabel(copy, text=explanation, text_color=c["muted"],
                         font=(FONT, 9), anchor="w", justify="left",
                         wraplength=340).pack(anchor="w", pady=(1, 0))

        ctk.CTkLabel(shell, text="HARMONIC MIX  /  PRÊT QUAND TU L'ES",
                     text_color=c["dim"], font=(FONT_BOLD, 8), anchor="w").pack(
                         anchor="w", pady=(16, 0))

    def _build_dashboard(self):
        c = COLORS
        shell = ctk.CTkFrame(self.dashboard_page, fg_color=c["background"], corner_radius=0)
        shell.pack(fill="both", expand=True, padx=16, pady=13)

        header = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", pady=(0, 8))
        brand = ctk.CTkFrame(header, fg_color="transparent", corner_radius=0)
        brand.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(brand, text="HARMONIC MIX", text_color=c["violet"],
                     font=(FONT_BOLD, 13), anchor="w").pack(anchor="w")
        ctk.CTkLabel(brand, text="La prochaine piste, en harmonie avec ton set",
                     text_color=c["muted"], font=(FONT, 10), anchor="w").pack(
                         anchor="w", pady=(2, 0))
        self.pin_button = ctk.CTkButton(
            header, text="●  ÉPINGLÉ", command=self.toggle_topmost, width=104,
            height=32, corner_radius=16, fg_color=c["surface_2"],
            hover_color=c["surface_hover"], text_color=c["mint"], font=(FONT_BOLD, 10),
            border_width=1, border_color=c["mint"])
        self.pin_button.pack(side="right", anchor="n")

        now = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=18,
                           border_width=1, border_color=c["border"], height=140)
        now.pack(fill="x", pady=(0, 10))
        now.pack_propagate(False)
        accent = ctk.CTkFrame(now, width=4, fg_color=c["mint"], corner_radius=3)
        accent.pack(side="left", fill="y", padx=(10, 0), pady=13)
        current = ctk.CTkFrame(now, fg_color="transparent", corner_radius=0)
        current.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        current_header = ctk.CTkFrame(current, fg_color="transparent", corner_radius=0)
        current_header.pack(fill="x")
        self.current_section_label = ctk.CTkLabel(
            current_header, text="DERNIÈRE PISTE", text_color=c["muted"],
            font=(FONT_BOLD, 9), anchor="w")
        self.current_section_label.pack(side="left")
        self.status_label = ctk.CTkLabel(current_header, text="", text_color=c["mint"],
                                         font=(FONT_BOLD, 9), anchor="e")
        self.status_label.pack(side="right")
        self.current_label = ctk.CTkLabel(
            current, text="En attente de Serato", text_color=c["text"],
            font=(FONT_BOLD, 18), anchor="w", justify="left", wraplength=380)
        self.current_label.pack(fill="x", pady=(6, 2))
        self.detail_label = ctk.CTkLabel(
            current, text="", text_color=c["muted"], font=(FONT, 10),
            anchor="w", justify="left", wraplength=380)
        self.detail_label.pack(fill="x")

        section = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        section.pack(fill="x", pady=(0, 7))
        ctk.CTkLabel(section, text="MEILLEURS MATCHS", text_color=c["text"],
                     font=(FONT_BOLD, 12), anchor="w").pack(side="left")
        self.home_button = ctk.CTkButton(
            section, text="⌂", command=self.show_home, width=34, height=32,
            corner_radius=12, fg_color=c["surface_2"], hover_color=c["surface_hover"],
            text_color=c["violet"], font=(FONT_BOLD, 15), border_width=1,
            border_color=c["border"])
        self.home_button.pack(side="right", padx=(5, 0))
        self.refresh_button = ctk.CTkButton(
            section, text="↻", command=self.on_refresh, width=35, height=32,
            corner_radius=12, fg_color=c["surface_2"], hover_color=c["surface_hover"],
            text_color=c["violet"], font=(FONT_BOLD, 15), border_width=1,
            border_color=c["border"])
        self.refresh_button.pack(side="right")

        self.cards = ctk.CTkScrollableFrame(
            shell, fg_color="transparent", corner_radius=0,
            scrollbar_fg_color=c["background"], scrollbar_button_color=c["border"],
            scrollbar_button_hover_color=c["violet"])
        self.cards.pack(fill="both", expand=True)

        self.load_bar = ctk.CTkFrame(shell, fg_color="transparent", corner_radius=0)
        self.load_bar.pack(fill="x", pady=(7, 0))
        self.load_hint = ctk.CTkLabel(
            self.load_bar, text="Sélectionne un morceau pour le rechercher dans Serato",
            text_color=c["muted"], font=(FONT, 9), anchor="w")
        self.load_hint.pack(fill="x", pady=(0, 5))
        self.search_button = ctk.CTkButton(
            self.load_bar, text="⌕  CHERCHER DANS SERATO", state="disabled",
            command=self._search_selected, height=38, corner_radius=12,
            fg_color=c["surface_2"], hover_color=c["surface_hover"],
            text_color=c["violet"], font=(FONT_BOLD, 11),
            border_width=1, border_color=c["border"])
        self.search_button.pack(fill="x")

        self.reason_box = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=14,
                                       border_width=1, border_color=c["border"])
        self.reason_box.pack(fill="x", pady=(7, 9))
        self.reason_label = ctk.CTkLabel(
            self.reason_box, text="Clique sur une carte pour voir pourquoi elle est proposée",
            text_color=c["muted"], font=(FONT, 9), anchor="w", justify="left",
            wraplength=410)
        self.reason_label.pack(fill="x", padx=11, pady=8)

        footer = ctk.CTkFrame(shell, fg_color=c["surface"], corner_radius=14,
                              border_width=1, border_color=c["border"])
        footer.pack(fill="x")
        legend = (("ROUGE", "très jouées", c["red"]),
                  ("ORANGE", "répétées", c["orange"]),
                  ("JAUNE", "rares", c["yellow"]),
                  ("BLEU", "jamais · théorie", c["blue"]))
        for index, (name, meaning, color) in enumerate(legend):
            cell = ctk.CTkFrame(footer, fg_color="transparent", corner_radius=0)
            cell.grid(row=0, column=index, sticky="ew", padx=(9 if index == 0 else 3, 3), pady=8)
            ctk.CTkLabel(cell, text=name, text_color=color,
                         font=(FONT_BOLD, 9), anchor="w").pack(anchor="w")
            ctk.CTkLabel(cell, text=meaning, text_color=c["muted"],
                         font=(FONT, 8), anchor="w").pack(anchor="w", pady=(1, 0))
            footer.grid_columnconfigure(index, weight=1)

    def _place_near_serato(self):
        self._set_page_geometry(470, 850)

    def _set_page_geometry(self, preferred_width, preferred_height):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(preferred_width, screen_w - 28)
        height = min(preferred_height, screen_h - 28)
        x = screen_w - width - 14
        self.root.geometry(f"{width}x{height}+{x}+14")

    def toggle_topmost(self):
        self.set_topmost(not self.topmost)

    def set_topmost(self, enabled):
        self.topmost = bool(enabled)
        self.root.attributes("-topmost", self.topmost)
        c = COLORS
        for button in (self.pin_button,):
            button.configure(
                text="●  ÉPINGLÉ" if self.topmost else "○  LIBRE",
                fg_color=c["surface_2"],
                hover_color=c["surface_hover"],
                text_color=c["mint"] if self.topmost else c["muted"],
                border_color=c["mint"] if self.topmost else c["border"])

    def show_home(self):
        self._set_page_geometry(470, 850)
        self.home_page.tkraise()

    def show_dashboard(self):
        self._set_page_geometry(470, 850)
        self.dashboard_page.tkraise()

    def set_profile(self, name):
        self.profile_name = name
        self.home_profile_button.configure(text=f"PROFIL · {name.upper()}")
        self.home_username_label.configure(text=name)
        self.home_track_label.configure(text=f"En attente de {self._software_name()}")

    def _software_name(self):
        return "Serato DJ" if self.software == "serato" else "Traktor"

    def set_software(self, software):
        self.software = software if software in {"serato", "traktor"} else "serato"
        self._update_software_buttons()
        label = self._software_name()
        self.root.title(f"{label} · Harmonic Mix")
        self.home_software_caption.configure(text=f"{label.upper()} · COMPAGNON DE MIX")
        self.current_label.configure(text=f"En attente de {label}")
        self.home_track_label.configure(text=f"En attente de {label}")
        self.search_button.configure(text=f"⌕  CHERCHER DANS {label.upper()}")
        self.load_hint.configure(text=f"Sélectionne un morceau pour le rechercher dans {label}")

    def _update_software_buttons(self):
        c = COLORS
        for software_id, button in self.software_buttons.items():
            selected = software_id == self.software
            accent = c["mint"] if software_id == "serato" else c["violet"]
            button.configure(
                fg_color=c["surface_2"] if selected else c["surface"],
                text_color=accent if selected else c["muted"],
                border_color=accent if selected else c["border"])

    def show_error(self, message):
        self.status_label.configure(text="● ERREUR", text_color=COLORS["gold"])
        self.reason_label.configure(text=message)

    def _search_selected(self):
        if self.selected_suggestion is not None:
            self.search_button.configure(state="disabled")
            self.load_hint.configure(text=f"Recherche progressive dans {self._software_name()}…",
                                     text_color=COLORS["violet"])
            self.on_search(self.selected_suggestion)

    def show_search_result(self, message, success=True):
        color = COLORS["mint"] if success else COLORS["gold"]
        self.load_hint.configure(text=message, text_color=color)
        if self.selected_suggestion is not None:
            self.search_button.configure(state="normal")

    def render(self, title, detail, status, status_color, suggestions,
               session_date="", session_detail=""):
        is_playing = "EN DIRECT" in status or status == "● SERATO"
        self.current_label.configure(text=title)
        self.detail_label.configure(text=detail)
        self.home_track_label.configure(text=session_date or "Aucune session détectée")
        self.home_detail_label.configure(text=session_detail or "Choisis Serato DJ ou Traktor ci-dessus")
        self.home_status_label.configure(text="DERNIÈRE SESSION", text_color=status_color)
        self.current_section_label.configure(
            text="EN COURS" if is_playing else "DERNIÈRE PISTE",
            text_color=COLORS["mint"] if is_playing else COLORS["muted"])
        self.status_label.configure(text=status, text_color=status_color)
        self._render_cards(suggestions)

    def _render_cards(self, suggestions):
        c = COLORS
        for child in self.cards.winfo_children():
            child.destroy()
        self._cards = []
        self._selected = None
        self.selected_suggestion = None
        self.search_button.configure(state="disabled")
        self.load_hint.configure(text="Sélectionne un morceau pour le rechercher dans Serato",
                                 text_color=c["muted"])
        if not suggestions:
            ctk.CTkLabel(self.cards, text="Pas encore assez d'historique pour ce morceau.",
                         text_color=c["muted"], font=(FONT, 9), anchor="w").pack(
                             fill="x", padx=4, pady=14)
            return

        for rank, suggestion in enumerate(suggestions, 1):
            tier = c[suggestion.category]
            tier_bg = c[f"{suggestion.category}_dark"]

            card = ctk.CTkFrame(self.cards, fg_color=c["surface"], corner_radius=16,
                                border_width=1, border_color=c["border"])
            card.pack(fill="x", padx=2, pady=4)
            self._cards.append((card, tier))
            top = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
            top.pack(fill="x", padx=11, pady=(9, 0))

            rank_label = ctk.CTkLabel(top, text=f"{rank:02}", width=30, height=27,
                                      corner_radius=9, fg_color=tier_bg,
                                      text_color=tier, font=(FONT_BOLD, 8))
            rank_label.pack(side="left", anchor="n", padx=(0, 8))
            names = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
            names.pack(side="left", fill="x", expand=True)
            title_label = ctk.CTkLabel(
                names, text=suggestion.title, text_color=c["text"],
                font=(FONT_BOLD, 12), anchor="w", justify="left", wraplength=290)
            title_label.pack(fill="x")
            artist_label = ctk.CTkLabel(
                names, text=suggestion.artist or "Artiste non renseigné",
                text_color=c["muted"], font=(FONT, 10), anchor="w", justify="left",
                wraplength=290)
            artist_label.pack(fill="x", pady=(1, 0))
            score_label = ctk.CTkLabel(
                top, text=f"{suggestion.score:.0f}%", width=59, height=30,
                corner_radius=12, fg_color=tier_bg, text_color=tier,
                font=(FONT_BOLD, 11))
            score_label.pack(side="right", anchor="n", padx=(7, 0))

            chips = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
            chips.pack(fill="x", padx=12, pady=(7, 5))
            if suggestion.bpm:
                tempo = f"{suggestion.bpm:g} BPM"
                if suggestion.bpm_delta_pct is not None:
                    tempo += f"  ·  Δ{suggestion.bpm_delta_pct:.1f}%"
                if suggestion.bpm_ratio != 1.0:
                    tempo += "  ×2" if suggestion.bpm_ratio == 2.0 else "  ÷2"
                self._chip(chips, tempo, c["surface_2"], c["mint"])
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
                           c["surface_2"], c["violet"])
            elif suggestion.key:
                self._chip(chips, suggestion.key, c["surface_2"], c["violet"])
            if suggestion.transition_count:
                self._chip(chips, f"{suggestion.transition_count}× en set",
                           tier_bg, tier)
            else:
                self._chip(chips, "jamais enchaînée · harmonie", tier_bg, tier)

            meter = ctk.CTkProgressBar(
                card, height=5, corner_radius=4, fg_color=c["progress_bg"],
                progress_color=tier)
            meter.pack(fill="x", padx=12, pady=(0, 10))
            meter.set(max(0, min(100, suggestion.score)) / 100)

            def select(_event=None, item=suggestion, selected=card, selected_tier=tier):
                self.reason_label.configure(text=item.reason)
                self.selected_suggestion = item
                self.search_button.configure(state="normal")
                self.load_hint.configure(text=f"Prêt à chercher : {item.title}",
                                         text_color=c["text"])
                previous = self._selected
                self._selected = selected
                if previous is not None and previous is not selected:
                    previous.configure(border_color=c["border"])
                selected.configure(border_color=selected_tier)

            def enter(_event=None, frame=card):
                if frame is not self._selected:
                    frame.configure(border_color=c["border_hover"])

            def leave(_event=None, frame=card):
                if frame is not self._selected:
                    frame.configure(border_color=c["border"])

            for widget in (card, top, rank_label, names, title_label, artist_label,
                           score_label, chips):
                widget.bind("<Button-1>", select, add="+")
                widget.bind("<Enter>", enter, add="+")
                widget.bind("<Leave>", leave, add="+")

    @staticmethod
    def _chip(parent, text, background, foreground):
        ctk.CTkLabel(parent, text=text, height=23, corner_radius=11,
                     fg_color=background, text_color=foreground,
                     font=(FONT_BOLD, 8), padx=8).pack(side="left", padx=(0, 5))
