using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using SimCore.Entities;
using SimCore.Interfaces;

namespace AIEngine
{
    public class AiClient : IAiClient
    {
        private readonly HttpClient _httpClient;
        private readonly string _modelName;
        private readonly string _baseUrl;

        public AiClient(string apiKey = "not-needed", string modelName = "local", string baseUrl = "http://localhost:8080/v1")
        {
            _modelName = modelName;
            _baseUrl = baseUrl.EndsWith("/") ? baseUrl.TrimEnd('/') : baseUrl;
            _httpClient = new HttpClient();
            _httpClient.DefaultRequestHeaders.Add("User-Agent", "Simulator112/1.0");
        }

        public async Task<string> GenerateResponseAsync(string textPrompt, string operatorReply)
        {
            try
            {
                var request = new HttpRequestMessage(HttpMethod.Post, $"{_baseUrl}/chat/completions");
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", "not-needed");

                var requestBody = new
                {
                    model = _modelName,
                    messages = new[]
                    {
                        new { role = "system", content = textPrompt },
                        new { role = "user", content = $"Оператор 112 говорит: \"{operatorReply}\"" }
                    },
                    temperature = 0.3,
                    max_tokens = 100
                };

                string jsonPayload = JsonSerializer.Serialize(requestBody);
                request.Content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

                var response = await _httpClient.SendAsync(request);
                string responseString = await response.Content.ReadAsStringAsync();

                if (!response.IsSuccessStatusCode)
                    return $"[Ошибка ИИ: {response.StatusCode}]";

                using var doc = JsonDocument.Parse(responseString);
                var choices = doc.RootElement.GetProperty("choices");
                string aiText = choices[0].GetProperty("message").GetProperty("content").GetString() ?? "...";

                return aiText.Trim();
            }
            catch (Exception ex)
            {
                return $"[Ошибка симуляции: {ex.Message}]";
            }
        }

