
import cv2,subprocess,json
from pathlib import Path

def duration(path):
 p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(path)],capture_output=True,text=True,check=True,timeout=30)
 return float(p.stdout.strip() or 0)

def action_windows(path,count,clip_len=30,region_start=0,region_end=None):
 D=duration(path)
 region_start=max(0,min(float(region_start),D))
 region_end=D if region_end is None else max(region_start,min(float(region_end),D))
 if D<=clip_len:return [(0,0)]
 cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 30
 frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0); step=max(1,int(fps))
 first=max(0,int(region_start*fps)); last=min(frames,int(region_end*fps))
 prev=None;scores=[];i=first
 while i<last:
  cap.set(cv2.CAP_PROP_POS_FRAMES,i); ok,frame=cap.read()
  if not ok: break
  gray=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(320,180))
  if prev is not None:scores.append((float(cv2.absdiff(prev,gray).mean()),i/fps))
  prev=gray;i+=step
 cap.release()
 scores.sort(reverse=True); chosen=[]
 max_start=max(region_start,region_end-clip_len)
 for _,t in scores:
  start=max(region_start,min(t-clip_len/2,max_start))
  if all(abs(start-x)>clip_len*0.7 for x in chosen):chosen.append(start)
  if len(chosen)>=count:break
 if not chosen: chosen=[region_start]
 return [(1,x) for x in chosen]

def render(src,start,out,clip_len=30,music=None,music_start=0,vertical=True):
 vf="scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2" if vertical else "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"
 cmd=["ffmpeg","-y","-ss",str(start),"-i",str(src)]
 if music and Path(music).exists():
  cmd+=["-ss",str(music_start),"-i",str(music),"-map","0:v:0","-map","1:a:0"]
 elif not any(s['codec_type']=='audio' for s in media_info(src)['streams']):
  cmd+=["-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-map","0:v:0","-map","1:a:0"]
 cmd+=["-t",str(clip_len),"-vf",vf,"-r","30","-threads","1","-pix_fmt","yuv420p","-movflags","+faststart","-c:v","libx264","-preset","veryfast","-c:a","aac","-b:a","128k","-ar","48000","-shortest",str(out)]
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=600)


def media_info(path):
 return json.loads(subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=30).stdout)
