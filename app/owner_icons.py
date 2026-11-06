"""Outline icons for the Student Owner rail (Step 31A).

Same line style as the student sidebar (app/icon_shapes.py, drawn by app/sidebar_icons.py) but
kept in their own table so the student sidebar's icon set is untouched. Settings and Log Out
reuse the student icons.
"""
from PySide6.QtGui import QIcon

import app.sidebar_icons as _icons
from app import design_tokens as tk
from app.icon_shapes import ICON_BOX
from app.sidebar_icons import make_nav_icon

OWNER_ICON_SHAPES = {
    # a storefront / shelf: owner overview
    "owner_dashboard": [("path", [("M", 4, 9.5), ("L", 5.5, 4.5), ("L", 18.5, 4.5), ("L", 20, 9.5),
                                  ("C", 20, 11, 18.8, 12, 17.5, 12), ("C", 16.2, 12, 15, 11, 15, 9.5),
                                  ("C", 15, 11, 13.8, 12, 12.5, 12), ("C", 11.2, 12, 10, 11, 10, 9.5),
                                  ("C", 10, 11, 8.8, 12, 7.5, 12), ("C", 6.2, 12, 5, 11, 5, 9.5)]),
                        ("rrect", 5, 12, 14, 8, 1.5), ("rrect", 10, 14.5, 4, 5.5, 1)],
    # a box: my listings
    "my_listings": [("poly", [(12, 3.5), (20, 7.5), (20, 16.5), (12, 20.5), (4, 16.5), (4, 7.5)], True),
                    ("poly", [(4, 7.5), (12, 11.5), (20, 7.5)], False),
                    ("line", 12, 11.5, 12, 20.5)],
    # a request sheet with three review lines
    "incoming_requests": [("rrect", 5, 3.5, 14, 17, 1.5),
                          ("line", 8, 8, 16, 8), ("line", 8, 12, 16, 12),
                          ("line", 8, 16, 14, 16)],
    # two opposite arrows: switch workspace
    "switch": [("line", 4.5, 8, 19, 8), ("poly", [(15.5, 4.5), (19, 8), (15.5, 11.5)], False),
               ("line", 19.5, 16, 5, 16), ("poly", [(8.5, 12.5), (5, 16), (8.5, 19.5)], False)],
}


def owner_icon(key: str, size: int = 24) -> QIcon:
    """The three-look (normal / focused / checked) icon for an owner-rail button."""
    if key not in OWNER_ICON_SHAPES:
        return make_nav_icon(key, size)  # settings, logout: the student icons
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
    scale = _icons.RENDER_SCALE

    def draw(color: str):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.transparent)
        pixmap.setDevicePixelRatio(scale)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size / ICON_BOX, size / ICON_BOX)
        pen = QPen(QColor(color), _icons.STROKE_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for shape in OWNER_ICON_SHAPES[key]:
            painter.drawPath(_icons._build_path(shape))
        painter.end()
        return pixmap

    icon = QIcon()
    normal, focused, checked = (draw(tk.COLOR_TEXT_SECONDARY), draw(tk.COLOR_TEXT_PRIMARY),
                                draw(tk.COLOR_ACCENT_HOVER))
    icon.addPixmap(normal, QIcon.Normal, QIcon.Off)
    icon.addPixmap(focused, QIcon.Active, QIcon.Off)
    icon.addPixmap(checked, QIcon.Normal, QIcon.On)
    icon.addPixmap(checked, QIcon.Active, QIcon.On)
    return icon
