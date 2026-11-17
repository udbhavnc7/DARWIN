"""Check the dashboard theme tokens against WCAG 2.1 AA contrast thresholds.

The dashboard ships six palettes. Each one is a fixed set of CSS custom
properties in `frontend/src/style.css`, so the contrast of every text/background
pair the UI composes can be computed directly instead of sampled.

Exits non-zero when a pair falls below its threshold, so a palette change that
harms readability fails before it ships.

Usage:
    python scripts/check_contrast.py [--css frontend/src/style.css]
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEX = re.compile(r'--([a-z-]+):\s*(#[0-9a-fA-F]{6})\b')
THEME = re.compile(r":root\[data-theme='([a-z]+)'\]\s*\{(.*?)\n\}", re.S)

# (foreground, background, minimum ratio). Text pairs need 4.5:1 at normal size;
# input and control outlines are non-text UI, which AA requires at 3:1.
PAIRS = [
    *[('text', surface, 4.5) for surface in
      ('background', 'sidebar', 'surface', 'raised', 'field', 'hero')],
    *[('muted', surface, 4.5) for surface in
      ('background', 'sidebar', 'surface', 'raised', 'field', 'hero')],
    *[('accent', surface, 4.5) for surface in
      ('background', 'sidebar', 'surface', 'raised')],
    ('on-accent', 'accent', 4.5),
    ('on-accent', 'accent-hover', 4.5),
    ('good', 'good-bg', 4.5),
    ('bad', 'bad-bg', 4.5),
    ('warn', 'warn-bg', 4.5),
    ('control-line', 'surface', 3.0),
    ('control-line', 'field', 3.0),
]


def luminance(value):
    channels = []
    for offset in (1, 3, 5):
        channel = int(value[offset:offset + 2], 16) / 255
        channels.append(channel / 12.92 if channel <= .03928 else ((channel + .055) / 1.055) ** 2.4)
    red, green, blue = channels
    return .2126 * red + .7152 * green + .0722 * blue


def contrast(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + .05) / (low + .05)


def read_themes(text):
    """Return the six palettes, keyed by theme id, from the stylesheet."""
    default = text[:text.index(':root[data-theme=')]
    themes = {'texture': dict(HEX.findall(default))}
    for name, block in THEME.findall(text):
        themes[name] = dict(HEX.findall(block))
    return themes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--css', type=Path, default=ROOT / 'frontend/src/style.css')
    args = parser.parse_args()

    themes = read_themes(args.css.read_text(encoding='utf-8'))
    if len(themes) < 6:
        raise SystemExit(f'Expected six palettes, found {len(themes)}: {sorted(themes)}')

    failures = []
    for name, tokens in themes.items():
        checked = 0
        lowest = (None, 99.0)
        for foreground, background, minimum in PAIRS:
            if foreground not in tokens or background not in tokens:
                failures.append(f'{name}: missing --{foreground} or --{background}')
                continue
            ratio = contrast(tokens[foreground], tokens[background])
            checked += 1
            if lowest[0] is None or ratio < lowest[1]:
                lowest = (f'{foreground} on {background}', ratio)
            if ratio < minimum:
                failures.append(
                    f'{name}: --{foreground} on --{background} is {ratio:.2f}:1, needs {minimum}:1')
        print(f'{name:10} {checked:2} pairs checked, lowest {lowest[1]:.2f}:1 ({lowest[0]})')

    if failures:
        print('\nContrast failures:')
        for failure in failures:
            print(f'  {failure}')
        raise SystemExit(1)
    print('\nAll palette pairs meet WCAG 2.1 AA.')


if __name__ == '__main__':
    main()
