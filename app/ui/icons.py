"""Bộ icon SVG dùng chung (nét mảnh, đồng bộ - không dùng emoji).

Dash không có component SVG nên icon được render bằng CSS mask:
màu icon tự động theo màu chữ (currentColor) của chỗ đặt nó.
"""
from __future__ import annotations

from urllib.parse import quote

from dash import html

_PATHS = {
    "dashboard": ["M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z"],
    "calendar": ["M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
                 "M3 10h18", "M8 3v4", "M16 3v4"],
    "users": ["M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
              "M22 20v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
    "upload": ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 9l5-5 5 5", "M12 4v12"],
    "settings": ["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
                 "M20.6 13.3a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 "
                 "0 0-1.87-.34 1.7 1.7 0 0 0-1 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 "
                 "1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 "
                 "1.7 1.7 0 0 0-1.56-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-"
                 ".34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 "
                 "0 1-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 "
                 "2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.56 1H21a2 2 0 1 "
                 "1 0 4h-.09a1.7 1.7 0 0 0-1.56 1z"],
    "logout": ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
    "download": ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
    "refresh": ["M23 4v6h-6", "M1 20v-6h6",
                "M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"],
    "save": ["M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z",
             "M17 21v-8H7v8", "M7 3v5h8"],
    "copy": ["M20 9h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2z",
             "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"],
    "zoom_in": ["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M21 21l-4.35-4.35", "M11 8v6", "M8 11h6"],
    "zoom_out": ["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M21 21l-4.35-4.35", "M8 11h6"],
    "expand": ["M15 3h6v6", "M9 21H3v-6", "M21 3l-7 7", "M3 21l7-7"],
    "check": ["M20 6L9 17l-5-5"],
    "edit": ["M12 20h9", "M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"],
    "alert": ["M12 9v4", "M12 17h.01",
              "M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"],
    "shield": ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", "M9 12l2 2 4-4"],
    "compare": ["M3 5h7v14H3zM14 5h7v9h-7z", "M17.5 17v4", "M15.5 19h4"],
    "mic": ["M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z", "M19 10v2a7 7 0 0 1-14 0v-2", "M12 19v4",
            "M8 23h8"],
    "camera": ["M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z",
               "M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"],
    "trash": ["M3 6h18", "M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2",
              "M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6", "M10 11v6", "M14 11v6"],
    "plus": ["M12 5v14", "M5 12h14"],
    "menu": ["M3 6h18", "M3 12h18", "M3 18h18"],
    "thu_gon": ["M3 6h18", "M3 12h12", "M3 18h18", "M20 15l-3-3 3-3"],
    "mo_rong": ["M3 6h18", "M9 12h12", "M3 18h18", "M4 9l3 3-3 3"],
    "book": ["M4 4a2 2 0 0 1 2-2h13v18H6a2 2 0 0 0-2 2z", "M9 7h7", "M9 11h7"],
    "table": ["M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
              "M3 9h18", "M9 9v12"],
    "trend": ["M23 6l-9.5 9.5-5-5L1 18", "M17 6h6v6"],
    "pie": ["M21.21 15.89A10 10 0 1 1 8 2.83", "M22 12A10 10 0 0 0 12 2v10z"],
    "database": ["M12 8c4.97 0 9-1.34 9-3s-4.03-3-9-3-9 1.34-9 3 4.03 3 9 3z",
                 "M21 12c0 1.66-4 3-9 3s-9-1.34-9-3", "M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"],
    "user": ["M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2", "M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"],
    "help": ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3",
             "M12 17h.01"],
}


def _svg(name: str) -> str:
    paths = "".join(f'<path d="{d}"/>' for d in _PATHS.get(name, _PATHS["dashboard"]))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="black" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round">{paths}</svg>')


def icon(name: str, size: int = 17, className: str = "") -> html.Span:
    uri = f"url(\"data:image/svg+xml;utf8,{quote(_svg(name))}\")"
    style = {"width": f"{size}px", "height": f"{size}px", "display": "inline-block",
             "flex": f"0 0 {size}px", "backgroundColor": "currentColor",
             "WebkitMaskImage": uri, "maskImage": uri,
             "WebkitMaskRepeat": "no-repeat", "maskRepeat": "no-repeat",
             "WebkitMaskSize": "contain", "maskSize": "contain"}
    return html.Span(style=style, className=className)
