using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using SimCore.Interfaces;

namespace AIEngine
{
    public class TtsService : ITtsService
    {
        private readonly HttpClient _httpClient;
        private readonly string _baseUrl;
        private readonly string _modelName;

        private readonly string _voice;

        public TtsService(
            string baseUrl = "https://localhost:8000/v1",
            string modelName = "silero",
            string voice = "aidar")
        {
            _baseUrl = baseUrl.TrimEnd('/');
            _modelName = modelName;
            _voice = voice;

            var handler = new HttpClientHandler
            {
                ServerCertificateCustomValidationCallback =
                    HttpClientHandler.DangerousAcceptAnyServerCertificateValidator
            };

            _httpClient = new HttpClient(handler);
            _httpClient.DefaultRequestHeaders.Add(
                "User-Agent",
                "Simulator112-LocalTTS/1.0"
            );
        }

        // Перегрузка по умолчанию (для совместимости с базовым интерфейсом ITtsService)
        public Task<byte[]> SynthesizeAsync(
            string text,
            CancellationToken ct = default)
        {
            return SynthesizeAsync(text, "male", 0, "CALL-UNKNOWN", ct);
        }

        // Основной метод синтеза, принимающий callId
        public async Task<byte[]> SynthesizeAsync(
            string text,
            string gender,
            int panicLevel,
            string callId,
            CancellationToken ct = default)
        {
            if (string.IsNullOrWhiteSpace(text))
                return Array.Empty<byte>();

            try
            {
                // Упаковываем call_id в json body для Python-сервера
                var requestBody = new
                {
                    model = _modelName,
                    input = text,
                    gender = gender,
                    panic_level = panicLevel,
                    call_id = callId
                };

                using var request = new HttpRequestMessage(
                    HttpMethod.Post,
                    $"{_baseUrl}/audio/speech"
                );

                request.Content = new StringContent(
                    JsonSerializer.Serialize(requestBody),
                    Encoding.UTF8,
                    "application/json"
                );

                var response = await _httpClient.SendAsync(request, ct);

                if (!response.IsSuccessStatusCode)
                {
                    string error = await response.Content.ReadAsStringAsync(ct);

                    Console.WriteLine(
                        $"[TTS ERROR] {(int)response.StatusCode} {response.StatusCode}: {error}"
                    );

                    return Array.Empty<byte>();
                }

                return await response.Content.ReadAsByteArrayAsync(ct);
            }
            catch (Exception ex)
            {
                Console.WriteLine(
                    $"[TTS EXCEPTION] {ex.GetType().Name}: {ex.Message}"
                );

                return Array.Empty<byte>();
            }
        }

        // Базовый стриминг-метод без контекста
        public async IAsyncEnumerable<byte[]> SynthesizeStreamingAsync(
            IAsyncEnumerable<string> textTokens,
            [EnumeratorCancellation] CancellationToken ct = default)
        {
            await foreach (var chunk in SynthesizeStreamingWithContextAsync(
                textTokens,
                "male",
                0,
                "CALL-UNKNOWN",
                ct))
            {
                yield return chunk;
            }
        }

        // Стриминг-метод с контекстом и поддержкой callId
        public async IAsyncEnumerable<byte[]> SynthesizeStreamingWithContextAsync(
            IAsyncEnumerable<string> textTokens,
            string gender,
            double panicLevel,
            string callId,
            [EnumeratorCancellation] CancellationToken ct = default)
        {
            var buffer = new StringBuilder();
            int intPanic = (int)panicLevel;

            string genderKey =
                gender?.ToLower().Contains("female") == true ||
                gender?.ToLower().Contains("woman") == true ||
                gender?.ToLower() == "baya"
                    ? "female"
                    : "male";

            await foreach (var token in textTokens.WithCancellation(ct))
            {
                buffer.Append(token);

                string currentText = buffer.ToString();

                bool endOfSentence =
                    token.Contains('.') ||
                    token.Contains('!') ||
                    token.Contains('?');

                bool bufferFull =
                    currentText.Length >= 120 &&
                    (token.Contains(" ") || token.EndsWith(" "));

                if (!endOfSentence && !bufferFull)
                    continue;

                string textChunk = currentText.Trim();
                buffer.Clear();

                if (textChunk.Length < 2)
                    continue;

                byte[] audio = await SynthesizeAsync(
                    textChunk,
                    genderKey,
                    intPanic,
                    callId,
                    ct
                );

                if (audio.Length > 0)
                    yield return audio;
            }

            if (buffer.Length > 0)
            {
                string textChunk = buffer.ToString().Trim();

                if (textChunk.Length >= 2)
                {
                    byte[] audio = await SynthesizeAsync(
                        textChunk,
                        genderKey,
                        intPanic,
                        callId,
                        ct
                    );

                    if (audio.Length > 0)
                        yield return audio;
                }
            }
        }
    }
}
