"""Turn saved DARWIN dashboard screenshots into a captioned offline demo."""
import argparse
import os
from pathlib import Path
import subprocess


SCENES = [
    ('shop', 'Replay the same checkout', 'The confirmation and the single payment effect survive replay.'),
    ('safe', 'Safe configuration passes', 'Three complete repetitions pass the full fault suite.'),
    ('unsafe', 'Duplicate payment is rejected', 'I-01 identifies three payment effects for a single key.'),
    ('lineage', 'Follow the search across generations', 'The saved record links proposals to their measured parents.'),
    ('pareto', 'Compare measured tradeoffs', 'Both configurations pass. Queued notifications trade CPU time for lower p95.'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=Path('artifacts/demo'))
    args = parser.parse_args()
    font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf'
    if not font.is_file():
        raise SystemExit('The demo renderer requires Windows Arial')
    font_option = "fontfile='" + font.as_posix().replace(':', r'\:') + "'"
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-filter_complex_threads', '1']
    filters = []
    for index, (name, title, detail) in enumerate(SCENES):
        command.extend(['-loop', '1', '-framerate', '24', '-t', '8', '-i', str(args.folder / f'{name}.png')])
        filters.append(
            f"[{index}:v]scale=1160:560:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            "pad=1280:720:(ow-iw)/2:94:color=0x101611,setsar=1,"
            f"drawtext={font_option}:text='DARWIN  /  RECORDED DEMO':fontsize=16:fontcolor=0xc3ee83:x=60:y=22,"
            f"drawtext={font_option}:text='{title}':fontsize=28:fontcolor=white:x=60:y=49,"
            f"drawtext={font_option}:text='{detail}':fontsize=20:fontcolor=0xe5e9e3:x=60:y=676[v{index}]")
    inputs = ''.join(f'[v{index}]' for index in range(len(SCENES)))
    filters.append(f'{inputs}concat=n={len(SCENES)}:v=1:a=0[out]')
    output = args.folder / 'darwin-recorded-demo.mp4'
    command.extend(['-filter_complex', ';'.join(filters), '-map', '[out]', '-c:v', 'libx264', '-threads', '1',
                    '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)])
    subprocess.run(command, check=True)
    print(output)


if __name__ == '__main__':
    main()
