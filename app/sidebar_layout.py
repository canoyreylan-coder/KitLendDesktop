"""Freeform sidebar layout model (Step 14F). Plain Python: no PySide6, no database.

Every sidebar item (profile avatar, the eight page icons, Log Out) can have its own
  * size      - the icon size in pixels (the avatar's size is its diameter), and
  * position  - where its clickable square sits inside the rail.

An item that has never been customised simply sits at its DEFAULT place, which is the same
evenly-spread look as Step 14E. Customising one item never moves or resizes another.

How positions are stored (so a resized window never loses them):
  * x      - pixels from the left edge of the rail
  * y      - pixels from the TOP edge of the rail when anchor == "top",
             or from the BOTTOM edge when anchor == "bottom"
  * anchor - legacy layouts may contain top/bottom anchors. New manual editing freezes
             ALL visible items at top-relative coordinates, so individual gaps stay the
             same when the window grows. A smaller window may compact items visually.

Safety rules:
  * An item can never leave the visible rail (it is clamped, only for DISPLAY: the saved
    numbers are never overwritten by a window resize).
  * A move or resize that would cover another item by more than MAX_OVERLAP_RATIO of the
    smaller square is refused (the method returns False and changes nothing).
"""

SIDEBAR_WIDTH = 72  # keep in sync with app.theme.SIDEBAR_WIDTH (a test checks this)

KEY_AVATAR = "avatar"
KEY_LOGOUT = "logout"
NAV_KEYS = ("dashboard", "catalog", "my_list", "my_requests", "borrowings",
            "reservations", "notifications", "settings")
# Top to bottom, the same order as Step 14E.
ITEM_KEYS = (KEY_AVATAR,) + NAV_KEYS + (KEY_LOGOUT,)

ITEM_LABELS = {
    KEY_AVATAR: "Profile avatar",
    "dashboard": "Dashboard",
    "catalog": "Browse Catalog",
    "my_list": "My List",
    "my_requests": "My Requests",
    "borrowings": "My Borrowings",
    "reservations": "Reservations",
    "notifications": "Notifications",
    "settings": "Settings",
    KEY_LOGOUT: "Log Out",
}

# Sizes (pixels). The defaults are the Step 14E look: 24px icons in 46px squares, 40px avatar.
ICON_PADDING = 22            # a page/Log Out square is the icon size + this
DEFAULT_ICON_SIZE = 24
DEFAULT_AVATAR_SIZE = 40
MIN_ICON_SIZE, MAX_ICON_SIZE = 16, 44      # 44 + 22 = 66, still inside the 72px rail
MIN_AVATAR_SIZE, MAX_AVATAR_SIZE = 28, 56

TOP_MARGIN = 16
BOTTOM_MARGIN = 14
MIN_DEFAULT_GAP = 2
MAX_OVERLAP_RATIO = 0.25     # more than this share of the smaller square covered = refused
MAX_SAVED_OFFSET = 5000      # sanity limit when reading saved data
LAYOUT_VERSION = 1

ANCHOR_TOP = "top"
ANCHOR_BOTTOM = "bottom"


def default_size(key: str) -> int:
    return DEFAULT_AVATAR_SIZE if key == KEY_AVATAR else DEFAULT_ICON_SIZE


def size_range(key: str) -> tuple:
    """(minimum, maximum) size for one item."""
    if key == KEY_AVATAR:
        return MIN_AVATAR_SIZE, MAX_AVATAR_SIZE
    return MIN_ICON_SIZE, MAX_ICON_SIZE


def box_for(key: str, size: int) -> int:
    """The side of the clickable square for an item of this size."""
    return size if key == KEY_AVATAR else size + ICON_PADDING


def _check_key(key: str):
    if key not in ITEM_KEYS:
        raise KeyError(f"Unknown sidebar item: {key!r}")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def overlap_ratio(a: tuple, b: tuple) -> float:
    """Share of the SMALLER square that is covered. Rects are (x, y, side)."""
    ax, ay, aw = a
    bx, by, bw = b
    width = min(ax + aw, bx + bw) - max(ax, bx)
    height = min(ay + aw, by + bw) - max(ay, by)
    if width <= 0 or height <= 0:
        return 0.0
    smaller = min(aw, bw)
    return (width * height) / float(smaller * smaller)


