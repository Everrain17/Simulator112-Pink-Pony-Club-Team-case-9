import io
import os
import json
import torch
import re  # <-- Добавляем для поиска чисел
import scipy.io.wavfile as wavfile  # <-- Добавляем для работы с WAV в памяти
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from vosk import Model, KaldiRecognizer
from num2words import num2words  

app = FastAPI(title="Local Silero v5 TTS + Vosk STT Server")

# Автоматически проверяем видеокарту RTX 4050
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[СЕРВЕР] Выбранное устройство: {device}")

TTS_MODEL_PATH = "v5_ru.pt"
STT_MODEL_PATH = "vosk-model-small-ru-0.22"

# === ЗАГРУЗКА TTS МОДЕЛИ ===
if not os.path.exists(TTS_MODEL_PATH):
    print(f"TTS модель не найдена: {TTS_MODEL_PATH}")
    exit(1)

print("[TTS] Загрузка Silero v5 с диска...")
try:
    importer = torch.package.PackageImporter(TTS_MODEL_PATH)
    tts_model = importer.load_pickle("tts_models", "model")
    tts_model.to(device) # Переносим веса на устройство (без перезаписи переменной!)
    TTS_SAMPLE_RATE = 24000
    print("TTS модель успешно загружена в Offline режиме!")
except Exception as e:
    print(f"Ошибка развертывания TTS пакета: {e}")
    exit(1)

# === ЗАГРУЗКА STT МОДЕЛИ (VOSK) ===
stt_model = None
if os.path.exists(STT_MODEL_PATH):
    print(f"[STT] Загрузка Vosk модели из {STT_MODEL_PATH}...")
    try:
        stt_model = Model(STT_MODEL_PATH)
        print("STT модель загружена! Микрофон полностью автономен.")
    except Exception as e:
        print(f"STT модель не загружена: {e}")
else:
    print(f"Vosk модель не найдена в {STT_MODEL_PATH}")


# ============================================================
# 🔥 ИСПРАВЛЕНО: СТЕРИЛЬНЫЙ POST ENDPOINT ДЛЯ C# СВЯЗКИ
# ============================================================
@app.post("/v1/audio/speech")
async def text_to_speech(request: dict):
    try:
        text = request.get("input", "")
        gender = request.get("gender", "male")
        panic_level = request.get("panic_level", 0)
        
        if not text or len(text.strip()) < 2:
            return StreamingResponse(io.BytesIO(), media_type="audio/wav")

        # 🔥 НАДСТРОЙКА: Находим все числа и переводим их в слова на русском
        # Например: "улица Обручева, 39" -> "улица Обручева, тридцать девять"
        def replace_match(match):
            return num2words(int(match.group(0)), lang='ru')
        
        normalized_text = re.sub(r'\d+', replace_match, text)

        speaker = "baya" if gender == "female" else "aidar"
        
        current_sample_rate = TTS_SAMPLE_RATE
        if panic_level > 80:
            current_sample_rate = int(TTS_SAMPLE_RATE * 1.2)
            print(f"[TTS] РЕЖИМ ПАНИКИ ({panic_level}%). Скорость повышена!")
        elif panic_level > 50:
            current_sample_rate = int(TTS_SAMPLE_RATE * 1.1)
            
        # Логируем уже очищенный текст, чтобы видеть, как он пойдет в Silero
        print(f"[TTS] Синтез: \"{normalized_text}\" | Голос: {speaker} | Выходной SampleRate: {current_sample_rate}Hz")

        with torch.no_grad():
            audio_tensor = tts_model.apply_tts(
                text=normalized_text,  # <-- Отправляем текст БЕЗ цифр
                speaker=speaker,
                sample_rate=TTS_SAMPLE_RATE
            )
        
        audio_numpy = audio_tensor.detach().cpu().numpy()
        buffer = io.BytesIO()
        
        wavfile.write(buffer, current_sample_rate, audio_numpy)
        buffer.seek(0)

        return StreamingResponse(buffer, media_type="audio/wav")
        
    except Exception as e:
        print(f"[TTS GENERATION ERROR] {e}")
        return StreamingResponse(io.BytesIO(), media_type="audio/wav", status_code=500)





# ============================================================
# STT WEBSOCKET: /stt (Остается без изменений)
# ============================================================
@app.websocket("/stt")
async def stt_websocket(websocket: WebSocket):
    await websocket.accept()
    if stt_model is None:
        await websocket.close()
        return

    recognizer = KaldiRecognizer(stt_model, 16000)
    recognizer.SetWords(True)
    print("[STT] WebSocket подключен к пульту")

    try:
        while True:
            data = await websocket.receive_bytes()
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")
                if text:
                    await websocket.send_json({"text": text, "final": True})
            else:
                partial = json.loads(recognizer.PartialResult())
                text = partial.get("partial", "")
                if text:
                    await websocket.send_json({"text": text, "final": False})
    except WebSocketDisconnect:
        print("[STT] WebSocket отключен")
    except Exception as e:
        print(f"[STT ERROR] {e}")

if __name__ == "__main__":
    from pathlib import Path
    import uvicorn

    BASE_DIR = Path(__file__).resolve().parent
    CERT_DIR = BASE_DIR.parent / "serv-112" / "certs"

    CERT_FILE = CERT_DIR / "server.crt"
    KEY_FILE = CERT_DIR / "server.key"

    print(f"[HTTPS] Сертификат: {CERT_FILE}")
    print(f"[HTTPS] Ключ: {KEY_FILE}")

    if not CERT_FILE.exists():
        print(f"SSL-сертификат не найден: {CERT_FILE}")
        exit(1)

    if not KEY_FILE.exists():
        print(f"SSL-ключ не найден: {KEY_FILE}")
        exit(1)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        ssl_certfile=str(CERT_FILE),
        ssl_keyfile=str(KEY_FILE)
    )