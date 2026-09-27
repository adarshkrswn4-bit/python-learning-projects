#!/usr/bin/env python3
"""
Neon Obsidian Desktop Media Engine
A self-contained PySide6 multimedia desktop player inspired by premium Lark Player-style UX.

Requirements:
    pip install PySide6

Supported local formats:
    .mp3, .wav, .m4a, .flac
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRectF, Signal, QUrl, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFrame,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
    QSizePolicy,
    QButtonGroup,
    QStyle,
    QStyledItemDelegate,
    QGraphicsDropShadowEffect,
    QMessageBox,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


APP_NAME = "Neon Lark Media Engine"

MAIN_BG = "#090A0F"
CARD_BG = "#161923"
CARD_BG_2 = "#11141D"
TEAL = "#00E5FF"
TEAL_SOFT = "#0ABBD0"
TEXT = "#EAF2F8"
MUTED = "#8E9AA8"
SLATE = "#5F6B7A"
BORDER = "#232838"
DANGER = "#FF4D6D"

VALID_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac"}

TRACK_ROLE = Qt.UserRole + 101
INDEX_ROLE = Qt.UserRole + 102
PLAYING_ROLE = Qt.UserRole + 103


@dataclass
class Track:
    path: str
    title: str
    artist: str


def format_ms(milliseconds: int) -> str:
    if milliseconds is None or milliseconds < 0:
        milliseconds = 0
    seconds = milliseconds // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    hours = minutes // 60
    minutes = minutes % 60

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def build_track(path: str) -> Track:
    p = Path(path)
    title = p.stem.strip() or p.name
    artist = f"{p.suffix.upper().replace('.', '')} audio • {p.parent}"
    return Track(path=str(p), title=title, artist=artist)


class NeonSlider(QWidget):
    """
    Custom painted horizontal slider with neon progress fill and hover-expanding circular handle.
    Used for both playback timeline and volume.
    """

    moved = Signal(int)
    releasedAt = Signal(int)
    sliderPressed = Signal()

    def __init__(
        self,
        minimum=0,
        maximum=100,
        value=0,
        accent=TEAL,
        parent=None,
        compact=False,
    ):
        super().__init__(parent)
        self._min = minimum
        self._max = max(maximum, minimum + 1)
        self._value = value
        self._accent = QColor(accent)
        self._hover = False
        self._dragging = False
        self._compact = compact

        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(22 if compact else 34)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def isDragging(self) -> bool:
        return self._dragging

    def value(self) -> int:
        return self._value

    def setRange(self, minimum: int, maximum: int):
        self._min = minimum
        self._max = max(maximum, minimum + 1)
        self._value = max(self._min, min(self._value, self._max))
        self.update()

    def setValue(self, value: int):
        value = max(self._min, min(int(value), self._max))
        if value != self._value:
            self._value = value
            self.update()

    def setAccent(self, color: str):
        self._accent = QColor(color)
        self.update()

    def sizeHint(self):
        return QSize(260, 24 if self._compact else 34)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        if not self._dragging:
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.sliderPressed.emit()
            self._set_value_from_x(event.position().x(), emit=True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._set_value_from_x(event.position().x(), emit=True)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._set_value_from_x(event.position().x(), emit=True)
            self._dragging = False
            self.releasedAt.emit(self._value)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _set_value_from_x(self, x: float, emit=False):
        margin = 12
        usable = max(1, self.width() - margin * 2)
        ratio = (x - margin) / usable
        ratio = max(0.0, min(1.0, ratio))
        value = int(self._min + ratio * (self._max - self._min))
        if value != self._value:
            self._value = value
            self.update()
            if emit:
                self.moved.emit(self._value)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()

        margin = 12
        track_h = 5 if self._compact else 6
        if self._hover or self._dragging:
            track_h += 2

        y = (h - track_h) / 2
        track_rect = QRectF(margin, y, max(1, w - margin * 2), track_h)

        # Base track
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2A3040"))
        painter.drawRoundedRect(track_rect, track_h / 2, track_h / 2)

        # Progress track
        ratio = (self._value - self._min) / max(1, self._max - self._min)
        progress_w = max(track_h, track_rect.width() * ratio)
        progress_rect = QRectF(track_rect.x(), track_rect.y(), progress_w, track_rect.height())

        glow = QColor(self._accent)
        glow.setAlpha(70)
        painter.setBrush(glow)
        painter.drawRoundedRect(
            QRectF(progress_rect.x(), progress_rect.y() - 1, progress_rect.width(), progress_rect.height() + 2),
            (track_h + 2) / 2,
            (track_h + 2) / 2,
        )

        painter.setBrush(self._accent)
        painter.drawRoundedRect(progress_rect, track_h / 2, track_h / 2)

        # Handle
        handle_x = track_rect.x() + track_rect.width() * ratio
        radius = 6 if self._compact else 7
        if self._hover or self._dragging:
            radius = 9 if self._compact else 11

        outer = QColor(self._accent)
        outer.setAlpha(55)
        painter.setBrush(outer)
        painter.drawEllipse(QRectF(handle_x - radius - 4, h / 2 - radius - 4, (radius + 4) * 2, (radius + 4) * 2))

        painter.setBrush(QColor("#EFFFFF"))
        painter.setPen(QPen(self._accent, 2))
        painter.drawEllipse(QRectF(handle_x - radius, h / 2 - radius, radius * 2, radius * 2))


class TrackItemDelegate(QStyledItemDelegate):
    """
    Custom list delegate rendering bold track titles and subtle slate-silver metadata.
    """

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 70)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = option.rect.adjusted(8, 5, -8, -5)
        track = index.data(TRACK_ROLE)
        is_playing = bool(index.data(PLAYING_ROLE))
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        if selected or hovered or is_playing:
            bg = QColor(CARD_BG)
            if selected:
                bg = QColor("#10232B")
            elif hovered:
                bg = QColor("#141A25")
            painter.setPen(QPen(QColor(TEAL if selected or is_playing else BORDER), 1))
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 15, 15)

        if is_playing:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(TEAL))
            painter.drawRoundedRect(QRectF(rect.left() + 9, rect.top() + 16, 4, rect.height() - 32), 2, 2)

        left = rect.left() + 24
        top = rect.top() + 13
        right_pad = 18

        title = track.title if track else "Unknown Track"
        subtitle = track.artist if track else ""

        title_font = QFont(option.font)
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(TEAL if is_playing else TEXT))

        title_rect = QRectF(left, top, rect.width() - 42 - right_pad, 22)
        elided_title = painter.fontMetrics().elidedText(title, Qt.ElideRight, int(title_rect.width()))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        meta_font = QFont(option.font)
        meta_font.setPointSize(8)
        meta_font.setWeight(QFont.Normal)
        painter.setFont(meta_font)
        painter.setPen(QColor(MUTED))

        meta_rect = QRectF(left, top + 27, rect.width() - 42 - right_pad, 18)
        elided_meta = painter.fontMetrics().elidedText(subtitle, Qt.ElideMiddle, int(meta_rect.width()))
        painter.drawText(meta_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_meta)

        painter.restore()


class MediaEngineWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1240, 780)
        self.setMinimumSize(980, 650)

        self.tracks: list[Track] = []
        self.path_set: set[str] = set()
        self.imported_folders: list[str] = []
        self.current_index = -1
        self._last_duration = 0

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.80)

        self._build_ui()
        self._connect_player()
        self._apply_styles()
        self._reset_now_playing()

    # ---------------------------------------------------------------------
    # UI construction
    # ---------------------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(18)

        self.sidebar = self._build_sidebar()
        main_layout.addWidget(self.sidebar)

        self.content_shell = QFrame()
        self.content_shell.setObjectName("ContentShell")
        content_layout = QVBoxLayout(self.content_shell)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        self.header = self._build_header()
        content_layout.addWidget(self.header)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ViewStack")

        self.library_page = self._build_library_page()
        self.queue_page = self._build_queue_page()
        self.folders_page = self._build_folders_page()
        self.settings_page = self._build_settings_page()

        self.stack.addWidget(self.library_page)
        self.stack.addWidget(self.queue_page)
        self.stack.addWidget(self.folders_page)
        self.stack.addWidget(self.settings_page)

        content_layout.addWidget(self.stack, 1)

        self.control_dock = self._build_control_dock()
        content_layout.addWidget(self.control_dock)

        main_layout.addWidget(self.content_shell, 1)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        logo = QLabel("LARK\nNEON")
        logo.setObjectName("Logo")
        logo.setAlignment(Qt.AlignLeft)
        layout.addWidget(logo)

        tagline = QLabel("Obsidian media console")
        tagline.setObjectName("SidebarTagline")
        layout.addWidget(tagline)

        layout.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []

        nav_items = [
            ("Library", "Music Collection"),
            ("Queue", "Active Track Queue"),
            ("Folders", "Directory Ingestion"),
            ("Settings", "Configuration"),
        ]

        for idx, (label, tooltip) in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda checked=False, i=idx: self.route_to(i))
            self.nav_group.addButton(btn, idx)
            self.nav_buttons.append(btn)
            layout.addWidget(btn)

        self.nav_buttons[0].setChecked(True)

        layout.addStretch(1)

        self.side_add_file = QPushButton("+ Add Files")
        self.side_add_file.setObjectName("AccentButton")
        self.side_add_file.clicked.connect(self.add_files)

        self.side_add_folder = QPushButton("+ Add Folder")
        self.side_add_folder.setObjectName("GhostButton")
        self.side_add_folder.clicked.connect(self.add_folder)

        layout.addWidget(self.side_add_file)
        layout.addWidget(self.side_add_folder)

        version = QLabel("Native Qt Multimedia backend")
        version.setObjectName("SidebarFooter")
        layout.addWidget(version)

        return sidebar

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(4, 0, 4, 0)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)

        self.header_title = QLabel("Music Collection")
        self.header_title.setObjectName("HeaderTitle")

        self.header_subtitle = QLabel("Import local audio files or recursively scan folders.")
        self.header_subtitle.setObjectName("HeaderSubtitle")

        text_box.addWidget(self.header_title)
        text_box.addWidget(self.header_subtitle)

        layout.addLayout(text_box, 1)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("StatusPill")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        return header

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 229, 255, 20))
        shadow.setOffset(0, 0)
        card.setGraphicsEffect(shadow)
        return card

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._make_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Local Music Library")
        title.setObjectName("CardTitle")
        subtitle = QLabel("Double-click any track to begin playback.")
        subtitle.setObjectName("CardSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        top.addLayout(title_box, 1)

        add_files = QPushButton("Add Files")
        add_files.setObjectName("AccentButton")
        add_files.clicked.connect(self.add_files)

        add_folder = QPushButton("Add Folder")
        add_folder.setObjectName("GhostButton")
        add_folder.clicked.connect(self.add_folder)

        top.addWidget(add_files)
        top.addWidget(add_folder)

        card_layout.addLayout(top)

        self.library_list = QListWidget()
        self.library_list.setObjectName("TrackList")
        self.library_list.setItemDelegate(TrackItemDelegate(self.library_list))
        self.library_list.setMouseTracking(True)
        self.library_list.itemDoubleClicked.connect(self._library_item_double_clicked)
        card_layout.addWidget(self.library_list, 1)

        layout.addWidget(card, 1)
        return page

    def _build_queue_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._make_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Active Track Queue")
        title.setObjectName("CardTitle")
        subtitle = QLabel("Sequential transport queue mirrors the sorted local collection.")
        subtitle.setObjectName("CardSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)

        clear_btn = QPushButton("Clear Library")
        clear_btn.setObjectName("DangerButton")
        clear_btn.clicked.connect(self.clear_library)
        top.addWidget(clear_btn)

        card_layout.addLayout(top)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("TrackList")
        self.queue_list.setItemDelegate(TrackItemDelegate(self.queue_list))
        self.queue_list.setMouseTracking(True)
        self.queue_list.itemDoubleClicked.connect(self._queue_item_double_clicked)
        card_layout.addWidget(self.queue_list, 1)

        layout.addWidget(card, 1)
        return page

    def _build_folders_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._make_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Directory Scanner")
        title.setObjectName("CardTitle")
        subtitle = QLabel("Recursive import isolates .mp3, .wav, .m4a, and .flac files while avoiding duplicates.")
        subtitle.setObjectName("CardSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)

        scan = QPushButton("Add Folder")
        scan.setObjectName("AccentButton")
        scan.clicked.connect(self.add_folder)
        top.addWidget(scan)

        card_layout.addLayout(top)

        self.folder_list = QListWidget()
        self.folder_list.setObjectName("FolderList")
        card_layout.addWidget(self.folder_list, 1)

        layout.addWidget(card, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._make_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(18)

        title = QLabel("Configuration")
        title.setObjectName("CardTitle")
        subtitle = QLabel("Native platform audio output, custom neon controls, and local-library ingestion.")
        subtitle.setObjectName("CardSubtitle")
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        section = QFrame()
        section.setObjectName("InnerPanel")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(18, 18, 18, 18)
        section_layout.setSpacing(12)

        volume_row = QHBoxLayout()
        volume_label = QLabel("Default Output Volume")
        volume_label.setObjectName("SettingsLabel")

        self.settings_volume_value = QLabel("80%")
        self.settings_volume_value.setObjectName("SettingsValue")
        volume_row.addWidget(volume_label)
        volume_row.addStretch(1)
        volume_row.addWidget(self.settings_volume_value)
        section_layout.addLayout(volume_row)

        self.settings_volume_slider = NeonSlider(0, 100, 80, compact=True)
        self.settings_volume_slider.moved.connect(self.set_volume_percent)
        self.settings_volume_slider.releasedAt.connect(self.set_volume_percent)
        section_layout.addWidget(self.settings_volume_slider)

        supported = QLabel("Supported media extensions: MP3, WAV, M4A, FLAC")
        supported.setObjectName("CardSubtitle")
        section_layout.addWidget(supported)

        backend = QLabel("Playback backend: Qt Multimedia mapped to native platform media services.")
        backend.setObjectName("CardSubtitle")
        section_layout.addWidget(backend)

        card_layout.addWidget(section)
        card_layout.addStretch(1)

        layout.addWidget(card, 1)
        return page

    def _build_control_dock(self) -> QFrame:
        dock = QFrame()
        dock.setObjectName("ControlDock")
        dock.setMinimumHeight(128)

        shadow = QGraphicsDropShadowEffect(dock)
        shadow.setBlurRadius(38)
        shadow.setColor(QColor(0, 229, 255, 55))
        shadow.setOffset(0, 0)
        dock.setGraphicsEffect(shadow)

        layout = QHBoxLayout(dock)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(22)

        # Now playing metadata
        meta = QVBoxLayout()
        meta.setSpacing(3)

        self.now_title = QLabel("No track selected")
        self.now_title.setObjectName("NowTitle")
        self.now_title.setMinimumWidth(260)
        self.now_title.setMaximumWidth(340)

        self.now_artist = QLabel("Import music to begin")
        self.now_artist.setObjectName("NowArtist")
        self.now_artist.setMinimumWidth(260)
        self.now_artist.setMaximumWidth(340)

        meta.addStretch(1)
        meta.addWidget(self.now_title)
        meta.addWidget(self.now_artist)
        meta.addStretch(1)
        layout.addLayout(meta)

        # Central transport
        center = QVBoxLayout()
        center.setSpacing(8)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch(1)

        self.prev_button = QPushButton("⏮")
        self.prev_button.setObjectName("TransportButton")
        self.prev_button.clicked.connect(self.previous_track)

        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("PlayButton")
        self.play_button.clicked.connect(self.toggle_play)

        self.next_button = QPushButton("⏭")
        self.next_button.setObjectName("TransportButton")
        self.next_button.clicked.connect(lambda: self.next_track(auto=False))

        buttons.addWidget(self.prev_button)
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.next_button)
        buttons.addStretch(1)

        center.addLayout(buttons)

        timeline_row = QHBoxLayout()
        timeline_row.setSpacing(10)

        self.position_label = QLabel("0:00")
        self.position_label.setObjectName("TimeLabel")
        self.duration_label = QLabel("0:00")
        self.duration_label.setObjectName("TimeLabel")

        self.timeline = NeonSlider(0, 1, 0, accent=TEAL)
        self.timeline.moved.connect(self.on_timeline_preview)
        self.timeline.releasedAt.connect(self.seek_to)

        timeline_row.addWidget(self.position_label)
        timeline_row.addWidget(self.timeline, 1)
        timeline_row.addWidget(self.duration_label)

        center.addLayout(timeline_row)
        layout.addLayout(center, 1)

        # Volume
        vol = QHBoxLayout()
        vol.setSpacing(10)

        volume_icon = QLabel("VOL")
        volume_icon.setObjectName("VolumeIcon")
        self.volume_value = QLabel("80%")
        self.volume_value.setObjectName("VolumeValue")

        self.volume_slider = NeonSlider(0, 100, 80, accent=TEAL, compact=True)
        self.volume_slider.setFixedWidth(150)
        self.volume_slider.moved.connect(self.set_volume_percent)
        self.volume_slider.releasedAt.connect(self.set_volume_percent)

        vol.addWidget(volume_icon)
        vol.addWidget(self.volume_slider)
        vol.addWidget(self.volume_value)

        layout.addLayout(vol)

        return dock

    # ---------------------------------------------------------------------
    # Styling
    # ---------------------------------------------------------------------
    def _apply_styles(self):
        self.setStyleSheet(f"""
            * {{
                font-family: "Segoe UI", "Inter", "SF Pro Display", Arial, sans-serif;
            }}

            QMainWindow, QWidget#Root {{
                background: {MAIN_BG};
                color: {TEXT};
            }}

            QFrame#Sidebar {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 24px;
            }}

            QLabel#Logo {{
                color: {TEAL};
                font-size: 28px;
                font-weight: 900;
                letter-spacing: 3px;
                line-height: 0.9em;
            }}

            QLabel#SidebarTagline {{
                color: {MUTED};
                font-size: 12px;
            }}

            QLabel#SidebarFooter {{
                color: {SLATE};
                font-size: 11px;
                padding-top: 8px;
            }}

            QPushButton {{
                border: none;
                outline: none;
            }}

            QPushButton#NavButton {{
                background: transparent;
                color: {MUTED};
                text-align: left;
                padding: 14px 16px;
                border-radius: 14px;
                font-size: 14px;
                font-weight: 700;
            }}

            QPushButton#NavButton:hover {{
                background: #1B202C;
                color: {TEXT};
            }}

            QPushButton#NavButton:checked {{
                background: #10232B;
                color: {TEAL};
                border: 1px solid rgba(0, 229, 255, 0.45);
            }}

            QFrame#Header {{
                background: transparent;
            }}

            QLabel#HeaderTitle {{
                color: {TEXT};
                font-size: 28px;
                font-weight: 900;
            }}

            QLabel#HeaderSubtitle {{
                color: {MUTED};
                font-size: 13px;
            }}

            QLabel#StatusPill {{
                color: {TEAL};
                background: rgba(0, 229, 255, 0.08);
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-radius: 16px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 700;
                min-width: 130px;
            }}

            QFrame#Card {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 24px;
            }}

            QFrame#InnerPanel {{
                background: {CARD_BG_2};
                border: 1px solid {BORDER};
                border-radius: 18px;
            }}

            QLabel#CardTitle {{
                color: {TEXT};
                font-size: 19px;
                font-weight: 900;
            }}

            QLabel#CardSubtitle {{
                color: {MUTED};
                font-size: 12px;
            }}

            QLabel#SettingsLabel {{
                color: {TEXT};
                font-size: 14px;
                font-weight: 800;
            }}

            QLabel#SettingsValue {{
                color: {TEAL};
                font-size: 13px;
                font-weight: 900;
            }}

            QPushButton#AccentButton {{
                color: #001014;
                background: {TEAL};
                padding: 11px 16px;
                border-radius: 14px;
                font-size: 13px;
                font-weight: 900;
            }}

            QPushButton#AccentButton:hover {{
                background: #55F0FF;
            }}

            QPushButton#GhostButton {{
                color: {TEAL};
                background: rgba(0, 229, 255, 0.07);
                border: 1px solid rgba(0, 229, 255, 0.32);
                padding: 11px 16px;
                border-radius: 14px;
                font-size: 13px;
                font-weight: 900;
            }}

            QPushButton#GhostButton:hover {{
                background: rgba(0, 229, 255, 0.15);
            }}

            QPushButton#DangerButton {{
                color: #FFEAF0;
                background: rgba(255, 77, 109, 0.13);
                border: 1px solid rgba(255, 77, 109, 0.35);
                padding: 11px 16px;
                border-radius: 14px;
                font-size: 13px;
                font-weight: 900;
            }}

            QPushButton#DangerButton:hover {{
                background: rgba(255, 77, 109, 0.22);
            }}

            QListWidget#TrackList, QListWidget#FolderList {{
                background: transparent;
                border: none;
                outline: none;
                color: {TEXT};
                font-size: 13px;
                padding: 4px;
            }}

            QListWidget#FolderList::item {{
                color: {MUTED};
                background: #11141D;
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 12px;
                margin: 5px;
            }}

            QListWidget#FolderList::item:selected {{
                color: {TEAL};
                border: 1px solid rgba(0, 229, 255, 0.45);
                background: #10232B;
            }}

            QFrame#ControlDock {{
                background: rgba(22, 25, 35, 0.96);
                border: 1px solid rgba(0, 229, 255, 0.22);
                border-radius: 28px;
            }}

            QLabel#NowTitle {{
                color: {TEXT};
                font-size: 15px;
                font-weight: 900;
            }}

            QLabel#NowArtist {{
                color: {MUTED};
                font-size: 11px;
            }}

            QPushButton#TransportButton {{
                color: {TEXT};
                background: #202635;
                border: 1px solid {BORDER};
                border-radius: 20px;
                min-width: 42px;
                min-height: 42px;
                font-size: 16px;
                font-weight: 900;
            }}

            QPushButton#TransportButton:hover {{
                color: {TEAL};
                background: #263044;
                border: 1px solid rgba(0, 229, 255, 0.40);
            }}

            QPushButton#PlayButton {{
                color: #001014;
                background: {TEAL};
                border-radius: 25px;
                min-width: 54px;
                min-height: 54px;
                font-size: 22px;
                font-weight: 900;
            }}

            QPushButton#PlayButton:hover {{
                background: #55F0FF;
            }}

            QLabel#TimeLabel {{
                color: {MUTED};
                font-size: 11px;
                font-weight: 700;
                min-width: 38px;
            }}

            QLabel#VolumeIcon {{
                color: {MUTED};
                font-size: 10px;
                font-weight: 900;
                letter-spacing: 1px;
            }}

            QLabel#VolumeValue {{
                color: {TEAL};
                font-size: 11px;
                font-weight: 900;
                min-width: 34px;
            }}

            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 4px 0 4px 0;
            }}

            QScrollBar::handle:vertical {{
                background: rgba(142, 154, 168, 0.32);
                border-radius: 5px;
                min-height: 34px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: rgba(0, 229, 255, 0.62);
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QScrollBar:horizontal {{
                background: transparent;
                height: 10px;
                margin: 0 4px 0 4px;
            }}

            QScrollBar::handle:horizontal {{
                background: rgba(142, 154, 168, 0.32);
                border-radius: 5px;
                min-width: 34px;
            }}

            QScrollBar::handle:horizontal:hover {{
                background: rgba(0, 229, 255, 0.62);
            }}

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """)

    # ---------------------------------------------------------------------
    # Player wiring
    # ---------------------------------------------------------------------
    def _connect_player(self):
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.errorOccurred.connect(self.on_player_error)

        try:
            self.audio_output.volumeChanged.connect(self.on_audio_volume_changed)
        except Exception:
            pass

    # ---------------------------------------------------------------------
    # Navigation
    # ---------------------------------------------------------------------
    def route_to(self, index: int):
        self.stack.setCurrentIndex(index)

        titles = [
            ("Music Collection", "Import local audio files or recursively scan folders."),
            ("Active Track Queue", "Double-click queue entries or use transport controls."),
            ("Directory Ingestion", "Recursive folder walking with duplicate filtering."),
            ("Configuration", "Output volume and media backend details."),
        ]

        title, subtitle = titles[index]
        self.header_title.setText(title)
        self.header_subtitle.setText(subtitle)

        if 0 <= index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

    # ---------------------------------------------------------------------
    # Local media ingestion
    # ---------------------------------------------------------------------
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Audio Files",
            str(Path.home()),
            "Audio Files (*.mp3 *.wav *.m4a *.flac);;All Files (*)",
        )
        if files:
            self.ingest_paths(files)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Add Music Folder",
            str(Path.home()),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not folder:
            return

        self.set_status("Scanning folder…")

        paths = []
        for root, _dirs, files in os.walk(folder, onerror=lambda e: None):
            for filename in files:
                if Path(filename).suffix.lower() in VALID_EXTENSIONS:
                    paths.append(os.path.join(root, filename))

        paths.sort(key=lambda p: (Path(p).stem.lower(), str(p).lower()))
        self.ingest_paths(paths, source_folder=folder)

    def ingest_paths(self, paths, source_folder: str | None = None):
        if not paths:
            self.set_status("No media found")
            return

        current_path = None
        if 0 <= self.current_index < len(self.tracks):
            current_path = self.tracks[self.current_index].path

        new_tracks: list[Track] = []

        for raw_path in paths:
            try:
                full_path = os.path.abspath(os.path.expanduser(str(raw_path)))
            except Exception:
                continue

            if not os.path.isfile(full_path):
                continue

            if Path(full_path).suffix.lower() not in VALID_EXTENSIONS:
                continue

            key = os.path.normcase(full_path)
            if key in self.path_set:
                continue

            self.path_set.add(key)
            new_tracks.append(build_track(full_path))

        if source_folder:
            folder_abs = os.path.abspath(source_folder)
            if folder_abs not in self.imported_folders:
                self.imported_folders.append(folder_abs)
                self.imported_folders.sort(key=str.lower)
                self.refresh_folder_list()

        if not new_tracks:
            self.set_status("No new tracks")
            return

        self.tracks.extend(new_tracks)
        self.tracks.sort(key=lambda t: (t.title.lower(), t.path.lower()))

        if current_path:
            self.current_index = self._find_track_index(current_path)

        self.refresh_track_lists()
        self.set_status(f"Added {len(new_tracks)} track{'s' if len(new_tracks) != 1 else ''}")

    def clear_library(self):
        if not self.tracks:
            self.set_status("Library already empty")
            return

        confirm = QMessageBox.question(
            self,
            "Clear Library",
            "Remove all imported tracks from the current library?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if confirm != QMessageBox.Yes:
            return

        self.player.stop()
        self.player.setSource(QUrl())
        self.tracks.clear()
        self.path_set.clear()
        self.current_index = -1
        self._last_duration = 0

        self.refresh_track_lists()
        self._reset_now_playing()
        self.timeline.setRange(0, 1)
        self.timeline.setValue(0)
        self.position_label.setText("0:00")
        self.duration_label.setText("0:00")
        self.set_status("Library cleared")

    # ---------------------------------------------------------------------
    # List rendering
    # ---------------------------------------------------------------------
    def refresh_track_lists(self):
        self._populate_track_list(self.library_list)
        self._populate_track_list(self.queue_list)

    def refresh_folder_list(self):
        self.folder_list.clear()
        if not self.imported_folders:
            item = QListWidgetItem("No folders imported yet.")
            self.folder_list.addItem(item)
            return

        for folder in self.imported_folders:
            item = QListWidgetItem(folder)
            item.setToolTip(folder)
            self.folder_list.addItem(item)

    def _populate_track_list(self, widget: QListWidget):
        widget.clear()

        if not self.tracks:
            empty = QListWidgetItem("No tracks imported. Use Add Files or Add Folder.")
            empty.setFlags(Qt.NoItemFlags)
            empty.setForeground(QColor(MUTED))
            widget.addItem(empty)
            return

        for idx, track in enumerate(self.tracks):
            item = QListWidgetItem()
            item.setData(TRACK_ROLE, track)
            item.setData(INDEX_ROLE, idx)
            item.setData(PLAYING_ROLE, idx == self.current_index)
            item.setToolTip(track.path)
            item.setSizeHint(QSize(100, 70))
            widget.addItem(item)

    def update_playing_highlights(self):
        for widget in (self.library_list, self.queue_list):
            for row in range(widget.count()):
                item = widget.item(row)
                idx = item.data(INDEX_ROLE)
                if idx is not None:
                    item.setData(PLAYING_ROLE, idx == self.current_index)
            widget.viewport().update()

    def _library_item_double_clicked(self, item: QListWidgetItem):
        idx = item.data(INDEX_ROLE)
        if idx is not None:
            self.play_index(idx)

    def _queue_item_double_clicked(self, item: QListWidgetItem):
        idx = item.data(INDEX_ROLE)
        if idx is not None:
            self.play_index(idx)

    # ---------------------------------------------------------------------
    # Transport controls
    # ---------------------------------------------------------------------
    def play_index(self, index: int):
        if not (0 <= index < len(self.tracks)):
            return

        self.current_index = index
        track = self.tracks[index]

        self.player.setSource(QUrl.fromLocalFile(track.path))
        self.player.play()

        self.now_title.setText(track.title)
        self.now_artist.setText(track.artist)
        self.set_status("Playing")
        self.update_playing_highlights()

    def toggle_play(self):
        if not self.tracks:
            self.set_status("Import music first")
            return

        state = self.player.playbackState()

        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return

        if self.current_index < 0:
            self.play_index(0)
            return

        if self.player.source().isEmpty():
            self.play_index(self.current_index)
        else:
            self.player.play()

    def previous_track(self):
        if not self.tracks:
            self.set_status("Queue empty")
            return

        # If more than 4 seconds into a track, restart it first.
        if self.player.position() > 4000:
            self.player.setPosition(0)
            return

        if self.current_index <= 0:
            self.play_index(len(self.tracks) - 1)
        else:
            self.play_index(self.current_index - 1)

    def next_track(self, auto=False):
        if not self.tracks:
            self.set_status("Queue empty")
            return

        if self.current_index < 0:
            self.play_index(0)
            return

        next_index = self.current_index + 1

        if next_index >= len(self.tracks):
            if auto:
                self.player.stop()
                self.player.setPosition(0)
                self.timeline.setValue(0)
                self.position_label.setText("0:00")
                self.set_status("Queue finished")
                return
            next_index = 0

        self.play_index(next_index)

    # ---------------------------------------------------------------------
    # Media signal handlers
    # ---------------------------------------------------------------------
    def on_position_changed(self, position: int):
        if not self.timeline.isDragging():
            self.timeline.setValue(position)
            self.position_label.setText(format_ms(position))

    def on_duration_changed(self, duration: int):
        self._last_duration = max(0, duration)
        self.timeline.setRange(0, max(1, self._last_duration))
        self.duration_label.setText(format_ms(self._last_duration))

    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setText("⏸")
            self.set_status("Playing")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.play_button.setText("▶")
            self.set_status("Paused")
        else:
            self.play_button.setText("▶")

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            QTimer.singleShot(120, lambda: self.next_track(auto=True))

    def on_player_error(self, error, error_string=""):
        if error == QMediaPlayer.Error.NoError:
            return
        msg = error_string or "Playback error"
        self.set_status("Playback error")
        QMessageBox.warning(self, "Playback Error", msg)

    def on_timeline_preview(self, value: int):
        self.position_label.setText(format_ms(value))

    def seek_to(self, value: int):
        if self.player.source().isEmpty():
            return
        self.player.setPosition(value)
        self.position_label.setText(format_ms(value))

    def set_volume_percent(self, percent: int):
        percent = max(0, min(100, int(percent)))
        self.audio_output.setVolume(percent / 100.0)
        self.volume_slider.setValue(percent)
        self.settings_volume_slider.setValue(percent)
        self.volume_value.setText(f"{percent}%")
        self.settings_volume_value.setText(f"{percent}%")

    def on_audio_volume_changed(self, volume: float):
        percent = int(round(volume * 100))
        self.volume_slider.setValue(percent)
        self.settings_volume_slider.setValue(percent)
        self.volume_value.setText(f"{percent}%")
        self.settings_volume_value.setText(f"{percent}%")

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _find_track_index(self, path: str) -> int:
        key = os.path.normcase(os.path.abspath(path))
        for i, track in enumerate(self.tracks):
            if os.path.normcase(os.path.abspath(track.path)) == key:
                return i
        return -1

    def _reset_now_playing(self):
        self.now_title.setText("No track selected")
        self.now_artist.setText("Import music to begin")
        self.play_button.setText("▶")

    def set_status(self, text: str):
        self.status_label.setText(text)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("NeonObsidian")

    window = MediaEngineWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()