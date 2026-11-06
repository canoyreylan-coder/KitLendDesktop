"""Outline icon shapes for the compact sidebar (Stage 1B). No Qt in this file.

Every icon is a short list of simple shapes drawn as 1.75px outlines (no fills) inside a
24 x 24 box, so all icons share one clean, consistent line style. app/sidebar_icons.py
paints them with QPainter; keeping the shapes as plain data means no image files are
needed and the shapes can be tested without a window.

Shape formats
  ("rrect", x, y, width, height, radius)
  ("circle", cx, cy, radius)
  ("line", x1, y1, x2, y2)
  ("poly", [(x, y), ...], closed)
  ("path", [("M", x, y), ("L", x, y), ("C", x1, y1, x2, y2, x, y), ("Z",)])
"""
import math

ICON_BOX = 24      # every shape lives inside 0..24
STROKE_WIDTH = 1.75


def _star(cx: float, cy: float, outer: float, inner: float) -> list:
    points = []
    for i in range(10):
        radius = outer if i % 2 == 0 else inner
        angle = -math.pi / 2 + i * math.pi / 5
        points.append((round(cx + radius * math.cos(angle), 3),
                       round(cy + radius * math.sin(angle), 3)))
    return points


def _slider(y: float, knob_x: float) -> list:
    """One settings 'slider' row: a line with a gap around a small round knob."""
    return [("line", 4, y, knob_x - 3.1, y), ("line", knob_x + 3.1, y, 20, y),
            ("circle", knob_x, y, 2.2)]


ICON_SHAPES = {
    # four rounded tiles
    "dashboard": [("rrect", 3.5, 3.5, 7, 7, 2), ("rrect", 13.5, 3.5, 7, 7, 2),
                  ("rrect", 3.5, 13.5, 7, 7, 2), ("rrect", 13.5, 13.5, 7, 7, 2)],
    # magnifying glass
    "catalog": [("circle", 10.5, 10.5, 6.5), ("line", 15.4, 15.4, 20.5, 20.5)],
    # star
    "my_list": [("poly", _star(12, 12.8, 9, 4.1), True)],
    # clipboard with lines
    "my_requests": [("rrect", 5, 3.5, 14, 17.5, 2.5), ("line", 8.5, 9, 15.5, 9),
                    ("line", 8.5, 13, 15.5, 13), ("line", 8.5, 17, 12.5, 17)],
    # open book
    "borrowings": [("path", [("M", 12, 6.5), ("C", 10, 5, 7, 4.6, 4, 5), ("L", 4, 18),
                             ("C", 7, 17.6, 10, 18, 12, 19.5), ("C", 14, 18, 17, 17.6, 20, 18),
                             ("L", 20, 5), ("C", 17, 4.6, 14, 5, 12, 6.5), ("Z",)]),
                   ("line", 12, 6.5, 12, 19.5)],
    # bookmark
    "reservations": [("poly", [(7, 3.5), (17, 3.5), (17, 20.5), (12, 16.5), (7, 20.5)], True)],
    # bell
    "notifications": [("path", [("M", 6, 16.5), ("L", 6, 11), ("C", 6, 7.7, 8.7, 5, 12, 5),
                                ("C", 15.3, 5, 18, 7.7, 18, 11), ("L", 18, 16.5),
                                ("L", 19.5, 18), ("L", 4.5, 18), ("Z",)]),
                      ("line", 12, 3, 12, 5),
                      ("path", [("M", 10, 20.5), ("C", 10.6, 21.7, 13.4, 21.7, 14, 20.5)])],
    # three sliders
    "settings": _slider(6, 9) + _slider(12, 15) + _slider(18, 8),
    # door with an arrow leaving it (Log Out)
    "logout": [("path", [("M", 10, 4), ("L", 6, 4), ("C", 4.9, 4, 4, 4.9, 4, 6), ("L", 4, 18),
                         ("C", 4, 19.1, 4.9, 20, 6, 20), ("L", 10, 20)]),
               ("line", 10, 12, 20, 12), ("poly", [(16, 8), (20, 12), (16, 16)], False)],
}


def shapes_for(key: str) -> list:
    """The shapes for one icon key. Raises KeyError for an unknown key."""
    return ICON_SHAPES[key]


def all_points(key: str):
    """Every coordinate pair used by an icon (used by tests to check the 24 x 24 box)."""
    for shape in shapes_for(key):
        kind = shape[0]
        if kind == "rrect":
            _, x, y, w, h, _r = shape
            yield (x, y)
            yield (x + w, y + h)
        elif kind == "circle":
            _, cx, cy, r = shape
            yield (cx - r, cy - r)
            yield (cx + r, cy + r)
        elif kind == "line":
            yield (shape[1], shape[2])
            yield (shape[3], shape[4])
        elif kind == "poly":
            yield from shape[1]
        elif kind == "path":
            for command in shape[1]:
                numbers = command[1:]
                for i in range(0, len(numbers), 2):
                    yield (numbers[i], numbers[i + 1])
