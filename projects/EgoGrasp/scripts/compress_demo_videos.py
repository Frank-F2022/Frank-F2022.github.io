#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_INPUT_DIR = Path("/home/hanyu/data1/web/EgoGrasp_Mat/demo video")
DEFAULT_OUTPUT_DIR = Path("/home/hanyu/data1/web/EgoGrasp.io/videos/demo")
VIDEO_SUFFIXES = {".mp4"}


def default_jobs() -> int:
    cpu_count = os.cpu_count() or 1
    return min(8, max(1, cpu_count // 16))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compress EgoGrasp demo videos for the project website without touching "
            "the originals. The default path keeps the original resolution and "
            "uses VP9/WebM for smaller browser-friendly outputs."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--encoder",
        choices=["libvpx-vp9", "libx265", "libx264"],
        default="libvpx-vp9",
        help=(
            "Video encoder. libvpx-vp9 is the default for smaller web playback; "
            "libx265/libx264 produce MP4 outputs."
        ),
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=28,
        help="Quality factor. Lower is higher quality and larger files.",
    )
    parser.add_argument(
        "--preset",
        default="medium",
        help="Encoding speed/ratio trade-off for libx265/libx264.",
    )
    parser.add_argument(
        "--max-edge",
        type=int,
        default=0,
        help=(
            "Maximum long-edge resolution. Use 0 to keep original resolution. "
            "The default is 0 to preserve the source size exactly."
        ),
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="Number of videos to encode in parallel. 0 chooses an automatic value.",
    )
    parser.add_argument(
        "--ffmpeg-threads",
        type=int,
        default=0,
        help="Thread limit per ffmpeg process. 0 chooses an automatic value.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite files that already exist in the output directory.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N videos. Useful for quick testing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without running ffmpeg.",
    )
    parser.add_argument(
        "--vp9-deadline",
        choices=["good", "best", "realtime"],
        default="good",
        help="VP9 deadline mode. Ignored for x264/x265.",
    )
    parser.add_argument(
        "--vp9-cpu-used",
        type=int,
        default=2,
        help="VP9 speed setting. Lower is slower but more efficient.",
    )
    return parser.parse_args()


def ensure_ffmpeg_tools() -> None:
    for binary_name in ("ffmpeg", "ffprobe"):
        if shutil.which(binary_name) is None:
            raise RuntimeError(f"Cannot find required binary: {binary_name}")


def normalize_args(args: argparse.Namespace) -> argparse.Namespace:
    cpu_count = os.cpu_count() or 1

    if args.jobs < 0:
        raise ValueError("--jobs must be >= 0")
    if args.ffmpeg_threads < 0:
        raise ValueError("--ffmpeg-threads must be >= 0")
    if args.max_edge < 0:
        raise ValueError("--max-edge must be >= 0")

    if args.jobs == 0:
        args.jobs = default_jobs()

    if args.jobs > 1 and args.ffmpeg_threads == 0:
        args.ffmpeg_threads = max(1, min(16, cpu_count // args.jobs // 2))

    return args


def log(message: str) -> None:
    print(message, flush=True)


def is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def find_videos(input_dir: Path) -> list[Path]:
    videos = [
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    return sorted(videos)


def probe_video(video_path: Path) -> dict:
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])

    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), None
    )
    if video_stream is None:
        raise RuntimeError(f"No video stream found in {video_path}")

    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "codec_name": video_stream.get("codec_name", "unknown"),
    }


def scale_dimensions(width: int, height: int, max_edge: int) -> tuple[int, int]:
    if max_edge <= 0 or max(width, height) <= max_edge:
        return width, height

    if width >= height:
        scaled_width = max_edge
        scaled_height = max(2, int(round((height * max_edge / width) / 2) * 2))
    else:
        scaled_height = max_edge
        scaled_width = max(2, int(round((width * max_edge / height) / 2) * 2))
    return scaled_width, scaled_height


def build_scale_filter(
    width: int,
    height: int,
    max_edge: int,
) -> tuple[str | None, int, int]:
    target_width, target_height = scale_dimensions(width, height, max_edge)
    if (target_width, target_height) == (width, height):
        return None, target_width, target_height

    if width >= height:
        return f"scale={max_edge}:-2:flags=lanczos", target_width, target_height
    return f"scale=-2:{max_edge}:flags=lanczos", target_width, target_height


def format_bytes(num_bytes: int) -> str:
    size = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f}{unit}"
        size /= 1024
    return f"{size:.2f}TB"


def output_suffix(encoder: str) -> str:
    if encoder == "libvpx-vp9":
        return ".webm"
    return ".mp4"


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    scale_filter: str | None,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-y",
        "-i",
        str(input_path),
        "-map_metadata",
        "0",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        args.encoder,
        "-crf",
        str(args.crf),
    ]

    if args.ffmpeg_threads > 0:
        command.extend(["-threads", str(args.ffmpeg_threads)])

    if scale_filter is not None:
        command.extend(["-vf", scale_filter])

    if args.encoder == "libvpx-vp9":
        command.extend(
            [
                "-b:v",
                "0",
                "-deadline",
                args.vp9_deadline,
                "-cpu-used",
                str(args.vp9_cpu_used),
                "-row-mt",
                "1",
                "-tile-columns",
                "2",
                "-frame-parallel",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "libopus",
                "-b:a",
                "128k",
            ]
        )
    else:
        command.extend(
            [
                "-movflags",
                "+faststart",
                "-preset",
                args.preset,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
            ]
        )
        if args.encoder == "libx265":
            command.extend(["-tag:v", "hvc1", "-x265-params", "log-level=error"])

    command.append(str(output_path))
    return command


