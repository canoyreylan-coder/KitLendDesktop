"""Paints the sidebar's outline icons (Stage 1B). The shapes live in app/icon_shapes.py.

Icons are drawn with QPainter at 2x resolution, so they stay crisp on high-DPI screens
and no image files are needed.

One icon (QIcon) has three looks:
  * normal  - quiet, secondary text color
  * focused - brighter (keyboard focus)
  * checked - lavender accent: the page that is open
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from app import design_tokens as tk
from app.icon_shapes import ICON_BOX, STROKE_WIDTH, shapes_for

RENDER_SCALE = 2  # pixmaps are drawn at 2x and marked with a device pixel ratio of 2


def _build_path(shape) -> QPainterPath:
    path = QPainterPath()
    kind = shape[0]
    if kind == "rrect":
        _, x, y, w, h, r = shape
        path.addRoundedRect(QRectF(x, y, w, h), r, r)
    elif kind == "circle":
        _, cx, cy, r = shape
        path.addEllipse(QPointF(cx, cy), r, r)
    elif kind == "line":
        path.moveTo(shape[1], shape[2])
        path.lineTo(shape[3], shape[4])
    elif kind == "poly":
        points = shape[1]
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        if shape[2]:
            path.closeSubpath()
    elif kind == "path":
        for command in shape[1]:
            op, numbers = command[0], command[1:]
            if op == "M":
                path.moveTo(*numbers)
            elif op == "L":
                path.lineTo(*numbers)
            elif op == "C":
                path.cubicTo(*numbers)
            elif op == "Z":
                path.closeSubpath()
    return path


def render_icon_pixmap(key: str, color: str, size: int = 24) -> QPixmap:
    """One outline icon in one color, as a transparent pixmap of `size` logical pixels."""
    pixmap = QPixmap(size * RENDER_SCALE, size * RENDER_SCALE)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(RENDER_SCALE)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / ICON_BOX, size / ICON_BOX)
    pen = QPen(QColor(color), STROKE_WIDTH)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    for shape in shapes_for(key):
        painter.drawPath(_build_path(shape))
    painter.end()
    return pixmap


def make_nav_icon(key: str, size: int = 24) -> QIcon:
    """The three-look icon used by the sidebar's checkable buttons."""
    icon = QIcon()
    normal = render_icon_pixmap(key, tk.COLOR_TEXT_SECONDARY, size)
    focused = render_icon_pixmap(key, tk.COLOR_TEXT_PRIMARY, size)
    checked = render_icon_pixmap(key, tk.COLOR_ACCENT_HOVER, size)
    icon.addPixmap(normal, QIcon.Normal, QIcon.Off)
    icon.addPixmap(focused, QIcon.Active, QIcon.Off)
    icon.addPixmap(checked, QIcon.Normal, QIcon.On)
    icon.addPixmap(checked, QIcon.Active, QIcon.On)
    return icon


def circular_pixmap(source, size: int):
    """A profile photo cropped to a circle, or None if the image is missing or unreadable.

    `source` is a file path or a QPixmap. The photo is scaled to fill the circle and the
    overflow is cropped, so photos of any shape look right.
    """
    pixmap = source if isinstance(source, QPixmap) else QPixmap(str(source))
    if pixmap.isNull():
        return None
    pixmap = pixmap.scaled(size * RENDER_SCALE, size * RENDER_SCALE,
                           Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    side = size * RENDER_SCALE
    x, y = (pixmap.width() - side) // 2, (pixmap.height() - side) // 2
    pixmap = pixmap.copy(x, y, side, side)
    result = QPixmap(side, side)
    result.fill(Qt.transparent)
    result.setDevicePixelRatio(RENDER_SCALE)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(clip)
    painter.drawPixmap(QRectF(0, 0, size, size), pixmap, QRectF(0, 0, side, side))
    painter.end()
    return result
