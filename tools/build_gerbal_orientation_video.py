"""Encode generated human-Gerbal keyframes into the replacement orientation film.

The stock orientation clip is 2,724 frames at 30 fps (90.8 seconds).  This script retains that
duration so KSP2's existing narration and subtitle timings stay aligned, while creating movement
through slow pans, zooms, and short crossfades between independently generated frames.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import av
from PIL import Image, ImageOps


DEFAULT_SIZE = (1920, 1080)


def parse_size(value: str) -> tuple[int, int]:
    width, height = value.lower().split("x", 1)
    return int(width), int(height)


def prepare_frame(path: Path, output_size: tuple[int, int]) -> Image.Image:
    width, height = output_size
    # A little overscan gives the pan/zoom motion room without exposing any borders.
    overscan = (round(width * 1.075), round(height * 1.075))
    with Image.open(path) as image:
        return ImageOps.fit(image.convert("RGB"), overscan, Image.Resampling.LANCZOS)


def pan_crop(image: Image.Image, output_size: tuple[int, int], progress: float, index: int) -> Image.Image:
    width, height = output_size
    max_x = image.width - width
    max_y = image.height - height
    # Alternate the travel direction so the presentation feels alive without requiring video AI.
    starts = ((0.15, 0.25), (0.78, 0.28), (0.20, 0.72), (0.72, 0.70), (0.28, 0.20), (0.75, 0.78))
    ends = ((0.78, 0.70), (0.20, 0.72), (0.75, 0.22), (0.24, 0.28), (0.72, 0.76), (0.22, 0.20))
    start = starts[index % len(starts)]
    end = ends[index % len(ends)]
    x = round(max_x * (start[0] + (end[0] - start[0]) * progress))
    y = round(max_y * (start[1] + (end[1] - start[1]) * progress))
    return image.crop((x, y, x + width, y + height))


def render_frame(frames: list[Image.Image], time_seconds: float, duration: float, output_size: tuple[int, int]) -> Image.Image:
    scene_duration = duration / len(frames)
    transition = min(1.25, scene_duration * 0.20)
    index = min(int(time_seconds / scene_duration), len(frames) - 1)
    local_time = time_seconds - index * scene_duration
    current = pan_crop(frames[index], output_size, min(local_time / scene_duration, 1.0), index)

    if index == len(frames) - 1 or local_time < scene_duration - transition:
        return current
    next_index = index + 1
    next_frame = pan_crop(frames[next_index], output_size, 0.0, next_index)
    blend = (local_time - (scene_duration - transition)) / transition
    return Image.blend(current, next_frame, blend)


def encode(frames_dir: Path, destination: Path, duration: float, fps: int, output_size: tuple[int, int]) -> None:
    frame_paths = sorted(frames_dir.glob("orientation_*.png"))
    if len(frame_paths) < 2:
        raise ValueError(f"Expected at least two orientation_*.png frames in {frames_dir}")

    prepared = [prepare_frame(path, output_size) for path in frame_paths]
    frame_count = round(duration * fps)
    destination.parent.mkdir(parents=True, exist_ok=True)

    container = av.open(str(destination), "w", options={"movflags": "+faststart"})
    try:
        stream = container.add_stream("libx264", rate=fps)
        stream.width, stream.height = output_size
        stream.pix_fmt = "yuv420p"
        # Explicit Rec. 709 metadata avoids Windows Media Foundation treating the otherwise
        # unspecified H.264 color tags as a format it needs to guess at during Unity import.
        stream.codec_context.color_primaries = 1  # AVCOL_PRI_BT709
        stream.codec_context.color_trc = 1  # AVCOL_TRC_BT709
        stream.codec_context.colorspace = 1  # AVCOL_SPC_BT709
        stream.bit_rate = 2_500_000
        stream.gop_size = fps * 2
        # Unity's Windows video importer is most reliable with a simple H.264 stream: no B-frames,
        # closed GOPs, and a baseline-compatible profile keep presentation timestamps monotonic.
        stream.options = {
            "profile": "baseline",
            "preset": "medium",
            "tune": "stillimage",
            "bf": "0",
            "refs": "1",
            "x264-params": f"keyint={fps * 2}:min-keyint={fps * 2}:scenecut=0:open-gop=0",
        }

        for index in range(frame_count):
            image = render_frame(prepared, index / fps, duration, output_size)
            frame = av.VideoFrame.from_image(image)
            frame.pts = index
            for packet in stream.encode(frame):
                container.mux(packet)
            if index % (fps * 10) == 0:
                print(f"encoded {index / fps:.0f}s / {duration:.1f}s")

        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--duration", type=float, default=90.8)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--size", default="1920x1080")
    args = parser.parse_args()

    encode(args.frames_dir, args.destination, args.duration, args.fps, parse_size(args.size))


if __name__ == "__main__":
    main()
