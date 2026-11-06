"""Sizing rules for the floating app container (Step 30A). No Qt code in this file.

The whole student app (sidebar + pages) sits inside one rounded container that floats on a
slightly darker window background. The gap around it grows with the window:

  * default window (1000 x 650)  -> about 20 px
  * laptop (1366 x 768) and up   -> 30 px (the maximum, a fixed design value)
  * at the smallest window size  -> 0 px, because the sidebar needs every pixel of height
    there (tests/test_sidebar.py guarantees nothing overlaps at 500 px).
"""
SHELL_RADIUS = 20        # px: corner radius of the floating container (design token RADIUS_XL)
MAX_MARGIN = 30          # px: widest gap around the container (Step 30A size adjustment)
SMALLEST_WIDTH = 800     # the window's minimum size (MainWindow.setMinimumSize)
SMALLEST_HEIGHT = 500
MIN_OUTER_MARGIN = 12    # px: the Outer Margin slider's range (Settings -> Appearance)
MAX_OUTER_MARGIN = 48


def shell_margin(width: int, height: int) -> int:
    """The gap (px) on all four sides for a dashboard of this size. Always 0..MAX_MARGIN."""
    from_height = (height - SMALLEST_HEIGHT) // 6
    from_width = (width - SMALLEST_WIDTH) // 10
    return int(max(0, min(MAX_MARGIN, from_height, from_width)))


def clamp_outer_margin(value) -> int:
    """Keep a chosen Outer Margin inside the slider's range (12-48 px)."""
    return int(max(MIN_OUTER_MARGIN, min(MAX_OUTER_MARGIN, int(value))))


def effective_margin(chosen, width: int, height: int) -> int:
    """The gap (px) actually used around the container.

    `chosen` is the student's saved Outer Margin, or None for the automatic gap (shell_margin).
    A chosen margin is never allowed to squeeze the container below the smallest window size
    (800 x 500), where the sidebar and pages are known to fit. So in a small window the gap is
    reduced for as long as needed (down to 0), and nothing is clipped. Always 0..48.
    """
    if chosen is None:
        return shell_margin(width, height)
    room = min((height - SMALLEST_HEIGHT) // 2, (width - SMALLEST_WIDTH) // 2)
    return int(max(0, min(clamp_outer_margin(chosen), room)))
