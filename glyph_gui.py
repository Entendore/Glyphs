"""
Glyph Generator - PySide6 Graphical Interface
"""

import json
import logging
import os
import random
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QCheckBox, QLineEdit, QFileDialog, QProgressBar,
    QMessageBox, QScrollArea, QGridLayout, QSplitter,
)
from PySide6.QtCore import Qt, QThread, Signal, QByteArray
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor

from glyph_core import (
    GlyphConfig, ColorPalette, SymmetryMode, OutputFormat,
    VALID_SHAPES, generate_glyphs, generate_single_to_bytes,
    PIL_AVAILABLE, SVGWRITE_AVAILABLE, NUMBA_AVAILABLE,
    PALETTE_GENERATORS, CUSTOM_PALETTE, hex_to_rgb,
)

logger = logging.getLogger("glyph")


def _sample_palette(palette: ColorPalette, n: int = 12) -> list:
    """Draw n random samples from a palette generator, return list of (r,g,b)."""
    if palette == ColorPalette.CUSTOM:
        return [hex_to_rgb(c) for c in CUSTOM_PALETTE[:n]]
    gen = PALETTE_GENERATORS[palette]
    return [gen() for _ in range(n)]


def _make_palette_image(colors: list, width: int = 280, height: int = 28) -> QImage:
    """Create a horizontal strip image with one color swatch per entry."""
    img = QImage(width, height, QImage.Format_RGB32)
    img.fill(QColor(240, 240, 240))
    painter = QPainter(img)
    n = len(colors)
    if n == 0:
        painter.end()
        return img
    swatch_w = width / n
    for i, (r, g, b) in enumerate(colors):
        painter.fillRect(int(i * swatch_w), 0, int(swatch_w) + 1, height, QColor(r, g, b))
    # thin border
    painter.setPen(QColor(180, 180, 180))
    painter.drawRect(0, 0, width - 1, height - 1)
    painter.end()
    return img


class PreviewWorker(QThread):
    preview_ready = Signal(bytes)

    def __init__(self, config: GlyphConfig, use_numba: bool):
        super().__init__()
        self.config = config
        self.use_numba = use_numba

    def run(self):
        try:
            data = generate_single_to_bytes(self.config, use_numba=self.use_numba)
            if data:
                self.preview_ready.emit(data)
        except Exception as e:
            logger.error("Preview failed: %s", e, exc_info=True)


class BatchWorker(QThread):
    progress = Signal(int, int, str)
    finished_sig = Signal(int, int)
    error = Signal(str)

    def __init__(self, config: GlyphConfig, output_dir: str, count: int, use_numba: bool):
        super().__init__()
        self.config = config
        self.output_dir = output_dir
        self.count = count
        self.use_numba = use_numba

    def run(self):
        try:
            files = generate_glyphs(
                self.config, self.output_dir, self.count,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                use_numba=self.use_numba)
            self.finished_sig.emit(len(files), self.count)
        except Exception as e:
            logger.error("Batch failed: %s", e, exc_info=True)
            self.error.emit(str(e))


class GlyphGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Glyph Generator")
        self.setMinimumSize(920, 720)
        self._preview_worker = None
        self._batch_worker = None
        self._setup_ui()
        self._update_palette_preview()
        self._update_preview()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        ml = QHBoxLayout(central)
        ml.setContentsMargins(6, 6, 6, 6)
        splitter = QSplitter(Qt.Horizontal)
        ml.addWidget(splitter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(330)
        scroll.setMaximumWidth(420)
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setSpacing(8)
        scroll.setWidget(sw)
        splitter.addWidget(scroll)

        rp = QWidget()
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(rp)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # --- Output ---
        g1 = QGroupBox("Output")
        gl = QGridLayout(g1)
        gl.addWidget(QLabel("Format:"), 0, 0)
        self.cb_fmt = QComboBox()
        self.cb_fmt.addItems(["svg", "png"])
        self.cb_fmt.currentTextChanged.connect(self._update_preview)
        gl.addWidget(self.cb_fmt, 0, 1)
        gl.addWidget(QLabel("Size:"), 1, 0)
        self.sp_size = QSpinBox()
        self.sp_size.setRange(64, 4096)
        self.sp_size.setSingleStep(64)
        self.sp_size.setValue(512)
        self.sp_size.valueChanged.connect(self._update_preview)
        gl.addWidget(self.sp_size, 1, 1)
        if NUMBA_AVAILABLE:
            self.chk_numba = QCheckBox("Numba acceleration")
            self.chk_numba.setChecked(True)
            self.chk_numba.setToolTip("Use Numba JIT for faster PNG rendering")
            self.chk_numba.stateChanged.connect(self._update_preview)
            gl.addWidget(self.chk_numba, 2, 0, 1, 2)
        sl.addWidget(g1)

        # --- Style ---
        g2 = QGroupBox("Style")
        gl2 = QGridLayout(g2)
        gl2.addWidget(QLabel("Palette:"), 0, 0)
        self.cb_pal = QComboBox()
        self.cb_pal.addItems([p.value for p in ColorPalette])
        self.cb_pal.currentTextChanged.connect(self._on_palette_changed)
        gl2.addWidget(self.cb_pal, 0, 1)

        # Palette color preview strip
        self.lbl_palette_preview = QLabel()
        self.lbl_palette_preview.setFixedHeight(32)
        self.lbl_palette_preview.setStyleSheet("border: 1px solid #aaa; border-radius: 3px;")
        gl2.addWidget(self.lbl_palette_preview, 1, 0, 1, 2)

        gl2.addWidget(QLabel("Background:"), 2, 0)
        self.cb_bg = QComboBox()
        self.cb_bg.addItems(["white", "black", "transparent"])
        self.cb_bg.setEditable(True)
        self.cb_bg.currentTextChanged.connect(self._update_preview)
        gl2.addWidget(self.cb_bg, 2, 1)
        gl2.addWidget(QLabel("Opacity:"), 3, 0)
        self.sp_opa = QDoubleSpinBox()
        self.sp_opa.setRange(0, 1)
        self.sp_opa.setSingleStep(0.05)
        self.sp_opa.setValue(1.0)
        self.sp_opa.valueChanged.connect(self._update_preview)
        gl2.addWidget(self.sp_opa, 3, 1)
        sl.addWidget(g2)

        # --- Symmetry ---
        g3 = QGroupBox("Symmetry")
        gl3 = QGridLayout(g3)
        gl3.addWidget(QLabel("Mode:"), 0, 0)
        self.cb_sym = QComboBox()
        self.cb_sym.addItems([s.value for s in SymmetryMode])
        self.cb_sym.setCurrentText("kaleidoscope")
        self.cb_sym.currentTextChanged.connect(self._on_sym)
        gl3.addWidget(self.cb_sym, 0, 1)
        gl3.addWidget(QLabel("Segments:"), 1, 0)
        self.sp_seg = QSpinBox()
        self.sp_seg.setRange(2, 64)
        self.sp_seg.setValue(8)
        self.sp_seg.valueChanged.connect(self._update_preview)
        gl3.addWidget(self.sp_seg, 1, 1)
        sl.addWidget(g3)

        # --- Grid & Shapes ---
        g4 = QGroupBox("Grid & Shapes")
        gl4 = QGridLayout(g4)
        gl4.addWidget(QLabel("Grid size:"), 0, 0)
        self.sp_grid = QSpinBox()
        self.sp_grid.setRange(4, 128)
        self.sp_grid.setValue(16)
        self.sp_grid.valueChanged.connect(self._update_preview)
        gl4.addWidget(self.sp_grid, 0, 1)
        gl4.addWidget(QLabel("Min/cell:"), 1, 0)
        self.sp_min = QSpinBox()
        self.sp_min.setRange(0, 20)
        self.sp_min.setValue(1)
        self.sp_min.valueChanged.connect(self._update_preview)
        gl4.addWidget(self.sp_min, 1, 1)
        gl4.addWidget(QLabel("Max/cell:"), 2, 0)
        self.sp_max = QSpinBox()
        self.sp_max.setRange(1, 20)
        self.sp_max.setValue(3)
        self.sp_max.valueChanged.connect(self._update_preview)
        gl4.addWidget(self.sp_max, 2, 1)
        gl4.addWidget(QLabel("Stroke:"), 3, 0)
        self.sp_stk = QSpinBox()
        self.sp_stk.setRange(1, 20)
        self.sp_stk.setValue(1)
        gl4.addWidget(self.sp_stk, 3, 1)
        gl4.addWidget(QLabel("Shapes:"), 4, 0)
        shw = QWidget()
        shl = QVBoxLayout(shw)
        shl.setContentsMargins(0, 0, 0, 0)
        shl.setSpacing(2)
        self.sh_chk = {}
        for s in VALID_SHAPES:
            cb = QCheckBox(s)
            cb.setChecked(s in {'rect', 'circle', 'line', 'triangle'})
            cb.stateChanged.connect(self._update_preview)
            self.sh_chk[s] = cb
            shl.addWidget(cb)
        gl4.addWidget(shw, 4, 1)
        sl.addWidget(g4)

        # --- Seed ---
        g5 = QGroupBox("Seed")
        h5 = QHBoxLayout(g5)
        self.chk_seed = QCheckBox("Fixed:")
        self.sp_seed = QSpinBox()
        self.sp_seed.setRange(0, 999999)
        self.sp_seed.setValue(42)
        self.sp_seed.setEnabled(False)
        self.chk_seed.toggled.connect(self.sp_seed.setEnabled)
        self.chk_seed.toggled.connect(self._update_preview)
        self.sp_seed.valueChanged.connect(self._update_preview)
        h5.addWidget(self.chk_seed)
        h5.addWidget(self.sp_seed)
        sl.addWidget(g5)

        b1 = QPushButton("\U0001f3b2  Randomize")
        b1.clicked.connect(self._rand_seed)
        sl.addWidget(b1)
        b2 = QPushButton("\U0001f504  Refresh")
        b2.clicked.connect(self._update_preview)
        sl.addWidget(b2)
        sl.addStretch()

        # --- Preview ---
        gp = QGroupBox("Preview")
        pvl = QVBoxLayout(gp)
        self.lbl_pv = QLabel("Generating...")
        self.lbl_pv.setAlignment(Qt.AlignCenter)
        self.lbl_pv.setMinimumSize(256, 256)
        self.lbl_pv.setStyleSheet("background:#f0f0f0;border:1px solid #ccc;")
        pvl.addWidget(self.lbl_pv)
        rl.addWidget(gp)

        # --- Batch ---
        gb = QGroupBox("Batch Generation")
        gbl = QGridLayout(gb)
        gbl.addWidget(QLabel("Count:"), 0, 0)
        self.sp_cnt = QSpinBox()
        self.sp_cnt.setRange(1, 1000)
        self.sp_cnt.setValue(10)
        gbl.addWidget(self.sp_cnt, 0, 1)
        gbl.addWidget(QLabel("Output:"), 1, 0)
        hd = QHBoxLayout()
        self.le_out = QLineEdit("glyphs_output")
        bb = QPushButton("Browse\u2026")
        bb.clicked.connect(self._browse)
        hd.addWidget(self.le_out)
        hd.addWidget(bb)
        gbl.addLayout(hd, 1, 1)
        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        gbl.addWidget(self.pbar, 2, 0, 1, 2)
        self.btn_gen = QPushButton("\u26a1  Generate Batch")
        self.btn_gen.setMinimumHeight(40)
        self.btn_gen.clicked.connect(self._start_batch)
        gbl.addWidget(self.btn_gen, 3, 0, 1, 2)
        rl.addWidget(gb)

        # --- Config buttons ---
        hc = QHBoxLayout()
        bs = QPushButton("\U0001f4be Save Config")
        bs.clicked.connect(self._save_config)
        bl = QPushButton("\U0001f4c2 Load Config")
        bl.clicked.connect(self._load_config)
        hc.addWidget(bs)
        hc.addWidget(bl)
        rl.addLayout(hc)
        rl.addStretch()

        self.statusBar().showMessage("Ready")
        self._on_sym()

    # -------------------------------------------------------------- palette preview
    def _on_palette_changed(self, text: str):
        self._update_palette_preview()
        self._update_preview()

    def _update_palette_preview(self):
        """Sample 12 colors from the selected palette and draw a swatch strip."""
        try:
            pal = ColorPalette(self.cb_pal.currentText())
        except ValueError:
            self.lbl_palette_preview.setPixmap(QPixmap())
            return
        # Sample with a fixed seed so the strip is stable while browsing
        old_state = random.getstate()
        random.seed(12345)
        colors = _sample_palette(pal, n=12)
        random.setstate(old_state)

        img = _make_palette_image(colors, width=280, height=28)
        self.lbl_palette_preview.setPixmap(QPixmap.fromImage(img))

    # -------------------------------------------------------------- helpers
    def _use_numba(self) -> bool:
        if not NUMBA_AVAILABLE:
            return False
        if hasattr(self, 'chk_numba'):
            return self.chk_numba.isChecked()
        return True

    def _get_config(self) -> GlyphConfig:
        shapes = [s for s, cb in self.sh_chk.items() if cb.isChecked()] or ['rect']
        return GlyphConfig(
            width=self.sp_size.value(), height=self.sp_size.value(),
            grid_size=self.sp_grid.value(),
            max_shapes_per_cell=self.sp_max.value(), min_shapes_per_cell=self.sp_min.value(),
            symmetry=SymmetryMode(self.cb_sym.currentText()),
            rotation_segments=self.sp_seg.value(),
            color_palette=ColorPalette(self.cb_pal.currentText()),
            background_color=self.cb_bg.currentText(), shape_types=shapes,
            output_format=OutputFormat(self.cb_fmt.currentText()),
            seed=self.sp_seed.value() if self.chk_seed.isChecked() else None,
            opacity=self.sp_opa.value(), stroke_width=self.sp_stk.value())

    def _on_sym(self, *_):
        self.sp_seg.setEnabled(self.cb_sym.currentText() in ('radial', 'kaleidoscope'))
        self._update_preview()

    def _rand_seed(self):
        self.chk_seed.setChecked(True)
        self.sp_seed.setValue(random.randint(0, 999999))

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Output Directory")
        if d:
            self.le_out.setText(d)

    def _update_preview(self, *_):
        if not PIL_AVAILABLE:
            self.lbl_pv.setText("Pillow not available.\npip install Pillow")
            return
        if self._preview_worker and self._preview_worker.isRunning():
            self._preview_worker.terminate()
            self._preview_worker.wait()
        self._preview_worker = PreviewWorker(self._get_config(), self._use_numba())
        self._preview_worker.preview_ready.connect(self._show_pv)
        self._preview_worker.start()

    def _show_pv(self, data: bytes):
        qi = QImage()
        qi.loadFromData(QByteArray(data), "PNG")
        self.lbl_pv.setPixmap(QPixmap.fromImage(qi).scaled(
            self.lbl_pv.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.statusBar().showMessage("Preview updated")

    def _start_batch(self):
        if self._batch_worker and self._batch_worker.isRunning():
            QMessageBox.warning(self, "Busy", "Already running")
            return
        cfg = self._get_config()
        out = self.le_out.text().strip()
        if not out:
            QMessageBox.warning(self, "Error", "Set output dir")
            return
        cnt = self.sp_cnt.value()
        fmt = cfg.output_format.value
        if fmt == 'png' and not PIL_AVAILABLE:
            QMessageBox.critical(self, "Error", "pip install Pillow")
            return
        if fmt == 'svg' and not SVGWRITE_AVAILABLE:
            QMessageBox.critical(self, "Error", "pip install svgwrite")
            return
        un = self._use_numba() and fmt == 'png'
        logger.info("Batch: %d glyphs -> %s (numba=%s)", cnt, out, un)
        print(f"[GUI] Batch: {cnt} glyphs -> {out} (numba={un})", file=sys.stderr)
        self.btn_gen.setEnabled(False)
        self.pbar.setValue(0)
        self.statusBar().showMessage("Generating\u2026")
        self._batch_worker = BatchWorker(cfg, out, cnt, un)
        self._batch_worker.progress.connect(self._on_prog)
        self._batch_worker.finished_sig.connect(self._on_done)
        self._batch_worker.error.connect(self._on_err)
        self._batch_worker.start()

    def _on_prog(self, c, t, msg):
        self.pbar.setValue(int(c / t * 100))
        tag = "FAIL" if ':' in msg else " OK "
        print(f"[GUI] [{c}/{t}] {tag}  {msg}", file=sys.stderr)
        self.statusBar().showMessage(f"[{c}/{t}] {msg}")

    def _on_done(self, g, t):
        self.btn_gen.setEnabled(True)
        self.pbar.setValue(100)
        msg = f"Done: {g}/{t} glyphs"
        self.statusBar().showMessage(msg)
        print(f"[GUI] {msg}", file=sys.stderr)
        QMessageBox.information(self, "Complete", f"Generated {g}/{t} glyphs.")

    def _on_err(self, msg):
        self.btn_gen.setEnabled(True)
        self.statusBar().showMessage("Error")
        print(f"[GUI] ERROR: {msg}", file=sys.stderr)
        QMessageBox.critical(self, "Error", msg)

    def _save_config(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save Config", "glyph_config.json", "JSON (*.json)")
        if p:
            with open(p, 'w') as f:
                json.dump(self._get_config().to_dict(), f, indent=2)
            logger.info("Config saved: %s", p)
            self.statusBar().showMessage(f"Saved to {p}")

    def _load_config(self):
        p, _ = QFileDialog.getOpenFileName(self, "Load Config", "", "JSON (*.json)")
        if not p:
            return
        try:
            with open(p) as f:
                d = json.load(f)
            self._apply_cfg(GlyphConfig.from_dict(d))
            logger.info("Config loaded: %s", p)
            self.statusBar().showMessage(f"Loaded from {p}")
        except Exception as e:
            logger.error("Load failed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _apply_cfg(self, c: GlyphConfig):
        self.cb_fmt.setCurrentText(c.output_format.value)
        self.sp_size.setValue(c.width)
        self.cb_pal.setCurrentText(c.color_palette.value)
        self.cb_bg.setCurrentText(c.background_color)
        self.sp_opa.setValue(c.opacity)
        self.cb_sym.setCurrentText(c.symmetry.value)
        self.sp_seg.setValue(c.rotation_segments)
        self.sp_grid.setValue(c.grid_size)
        self.sp_min.setValue(c.min_shapes_per_cell)
        self.sp_max.setValue(c.max_shapes_per_cell)
        self.sp_stk.setValue(c.stroke_width)
        for s, cb in self.sh_chk.items():
            cb.setChecked(s in c.shape_types)
        if c.seed is not None:
            self.chk_seed.setChecked(True)
            self.sp_seed.setValue(c.seed)
        else:
            self.chk_seed.setChecked(False)
        self._on_sym()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.lbl_pv.pixmap():
            self.lbl_pv.setPixmap(self.lbl_pv.pixmap().scaled(
                self.lbl_pv.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def closeEvent(self, e):
        for w in (self._preview_worker, self._batch_worker):
            if w and w.isRunning():
                w.terminate()
                w.wait()
        super().closeEvent(e)


def run_gui():
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)-5s  %(message)s',
        stream=sys.stderr,
        force=True,
    )
    logger.info("Launching GUI (numba=%s)", NUMBA_AVAILABLE)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = GlyphGUI()
    w.show()
    sys.exit(app.exec())