"""Force UFO outlines into the Mekorot style: smooth x powers-of-two grid.

The invariant (docs: img2ufo/docs/mekorot-style.md): every on-curve point is
smooth with an exactly horizontal or vertical tangent; on-curve coordinates
snap to the 8-unit grid; handle lengths snap to the 2-unit grid; each handle
shares its constrained coordinate with its on-curve point (axis alignment),
so collinearity is structural.

Method per contour ("sanding"):
  1. flatten the original outline to a dense polyline;
  2. nodes = local x- and y-extrema of the polyline (corners at extrema
     become smooth; everything not at an extremum is sanded away);
  3. between consecutive nodes fit one cubic whose end tangents are fixed
     H/V — only the two handle LENGTHS are free (linear least squares);
  4. snap nodes to 8u, handle lengths to 2u.

Converted glyphs are machine output: markColor is set to ORANGE per the
grading convention. Components are copied through unchanged (their base
glyphs are converted); non-axis-aligned component transforms are reported.

    python3 scripts/mekorot_style.py <in.ufo> <out.ufo> [--scale F]
"""

import math
import shutil
import sys
from pathlib import Path

from fontTools.ufoLib.glifLib import GlyphSet
from fontTools.pens.pointPen import AbstractPointPen

ORANGE = (1.0, 0.5, 0.0, 1.0)
NODE_GRID = 8
HANDLE_GRID = 2
SAMPLES_PER_SEG = 64
MIN_NODE_DIST = 6.0  # collapse jitter extrema closer than this


def snap(v, grid):
    return round(v / grid) * grid


# --- glif reading -------------------------------------------------------------

class ContourRecorder(AbstractPointPen):
    def __init__(self):
        self.contours = []   # list of list of (x, y, segmentType, smooth)
        self.components = []

    def beginPath(self, **kwargs):
        self.contours.append([])

    def addPoint(self, pt, segmentType=None, smooth=False, name=None, **kwargs):
        self.contours[-1].append((pt[0], pt[1], segmentType, smooth))

    def endPath(self):
        pass

    def addComponent(self, baseGlyph, transformation, **kwargs):
        self.components.append((baseGlyph, transformation))


class GlyphShell:
    """Minimal glyph object for GlyphSet.readGlyph/writeGlyph."""
    pass


# --- geometry -----------------------------------------------------------------

def cubic_point(p0, p1, p2, p3, t):
    mt = 1 - t
    return (mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
            mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1])


def flatten(contour):
    """Dense polyline for one closed contour of UFO points."""
    pts = contour
    n = len(pts)
    start = next((i for i, p in enumerate(pts) if p[2] is not None), None)
    if start is None:
        return []  # all-offcurve (TrueType style): not expected in these sources
    ordered = pts[start:] + pts[:start]
    poly = []
    i = 0
    cur = (ordered[0][0], ordered[0][1])
    poly.append(cur)
    k = 1
    while k <= len(ordered):
        seg = []
        while k <= len(ordered):
            p = ordered[k % len(ordered)]
            k += 1
            seg.append(p)
            if p[2] is not None:
                break
        end = (seg[-1][0], seg[-1][1])
        offs = [(p[0], p[1]) for p in seg[:-1]]
        if not offs:
            for t in range(1, SAMPLES_PER_SEG + 1):
                u = t / SAMPLES_PER_SEG
                poly.append((cur[0] + (end[0] - cur[0]) * u,
                             cur[1] + (end[1] - cur[1]) * u))
        elif len(offs) == 2:
            for t in range(1, SAMPLES_PER_SEG + 1):
                poly.append(cubic_point(cur, offs[0], offs[1], end, t / SAMPLES_PER_SEG))
        else:  # quadratic or odd: sample through implied cubic-ish (rare)
            ctrl = offs[0]
            for t in range(1, SAMPLES_PER_SEG + 1):
                u = t / SAMPLES_PER_SEG
                mt = 1 - u
                poly.append((mt**2 * cur[0] + 2 * mt * u * ctrl[0] + u**2 * end[0],
                             mt**2 * cur[1] + 2 * mt * u * ctrl[1] + u**2 * end[1]))
        cur = end
        if k > len(ordered):
            break
    return poly[:-1]  # closed: drop duplicated start


