#!/usr/bin/env python3
"""Render the public architecture overview; not implementation evidence.

Revision: 3
Date: 2026-09-22
Time: 02:32 UTC

Requires Pillow and DejaVu Sans (regular and bold) fonts discoverable by Pillow.
These are optional diagram-generation tools, not project runtime dependencies.
Run from any directory:
    python3 docs/diagrams/render_architecture.py
Outputs spec-ir-uvmgen-architecture.png beside this script (overwrites that PNG).
"""
from pathlib import Path
import math

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, SCALE = 1600, 1190, 2
BG = '#f7f9fc'
INK = '#172033'
TEXT = '#35465e'
GRAY = '#647792'
BLUE = '#0072ad'
PURPLE = '#8045ff'
GREEN = '#008568'
AMBER = '#a76408'
image = Image.new('RGB', (WIDTH * SCALE, HEIGHT * SCALE), BG)
draw = ImageDraw.Draw(image)


def font(size, bold=False):
    return ImageFont.truetype(
        'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf', size * SCALE
    )


def text(x, y, content, size=22, color=TEXT, bold=False):
    draw.text((x * SCALE, y * SCALE), content, font=font(size, bold), fill=color)


def lines(content, width, size=22):
    result = []
    for paragraph in content.split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = (line + ' ' + word).strip()
            if draw.textlength(candidate, font=font(size)) > width * SCALE and line:
                result.append(line)
                line = word
            else:
                line = candidate
        result.append(line)
    return result


def box(x, y, w, h, title, body, color=BLUE):
    draw.rounded_rectangle(
        (x * SCALE, y * SCALE, (x + w) * SCALE, (y + h) * SCALE),
        radius=17 * SCALE, fill='white', outline=color, width=2 * SCALE
    )
    if draw.textlength(title, font=font(25, True)) > (w - 44) * SCALE:
        raise ValueError(f'Title does not fit: {title}')
    text(x + 22, y + 18, title, 25, color, True)
    wrapped = lines(body, w - 44)
    if 64 + len(wrapped) * 32 > h - 12:
        raise ValueError(f'Body does not fit: {title}')
    for i, line in enumerate(wrapped):
        text(x + 22, y + 64 + i * 32, line)


def arrow(points, color=GRAY):
    draw.line([(x * SCALE, y * SCALE) for x, y in points], fill=color, width=3 * SCALE)
    x, y = points[-1]
    px, py = points[-2]
    angle = math.atan2(y - py, x - px)
    corners = [(x, y)] + [
        (x - 16 * math.cos(angle) + sign * 7 * math.sin(angle),
         y - 16 * math.sin(angle) - sign * 7 * math.cos(angle))
        for sign in (-1, 1)
    ]
    draw.polygon([(int(a * SCALE), int(b * SCALE)) for a, b in corners], fill=color)


text(40, 24, 'spec-ir-uvmgen', 42, INK, True)
text(40, 87, 'Deterministic spec-to-UVM prototype · two demonstrated tracks · no simulation evidence', 24)

text(40, 145, 'TIMER  /  structural generation', 25, BLUE, True)
box(40, 205, 340, 220, 'Structured spec',
    'simple_timer fixture\nMarkdown sections + tables\nDeterministic extraction')
box(435, 205, 350, 220, 'Validated IR',
    'Pydantic schema checks\nSpecification facts\n+ implementation contract')
box(840, 205, 350, 220, 'UVM renderer',
    'Derived scopes + names\nJinja2 templates\nSeven SV skeleton files')
box(1245, 205, 315, 220, 'Render evidence',
    '24 content checks\n7 baseline files:\nbyte-identical', GREEN)
for start, end in [(380, 435), (785, 840), (1190, 1245)]:
    arrow([(start, 315), (end - 5, 315)])
text(40, 450, 'Fixture-level evidence: content checks and a saved-baseline comparison, not compilation or DUT correctness.', 21)

text(40, 526, 'BUFFER  /  semantics + Python reference oracle', 25, PURPLE, True)
box(40, 694, 340, 205, 'DUT specification',
    'Concurrent transactions\nLifecycle, reset, hold\nBehavioral requirements', PURPLE)
box(455, 600, 515, 175, 'Semantic candidate',
    'Maintained extraction tables → JSON\nSchema + source-reference validation', PURPLE)
box(1080, 600, 480, 175, 'GR-009 validation',
    '36 requirements · reference consistency\nCandidate only; not generation-ready', GREEN)
box(455, 827, 515, 180, 'Python reference oracle',
    'Hand-written event/state contracts\nExpected lifecycle results + diagnostics', PURPLE)
box(1080, 827, 480, 180, 'Hand-authored traces',
    '8/8 selected stories + ordering guards\nObservations + expected verdict checks', GREEN)
arrow([(380, 737), (412, 737), (412, 687), (450, 687)])
arrow([(380, 855), (412, 855), (412, 917), (450, 917)])
arrow([(970, 687), (1075, 687)])
arrow([(1080, 932), (975, 932)])
text(986, 895, 'events', 19)
text(40, 922, 'Separate from the timer IR.', 21, INK, True)
text(40, 958, 'No oracle is generated here.', 21)

# Dashed boundary marks future integration, not an implemented data path.
for x in range(40, 1560, 22):
    draw.line([(x * SCALE, 1050 * SCALE), (min(x + 12, 1560) * SCALE, 1050 * SCALE)],
              fill=AMBER, width=2 * SCALE)
text(40, 1071, 'FUTURE — DUT + UVM simulation → monitor observations → oracle integration', 25, AMBER, True)
text(40, 1112, 'DUT/clock/reset hookup, functional agents/RAL/scoreboard, and simulation remain unverified.', 22)
text(40, 1152, 'Evidence boundaries and reproduction commands: PROOF.md   ·   Architecture detail: docs/architecture.md', 18, GRAY)

output = Path(__file__).resolve().with_name('spec-ir-uvmgen-architecture.png')
image.save(output)
print(f'{output.name}: {image.width} × {image.height} pixels')
