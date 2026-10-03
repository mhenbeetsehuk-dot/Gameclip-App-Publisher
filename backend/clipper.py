
import cv2,subprocess
from pathlib import Path

def duration(path):
 p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(path)],capture_output=True,text=True,check=True,timeout=30)
 return float(p.stdout.strip() or 0)

def action_windows(path,count,clip_len=30):
 cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 30
 frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0); step=max(1,int(fps))
 prev=None;scores=[];i=0
 while i<frames:
  cap.set(cv2.CAP_PROP_POS_FRAMES,i); ok,frame=cap.read()
  if not ok: break
  gray=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(320,180))
  if prev is not None:scores.append((float(cv2.absdiff(prev,gray).mean()),i/fps))
  prev=gray;i+=step
 cap.release(); D=duration(path)
 if D<=clip_len:return [(0,0)]
 scores.sort(reverse=True); chosen=[]
 for _,t in scores:
  start=max(0,min(t-clip_len/2,D-clip_len))
  if all(abs(start-x)>clip_len*0.7 for x in chosen):chosen.append(start)
  if len(chosen)>=count:break
 if not chosen: chosen=[0]
 return [(1,x) for x in chosen]

def render(src,start,out,clip_len=30,music=None,music_start=0,vertical=True):
 vf="scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2" if vertical else "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"
 cmd=["ffmpeg","-y","-ss",str(start),"-i",str(src),"-t",str(clip_len)]
 if music and Path(music).exists():
  cmd+=["-ss",str(music_start),"-i",str(music),"-map","0:v:0","-map","1:a:0"]
 cmd+=["-vf",vf,"-threads","1","-pix_fmt","yuv420p","-movflags","+faststart","-c:v","libx264","-preset","veryfast","-c:a","aac","-shortest",str(out)]
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=600)