RESAMPLE = 2.0       # arc-length step for uniform resampling
SMOOTH_R = 4         # box-smoothing radius in samples (~8u window)
PROMINENCE = 10.0    # an extremum must reverse by at least this much
FILLET = 24.0        # arc-length offset of fillet nodes from a corner
CORNER_TURN = 0.6    # rad (~34 deg): direction change that counts as a corner
AXIS_TOL = 0.35      # rad (~20 deg): edge direction close enough to an axis


def resample(poly, step=RESAMPLE):
    """Uniform arc-length resampling of a closed polyline."""
    out = []
    n = len(poly)
    carry = 0.0
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-9:
            continue
        t = carry
        while t < seg:
            u = t / seg
            out.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
            t += step
        carry = t - seg
    return out if len(out) >= 8 else poly


def smooth(poly, r=SMOOTH_R):
    """Circular box smoothing — kills trace jitter before node finding."""
    n = len(poly)
    if n < 2 * r + 1:
        return poly
    out = []
    for i in range(n):
        xs = ys = 0.0
        for k in range(-r, r + 1):
            p = poly[(i + k) % n]
            xs += p[0]
            ys += p[1]
        out.append((xs / (2 * r + 1), ys / (2 * r + 1)))
    return out


def prominent(poly, i, coord, prom=PROMINENCE):
    """True if the reversal at sample i travels back >= prom on both sides."""
    n = len(poly)
    v = poly[i][coord]
    for direction in (1, -1):
        j, best = i, 0.0
        for _ in range(n):
            j = (j + direction) % n
            best = max(best, abs(poly[j][coord] - v))
            if best >= prom:
                break
        if best < prom:
            return False
    return True


def tangent(poly, i, span=3):
    n = len(poly)
    a, b = poly[(i - span) % n], poly[(i + span) % n]
    dx, dy = b[0] - a[0], b[1] - a[1]
    h = math.hypot(dx, dy) or 1.0
    return dx / h, dy / h


def axis_of(d):
    """'H' / 'V' if direction d is near an axis, else None."""
    ang = math.atan2(d[1], d[0])
    for k in range(-2, 3):
        if abs(ang - k * math.pi / 2) < AXIS_TOL:
            return 'V' if k % 2 else 'H'
    return None


def find_nodes(poly):
    """Node indices + tangent axes: x/y extrema plus fillet pairs at corners.

    A corner between two near-axis, near-perpendicular edges becomes TWO
    nodes offset along each edge (the quarter-turn fillet). Corners
    involving diagonal edges get no legal node — the fit sweeps through
    them (the sanding). Extrema always yield nodes."""
    n = len(poly)
    step = sum(math.hypot(poly[(i + 1) % n][0] - poly[i][0],
                          poly[(i + 1) % n][1] - poly[i][1])
               for i in range(n)) / n or 1.0
    off = max(2, int(round(FILLET / step)))
    nodes = []
    for i in range(n):
        xp, x, xn = poly[(i - 1) % n][0], poly[i][0], poly[(i + 1) % n][0]
        yp, y, yn = poly[(i - 1) % n][1], poly[i][1], poly[(i + 1) % n][1]
        if (x - xp) * (xn - x) < 0 and prominent(poly, i, 0):
            nodes.append((i, 'V'))
        elif (y - yp) * (yn - y) < 0 and prominent(poly, i, 1):
            nodes.append((i, 'H'))
        else:
            t_in = tangent(poly, (i - off) % n, 2)
            t_out = tangent(poly, (i + off) % n, 2)
            turn = abs(math.atan2(t_in[0] * t_out[1] - t_in[1] * t_out[0],
                                  t_in[0] * t_out[0] + t_in[1] * t_out[1]))
            if turn > CORNER_TURN:
                # fillet node on each side whose edge is axis-aligned;
                # diagonal sides get none (the fit sweeps through them)
                a_in, a_out = axis_of(t_in), axis_of(t_out)
                if a_in:
                    nodes.append(((i - off) % n, a_in))
                if a_out:
                    nodes.append(((i + off) % n, a_out))
    # dedupe: sort by index, collapse clusters
    nodes = sorted(set(nodes))
    out = []
    for idx, axis in nodes:
        if out:
            px, py = poly[out[-1][0]]
            if math.hypot(poly[idx][0] - px, poly[idx][1] - py) < MIN_NODE_DIST:
                continue
        out.append((idx, axis))
    if len(out) >= 2:
        px, py = poly[out[-1][0]]
        qx, qy = poly[out[0][0]]
        if math.hypot(qx - px, qy - py) < MIN_NODE_DIST:
            out.pop()
    return out