def summarize_ffmpeg_error(exc: subprocess.CalledProcessError) -> str:
    stderr_text = (exc.stderr or exc.stdout or "").strip()
    if not stderr_text:
        return f"ffmpeg exited with code {exc.returncode}"
    return stderr_text.splitlines()[-1]


def compress_video(
    video_path: Path,
    input_dir: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> tuple[str, int, int, str]:
    relative_path = video_path.relative_to(input_dir)
    relative_output = relative_path.with_suffix(output_suffix(args.encoder))
    output_path = output_dir / relative_output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not args.overwrite:
        return "skipped", 0, 0, f"[skip] {relative_output} -> already exists"

    try:
        info = probe_video(video_path)
    except Exception as exc:
        return "failed", 0, 0, f"[fail] {relative_path}: probe failed ({exc})"

    scale_filter, target_width, target_height = build_scale_filter(
        info["width"], info["height"], args.max_edge
    )
    temp_output_path = output_path.with_name(
        f"{output_path.stem}.tmp{output_path.suffix}"
    )
    command = build_ffmpeg_command(
        input_path=video_path,
        output_path=temp_output_path,
        scale_filter=scale_filter,
        args=args,
    )

    if args.dry_run:
        dry_run_lines = [
            f"[dry-run] {relative_path} | {info['codec_name']} {info['width']}x{info['height']} "
            f"-> {target_width}x{target_height}",
            f"          {' '.join(command)}",
        ]
        return "dry-run", 0, 0, "\n".join(dry_run_lines)

    if temp_output_path.exists():
        temp_output_path.unlink()

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        temp_output_path.replace(output_path)
    except subprocess.CalledProcessError as exc:
        if temp_output_path.exists():
            temp_output_path.unlink()
        return "failed", 0, 0, f"[fail] {relative_path}: {summarize_ffmpeg_error(exc)}"
    except Exception as exc:
        if temp_output_path.exists():
            temp_output_path.unlink()
        return "failed", 0, 0, f"[fail] {relative_path}: {exc}"

    input_size = video_path.stat().st_size
    output_size = output_path.stat().st_size
    saved_size = input_size - output_size
    ratio = output_size / input_size if input_size else 0.0

    message = (
        f"[done] {relative_path} | {info['codec_name']} {info['width']}x{info['height']} "
        f"-> {target_width}x{target_height} | {format_bytes(input_size)} -> "
        f"{format_bytes(output_size)} ({ratio:.2%} of original, saved {format_bytes(saved_size)})"
    )
    return "done", input_size, output_size, message


def log_result(index: int, total: int, message: str) -> None:
    lines = message.splitlines()
    if not lines:
        return
    log(f"[{index}/{total}] {lines[0]}")
    for line in lines[1:]:
        log(line)


def main() -> int:
    try:
        args = normalize_args(parse_args())
    except ValueError as exc:
        log(str(exc))
        return 1

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()

    if not input_dir.exists():
        log(f"Input directory does not exist: {input_dir}")
        return 1

    if is_relative_to(output_dir, input_dir) or input_dir == output_dir:
        log("Output directory must be outside the input directory.")
        return 1

    try:
        ensure_ffmpeg_tools()
    except RuntimeError as exc:
        log(str(exc))
        return 1

    videos = find_videos(input_dir)
    if args.limit > 0:
        videos = videos[: args.limit]

    if not videos:
        log(f"No mp4 files found under: {input_dir}")
        return 0

    log(f"Found {len(videos)} video(s) under {input_dir}")
    log(f"Output directory: {output_dir}")
    log(
        f"Encoder={args.encoder}, CRF={args.crf}, preset={args.preset}, max_edge={args.max_edge}, "
        f"jobs={args.jobs}, ffmpeg_threads={args.ffmpeg_threads if args.ffmpeg_threads > 0 else 'auto'}"
    )

    processed_count = 0
    skipped_count = 0
    failed_count = 0
    total_input_bytes = 0
    total_output_bytes = 0
    total_videos = len(videos)

    def handle_result(index: int, result: tuple[str, int, int, str]) -> None:
        nonlocal processed_count
        nonlocal skipped_count
        nonlocal failed_count
        nonlocal total_input_bytes
        nonlocal total_output_bytes
        status, input_bytes, output_bytes, message = result
        log_result(index, total_videos, message)
        if status == "done":
            processed_count += 1
            total_input_bytes += input_bytes
            total_output_bytes += output_bytes
        elif status in {"skipped", "dry-run"}:
            skipped_count += 1
        else:
            failed_count += 1

    if args.jobs == 1 or args.dry_run:
        for index, video_path in enumerate(videos, start=1):
            handle_result(index, compress_video(video_path, input_dir, output_dir, args))
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            future_to_video = {
                executor.submit(
                    compress_video, video_path, input_dir, output_dir, args
                ): video_path
                for video_path in videos
            }
            for index, future in enumerate(as_completed(future_to_video), start=1):
                video_path = future_to_video[future]
                try:
                    result = future.result()
                except Exception as exc:
                    relative_path = video_path.relative_to(input_dir)
                    result = (
                        "failed",
                        0,
                        0,
                        f"[fail] {relative_path}: unexpected worker error ({exc})",
                    )
                handle_result(index, result)

    log("\nSummary")
    log(f"  processed: {processed_count}")
    log(f"  skipped:   {skipped_count}")
    log(f"  failed:    {failed_count}")

    if processed_count > 0:
        saved_bytes = total_input_bytes - total_output_bytes
        ratio = total_output_bytes / total_input_bytes if total_input_bytes else 0.0
        log(f"  total in:  {format_bytes(total_input_bytes)}")
        log(f"  total out: {format_bytes(total_output_bytes)}")
        log(f"  size ratio:{ratio:.2%}")
        log(f"  saved:     {format_bytes(saved_bytes)}")

    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
