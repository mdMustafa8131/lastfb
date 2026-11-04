import subprocess
from pathlib import Path
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
D = Path("media/video/ripple_maps_9_347_150")

for name in ("xm", "ym"):
    if not Path(f"{name}.mp4").exists():
        subprocess.run([FF, "-y", "-framerate", "10", "-i", str(D / f"{name}_%03d.png"),
                        "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", f"{name}.mp4"],
                       capture_output=True)
print("maps encoded")

IMG = sorted(Path("media/ready").glob("*/*.jpg"))[0]
MUS = sorted(Path("media/music/islam/qabr").glob("*"))[0]
OUT = Path("out_test2.mp4")

fc = ("[0:v]scale=720:1280,setsar=1[base];"
      "[2:v]format=gray,setsar=1[xm];[3:v]format=gray,setsar=1[ym];"
      "[base][xm][ym]displace=edge=mirror,rgbashift=rh=4:bh=-4,setsar=1[v]")

cmd = [FF, "-y", "-loop", "1", "-framerate", "25", "-i", str(IMG),
       "-stream_loop", "-1", "-i", str(MUS),
       "-stream_loop", "-1", "-i", "xm.mp4",
       "-stream_loop", "-1", "-i", "ym.mp4",
       "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-t", "15",
       "-c:v", "libx264", "-preset", "ultrafast", "-crf", "27",
       "-pix_fmt", "yuv420p", "-r", "25", "-c:a", "aac", "-b:a", "96k",
       "-shortest", str(OUT)]

p = subprocess.run(cmd, capture_output=True, text=True)
print("encode rc", p.returncode)
print((p.stderr or "")[-400:])

r = subprocess.run([FF, "-v", "error", "-stats", "-i", str(OUT), "-map", "0:v", "-f", "null", "-"],
                   capture_output=True, text=True)
print("decode rc", r.returncode)
print(r.stderr[-300:])