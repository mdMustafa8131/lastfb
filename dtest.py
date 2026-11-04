import subprocess
from pathlib import Path
import numpy as np
from PIL import Image
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
IMG = Path("media/ready/770827062784222/1793788583313_935cec.jpg")
MUS = Path("media/music/islam/qabr/Sad-Islamic-Nasheed-SnapYT.App.mp3")
OUT = Path("out_test.mp4")
TMP = Path("media/video/ripple_tmp_w520_a13")
TMP.mkdir(parents=True, exist_ok=True)

W, H, N, MAP_FPS = 1080, 1920, 100, 16
AMP, LAM = 13.0, 520.0

if not (TMP / f"xm_{N - 1:03d}.png").exists():
    ys = np.arange(H, dtype=np.float32)[:, None]
    xs = np.arange(W, dtype=np.float32)[None, :]
    for i in range(N):
        ph = 2 * np.pi * i / N
        xm = np.broadcast_to(128.0 + AMP * np.sin(2 * np.pi * ys / LAM + ph), (H, W))
        ym = np.broadcast_to(128.0 + AMP * np.sin(2 * np.pi * xs / LAM + ph), (H, W))
        Image.fromarray(np.clip(xm, 0, 255).astype(np.uint8), "L").save(TMP / f"xm_{i:03d}.png")
        Image.fromarray(np.clip(ym, 0, 255).astype(np.uint8), "L").save(TMP / f"ym_{i:03d}.png")
print("maps:", N)

fc = (
    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=22[bg];"
    "[0:v]scale=1080:-2[fg];"
    "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
    "[2:v]format=gray[xm];[3:v]format=gray[ym];"
    "[base][xm][ym]displace=edge=mirror,format=yuv420p,fade=t=out:st=13:d=2[v]"
)

cmd = [FF, "-y", "-loop", "1", "-framerate", "30", "-i", str(IMG), "-i", str(MUS),
       "-f", "image2", "-stream_loop", "-1", "-framerate", str(MAP_FPS), "-i", str(TMP / "xm_%03d.png"),
       "-f", "image2", "-stream_loop", "-1", "-framerate", str(MAP_FPS), "-i", str(TMP / "ym_%03d.png"),
       "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-t", "15",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
       "-c:a", "aac", "-b:a", "128k", "-shortest", str(OUT)]

p = subprocess.run(cmd, capture_output=True, text=True)
print("returncode:", p.returncode)
print((p.stderr or "")[-1200:])