def fit_segment(samples, a_pt, a_dir, b_pt, b_dir):
    """LSQ fit of handle lengths for a cubic with fixed unit tangents."""
    if len(samples) < 2:
        chord = math.hypot(b_pt[0] - a_pt[0], b_pt[1] - a_pt[1])
        return max(HANDLE_GRID, chord / 3), max(HANDLE_GRID, chord / 3)
    # chord-length parameterization
    ts, total = [0.0], 0.0
    for i in range(1, len(samples)):
        total += math.hypot(samples[i][0] - samples[i - 1][0],
                            samples[i][1] - samples[i - 1][1])
        ts.append(total)
    ts = [t / total if total else 0 for t in ts]
    # P(t) = B0 A + B1 (A + a tA) + B2 (B - b tB) + B3 B
    # residual r = P(t) - S; unknowns a, b
    m00 = m01 = m11 = r0 = r1 = 0.0
    for (sx, sy), t in zip(samples, ts):
        mt = 1 - t
        b1 = 3 * mt * mt * t
        b2 = 3 * mt * t * t
        base_x = (mt**3 + b1) * a_pt[0] + (b2 + t**3) * b_pt[0]
        base_y = (mt**3 + b1) * a_pt[1] + (b2 + t**3) * b_pt[1]
        # coefficient vectors for a and b
        ca = (b1 * a_dir[0], b1 * a_dir[1])
        cb = (-b2 * b_dir[0], -b2 * b_dir[1])
        dx, dy = sx - base_x, sy - base_y
        m00 += ca[0] * ca[0] + ca[1] * ca[1]
        m01 += ca[0] * cb[0] + ca[1] * cb[1]
        m11 += cb[0] * cb[0] + cb[1] * cb[1]
        r0 += ca[0] * dx + ca[1] * dy
        r1 += cb[0] * dx + cb[1] * dy
    det = m00 * m11 - m01 * m01
    chord = math.hypot(b_pt[0] - a_pt[0], b_pt[1] - a_pt[1])
    if abs(det) < 1e-9:
        return chord / 3, chord / 3
    a = (r0 * m11 - r1 * m01) / det
    b = (r1 * m00 - r0 * m01) / det
    lim = chord * 1.2
    return min(max(a, 0.0), lim), min(max(b, 0.0), lim)