def default_geometry(height: int) -> dict:
    """{key: (x, y, box)} - the evenly spread Step 14E look for a rail `height` pixels tall.

    Always computed from the DEFAULT sizes, so changing one item never shifts the others.
    """
    height = max(int(height), 1)
    nav_box = box_for("dashboard", DEFAULT_ICON_SIZE)
    avatar_box = box_for(KEY_AVATAR, DEFAULT_AVATAR_SIZE)
    centered = lambda box: (SIDEBAR_WIDTH - box) // 2  # noqa: E731
    result = {KEY_AVATAR: (centered(avatar_box), TOP_MARGIN, avatar_box)}
    logout_y = max(height - BOTTOM_MARGIN - nav_box, 0)
    result[KEY_LOGOUT] = (centered(nav_box), logout_y, nav_box)
    first = TOP_MARGIN + avatar_box  # equal gaps: avatar | icons ... | Log Out
    span = logout_y - first
    gap = (span - len(NAV_KEYS) * nav_box) / float(len(NAV_KEYS) + 1)
    gap = max(gap, MIN_DEFAULT_GAP)
    for index, key in enumerate(NAV_KEYS):
        y = int(round(first + gap + index * (nav_box + gap)))
        result[key] = (centered(nav_box), y, nav_box)
    return result


