"""404Lab logo in the style of a small monochrome OLED. Every glyph here is drawn by hand for this file, nothing is taken from any firmware.

Writes logo.svg (33x33 pixels, for avatars) and banner.svg (a 128x64 screen). PNGs are not kept in git (no binary files here); to make them: rsvg-convert -w 512 logo.svg -o logo.png, rsvg-convert -w 1280 banner.svg -o banner.png
"""
from pathlib import Path
OUT = Path(__file__).parent
ON, OFF, BG = '#F3F5F7', '#111215', '#060607'

F57 = {  # own 5x7 pixel font
 '4': ['...X.', '..XX.', '.X.X.', 'X..X.', 'XXXXX', '...X.', '...X.'],
 '0': ['.XXX.', 'X...X', 'X..XX', 'X.X.X', 'XX..X', 'X...X', '.XXX.'],
 'L': ['X....', 'X....', 'X....', 'X....', 'X....', 'X....', 'XXXXX'],
 'A': ['.XXX.', 'X...X', 'X...X', 'XXXXX', 'X...X', 'X...X', 'X...X'],
 'B': ['XXXX.', 'X...X', 'X...X', 'XXXX.', 'X...X', 'X...X', 'XXXX.'],
 'S': ['.XXXX', 'X....', 'X....', '.XXX.', '....X', '....X', 'XXXX.'],
 'P': ['XXXX.', 'X...X', 'X...X', 'XXXX.', 'X....', 'X....', 'X....'],
 '-': ['.....', '.....', '.....', '.XXX.', '.....', '.....', '.....'],
 'M': ['X...X', 'XX.XX', 'X.X.X', 'X.X.X', 'X...X', 'X...X', 'X...X'],
 'K': ['X...X', 'X..X.', 'X.X..', 'XX...', 'X.X..', 'X..X.', 'X...X'],
 'I': ['.XXX.', '..X..', '..X..', '..X..', '..X..', '..X..', '.XXX.'],
 'O': ['.XXX.', 'X...X', 'X...X', 'X...X', 'X...X', 'X...X', '.XXX.'],
 'D': ['XXXX.', 'X...X', 'X...X', 'X...X', 'X...X', 'X...X', 'XXXX.'],
 'T': ['XXXXX', '..X..', '..X..', '..X..', '..X..', '..X..', '..X..'],
 ' ': ['.....']*7,
}
F35 = {'4': ['X.X', 'X.X', 'XXX', '..X', '..X'], '0': ['XXX', 'X.X', 'X.X', 'X.X', 'XXX']}

def text(lit, s, x, y, font=F57, scale=1, on=True):
    for ch in s:
        rows = font[ch]
        for j, row in enumerate(rows):
            for i, c in enumerate(row):
                if c == 'X':
                    for dy in range(scale):
                        for dx in range(scale):
                            (lit.add if on else lit.discard)((x+i*scale+dx, y+j*scale+dy))
        x += (len(rows[0])+1)*scale

def flask(cx=16):
    """Erlenmeyer flask on a 33-pixel grid, symmetric about column cx: a lip, a straight neck, walls at an even 1:2 slope, rounded bottom corners."""
    lit = set()
    for x in range(cx-4, cx+5):
        lit.add((x, 4))                                   # lip, one pixel wider than the neck
    for y in range(5, 12):
        lit |= {(cx-3, y), (cx+3, y)}                    # neck
    edge = {}
    for y in range(12, 28):
        left = cx-3 - ((y-12)//2 + 1)                     # one column out every two rows: a clean pixel line
        edge[y] = (left, 2*cx-left)
        lit |= {(left, y), (2*cx-left, y)}
    lb, rb = edge[27]
    for x in range(lb+1, rb):
        lit.add((x, 28))                                  # bottom, corners left open so they read round
    for y in range(17, 27):
        l, r = edge[y]
        for x in range(l+2, r-1):                         # one dark pixel between glass and liquid
            lit.add((x, y))
    text(lit, '404', cx-5, 21, F35, on=False)            # 404 cut into the liquid
    for b in [(cx+1, 14), (cx-1, 10), (cx, 7)]:          # bubbles rising above the liquid
        lit.add(b)
    return lit

def render(lit, w, h, p, round_=0):
    """Lit pixels are drawn one by one; the dark grid of unlit pixels is a repeated pattern, which keeps the file small."""
    q, m = p*0.84, p*0.08
    on = ''.join(f'<rect x="{x*p+m:.2f}" y="{y*p+m:.2f}" width="{q:.2f}" height="{q:.2f}" rx="{q*0.12:.2f}"/>' for (x, y) in sorted(lit) if 0 <= x < w and 0 <= y < h)
    W, H = w*p, h*p
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}"><defs>'
            f'<filter id="g" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="{p*0.45:.1f}" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
            f'<pattern id="off" width="{p:.4f}" height="{p:.4f}" patternUnits="userSpaceOnUse"><rect x="{m:.2f}" y="{m:.2f}" width="{q:.2f}" height="{q:.2f}" fill="{OFF}"/></pattern></defs>'
            f'<rect width="{W:.0f}" height="{H:.0f}" rx="{round_}" fill="{BG}"/><rect width="{W:.0f}" height="{H:.0f}" fill="url(#off)"/>'
            f'<g fill="{ON}" filter="url(#g)">{on}</g></svg>\n')

# Avatar: 33x33 pixels.
(OUT/'logo.svg').write_text(render(flask(), 33, 33, 512/33), encoding='utf-8')

# Banner: a 128x64 screen, the flask at double size on the left, the name and one line on the right.
banner = set()
for (x, y) in flask():
    for dx in range(2):
        for dy in range(2):
            banner.add((2*x+dx-6, 2*y+dy-1))
text(banner, '404LAB', 53, 16, scale=2)
text(banner, 'SP-404MKII', 58, 37)   # both lines centred under 404LAB (53..122)
text(banner, 'MOD TOOLS', 61, 47)
(OUT/'banner.svg').write_text(render(banner, 128, 64, 10), encoding='utf-8')
