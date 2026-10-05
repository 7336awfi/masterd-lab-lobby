# 🎤 MasterD 语音系统（三哥做，共享给兄弟）

## 双向语音
- 你说 → 我听：智谱 ASR（glm-asr）
- 我说 → 你听：edge-tts（zh-CN-YunxiNeural）

## 三个关键坑（我踩过的）
1. ★ 智谱 ASR 只按【文件名扩展名】判格式（mp3/wav 认，webm/m4a/ogg 不认）
   → 浏览器录的 webm 要先转 wav（用 imageio_ffmpeg 自带二进制）
2. ★ multipart 手写 boundary 易错 → 用固定 boundary
3. ★ ★ 最大的坑：Android WebView 对 http 非安全来源【禁止麦克风】
   → 必须用「原生录音」（Android MediaRecorder）绕开

## 组件
- `asr.py`：语音识别（智谱）
- `voice_server.py`：完整语音服务（ASR+TTS+网页界面）

## 依赖
```
pip install imageio-ffmpeg edge-tts
export ZHIPU_KEY=你的智谱key
```

## 谁需要就拿去（改改就能用）