        public async IAsyncEnumerable<string> GenerateResponseStreamingAsync(
    string textPrompt,
    string operatorReply,
    [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
        {
            // 🔥 ИСПРАВЛЕНО: Меняем эндпоинт на прямой /completion для Raw-текстового режима!
            var request = new HttpRequestMessage(HttpMethod.Post, $"{_baseUrl.Replace("/v1", "")}/completion");
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", "not-needed");

            // Наш монолитный промпт с жестко вшитыми стоп-токенами
            var requestBody = new
            {
                prompt = $"<|im_start|>system\n{textPrompt}<|im_end|>\n" +
                         $"<|im_start|>user\nОператор 112 говорит: \"{operatorReply}\"<|im_end|>\n" +
                         "<|im_start|>assistant\n",
                temperature = 0.25,
                max_tokens = 60,
                stream = true,
                repeat_penalty = 1.15,
                stop = new[]
                            {
                    "<|im_end|>",
                    "<|im_start|>",
                    "\n",
                    "assistant:",
                    "user:"
                }
                        };

            string jsonPayload = JsonSerializer.Serialize(requestBody);
            request.Content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

            using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            if (!response.IsSuccessStatusCode)
            {
                yield return $"[Ошибка ИИ: {response.StatusCode}]";
                yield break;
            }

            using var stream = await response.Content.ReadAsStreamAsync(ct);
            using var reader = new StreamReader(stream);

            while (!reader.EndOfStream && !ct.IsCancellationRequested)
            {
                string? line = await reader.ReadLineAsync();
                if (string.IsNullOrWhiteSpace(line)) continue;

                line = line.Trim();

                if (line.StartsWith("data: "))
                {
                    line = line.Substring(6).Trim();
                }

                if (line == "[DONE]") yield break;
                if (!line.StartsWith("{")) continue;

                string? tokenToYield = null;
                try
                {
                    using var doc = JsonDocument.Parse(line);

                    // 🔥 ИСПРАВЛЕНО: В эндпоинте /completion токен лежит в поле "content", а не в "choices[0].delta"
                    if (doc.RootElement.TryGetProperty("content", out var contentProperty))
                    {
                        tokenToYield = contentProperty.GetString();
                    }
                }
                catch (JsonException)
                {
                    continue;
                }

                if (!string.IsNullOrEmpty(tokenToYield))
                {
                    yield return tokenToYield;
                }
            }
        }


        public async Task<OperatorActionAnalysis> AnalyzeOperatorReplyAsync(string operatorReply, string incidentDescription)
        {
            try
            {
                var request = new HttpRequestMessage(HttpMethod.Post, $"{_baseUrl}/chat/completions");
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", "not-needed");

                string evaluationPrompt = $@"Ты — ИИ-модуль объективного контроля Системы-112. Твоя задача — определить, какие действия выполнил оператор в своей реплике.
Контекст происшествия: {incidentDescription}
Реплика оператора: ""{operatorReply}""
Выведи результат СТРОГО в формате JSON со следующими полями (без лишнего текста и размышлений):
{{
  ""addressClarified"": true/false (если оператор выясняет или подтверждает точный адрес, улицу, дом, квартиру),
  ""victimsInfoClarified"": true/false (если оператор спрашивает о наличии пострадавших, детях, их состоянии, сознании или дыхании),
  ""medicalInstructionGiven"": true/false (если оператор проводит инструктаж до прибытия служб: открыть окно, не трогать, перевернуть, остановить кровь),
  ""servicesDispatched"": true/false (если оператор сообщает о направлении служб, выезде бригады или передаче вызова),
  ""isCalmingOperator"": true/false (если оператор использует фразы психологического успокоения: ""успокойтесь"", ""мы уже помогаем"", ""дышите глубже""),
  ""summary"": ""краткое описание действия оператора на русском языке одним предложением""
}}
СТРОГОЕ ПРАВИЛО: Ответ должен состоять ТОЛЬКО из валидного JSON. Никаких Thinking Process, вступлений или заключений!";

                var requestBody = new
                {
                    model = _modelName,
                    messages = new[]
                           {
                        new { role = "user", content = evaluationPrompt }
                    },
                    temperature = 0.0,
                    max_tokens = 150
                };

                string jsonPayload = JsonSerializer.Serialize(requestBody);
                request.Content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

                var response = await _httpClient.SendAsync(request);
                string responseString = await response.Content.ReadAsStringAsync();

                using var doc = JsonDocument.Parse(responseString);
                string rawJson = doc.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString() ?? "{}";
                rawJson = rawJson.Replace("```json", "").Replace("```", "").Trim();

                using var parsedAnalysis = JsonDocument.Parse(rawJson);
                var aniRoot = parsedAnalysis.RootElement;

                return new OperatorActionAnalysis(
                     AddressClarified: aniRoot.TryGetProperty("addressClarified", out var addr) && addr.GetBoolean(),
                     MedicalInstructionGiven: aniRoot.TryGetProperty("medicalInstructionGiven", out var med) && med.GetBoolean(),
                     ServicesDispatched: aniRoot.TryGetProperty("servicesDispatched", out var serv) && serv.GetBoolean(),
                     IsCalmingOperator: aniRoot.TryGetProperty("isCalmingOperator", out var calm) && calm.GetBoolean(),
                     VictimsInfoClarified: aniRoot.TryGetProperty("victimsInfoClarified", out var victims) && victims.GetBoolean(),
                     Summary: aniRoot.TryGetProperty("summary", out var sum) ? sum.GetString() ?? "Реплика обработана" : "Реплика обработана"
                );
            }
            catch
            {
                return new OperatorActionAnalysis(false, false, false, false, false, "Ошибка анализа ИИ или сбой формата JSON");
            }
        }

        public async Task<TextAnalysisResult?> AnalyzeCardTextAsync(string operatorNotes, IncidentGroundTruth groundTruth)
        {
            try
            {
                var request = new HttpRequestMessage(HttpMethod.Post, $"{_baseUrl}/chat/completions");
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", "not-needed");

                string evaluationPrompt = $@"Ты — строгий методист ДДС города Москвы, проверяющий карточку происшествия, заполненную оператором системы-112.
РЕАЛЬНАЯ СИТУАЦИЯ (ЭТАЛОН):
- Адрес: {groundTruth.Address}
- Требуемые службы: {string.Join(", ", groundTruth.RequiredServices)}
- Критические факты: {string.Join(", ", groundTruth.CriticalTags)}

ТЕКСТ, ЗАПОЛНЕННЫЙ ОПЕРАТОРОМ:
""{operatorNotes}""

КРИТЕРИИ ОЦЕНКИ (строго по регламенту ДДС):

1. ПРАВИЛО 100 СИМВОЛОВ: В службу 03 передаются только первые 100 символов описания. Проверь, что критическая информация (адрес, тип происшествия, угроза жизни) находится в НАЧАЛЕ текста.

2. ФАКТИЧЕСКАЯ ТОЧНОСТЬ:
   - Указан ли правильный адрес (улица, дом)?
   - Упомянуты ли пострадавшие, если они есть в эталоне?
   - Соответствует ли тип происшествия реальному?
   - Указаны ли критические детали (этаж, подъезд, количество людей)?

3. ДЕЛОВОЙ СТИЛЬ: Текст должен быть написан языком официальной документации ДДС. Недопустимы: разговорные выражения, эмоции, сленг, восклицания.

4. ПОЛНОТА: Все ли ключевые факты из эталона отражены в тексте?

Выведи результат СТРОГО в формате JSON (без лишнего текста):
{{
  ""grammarScore"": 0-100,
  ""factualAccuracy"": 0-100,
  ""missingCriticalFacts"": [""список упущенных важных деталей из эталона""],
  ""first100CharsCheck"": true/false,
  ""aiComment"": ""Краткий комментарий (1-2 предложения) с указанием основных ошибок""
}}

СТРОГОЕ ПРАВИЛО: Ответ должен состоять ТОЛЬКО из валидного JSON.";

                var requestBody = new
                {
                    model = _modelName,
                    messages = new[]
                          {
                        new { role = "user", content = evaluationPrompt }
                    },
                    temperature = 0.0,
                    max_tokens = 400
                };

                string jsonPayload = JsonSerializer.Serialize(requestBody);
                request.Content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

                var response = await _httpClient.SendAsync(request);
                string responseString = await response.Content.ReadAsStringAsync();

                using var doc = JsonDocument.Parse(responseString);
                string rawJson = doc.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString() ?? "{}";
                rawJson = rawJson.Replace("```json", "").Replace("```", "").Trim();

                using var parsedAnalysis = JsonDocument.Parse(rawJson);
                var root = parsedAnalysis.RootElement;

                var missingFacts = new List<string>();
                if (root.TryGetProperty("missingCriticalFacts", out var factsArray) && factsArray.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in factsArray.EnumerateArray())
                    {
                        missingFacts.Add(item.GetString() ?? "");
                    }
                }

                return new TextAnalysisResult(
                    GrammarScore: root.TryGetProperty("grammarScore", out var gScore) ? gScore.GetInt32() : 50,
                    FactualAccuracy: root.TryGetProperty("factualAccuracy", out var fAcc) ? fAcc.GetInt32() : 50,
                    MissingCriticalFacts: missingFacts,
                    AiComment: root.TryGetProperty("aiComment", out var comment) ? comment.GetString() ?? "Анализ завершен" : "Анализ завершен",
                    First100CharsCheck: root.TryGetProperty("first100CharsCheck", out var f100) && f100.GetBoolean()
                );
            }
            catch
            {
                return new TextAnalysisResult(50, 50, new List<string> { "Не удалось проанализировать текст из-за сбоя ИИ" }, "Ошибка анализа", false);
            }
        }
    }
}