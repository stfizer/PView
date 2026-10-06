"""Fluent-style SVG icon set rendered with the current theme color."""
from __future__ import annotations

import os
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24x24 stroke icons; {c} = color, sw = stroke width
_T = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
_F = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{c}" stroke="none">{body}</svg>'

ICONS = {
    # window controls — Win11 native style: thin strokes, large square glyphs
    "win-min": _F.format(c="{c}", body='<path d="M6.5 12h11" fill="none" stroke="{c}" stroke-width="1.25" stroke-linecap="round"/>'),
    "win-max": _F.format(c="{c}", body='<rect x="6" y="6" width="12" height="12" fill="none" stroke="{c}" stroke-width="1.25"/>'),
    "win-restore": _F.format(c="{c}", body='<rect x="6.75" y="8.75" width="10" height="10" fill="none" stroke="{c}" stroke-width="1.25"/><path d="M9.5 6.25h7a1.25 1.25 0 0 1 1.25 1.25v7" fill="none" stroke="{c}" stroke-width="1.25"/>'),
    "win-close": _F.format(c="{c}", body='<path d="M6.75 6.75 17.25 17.25M17.25 6.75 6.75 17.25" fill="none" stroke="{c}" stroke-width="1.25" stroke-linecap="round"/>'),
    # chevrons / arrows
    "chev-left": _F.format(c="{c}", body='<path d="M14.5 5.5 8 12l6.5 6.5" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
    "chev-right": _F.format(c="{c}", body='<path d="M9.5 5.5 16 12l-6.5 6.5" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
    "chev-up": _F.format(c="{c}", body='<path d="M5.5 14.5 12 8l6.5 6.5" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
    "chev-down": _F.format(c="{c}", body='<path d="M5.5 9.5 12 16l6.5-6.5" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
    "first": _F.format(c="{c}", body='<path d="M17.5 5.5 11 12l6.5 6.5" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M6.5 5v14" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'),
    "last": _F.format(c="{c}", body='<path d="M6.5 5.5 13 12l-6.5 6.5" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M17.5 5v14" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'),
    # files / folders
    "folder": _F.format(c="{c}", body='<path d="M3.5 7.5A2.5 2.5 0 0 1 6 5h3.2c.7 0 1.4.3 1.9.9l1 1.1h5.9A2.5 2.5 0 0 1 20.5 9.5v7a2.5 2.5 0 0 1-2.5 2.5H6a2.5 2.5 0 0 1-2.5-2.5z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    "open": _F.format(c="{c}", body='<path d="M3.5 7.5A2.5 2.5 0 0 1 6 5h3.2c.7 0 1.4.3 1.9.9l1 1.1h5.9A2.5 2.5 0 0 1 20.5 9.5v1H9.2c-1 0-1.9.6-2.3 1.5l-3.4 6.9z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><path d="M3.5 19l3.4-7c.4-.9 1.3-1.5 2.3-1.5h11.3c1.6 0 2.6 1.7 1.9 3.1l-2.6 5c-.4.9-1.3 1.4-2.3 1.4z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    "image": _F.format(c="{c}", body='<rect x="3.5" y="4.5" width="17" height="15" rx="2.5" fill="none" stroke="{c}" stroke-width="1.6"/><circle cx="9" cy="9.5" r="1.6" fill="{c}" stroke="none"/><path d="M5 17.5 10.5 12l3.5 3.5 2.5-2.5 4 4.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    "archive": _F.format(c="{c}", body='<path d="M3.5 8.5v9A2 2 0 0 0 5.5 19.5h13a2 2 0 0 0 2-2v-9" fill="none" stroke="{c}" stroke-width="1.6"/><rect x="3.5" y="4.5" width="17" height="4" rx="1.2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M10 12h4" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    # rotate / flip
    "rotate-left": _F.format(c="{c}", body='<path d="M8.5 5.5 5 9l3.5 3.5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M5 9h8a6 6 0 1 1-6 6" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>'),
    "rotate-right": _F.format(c="{c}", body='<path d="M15.5 5.5 19 9l-3.5 3.5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 9h-8a6 6 0 1 0 6 6" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>'),
    "flip-h": _F.format(c="{c}", body='<path d="M12 3.5v17" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="2.5 2.5"/><path d="M9 7 4.5 12 9 17z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><path d="M15 7l4.5 5L15 17z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    "flip-v": _F.format(c="{c}", body='<path d="M3.5 12h17" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="2.5 2.5"/><path d="M7 9 12 4.5 17 9z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><path d="M7 15l5 4.5 5-4.5z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    # zoom / view
    "zoom-in": _F.format(c="{c}", body='<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M15.5 15.5 20 20" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/><path d="M8 10.5h5M10.5 8v5" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    "zoom-out": _F.format(c="{c}", body='<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M15.5 15.5 20 20" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/><path d="M8 10.5h5" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    "fit-window": _F.format(c="{c}", body='<path d="M3.5 8V5.5A2 2 0 0 1 5.5 3.5H8M16 3.5h2.5a2 2 0 0 1 2 2V8M20.5 16v2.5a2 2 0 0 1-2 2H16M8 20.5H5.5a2 2 0 0 1-2-2V16" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/><rect x="8.5" y="8.5" width="7" height="7" rx="1" fill="none" stroke="{c}" stroke-width="1.5"/>'),
    "fit-width": _F.format(c="{c}", body='<path d="M3.5 8V5.5a2 2 0 0 1 2-2H8M16 3.5h2.5a2 2 0 0 1 2 2V8M20.5 16v2.5a2 2 0 0 1-2 2H16M8 20.5H5.5a2 2 0 0 1-2-2V16" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/><path d="M7.5 12h9M9.5 9.5 7 12l2.5 2.5M14.5 9.5 17 12l-2.5 2.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "fit-height": _F.format(c="{c}", body='<path d="M3.5 8V5.5a2 2 0 0 1 2-2H8M16 3.5h2.5a2 2 0 0 1 2 2V8M20.5 16v2.5a2 2 0 0 1-2 2H16M8 20.5H5.5a2 2 0 0 1-2-2V16" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/><path d="M12 7.5v9M9.5 9.5 12 7l2.5 2.5M9.5 14.5 12 17l2.5-2.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "one2one": _F.format(c="{c}", body='<rect x="3.5" y="3.5" width="17" height="17" rx="3" fill="none" stroke="{c}" stroke-width="1.6"/><text x="7" y="15" font-family="Segoe UI" font-size="9" font-weight="600" fill="{c}" stroke="none">1</text><text x="13.5" y="15" font-family="Segoe UI" font-size="9" font-weight="600" fill="{c}" stroke="none">1</text>'),
    "stretch": _F.format(c="{c}", body='<rect x="3.5" y="5.5" width="17" height="13" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M7.5 9l-2 3 2 3M16.5 9l2 3-2 3" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'),
    "double-page": _F.format(c="{c}", body='<rect x="3.5" y="5" width="7.5" height="14" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6"/><rect x="13" y="5" width="7.5" height="14" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6"/>'),
    "webtoon": _F.format(c="{c}", body='<path d="M3.5 6.5A2 2 0 0 1 5.5 4.5h13a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M3.5 9.5h17M3.5 14.5h17" stroke="{c}" stroke-width="1.4"/>'),
    # slideshow / animation
    "slideshow": _F.format(c="{c}", body='<circle cx="12" cy="12" r="8.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M10 8.8v6.4l5.2-3.2z" fill="{c}" stroke="none"/>'),
    "play": _F.format(c="{c}", body='<path d="M8 5.8v12.4L18.5 12z" fill="{c}" stroke="none"/>'),
    "pause": _F.format(c="{c}", body='<rect x="6.5" y="5.5" width="3.6" height="13" rx="1.2" fill="{c}"/><rect x="13.9" y="5.5" width="3.6" height="13" rx="1.2" fill="{c}"/>'),
    "shuffle": _F.format(c="{c}", body='<path d="M4 7h3.5l9 10H20M4 17h3.5l2.6-2.9M14.5 9.9 16.5 7H20" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M17.5 4.5 20 7l-2.5 2.5M17.5 14.5 20 17l-2.5 2.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "repeat": _F.format(c="{c}", body='<path d="M17 3.5 20 6.5l-3 3" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M20 6.5H8a4 4 0 0 0-4 4v.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><path d="M7 20.5 4 17.5l3-3" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 17.5h12a4 4 0 0 0 4-4V13" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    "frame-prev": _F.format(c="{c}", body='<path d="M13.5 6.5 8 12l5.5 5.5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 6.5 11.5 12 17 17.5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'),
    "frame-next": _F.format(c="{c}", body='<path d="M10.5 6.5 16 12l-5.5 5.5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M7 6.5 12.5 12 7 17.5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'),
    # window states
    "fullscreen": _F.format(c="{c}", body='<path d="M8.5 3.5H5.5a2 2 0 0 0-2 2v3M15.5 3.5h3a2 2 0 0 1 2 2v3M20.5 15.5v3a2 2 0 0 1-2 2h-3M3.5 15.5v3a2 2 0 0 0 2 2h3" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>'),
    "exit-fullscreen": _F.format(c="{c}", body='<path d="M3.5 8.5h3.5a1.5 1.5 0 0 0 1.5-1.5V3.5M20.5 8.5H17a1.5 1.5 0 0 1-1.5-1.5V3.5M15.5 20.5H17a1.5 1.5 0 0 0 1.5-1.5V15.5M3.5 15.5H7a1.5 1.5 0 0 1 1.5 1.5v3.5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>'),
    "pin": _F.format(c="{c}", body='<path d="M9 3.5h6M12 3.5v6" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><path d="M8.5 9.5h7l1.5 5h-10z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 14.5v6" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    "pin-off": _F.format(c="{c}", body='<path d="M4 4l16 16" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><path d="M9 3.5h6M12 3.5v5" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><path d="M8.5 9.5h7l1.5 5h-10z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 14.5v6" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    # info / bookmark
    "info": _F.format(c="{c}", body='<circle cx="12" cy="12" r="8.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M12 11v5.5" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="7.8" r="1.1" fill="{c}" stroke="none"/>'),
    "star": _F.format(c="{c}", body='<path d="m12 3.8 2.5 5.1 5.6.8-4 4 .9 5.6-5-2.6-5 2.6.9-5.6-4-4 5.6-.8z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    "star-filled": _F.format(c="{c}", body='<path d="m12 3.8 2.5 5.1 5.6.8-4 4 .9 5.6-5-2.6-5 2.6.9-5.6-4-4 5.6-.8z" fill="{c}" stroke="none"/>'),
    # file ops
    "delete": _F.format(c="{c}", body='<path d="M4.5 6.5h15" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><path d="M8.5 6.5v-1a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M6.5 6.5l1 12a2 2 0 0 0 2 1.8h5a2 2 0 0 0 2-1.8l1-12" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><path d="M10 10.5v6M14 10.5v6" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'),
    "copy": _F.format(c="{c}", body='<rect x="8.5" y="8.5" width="12" height="12" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M5.5 15.5h-.7a1.8 1.8 0 0 1-1.8-1.8V5.3c0-1 .8-1.8 1.8-1.8h8.4c1 0 1.8.8 1.8 1.8V6" fill="none" stroke="{c}" stroke-width="1.6"/>'),
    "save": _F.format(c="{c}", body='<path d="M5.5 3.5h10.2L19.5 7.3v11.2a2 2 0 0 1-2 2h-12a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><path d="M7.5 3.5v5h8v-5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><rect x="7.5" y="13" width="9" height="7.5" fill="none" stroke="{c}" stroke-width="1.6"/>'),
    "convert": _F.format(c="{c}", body='<path d="M4 8h13M14 4.5 17.5 8 14 11.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M20 16H7M10 12.5 6.5 16l3.5 3.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "rename": _F.format(c="{c}", body='<rect x="3" y="8" width="18" height="8" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M12 3.5v17" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    "print": _F.format(c="{c}", body='<path d="M7 8V3.5h10V8" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><rect x="3.5" y="8" width="17" height="8.5" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><rect x="7" y="14" width="10" height="6.5" rx="1" fill="none" stroke="{c}" stroke-width="1.6"/>'),
    "wallpaper": _F.format(c="{c}", body='<rect x="3" y="4.5" width="18" height="12" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M5.5 14 9.5 9.5l3 3 2-2 4 3.5" fill="none" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/><path d="M9 20.5h6" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><path d="M12 16.5v4" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    "edit": _F.format(c="{c}", body='<path d="M4 20h16" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><path d="M13.8 4.9a2.1 2.1 0 0 1 3 3L8 16.7l-4 1 1-4z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    # UI misc
    "grid": _F.format(c="{c}", body='<rect x="4" y="4" width="7" height="7" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6"/><rect x="13" y="4" width="7" height="7" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6"/><rect x="4" y="13" width="7" height="7" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6"/><rect x="13" y="13" width="7" height="7" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6"/>'),
    "list": _F.format(c="{c}", body='<path d="M8.5 6h12M8.5 12h12M8.5 18h12" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><circle cx="4.5" cy="6" r="1.2" fill="{c}"/><circle cx="4.5" cy="12" r="1.2" fill="{c}"/><circle cx="4.5" cy="18" r="1.2" fill="{c}"/>'),
    "sort": _F.format(c="{c}", body='<path d="M7 4.5v15M7 19.5 4 16.5M7 19.5l3-3" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M13.5 7h7M13.5 11h5.5M13.5 15h4M13.5 19h2.5" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    "check": _F.format(c="{c}", body='<path d="M4.5 12.5 10 18 19.5 6.5" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'),
    "dot": _F.format(c="{c}", body='<circle cx="12" cy="12" r="4.5" fill="{c}"/>'),
    "more": _F.format(c="{c}", body='<circle cx="5" cy="12" r="1.6" fill="{c}"/><circle cx="12" cy="12" r="1.6" fill="{c}"/><circle cx="19" cy="12" r="1.6" fill="{c}"/>'),
    "settings": _F.format(c="{c}", body='<circle cx="12" cy="12" r="3.2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M12 2.8 13 5.4a6.8 6.8 0 0 1 2.1.9l2.7-.9 1.7 3-2 1.9c.1.4.1.8.1 1.2s0 .8-.1 1.2l2 1.9-1.7 3-2.7-.9a6.8 6.8 0 0 1-2.1.9l-1 2.6h-2l-1-2.6a6.8 6.8 0 0 1-2.1-.9l-2.7.9-1.7-3 2-1.9a7.6 7.6 0 0 1 0-2.4l-2-1.9 1.7-3 2.7.9a6.8 6.8 0 0 1 2.1-.9l1-2.6z" fill="none" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>'),
    "keyboard": _F.format(c="{c}", body='<rect x="2.5" y="6.5" width="19" height="11" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M6 10h.01M9.5 10h.01M13 10h.01M16.5 10h.01M6 14h.01M9 14h6.5M18 14h.01" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'),
    "globe": _F.format(c="{c}", body='<circle cx="12" cy="12" r="8.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M3.5 12h17M12 3.5c-5 5.5-5 11.5 0 17M12 3.5c5 5.5 5 11.5 0 17" fill="none" stroke="{c}" stroke-width="1.4"/>'),
    "sliders": _F.format(c="{c}", body='<path d="M5 4.5v6M5 14v5.5M12 4.5v3M12 11v8.5M19 4.5v9M19 17v2.5" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><circle cx="5" cy="12" r="1.8" fill="none" stroke="{c}" stroke-width="1.6"/><circle cx="12" cy="9" r="1.8" fill="none" stroke="{c}" stroke-width="1.6"/><circle cx="19" cy="15" r="1.8" fill="none" stroke="{c}" stroke-width="1.6"/>'),
    "theme": _F.format(c="{c}", body='<path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5c0-1-.8-1.5-1.6-1.5H16a2 2 0 0 1-2-2V5.1c0-.8-.5-1.6-2-1.6z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><circle cx="8.5" cy="10" r="1.1" fill="{c}"/><circle cx="9.5" cy="15" r="1.1" fill="{c}"/>'),
    "sun": _F.format(c="{c}", body='<circle cx="12" cy="12" r="4" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M18.7 5.3l-1.8 1.8M7.1 16.9l-1.8 1.8" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
    "moon": _F.format(c="{c}", body='<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    "info-circ": _F.format(c="{c}", body='<circle cx="12" cy="12" r="8.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M12 11v5.5" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="7.8" r="1.1" fill="{c}"/>'),
    "folder-open": _F.format(c="{c}", body='<path d="M3.5 19V7.5A2.5 2.5 0 0 1 6 5h3.2c.7 0 1.4.3 1.9.9l1 1.1h5.9A2.5 2.5 0 0 1 20.5 9.5v9.5z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/><path d="M3.5 19l2.9-5.4c.4-.7 1.1-1.1 1.9-1.1h11.8c1.3 0 2.1 1.4 1.4 2.5l-2.3 4z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'),
    "compass": _F.format(c="{c}", body='<circle cx="12" cy="12" r="8.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="m15.5 8.5-2 5-5 2 2-5z" fill="none" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>'),
    "chevs-down": _F.format(c="{c}", body='<path d="M5.5 7.5 12 14l6.5-6.5M5.5 12.5 12 19l6.5-6.5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'),
    "zoom-fix": _F.format(c="{c}", body='<rect x="8" y="8" width="8" height="8" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-dasharray="2.4 2.4"/><path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'),
}

_cache: dict = {}
_icon_dir = ""


def init_icon_cache(icon_dir: str):
    """Write the small SVGs that QSS needs (checkbox etc.) into icon_dir."""
    global _icon_dir
    _icon_dir = icon_dir
    os.makedirs(icon_dir, exist_ok=True)
    static = {
        "chevdown": ICONS["chev-down"].replace("{c}", "#888888"),
        "chevup": ICONS["chev-up"].replace("{c}", "#888888"),
        "check": ICONS["check"].replace("{c}", "#ffffff"),
        "dot": ICONS["dot"].replace("{c}", "#ffffff"),
    }
    for name, svg in static.items():
        with open(os.path.join(icon_dir, name + ".svg"), "w", encoding="utf-8") as f:
            f.write(svg)


def _render(svg: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return QPixmap.fromImage(img)


def icon(name: str, color: str, size: int = 24, filled: bool = False) -> QIcon:
    key = (name, color, size, filled)
    if key in _cache:
        return _cache[key]
    base = ICONS.get(name)
    if base is None:
        ic = QIcon()
    else:
        nm = name
        if filled and not name.endswith("-filled"):
            nm = name + "-filled"
        svg = ICONS.get(nm, base).replace("{c}", color)
        ic = QIcon(_render(svg, size))
        ic.addPixmap(_render(svg, 48))  # hi-dpi source
    _cache[key] = ic
    return ic
