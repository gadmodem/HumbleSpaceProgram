"""Turn an opaque AI preview checkerboard into a transparent sprite-sheet background.

The image generator can return its transparency preview as near-white checkerboard pixels.  This
tool flood-fills only neutral, high-value pixels connected to the canvas edge, so enclosed white
details such as eyes and spacesuit collars stay intact.  It also performs a nearest-neighbor resize
to keep pixel-art frame boundaries crisp.
"""

from __future__ import annotations

import argparse
from collections import deque

from PIL import Image


def is_preview_background(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, _ = pixel
    return min(r, g, b) >= 210 and max(r, g, b) - min(r, g, b) <= 16


def remove_edge_connected_preview_grid(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    width, height = image.size
    pixels = image.load()
    background: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    def add_if_background(x: int, y: int) -> None:
        if (x, y) in background or not is_preview_background(pixels[x, y]):
            return
        background.add((x, y))
        queue.append((x, y))

    for x in range(width):
        add_if_background(x, 0)
        add_if_background(x, height - 1)
    for y in range(height):
        add_if_background(0, y)
        add_if_background(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                add_if_background(nx, ny)

    for x, y in background:
        r, g, b, _ = pixels[x, y]
        pixels[x, y] = (r, g, b, 0)
    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--size", default="256x384", help="output size, e.g. 256x384")
    args = parser.parse_args()
    width_text, height_text = args.size.lower().split("x", 1)
    output_size = (int(width_text), int(height_text))

    image = remove_edge_connected_preview_grid(Image.open(args.source))
    image.resize(output_size, Image.Resampling.NEAREST).save(args.destination)


if __name__ == "__main__":
    main()
