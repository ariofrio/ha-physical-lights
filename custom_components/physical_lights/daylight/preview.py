"""Build a static local-day preview for the Configure review step."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import azimuth, elevation

from .orientation import oriented_daylight, validate_options

PLOT_LEFT = 95
PLOT_WIDTH = 475


def daily_curve(latitude, longitude, zone, local_date, options):
    """Sample an entire local calendar day, including daylight-saving changes."""
    options = validate_options(options)
    tz = ZoneInfo(zone)
    begin = datetime.combine(local_date, datetime.min.time(), tz)
    end = datetime.combine(local_date + timedelta(days=1), datetime.min.time(), tz)
    cursor = begin.astimezone(timezone.utc)
    stop = end.astimezone(timezone.utc)
    observer = Observer(latitude, longitude, 0)
    rows = []
    while cursor < stop:
        local = cursor.astimezone(tz)
        angle = elevation(observer, cursor, with_refraction=False)
        bearing = azimuth(observer, cursor)
        result = oriented_daylight(angle, bearing, **options)
        rows.append(
            {
                "time": local,
                "lux": result["lux"],
                "melanopic_edi": result["melanopic_edi"],
                "cct_kelvin": result["cct_kelvin"],
            }
        )
        cursor += timedelta(minutes=10)
    end_result = oriented_daylight(
        elevation(observer, stop, with_refraction=False), azimuth(observer, stop), **options
    )
    rows.append(
        {
            "time": end,
            "lux": end_result["lux"],
            "melanopic_edi": end_result["melanopic_edi"],
            "cct_kelvin": end_result["cct_kelvin"],
        }
    )
    return rows


def _path(values, y0, height, minimum, maximum):
    parts = []
    drawing = False
    count = len(values) - 1
    for index, value in enumerate(values):
        if value is None:
            drawing = False
            continue
        x = PLOT_LEFT + PLOT_WIDTH * index / count
        y = y0 + height - height * max(0, min(1, (value - minimum) / (maximum - minimum)))
        parts.append(f"{'L' if drawing else 'M'}{x:.1f},{y:.1f}")
        drawing = True
    return " ".join(parts)


def render_svg(rows):
    """Render readable aligned panels without a plotting dependency at runtime."""
    panels = [
        ("Illuminance", "lx", "lux", "#729dff", 130),
        ("Melanopic EDI", "lx", "melanopic_edi", "#72dcc2", 335),
        ("Color temperature", "K", "cct_kelvin", "#ffb86b", 540),
    ]
    fragments = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="745" viewBox="0 0 600 745" role="img" aria-label="Daily daylight preview">',
        '<rect width="600" height="745" fill="#18212b"/>',
        '<text x="20" y="38" fill="#e8eef5" font-size="20" font-family="sans-serif">Clear-sky daylight · local day</text>',
    ]
    for title, unit, key, color, top in panels:
        values = [row[key] for row in rows]
        present = [value for value in values if value is not None]
        minimum = min(present) * 0.9 if key == "cct_kelvin" and present else 0
        maximum = max(1, (max(present, default=0) or 1) * 1.05)
        fragments.extend(
            [
                f'<text x="20" y="{top - 16}" fill="#e8eef5" font-size="17" font-family="sans-serif">{title}</text>',
                f'<text x="570" y="{top - 16}" fill="#a9bacb" text-anchor="end" font-size="13" font-family="sans-serif">{unit}</text>',
                f'<rect x="{PLOT_LEFT}" y="{top}" width="{PLOT_WIDTH}" height="145" fill="#202c38"/>',
            ]
        )
        for fraction in (0, 0.5, 1):
            y = top + 145 * (1 - fraction)
            value = minimum + fraction * (maximum - minimum)
            fragments.append(
                f'<path d="M{PLOT_LEFT},{y:.1f}h{PLOT_WIDTH}" stroke="#3c4b59" stroke-width="1"/>'
            )
            fragments.append(
                f'<text x="85" y="{y + 4:.1f}" fill="#a9bacb" text-anchor="end" font-size="13" font-family="sans-serif">{value:,.0f}</text>'
            )
        for hour in (0, 6, 12, 18, 24):
            x = PLOT_LEFT + PLOT_WIDTH * hour / 24
            fragments.append(f'<path d="M{x:.1f},{top}v145" stroke="#4c5967" stroke-width="1"/>')
            if top == 540:
                label = (
                    "24:00"
                    if hour == 24
                    else rows[round((len(rows) - 1) * hour / 24)]["time"].strftime("%H:%M")
                )
                fragments.append(
                    f'<text x="{x:.1f}" y="708" fill="#a9bacb" text-anchor="middle" font-size="13" font-family="sans-serif">{label}</text>'
                )
        fragments.append(
            f'<path d="{_path(values, top, 145, minimum, maximum)}" fill="none" stroke="{color}" stroke-width="2.5"/>'
        )
    fragments.append("</svg>")
    return "".join(fragments)