class SidebarLayout:
    """The per-item sizes and positions. Items that were never customised hold nothing."""

    def __init__(self):
        self._items = {}  # key -> {"size": int, "x": int, "y": int, "anchor": str} (any subset)

    # ---------- copying, comparing, saving ----------
    def copy(self) -> "SidebarLayout":
        other = SidebarLayout()
        other._items = {key: dict(entry) for key, entry in self._items.items()}
        return other

    def __eq__(self, other):
        return isinstance(other, SidebarLayout) and self._items == other._items

    def is_default(self) -> bool:
        return not self._items

    def customised_keys(self) -> list:
        return [key for key in ITEM_KEYS if key in self._items]

    def has_position(self, key: str) -> bool:
        return "x" in self._items.get(key, {})

    def has_size(self, key: str) -> bool:
        return "size" in self._items.get(key, {})

    def to_dict(self) -> dict:
        return {"version": LAYOUT_VERSION,
                "items": {key: dict(self._items[key]) for key in ITEM_KEYS if key in self._items}}

    @classmethod
    def from_dict(cls, data) -> "SidebarLayout":
        """Tolerant reader: anything damaged or unknown is ignored, never an error."""
        layout = cls()
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, dict):
            return layout
        for key in ITEM_KEYS:
            raw = items.get(key)
            if not isinstance(raw, dict):
                continue
            entry = {}
            low, high = size_range(key)
            if _is_int(raw.get("size")) and low <= raw["size"] <= high:
                entry["size"] = raw["size"]
            x, y, anchor = raw.get("x"), raw.get("y"), raw.get("anchor")
            if (_is_int(x) and _is_int(y) and anchor in (ANCHOR_TOP, ANCHOR_BOTTOM)
                    and 0 <= x <= SIDEBAR_WIDTH and 0 <= y <= MAX_SAVED_OFFSET):
                entry.update(x=x, y=y, anchor=anchor)
            if entry:
                layout._items[key] = entry
        return layout

    # ---------- reading ----------
    def size_of(self, key: str) -> int:
        _check_key(key)
        return self._items.get(key, {}).get("size", default_size(key))

    def geometry(self, height: int) -> dict:
        """{key: (x, y, box)} for a rail `height` pixels tall, always inside the rail."""
        height = max(int(height), 1)
        defaults = default_geometry(height)
        result = {}
        for key in ITEM_KEYS:
            entry = self._items.get(key, {})
            size = entry.get("size", default_size(key))
            box = box_for(key, size)
            if "x" in entry:
                x = entry["x"]
                y = entry["y"] if entry["anchor"] == ANCHOR_TOP else height - box - entry["y"]
            else:
                dx, dy, dbox = defaults[key]  # grow/shrink around the default centre
                x = dx + (dbox - box) // 2
                y = dy + (dbox - box) // 2
            result[key] = (clamp(x, 0, max(SIDEBAR_WIDTH - box, 0)),
                           clamp(y, 0, max(height - box, 0)), box)
        return result

    def display_geometry(self, height: int) -> dict:
        """Collision-safe positions for drawing the sidebar at the current height.

        A manually placed icon can be anchored to the top or bottom. When the
        window becomes shorter, independent anchors can pull icons on top of
        each other. Resolve *display-only* vertical collisions while keeping
        saved coordinates, sizes and order untouched. Restoring the window
        restores the exact original placement.
        """
        preferred = self.geometry(height)
        order = sorted(ITEM_KEYS, key=lambda key: (preferred[key][1], ITEM_KEYS.index(key)))

        def intersects(a, b):
            ax, ay, aw = a
            bx, by, bw = b
            return ax < bx + bw and bx < ax + aw and ay < by + bw and by < ay + aw

        if not any(intersects(preferred[a], preferred[b])
                   for i, a in enumerate(order) for b in order[i + 1:]):
            return preferred

        # Fit the icon squares with a small breathing space where possible.
        boxes = [preferred[key][2] for key in order]
        spare = max(0, int(height) - sum(boxes))
        gap = min(5, spare // max(len(order) - 1, 1))
        offsets = []
        running = 0
        for box in boxes:
            offsets.append(running)
            running += box + gap
        needed = sum(boxes) + gap * (len(boxes) - 1)
        upper = max(0, int(height) - needed)

        # Least-squares monotonic packing (pool-adjacent-violators): shift only
        # the icons affected by a collision, minimizing total displacement.
        blocks = []  # [start_index, end_index, total_preference, count]
        for index, key in enumerate(order):
            ideal_start = preferred[key][1] - offsets[index]
            blocks.append([index, index, float(ideal_start), 1])
            while len(blocks) > 1:
                left, right = blocks[-2], blocks[-1]
                if left[2] / left[3] <= right[2] / right[3]:
                    break
                blocks[-2:] = [[left[0], right[1],
                                left[2] + right[2], left[3] + right[3]]]

        result = dict(preferred)
        for first, last, total, count in blocks:
            start = clamp(round(total / count), 0, upper)
            for index in range(first, last + 1):
                key = order[index]
                x, _y, box = preferred[key]
                y = start + offsets[index]
                result[key] = (x, clamp(y, 0, max(int(height) - box, 0)), box)
        return result

    def pin_visible_positions(self, height: int) -> None:
        """Turn the *currently visible* arrangement into fixed top-relative coordinates.

        Used only when someone edits the sidebar. In particular, the lower icons
        must not suddenly separate from the upper icons when a sidebar edited in
        a small window is shown in a taller one. The screen positions (including
        any temporary collision-avoidance adjustments) become the baseline for
        ALL icons, not just the one being dragged. Icon sizes are untouched.

        Older saved bottom-anchored layouts can still be read; they are converted
        only on the next successful user edit. This never runs on window resize.
        """
        visible = self.display_geometry(height)
        for key, (x, y, _box) in visible.items():
            entry = dict(self._items.get(key, {}))
            entry.update(x=x, y=y, anchor=ANCHOR_TOP)
            self._items[key] = entry

    def too_crowded(self, key: str, height: int, geometry: dict | None = None) -> bool:
        """True if `key` covers another item by more than MAX_OVERLAP_RATIO."""
        geometry = geometry if geometry is not None else self.geometry(height)
        mine = geometry[key]
        return any(overlap_ratio(mine, rect) > MAX_OVERLAP_RATIO
                   for other, rect in geometry.items() if other != key)

    # ---------- changing (every method returns True if it changed something) ----------
    def _store_position(self, key: str, x: int, y: int, box: int, height: int) -> dict:
        x = clamp(int(x), 0, max(SIDEBAR_WIDTH - box, 0))
        y = clamp(int(y), 0, max(height - box, 0))
        # New edits use only top-relative coordinates. Bottom-anchoring individual
        # items was what caused unexpected extra gaps on maximizing after editing
        # in a smaller window. Existing persisted bottom anchors are still read.
        return {"x": x, "y": y, "anchor": ANCHOR_TOP}

    def _try(self, key: str, new_entry: dict, height: int) -> bool:
        """Apply `new_entry` for `key` only if it is not too crowded; otherwise change nothing."""
        old = self._items.get(key)
        self._items[key] = new_entry
        if self.too_crowded(key, height):
            if old is None:
                del self._items[key]
            else:
                self._items[key] = old
            return False
        return True

    def set_position(self, key: str, x: int, y: int, height: int) -> bool:
        """Put the item's top-left corner at (x, y) measured from the rail's top-left."""
        _check_key(key)
        entry = dict(self._items.get(key, {}))
        box = box_for(key, self.size_of(key))
        entry.update(self._store_position(key, x, y, box, height))
        return self._try(key, entry, height)

    def set_size(self, key: str, size: int, height: int) -> bool:
        """Resize ONE item around its own centre. All other items stay exactly as they are."""
        _check_key(key)
        low, high = size_range(key)
        size = clamp(int(size), low, high)
        old_x, old_y, old_box = self.geometry(height)[key]
        new_box = box_for(key, size)
        entry = dict(self._items.get(key, {}))
        entry["size"] = size
        if "x" in entry:  # keep the centre where it was
            centre_x = old_x + old_box / 2.0
            centre_y = old_y + old_box / 2.0
            entry.update(self._store_position(
                key, round(centre_x - new_box / 2.0), round(centre_y - new_box / 2.0),
                new_box, height))
        return self._try(key, entry, height)

    def reset_item(self, key: str) -> bool:
        _check_key(key)
        return self._items.pop(key, None) is not None

    def reset_all(self) -> bool:
        changed = bool(self._items)
        self._items.clear()
        return changed
