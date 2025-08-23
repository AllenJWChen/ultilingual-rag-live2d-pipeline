import sys, pyttsx3, os

def speak(text: str, out_path='services/live2d/out.wav'):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    engine = pyttsx3.init()
    engine.save_to_file(text, out_path)
    engine.runAndWait()
    print("Saved:", out_path)

if __name__ == "__main__":
    txt = sys.argv[1] if len(sys.argv)>1 else "你好，這是 Live2D 嘴型同步的語音。"
    speak(txt)