def convert_contour(contour, scale):
    poly = [(x * scale, y * scale) for x, y in flatten(contour)]
    if len(poly) < 8:
        return None
    poly = smooth(resample(poly))
    nodes = find_nodes(poly)
    if len(nodes) < 2:
        return None
    n = len(poly)
    # snapped node positions + travel-direction tangents
    snapped = []
    for idx, axis in nodes:
        x, y = poly[idx]
        nxt = poly[(idx + 1) % n]
        prv = poly[(idx - 1) % n]
        if axis == 'V':  # vertical tangent: sign of y travel
            s = 1.0 if (nxt[1] - prv[1]) >= 0 else -1.0
            d = (0.0, s)
        else:
            s = 1.0 if (nxt[0] - prv[0]) >= 0 else -1.0
            d = (s, 0.0)
        snapped.append(((snap(x, NODE_GRID), snap(y, NODE_GRID)), d, idx))
    # fit each inter-node segment
    pts = []  # UFO point list: (x, y, type, smooth)
    m = len(snapped)
    for j in range(m):
        (a_pt, a_dir, ai) = snapped[j]
        (b_pt, b_dir, bi) = snapped[(j + 1) % m]
        if bi > ai:
            samples = poly[ai:bi + 1]
        else:
            samples = poly[ai:] + poly[:bi + 1]
        a_len, b_len = fit_segment(samples, a_pt, a_dir, b_pt, b_dir)
        a_len = max(HANDLE_GRID, snap(a_len, HANDLE_GRID))
        b_len = max(HANDLE_GRID, snap(b_len, HANDLE_GRID))
        c1 = (a_pt[0] + a_dir[0] * a_len, a_pt[1] + a_dir[1] * a_len)
        c2 = (b_pt[0] - b_dir[0] * b_len, b_pt[1] - b_dir[1] * b_len)
        pts.append((c1[0], c1[1], None, False))
        pts.append((c2[0], c2[1], None, False))
        pts.append((b_pt[0], b_pt[1], 'curve', True))
    return pts


# --- glyph + font driver --------------------------------------------------------

class StyleWriter:
    """Draw recorded (converted) data into a pointPen."""
    def __init__(self, contours, components):
        self.contours = contours
        self.components = components

    def drawPoints(self, pen):
        for c in self.contours:
            pen.beginPath()
            for x, y, typ, smooth in c:
                pen.addPoint((x, y), segmentType=typ, smooth=smooth)
            pen.endPath()
        for base, xf in self.components:
            pen.addComponent(base, xf)


def convert_ufo(src, dst, scale=1.0):
    src, dst = Path(src), Path(dst)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    gs = GlyphSet(dst / 'glyphs')
    stats = {'converted': 0, 'skipped': 0, 'components': 0, 'warn': []}
    for name in sorted(gs.keys()):
        shell = GlyphShell()
        rec = ContourRecorder()
        gs.readGlyph(name, shell, rec)
        new_contours = []
        ok = True
        for c in rec.contours:
            out = convert_contour(c, scale)
            if out is None and len(c) > 2:
                ok = False
            if out:
                new_contours.append(out)
        for base, xf in rec.components:
            if abs(xf[1]) > 1e-6 or abs(xf[2]) > 1e-6:
                stats['warn'].append(f'{name}: rotated/skewed component {base}')
            stats['components'] += 1
        if not rec.contours and not rec.components:
            stats['skipped'] += 1
            continue
        if scale != 1.0:
            shell.width = snap(getattr(shell, 'width', 0) * scale, HANDLE_GRID)
            rec.components = [
                (b, (xf[0], xf[1], xf[2], xf[3],
                     snap(xf[4] * scale, HANDLE_GRID), snap(xf[5] * scale, HANDLE_GRID)))
                for b, xf in rec.components]
        lib = getattr(shell, 'lib', None) or {}
        lib['public.markColor'] = '1,0.5,0,1'  # machine output = orange
        shell.lib = lib
        writer = StyleWriter(new_contours, rec.components)
        gs.writeGlyph(name, shell, writer.drawPoints)
        stats['converted'] += 1 if new_contours else 0
        if not ok:
            stats['warn'].append(f'{name}: contour too small to sand, dropped')
    gs.writeContents()
    return stats


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    scale = 1.0
    for a in sys.argv[1:]:
        if a.startswith('--scale'):
            scale = float(a.split('=')[1] if '=' in a else sys.argv[sys.argv.index(a) + 1])
    if len(args) < 2:
        raise SystemExit(__doc__)
    stats = convert_ufo(args[0], args[1], scale)
    print(f"{args[0]} -> {args[1]} (scale {scale})")
    print(f"  converted {stats['converted']} glyphs, "
          f"skipped {stats['skipped']} empty, {stats['components']} components")
    for w in stats['warn'][:20]:
        print(f'  WARN {w}')
    if len(stats['warn']) > 20:
        print(f"  ... {len(stats['warn']) - 20} more warnings")


if __name__ == '__main__':
    main()
