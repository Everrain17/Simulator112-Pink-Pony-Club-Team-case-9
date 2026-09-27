using System;
using System.Collections.Generic;
using System.Linq;
using SimCore.Entities;
using SimCore.Enums;

namespace AIEngine
{
    public static class AiPromptBuilder
    {
        public static AIPromptPayload BuildPrompt(
            Incident incident,
            CallerState caller,
            HiddenScenarioFacts hiddenFacts,
            string lastOperatorAction,
            List<string> suggestedTopics,
            int totalElapsedSeconds,
            double deltaSeconds)
        {
            string tone = caller.PanicLevel switch
            {
                < 30 => "спокойный",
                < 50 => "нервный",
                < 70 => "взволнованный",
                < 85 => "панический",
                _ => "истеричный"
            };

            double speed = 1.0 + (caller.PanicLevel / 100.0);
            if (speed > 2.0)
                speed = 2.0;

            string context = incident.Severity switch
            {
                <= 4 => "Ситуация стабильная.",
                <= 6 => "Есть реальная угроза.",
                <= 8 => "Серьезная опасность.",
                _ => "КРИТИЧЕСКАЯ ОПАСНОСТЬ."
            };

            string personaPrompt = caller.Persona.GetActorPrompt();

            string scenario = !string.IsNullOrWhiteSpace(incident.ScenarioDescription)
                ? incident.ScenarioDescription
                : incident.Description;

            string textPrompt = $@"Ты — заявитель, который сейчас разговаривает с оператором Службы-112.

ТВОЯ ЗАДАЧА:
Отвечай оператору как обычный живой человек, находящийся в описанной ситуации.

ГЛАВНОЕ ПРАВИЛО:
СУЩЕСТВУЕТ ТОЛЬКО ОДНА СЦЕНА И ОДНО ПРОИСШЕСТВИЕ.
Никогда не придумывай новое происшествие.
Никогда не добавляй новые события, которых нет в сценарии.
Никогда не смешивай эту ситуацию с другой.
Никогда не меняй причину происшествия.
Никогда не придумывай новых людей, предметы, травмы, адреса или обстоятельства.

ФАКТЫ СЦЕНАРИЯ:
Происшествие: {scenario}
Описание: {incident.Description}
Адрес происшествия: {hiddenFacts.Address}
Пострадавший: {hiddenFacts.VictimAge}
Симптомы / состояние: {hiddenFacts.Symptoms}
Кто звонит: {hiddenFacts.WhoIsCalling}

ТВОЯ РОЛЬ:
{personaPrompt}

ЭМОЦИОНАЛЬНОЕ СОСТОЯНИЕ:
{tone}
Паника: {caller.PanicLevel}%

ПРАВИЛА РЕЧИ:
1. Отвечай только на последний вопрос или реплику оператора.
2. Одна короткая реплика за один ответ.
3. Обычно 3–15 слов.
4. Можно повторяться, путаться или волноваться, если это соответствует персонажу.
5. Не пересказывай весь сценарий целиком.
6. Не перечисляй сразу все известные факты.
7. Не сообщай адрес, симптомы или другие сведения без причины. Сообщай их, когда оператор спрашивает или это естественно следует из разговора.
8. Если ты не знаешь какой-то детали по сценарию, не придумывай её.
9. Не используй метафоры и художественные описания.
10. Не используй технические термины, если персонаж их не знает.
11. Не пиши мысли, пояснения, комментарии или действия.
12. Не пиши ""assistant:"", ""user:"", XML-теги и служебный текст.
13. Не начинай каждую реплику словами ""Алло"" или ""Помогите"".
14. Не выдумывай продолжение события.
15. Не меняй пол, возраст, адрес или личность персонажа.

ВАЖНО:
Скрытые факты являются ИСТИНОЙ текущего сценария.
Используй только их.
Если оператор говорит что-то неверное, не создавай новое происшествие — просто реагируй как человек из текущего сценария.

Ответь только одной короткой репликой.";

            textPrompt = textPrompt
                .Replace("\r\n", "\n")
                .Replace("\r", "\n");

            return new AIPromptPayload(
                Timestamp: $"{totalElapsedSeconds}s",
                CallId: incident.Id,
                IncidentId: incident.Id,
                PanicLevel: caller.PanicLevel,
                EmotionalTone: tone,
                SpeakingRate: Math.Round(speed, 2),
                IncidentType: incident.Type.ToString(),
                ScenarioContext: context,
                Description: incident.Description,
                HasGivenAddress: caller.HasGivenAddress,
                HasGivenVictimsInfo: caller.HasGivenVictimsInfo,
                LastOperatorAction: lastOperatorAction,
                HiddenScenarioFacts: hiddenFacts,
                SuggestedTopics: suggestedTopics,
                IncidentSeverity: incident.Severity,
                IsCritical: incident.State == IncidentState.Critical,
                TextPrompt: textPrompt
            );
        }
    }
}